"""阶段六真实遥测身份、去重、迟滞恢复与观察模式测试。"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aiops_control.adapters.agent_metric_store import AgentMetricStore
from aiops_control.adapters.memory_repository import InMemoryRepository
from aiops_control.adapters.rolling_zscore import RollingZScoreDetector
from aiops_control.api.app import create_app
from aiops_control.application.agent_ingestion_service import (
    AgentIdentityError,
    AgentIngestionService,
)
from aiops_control.application.incident_service import IncidentApplicationService
from aiops_control.application.monitoring_service import MonitoringService
from aiops_control.domain.enums import IncidentStatus
from aiops_control.domain.models import Signal
from aiops_control.domain.monitoring import LatestMetric, MonitoredAsset, MonitorRule
from aiops_control.generated.agent.v1 import agent_pb2


def test_agent_identity_and_sequence_deduplication() -> None:
    """证书 CN 必须绑定节点，重复序列不能覆盖或再次持久化。"""

    repository = InMemoryRepository()
    store = AgentMetricStore()
    ingestion = AgentIngestionService(
        repository,
        store,
        {"tencent-lab-01": "aiops-agent-tencent-lab-01"},
    )
    with pytest.raises(AgentIdentityError):
        ingestion.connect("tencent-lab-01", "0.2.0", "instance-a", "wrong-client")

    node = ingestion.connect("tencent-lab-01", "0.2.0", "instance-a", "aiops-agent-tencent-lab-01")
    metric = _metric(10)
    assert ingestion.ingest(node, 1, [metric], [], []) is True
    assert ingestion.ingest(node, 1, [_metric(99)], [], []) is False
    assert store.list_metrics()[0].value == 10


def test_agent_protobuf_uses_typed_telemetry_fields() -> None:
    """公共协议必须保留强类型序列、资产和指标，不能退回任意 Struct。"""

    message = agent_pb2.AgentMessage(
        telemetry=agent_pb2.TelemetryBatch(
            sequence=7,
            metrics=[
                agent_pb2.MetricPoint(
                    name="aiops_container_up",
                    value=1,
                    labels={"asset_id": "docker/devops-lab/api"},
                )
            ],
        )
    )
    restored = agent_pb2.AgentMessage.FromString(message.SerializeToString())
    assert restored.telemetry.sequence == 7
    assert restored.telemetry.metrics[0].labels["asset_id"] == "docker/devops-lab/api"


def test_rule_requires_three_normal_cycles_before_recovery() -> None:
    """连续异常创建观察型 Incident，只有连续三轮正常才自动恢复。"""

    repository = InMemoryRepository()
    store = AgentMetricStore()
    service = MonitoringService(repository, repository, store)
    repository.save_monitor_rule(
        MonitorRule(
            id="test-cpu",
            name="测试 CPU 告警",
            metric_name="aiops_host_cpu_percent",
            asset_selector="host/tencent-lab-01",
            operator="gt",
            threshold=80,
            consecutive_cycles=2,
            recovery_cycles=3,
            severity="high",
            window_seconds=120,
        )
    )

    _evaluate_value(store, service, 1, 90)
    assert repository.list_incidents() == []
    _evaluate_value(store, service, 2, 91)
    assert repository.list_incidents()[0].status is IncidentStatus.OPEN

    _evaluate_value(store, service, 3, 20)
    _evaluate_value(store, service, 4, 20)
    assert repository.list_incidents()[0].status is IncidentStatus.OPEN
    _evaluate_value(store, service, 5, 20)
    assert repository.list_incidents()[0].status is IncidentStatus.RESOLVED
    assert repository.get_plan_by_incident(repository.list_incidents()[0].id) is None


def test_observe_only_real_signal_never_creates_write_plan() -> None:
    """即使真实资产异常分数很高，观察模式也只能创建开放 Incident。"""

    repository = InMemoryRepository()
    service = IncidentApplicationService(
        RollingZScoreDetector(minimum_samples=5),
        repository,
        repository,
        real_actions_mode="observe_only",
    )
    outcome = service.evaluate_signal(
        Signal(
            asset_id="docker/devops-lab/api",
            name="aiops_container_cpu_percent",
            value=99,
            occurred_at=datetime.now(UTC),
        ),
        [10, 10, 10, 10, 10],
    )
    assert outcome.incident is not None
    assert outcome.incident.status is IncidentStatus.OPEN
    assert outcome.plan is None


def test_real_asset_api_accepts_stable_id_with_slashes() -> None:
    """路径型资产 ID 能查询详情和注册指标，未知指标必须拒绝。"""

    app = create_app()
    now = datetime.now(UTC)
    app.state.container.repository.save_monitored_asset(
        MonitoredAsset(
            id="docker/devops-lab/api",
            node_id="tencent-lab-01",
            kind="docker_container",
            name="devops-api",
            status="running",
            environment="real",
            source="docker",
            last_seen_at=now,
            attributes={"service": "api"},
        )
    )
    app.state.container.metric_store.accept_batch(
        "tencent-lab-01",
        "instance-test",
        1,
        [
            LatestMetric(
                name="aiops_container_up",
                value=1,
                labels={"asset_id": "docker/devops-lab/api"},
                collected_at=now,
            )
        ],
    )
    with TestClient(app) as client:
        detail = client.get("/api/v1/assets/docker/devops-lab/api")
        assert detail.status_code == 200
        assert detail.json()["environment"] == "real"
        metrics = client.get("/api/v1/assets/docker/devops-lab/api/metrics")
        assert metrics.status_code == 200
        assert metrics.json()["latest"][0]["name"] == "aiops_container_up"
        rejected = client.get(
            "/api/v1/assets/docker/devops-lab/api/metrics?metric_name=unregistered"
        )
        assert rejected.status_code == 400


def _metric(value: float) -> LatestMetric:
    return LatestMetric(
        name="aiops_host_cpu_percent",
        value=value,
        labels={"asset_id": "host/tencent-lab-01", "environment": "real"},
        collected_at=datetime.now(UTC),
    )


def _evaluate_value(
    store: AgentMetricStore,
    service: MonitoringService,
    sequence: int,
    value: float,
) -> None:
    accepted = store.accept_batch("tencent-lab-01", "instance-a", sequence, [_metric(value)])
    assert accepted is True
    service.evaluate_all()
