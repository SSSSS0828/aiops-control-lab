"""FastAPI 组合根与显式依赖容器。

该模块只负责选择具体适配器并组装应用服务，不定义 HTTP 路由。
测试通过环境变量或直接替换容器字段即可改变外部依赖。
"""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from aiops_control.adapters.agent_metric_store import AgentMetricStore
from aiops_control.adapters.grpc_agent_gateway import (
    GrpcAgentGateway,
    GrpcGatewayConfiguration,
)
from aiops_control.adapters.grpc_plugin_runtime import GrpcPluginRuntime
from aiops_control.adapters.hashing_embeddings import HashingEmbeddingProvider
from aiops_control.adapters.http_agent_dispatcher import HttpAgentDispatcher
from aiops_control.adapters.http_lab_fault_injector import HttpLabFaultInjector
from aiops_control.adapters.lab_health_probe import HttpLabHealthProbe
from aiops_control.adapters.loki_query import LokiRangeQuery
from aiops_control.adapters.memory_repository import InMemoryRepository
from aiops_control.adapters.openai_compatible_llm import OpenAICompatibleDiagnosticModel
from aiops_control.adapters.postgres_repository import PostgresRepository
from aiops_control.adapters.prometheus_query import PrometheusRangeQuery
from aiops_control.adapters.registered_health_checker import RegisteredHealthChecker
from aiops_control.adapters.rolling_zscore import RollingZScoreDetector
from aiops_control.adapters.rule_based_diagnosis import RuleBasedDiagnosticModel
from aiops_control.adapters.safe_dispatcher import SafeDemoDispatcher
from aiops_control.application.agent_ingestion_service import AgentIngestionService
from aiops_control.application.builtin_knowledge import build_builtin_documents
from aiops_control.application.console_query_service import ConsoleQueryService
from aiops_control.application.diagnostic_assistant_service import DiagnosticAssistantService
from aiops_control.application.evidence_collection_service import EvidenceCollectionService
from aiops_control.application.hybrid_retrieval_service import HybridRetrievalService
from aiops_control.application.incident_correlation_service import IncidentCorrelationService
from aiops_control.application.incident_service import IncidentApplicationService
from aiops_control.application.monitoring_scheduler import MonitoringScheduler
from aiops_control.application.monitoring_service import MonitoringService
from aiops_control.application.rate_limit_service import SlidingWindowRateLimiter
from aiops_control.application.remediation_service import RemediationApplicationService
from aiops_control.domain.topology import TopologyEdge
from aiops_control.ports.repositories import ApplicationRepository
from aiops_control.ports.telemetry import MetricQueryPort


@dataclass(slots=True)
class ApplicationContainer:
    """API Router 使用的所有长生命周期依赖。"""

    repository: ApplicationRepository
    incident_service: IncidentApplicationService
    evidence_service: EvidenceCollectionService
    remediation_service: RemediationApplicationService
    console_service: ConsoleQueryService
    diagnostic_service: DiagnosticAssistantService
    plugin_runtime: GrpcPluginRuntime | None
    plugin_root: Path | None
    fault_injector: HttpLabFaultInjector | None
    lab_health_probe: HttpLabHealthProbe | None
    lab_rate_limiter: SlidingWindowRateLimiter
    admin_token: str | None
    admin_actions_enabled: bool
    trust_proxy_client_ip: bool
    access_mode: str
    prometheus_enabled: bool
    loki_enabled: bool
    llm_enabled: bool
    llm_model_name: str
    background_tasks: set[asyncio.Task[None]]
    metric_store: AgentMetricStore
    metric_query: MetricQueryPort | None
    health_checker: RegisteredHealthChecker
    monitoring_scheduler: MonitoringScheduler
    agent_gateway: GrpcAgentGateway | None
    real_actions_mode: str

    async def start(self) -> None:
        """启动可选 mTLS 网关和带数据库锁的真实监测循环。"""

        if self.agent_gateway is not None:
            await self.agent_gateway.start()
        task = asyncio.create_task(self.monitoring_scheduler.run())
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def close(self) -> None:
        """优雅停止插件并取消尚未触发的实验自动恢复任务。"""

        if self.plugin_runtime is not None:
            self.plugin_runtime.close()
        if self.agent_gateway is not None:
            await self.agent_gateway.close()
        for task in self.background_tasks:
            task.cancel()
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)


