"""告警时间窗口去重、拓扑合并和变更关联测试。"""

from datetime import UTC, datetime, timedelta

from aiops_control.adapters.memory_repository import InMemoryRepository
from aiops_control.adapters.rolling_zscore import RollingZScoreDetector
from aiops_control.application.incident_correlation_service import IncidentCorrelationService
from aiops_control.application.incident_service import IncidentApplicationService
from aiops_control.domain.changes import ChangeEvent
from aiops_control.domain.models import Signal
from aiops_control.domain.topology import TopologyEdge


def create_service(repository: InMemoryRepository) -> IncidentApplicationService:
    """构造包含实验室拓扑和变更仓储的 Incident 应用服务。"""

    return IncidentApplicationService(
        RollingZScoreDetector(minimum_samples=5),
        repository,
        repository,
        correlation_service=IncidentCorrelationService(),
        change_repository=repository,
        topology_edges=(
            TopologyEdge("lab-gateway", "lab-api"),
            TopologyEdge("lab-api", "lab-redis"),
        ),
    )


def test_repeated_asset_signal_reuses_incident_and_plan() -> None:
    """五分钟内同资产重复异常只能产生一个 Incident 和一份计划。"""

    repository = InMemoryRepository()
    service = create_service(repository)
    now = datetime.now(UTC)

    first = service.evaluate_signal(Signal("lab-api", "cpu", 99, now), [10.0] * 6)
    second = service.evaluate_signal(
        Signal("lab-api", "cpu", 98, now + timedelta(minutes=1)), [10.0] * 6
    )

    assert first.incident is not None and second.incident is not None
    assert first.plan is not None and second.plan is not None
    assert second.incident.id == first.incident.id
    assert second.plan.id == first.plan.id
    assert len(repository.list_incidents()) == 1
    assert len(second.incident.evidence) == 2


def test_direct_dependency_anomaly_merges_into_existing_incident() -> None:
    """Redis 与直接调用它的 API 同时异常时应合并为一个拓扑 Incident。"""

    repository = InMemoryRepository()
    service = create_service(repository)
    now = datetime.now(UTC)

    dependency = service.evaluate_signal(Signal("lab-redis", "health", 0, now), [1.0] * 6)
    caller = service.evaluate_signal(
        Signal("lab-api", "http_5xx", 50, now + timedelta(seconds=30)), [0.0] * 6
    )

    assert dependency.incident is not None and caller.incident is not None
    assert caller.incident.id == dependency.incident.id
    assert {item.asset_id for item in caller.incident.hypotheses} == {
        "lab-redis",
        "lab-api",
    }


def test_recent_change_is_attached_once_without_attributes() -> None:
    """故障前部署事件应关联一次，且不能复制任意 attributes。"""

    repository = InMemoryRepository()
    now = datetime.now(UTC)
    repository.save_change_event(
        ChangeEvent(
            id="change-1",
            provider="github-actions",
            event_type="deployment",
            service="lab-api",
            revision="abc123",
            status="succeeded",
            occurred_at=now - timedelta(minutes=5),
            attributes={"secret": "must-not-persist-in-evidence"},
        )
    )
    service = create_service(repository)

    first = service.evaluate_signal(Signal("lab-api", "cpu", 99, now), [10.0] * 6)
    second = service.evaluate_signal(
        Signal("lab-api", "cpu", 98, now + timedelta(minutes=1)), [10.0] * 6
    )

    assert first.incident is not None and second.incident is not None
    changes = [item for item in second.incident.evidence if item.source == "change_event"]
    assert len(changes) == 1
    assert "abc123" in changes[0].summary
    assert "must-not-persist" not in repr(changes[0])
