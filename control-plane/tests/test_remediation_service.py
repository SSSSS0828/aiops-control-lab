"""审批、幂等执行和内容完整性测试。"""

from datetime import UTC, datetime

import pytest

from aiops_control.adapters.memory_repository import InMemoryRepository
from aiops_control.adapters.rolling_zscore import RollingZScoreDetector
from aiops_control.adapters.safe_dispatcher import SafeDemoDispatcher
from aiops_control.application.incident_service import IncidentApplicationService
from aiops_control.application.remediation_service import RemediationApplicationService
from aiops_control.domain.enums import ActionStatus, IncidentStatus
from aiops_control.domain.errors import IntegrityViolationError
from aiops_control.domain.models import RemediationStep, Signal
from aiops_control.ports.execution import StepExecutionResult


class RollbackRecordingDispatcher:
    """按动作名制造验证失败，并记录补偿顺序。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, step: RemediationStep, approved_hash: str) -> StepExecutionResult:
        """记录类型化动作；verify_change 固定失败以触发自动补偿。"""

        self.calls.append(step.action_type)
        return StepExecutionResult(
            succeeded=step.action_type != "verify_change",
            message=f"{step.action_type} 已处理",
        )


class FailedRecoveryVerifier:
    """模拟容器动作成功但业务健康端点仍然失败。"""

    def verify(self, target: str) -> dict[str, object]:
        return {
            "source": "http-health-probe",
            "target": target,
            "healthy": False,
            "status_code": 503,
        }


def create_services() -> tuple[
    InMemoryRepository,
    IncidentApplicationService,
    RemediationApplicationService,
]:
    """构造无外部依赖的测试组合根。"""

    repository = InMemoryRepository()
    incidents = IncidentApplicationService(
        RollingZScoreDetector(minimum_samples=5), repository, repository
    )
    remediations = RemediationApplicationService(repository, repository, SafeDemoDispatcher())
    return repository, incidents, remediations


def test_approved_plan_executes_once() -> None:
    """相同幂等键重试必须返回同一执行记录。"""

    repository, incidents, remediations = create_services()
    outcome = incidents.evaluate_signal(
        Signal("lab-api", "cpu", 99.0, datetime.now(UTC)),
        [10.0] * 6,
    )
    assert outcome.plan is not None
    action = remediations.approve_and_execute(
        outcome.plan.id,
        "admin",
        outcome.plan.content_hash(),
        "demo-request-001",
    )
    repeated = remediations.approve_and_execute(
        outcome.plan.id,
        "admin",
        outcome.plan.content_hash(),
        "demo-request-001",
    )
    assert action.id == repeated.id
    assert action.status is ActionStatus.SUCCEEDED
    assert repository.get_incident(outcome.plan.incident_id).status is IncidentStatus.RESOLVED  # type: ignore[union-attr]


def test_modified_plan_hash_is_rejected() -> None:
    """浏览器批准的内容与服务端计划不一致时必须拒绝执行。"""

    _, incidents, remediations = create_services()
    outcome = incidents.evaluate_signal(
        Signal("lab-api", "cpu", 99.0, datetime.now(UTC)),
        [10.0] * 6,
    )
    assert outcome.plan is not None
    with pytest.raises(IntegrityViolationError):
        remediations.approve_and_execute(
            outcome.plan.id,
            "admin",
            "0" * 64,
            "demo-request-002",
        )


def test_failed_verification_runs_explicit_rollback() -> None:
    """验证失败后必须逆序执行已批准计划中声明的类型化回滚。"""

    repository = InMemoryRepository()
    incidents = IncidentApplicationService(
        RollingZScoreDetector(minimum_samples=5), repository, repository
    )
    dispatcher = RollbackRecordingDispatcher()
    remediations = RemediationApplicationService(repository, repository, dispatcher)
    outcome = incidents.evaluate_signal(
        Signal("lab-api", "cpu", 99.0, datetime.now(UTC)),
        [10.0] * 6,
    )
    assert outcome.plan is not None
    outcome.plan.steps = [
        RemediationStep(
            action_type="apply_change",
            target="lab-api",
            arguments={"version": "new"},
            expected_result="变更生效",
            rollback_action="restore_change",
            rollback_arguments={"version": "old"},
        ),
        RemediationStep(
            action_type="verify_change",
            target="lab-api",
            arguments={},
            expected_result="验证通过",
        ),
    ]
    repository.save_plan(outcome.plan)

    action = remediations.approve_and_execute(
        outcome.plan.id,
        "admin",
        outcome.plan.content_hash(),
        "demo-request-rollback",
    )

    assert action.status is ActionStatus.ROLLED_BACK
    assert dispatcher.calls == ["apply_change", "verify_change", "restore_change"]
    assert action.output["rollback"] == [
        {
            "action_type": "restore_change",
            "target": "lab-api",
            "succeeded": True,
            "message": "restore_change 已处理",
        }
    ]


def test_business_recovery_probe_controls_incident_resolution() -> None:
    """容器动作成功但依赖健康复检失败时不能关闭 Incident。"""

    repository = InMemoryRepository()
    incidents = IncidentApplicationService(
        RollingZScoreDetector(minimum_samples=5), repository, repository
    )
    remediations = RemediationApplicationService(
        repository,
        repository,
        SafeDemoDispatcher(),
        recovery_verifier=FailedRecoveryVerifier(),
    )
    outcome = incidents.evaluate_signal(
        Signal("lab-redis", "service_health", 0.0, datetime.now(UTC)),
        [1.0] * 6,
    )
    assert outcome.plan is not None

    action = remediations.approve_and_execute(
        outcome.plan.id,
        "admin",
        outcome.plan.content_hash(),
        "demo-request-health-verification",
    )

    assert action.status is ActionStatus.FAILED
    assert action.output["verification"]["status_code"] == 503
    incident = repository.get_incident(outcome.plan.incident_id)
    assert incident is not None
    assert incident.status is IncidentStatus.FAILED