def build_container() -> ApplicationContainer:
    """根据类型化环境边界组装控制面依赖。"""

    database_url = os.getenv("DATABASE_URL")
    repository: ApplicationRepository
    repository = PostgresRepository(database_url) if database_url else InMemoryRepository()
    topology_edges = (
        TopologyEdge("lab-gateway", "lab-api"),
        TopologyEdge("lab-api", "lab-redis"),
    )
    real_actions_mode = os.getenv("AIOPS_REAL_ACTIONS_MODE", "observe_only")
    if real_actions_mode not in {"observe_only", "approval_only"}:
        raise ValueError("AIOPS_REAL_ACTIONS_MODE 只允许 observe_only 或 approval_only")
    incident_service = IncidentApplicationService(
        detector=RollingZScoreDetector(threshold=3.0, minimum_samples=5),
        incident_repository=repository,
        remediation_repository=repository,
        correlation_service=IncidentCorrelationService(),
        change_repository=repository,
        topology_edges=topology_edges,
        real_actions_mode=real_actions_mode,
    )

    prometheus_url = os.getenv("PROMETHEUS_URL")
    loki_url = os.getenv("LOKI_URL")
    metric_query: MetricQueryPort | None = (
        PrometheusRangeQuery(prometheus_url) if prometheus_url else None
    )
    evidence_service = EvidenceCollectionService(
        incident_repository=repository,
        metric_query=metric_query,
        log_query=LokiRangeQuery(loki_url) if loki_url else None,
    )

    llm_base_url = os.getenv("AIOPS_LLM_BASE_URL", "")
    llm_api_key = os.getenv("AIOPS_LLM_API_KEY", "")
    llm_model_name = os.getenv("AIOPS_LLM_MODEL", "")
    llm_enabled = bool(llm_base_url and llm_api_key and llm_model_name)
    fallback_model = RuleBasedDiagnosticModel()
    primary_model = (
        OpenAICompatibleDiagnosticModel(llm_base_url, llm_api_key, llm_model_name)
        if llm_enabled
        else fallback_model
    )
    retrieval = HybridRetrievalService(
        build_builtin_documents(),
        HashingEmbeddingProvider(),
    )
    diagnostic_service = DiagnosticAssistantService(
        retrieval,
        primary_model,
        fallback_model,
        primary_enabled=llm_enabled,
    )

    access_mode = os.getenv("AIOPS_ACCESS_MODE", "private-forward")
    console_service = ConsoleQueryService(repository, topology_edges, access_mode)

    agent_url = os.getenv("AIOPS_AGENT_URL")
    agent_shared_secret = os.getenv("AIOPS_AGENT_SHARED_SECRET", "")
    dispatcher = (
        HttpAgentDispatcher(agent_url, agent_shared_secret) if agent_url else SafeDemoDispatcher()
    )
    plugin_root_value = os.getenv("AIOPS_PLUGIN_ROOT")
    plugin_root = Path(plugin_root_value) if plugin_root_value else None
    plugin_runtime = (
        GrpcPluginRuntime(
            plugin_root,
            Path(os.getenv("AIOPS_PLUGIN_RUNTIME_ROOT", "/tmp/aiops-plugins")),
        )
        if plugin_root is not None
        else None
    )

    real_faults_enabled = os.getenv("AIOPS_LAB_REAL_FAULTS", "false").lower() == "true"
    lab_api_url = os.getenv("AIOPS_LAB_API_URL", "")
    lab_health_probe = (
        HttpLabHealthProbe(lab_api_url) if real_faults_enabled and lab_api_url else None
    )
    fault_injector = (
        HttpLabFaultInjector(
            agent_url,
            agent_shared_secret,
            lab_api_url,
            os.getenv("AIOPS_LAB_CONTROL_TOKEN", ""),
        )
        if agent_url and real_faults_enabled
        else None
    )
    remediation_service = RemediationApplicationService(
        incident_repository=repository,
        remediation_repository=repository,
        dispatcher=dispatcher,
        recovery_verifier=lab_health_probe,
        real_actions_mode=real_actions_mode,
    )
    metric_store = AgentMetricStore()
    allowed_identities = _parse_agent_identities(
        os.getenv(
            "AIOPS_AGENT_CERT_IDENTITIES",
            "tencent-lab-01=aiops-agent-tencent-lab-01",
        )
    )
    ingestion_service = AgentIngestionService(repository, metric_store, allowed_identities)
    monitoring_service = MonitoringService(repository, repository, metric_store)
    monitoring_scheduler = MonitoringScheduler(
        repository,
        monitoring_service,
        int(os.getenv("AIOPS_MONITOR_INTERVAL_SECONDS", "60")),
    )
    grpc_enabled = os.getenv("AIOPS_AGENT_GRPC_ENABLED", "false").lower() == "true"
    agent_gateway = (
        GrpcAgentGateway(
            GrpcGatewayConfiguration(
                listen=os.getenv("AIOPS_AGENT_GRPC_LISTEN", "0.0.0.0:9443"),
                certificate_file=Path(
                    os.getenv("AIOPS_GRPC_SERVER_CERT", "/run/aiops-pki/server.crt")
                ),
                key_file=Path(os.getenv("AIOPS_GRPC_SERVER_KEY", "/run/aiops-pki/server.key")),
                client_ca_file=Path(os.getenv("AIOPS_GRPC_CLIENT_CA", "/run/aiops-pki/ca.crt")),
            ),
            ingestion_service,
        )
        if grpc_enabled
        else None
    )
    return ApplicationContainer(
        repository=repository,
        incident_service=incident_service,
        evidence_service=evidence_service,
        remediation_service=remediation_service,
        console_service=console_service,
        diagnostic_service=diagnostic_service,
        plugin_runtime=plugin_runtime,
        plugin_root=plugin_root,
        fault_injector=fault_injector,
        lab_health_probe=lab_health_probe,
        lab_rate_limiter=SlidingWindowRateLimiter(limit=3, window_seconds=60),
        admin_token=os.getenv("AIOPS_ADMIN_TOKEN"),
        # 明文 HTTP 公网演示必须关闭管理员写接口，避免 Bearer Token 在链路中泄露。
        admin_actions_enabled=os.getenv("AIOPS_ADMIN_ACTIONS_ENABLED", "true").lower() == "true",
        # 默认不信任代理头；只有受控入口覆盖真实地址且后端不直连公网时才启用。
        trust_proxy_client_ip=os.getenv("AIOPS_TRUST_X_REAL_IP", "false").lower() == "true",
        access_mode=access_mode,
        prometheus_enabled=bool(prometheus_url),
        loki_enabled=bool(loki_url),
        llm_enabled=llm_enabled,
        llm_model_name=llm_model_name,
        background_tasks=set(),
        metric_store=metric_store,
        metric_query=metric_query,
        health_checker=RegisteredHealthChecker(),
        monitoring_scheduler=monitoring_scheduler,
        agent_gateway=agent_gateway,
        real_actions_mode=real_actions_mode,
    )


def _parse_agent_identities(raw: str) -> dict[str, str]:
    """解析 `node_id=certificate_cn` 列表，拒绝含糊条目。"""

    result: dict[str, str] = {}
    for item in raw.split(","):
        node_id, separator, identity = item.strip().partition("=")
        if not separator or not node_id or not identity:
            raise ValueError("AIOPS_AGENT_CERT_IDENTITIES 格式必须是 node_id=certificate_cn")
        result[node_id] = identity
    return result
