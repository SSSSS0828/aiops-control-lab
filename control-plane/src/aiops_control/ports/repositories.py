"""领域仓储端口。

应用服务只依赖这些协议，因此内存实现、PostgreSQL 实现和测试替身可以互换。
"""

from typing import Protocol

from aiops_control.domain.changes import ChangeEvent
from aiops_control.domain.models import ActionRun, Approval, Incident, RemediationPlan
from aiops_control.ports.monitoring_repository import MonitoringRepository


class IncidentRepository(Protocol):
    """Incident 持久化端口。"""

    def save_incident(self, incident: Incident) -> None: ...

    def get_incident(self, incident_id: str) -> Incident | None: ...

    def list_incidents(self) -> list[Incident]: ...


class RemediationRepository(Protocol):
    """修复计划、审批和执行记录的持久化端口。"""

    def save_plan(self, plan: RemediationPlan) -> None: ...

    def get_plan(self, plan_id: str) -> RemediationPlan | None: ...

    def get_plan_by_incident(self, incident_id: str) -> RemediationPlan | None: ...

    def save_approval(self, approval: Approval) -> None: ...

    def save_action_run(self, action_run: ActionRun) -> None: ...

    def get_action_run_by_key(self, idempotency_key: str) -> ActionRun | None: ...

    def list_action_runs(self) -> list[ActionRun]: ...


class ChangeEventRepository(Protocol):
    """通用 DevOps 变更事件仓储端口。"""

    def save_change_event(self, event: ChangeEvent) -> None: ...

    def list_change_events(self, service: str | None = None) -> list[ChangeEvent]: ...


class ApplicationRepository(
    IncidentRepository,
    RemediationRepository,
    ChangeEventRepository,
    MonitoringRepository,
    Protocol,
):
    """控制面组合根所需的完整仓储能力。"""
