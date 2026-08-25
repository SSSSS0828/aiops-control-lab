"""多页面控制台的只读查询编排。

本服务把分散在仓储、静态实验拓扑和插件运行时中的信息整理成紧凑视图。
它不会修改领域实体，也不会探测任意用户输入的网络地址，避免只读页面扩大攻击面。
"""

from dataclasses import asdict
from typing import Any

from aiops_control.domain.console import CapabilityView, ConsoleOverview, ManagedAssetView
from aiops_control.domain.enums import ActionStatus, IncidentStatus
from aiops_control.domain.topology import TopologyEdge
from aiops_control.ports.repositories import ApplicationRepository


class ConsoleQueryService:
    """集中提供首页、资产、拓扑、执行和能力目录查询。"""

    def __init__(
        self,
        repository: ApplicationRepository,
        topology_edges: tuple[TopologyEdge, ...],
        access_mode: str,
    ) -> None:
        self._repository = repository
        self._topology_edges = topology_edges
        self._access_mode = access_mode

    def overview(self, plugin_count: int) -> ConsoleOverview:
        """按当前仓储快照计算首页指标。"""

        incidents = self._repository.list_incidents()
        executions = self._repository.list_action_runs()
        active_states = {
            IncidentStatus.OPEN,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.WAITING_APPROVAL,
            IncidentStatus.REMEDIATING,
        }
        return ConsoleOverview(
            incident_count=len(incidents),
            active_incident_count=sum(item.status in active_states for item in incidents),
            resolved_incident_count=sum(
                item.status is IncidentStatus.RESOLVED for item in incidents
            ),
            execution_count=len(executions),
            successful_execution_count=sum(
                item.status is ActionStatus.SUCCEEDED for item in executions
            ),
            asset_count=len(self.assets()),
            plugin_count=plugin_count,
            access_mode=self._access_mode,
        )

    def assets(self) -> tuple[ManagedAssetView, ...]:
        """优先返回 Agent 实际发现资产；尚未连接时保留实验资产回退视图。"""

        discovered = self._repository.list_monitored_assets()
        if discovered:
            return tuple(
                ManagedAssetView(
                    id=item.id,
                    name=item.name,
                    kind=item.kind,
                    node_id=item.node_id,
                    status="healthy" if item.status == "running" else "degraded",
                    address=item.attributes.get("service", item.source),
                    responsibilities=("真实环境持续监测", f"数据来源：{item.source}"),
                )
                for item in discovered
            )

        unhealthy_assets = {
            incident.asset_id
            for incident in self._repository.list_incidents()
            if incident.status not in {IncidentStatus.RESOLVED, IncidentStatus.FAILED}
        }
        definitions = (
            ("tencent-lab-01", "腾讯云实验节点", "linux_host", "local", "127.0.0.1"),
            ("aiops-agent", "节点执行 Agent", "agent", "tencent-lab-01", "agent:9105"),
            ("lab-gateway", "实验 Nginx 网关", "gateway", "tencent-lab-01", "lab-gateway:8080"),
            ("lab-api", "实验 API 服务", "service", "tencent-lab-01", "lab-api:8080"),
            ("lab-redis", "实验 Redis 依赖", "datastore", "tencent-lab-01", "lab-redis:6379"),
        )
        responsibilities = {
            "linux_host": ("承载控制面与实验环境", "提供主机指标"),
            "agent": ("资产发现", "受控动作执行", "幂等与签名校验"),
            "gateway": ("HTTP 流量入口", "健康状态传播"),
            "service": ("实验业务接口", "故障注入目标"),
            "datastore": ("API 依赖", "依赖故障实验"),
        }
        return tuple(
            ManagedAssetView(
                id=asset_id,
                name=name,
                kind=kind,
                node_id=node_id,
                status="degraded" if asset_id in unhealthy_assets else "healthy",
                address=address,
                responsibilities=responsibilities[kind],
            )
            for asset_id, name, kind, node_id, address in definitions
        )

    def topology(self) -> dict[str, Any]:
        """返回节点和有向依赖边，前端据此绘制服务拓扑。"""

        discovered_edges = self._repository.list_monitored_topology()
        if discovered_edges:
            return {
                "nodes": [asdict(item) for item in self.assets()],
                "edges": [asdict(edge) for edge in discovered_edges],
            }
        service_assets = [item for item in self.assets() if item.id.startswith("lab-")]
        return {
            "nodes": [asdict(item) for item in service_assets],
            "edges": [asdict(edge) for edge in self._topology_edges],
        }

    def incident_contexts(self) -> list[dict[str, Any]]:
        """关联 Incident、最新计划和执行记录，供审批中心一次读取。"""

        executions = self._repository.list_action_runs()
        contexts: list[dict[str, Any]] = []
        for incident in self._repository.list_incidents():
            plan = self._repository.get_plan_by_incident(incident.id)
            incident_runs = [item for item in executions if item.incident_id == incident.id]
            contexts.append(
                {
                    "incident": asdict(incident),
                    "plan": asdict(plan) | {"content_hash": plan.content_hash()} if plan else None,
                    "executions": [asdict(item) for item in incident_runs],
                }
            )
        return contexts

    def capabilities(self, llm_enabled: bool, loki_enabled: bool) -> tuple[CapabilityView, ...]:
        """如实声明在线、降级或实验能力，避免把代码存在等同于线上启用。"""

        return (
            CapabilityView(
                "rolling-zscore",
                "滚动 Z-Score",
                "异常检测",
                "online",
                "当前在线默认检测器",
            ),
            CapabilityView("ewma", "EWMA", "异常检测", "experiment", "已实现并进入离线算法评测"),
            CapabilityView(
                "seasonal", "季节性基线", "异常检测", "experiment", "已实现同季节位置比较"
            ),
            CapabilityView(
                "isolation-forest",
                "Isolation Forest",
                "异常检测",
                "experiment",
                "轻量一维无监督检测器",
            ),
            CapabilityView("prometheus", "Prometheus", "可观测性", "online", "指标证据查询数据源"),
            CapabilityView(
                "loki",
                "Loki",
                "可观测性",
                "online" if loki_enabled else "disabled",
                "日志证据数据源；轻量云部署默认关闭",
            ),
            CapabilityView(
                "llm",
                "OpenAI-compatible LLM",
                "AI 诊断",
                "online" if llm_enabled else "degraded",
                "未配置云模型时自动使用确定性规则诊断",
            ),
            CapabilityView(
                "rag",
                "关键词与哈希向量混合 RAG",
                "AI 诊断",
                "online",
                "Runbook 检索并返回稳定引用",
            ),
            CapabilityView(
                "autoencoder",
                "时序自编码器",
                "离线实验",
                "experiment",
                "仅用于 Notebook 和算法对比，不进入在线依赖",
            ),
        )
