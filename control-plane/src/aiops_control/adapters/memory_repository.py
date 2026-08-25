"""线程安全的内存仓储。

该实现用于阶段一演示和单元测试，接口保持与未来 PostgreSQL 适配器一致。
锁只保护字典读写，不在锁内执行网络或算法操作，避免扩大临界区。
"""

from collections.abc import Callable
from threading import Lock, RLock

from aiops_control.domain.changes import ChangeEvent
from aiops_control.domain.models import ActionRun, Approval, Incident, RemediationPlan
from aiops_control.domain.monitoring import (
    AgentNode,
    MonitoredAsset,
    MonitoredTopologyEdge,
    MonitorEvaluation,
    MonitorRule,
)


class InMemoryRepository:
    """在一个适配器中实现阶段一所需的两个仓储端口。"""

    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self._plans: dict[str, RemediationPlan] = {}
        self._approvals: dict[str, Approval] = {}
        self._action_runs: dict[str, ActionRun] = {}
        self._action_keys: dict[str, str] = {}
        self._change_events: dict[str, ChangeEvent] = {}
        self._agent_nodes: dict[str, AgentNode] = {}
        self._monitored_assets: dict[str, MonitoredAsset] = {}
        self._monitored_topology: dict[tuple[str, str, str], MonitoredTopologyEdge] = {}
        self._monitor_rules: dict[str, MonitorRule] = {}
        self._monitor_evaluations: dict[str, MonitorEvaluation] = {}
        self._lock = RLock()
        self._monitoring_cycle_lock = Lock()

    def save_incident(self, incident: Incident) -> None:
        """新增或覆盖一个 Incident。"""

        with self._lock:
            self._incidents[incident.id] = incident

    def get_incident(self, incident_id: str) -> Incident | None:
        """按 ID 查询 Incident。"""

        with self._lock:
            return self._incidents.get(incident_id)

    def list_incidents(self) -> list[Incident]:
        """按创建时间倒序返回 Incident。"""

        with self._lock:
            return sorted(self._incidents.values(), key=lambda item: item.created_at, reverse=True)

    def save_plan(self, plan: RemediationPlan) -> None:
        """新增或覆盖一个修复计划。"""

        with self._lock:
            self._plans[plan.id] = plan

    def get_plan(self, plan_id: str) -> RemediationPlan | None:
        """按 ID 查询修复计划。"""

        with self._lock:
            return self._plans.get(plan_id)

    def get_plan_by_incident(self, incident_id: str) -> RemediationPlan | None:
        """返回一个 Incident 最新创建的修复计划。"""

        with self._lock:
            plans = [plan for plan in self._plans.values() if plan.incident_id == incident_id]
        return max(plans, key=lambda item: item.created_at) if plans else None

    def save_approval(self, approval: Approval) -> None:
        """保存不可变审批记录。"""

        with self._lock:
            self._approvals[approval.id] = approval

    def save_action_run(self, action_run: ActionRun) -> None:
        """保存执行记录并建立幂等键索引。"""

        with self._lock:
            self._action_runs[action_run.id] = action_run
            self._action_keys[action_run.idempotency_key] = action_run.id

    def get_action_run_by_key(self, idempotency_key: str) -> ActionRun | None:
        """根据幂等键返回已有执行记录。"""

        with self._lock:
            action_id = self._action_keys.get(idempotency_key)
            return self._action_runs.get(action_id) if action_id else None

    def list_action_runs(self) -> list[ActionRun]:
        """按创建时间倒序返回执行记录。"""

        with self._lock:
            return sorted(
                self._action_runs.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )

    def save_change_event(self, event: ChangeEvent) -> None:
        """保存一个标准变更事件。"""

        with self._lock:
            self._change_events[event.id] = event

    def list_change_events(self, service: str | None = None) -> list[ChangeEvent]:
        """按时间倒序返回全部或指定服务的变更事件。"""

        with self._lock:
            events = list(self._change_events.values())
        if service is not None:
            events = [event for event in events if event.service == service]
        return sorted(events, key=lambda item: item.occurred_at, reverse=True)

    def save_agent_node(self, node: AgentNode) -> None:
        """按稳定节点 ID 保存最新心跳。"""

        with self._lock:
            self._agent_nodes[node.id] = node

    def list_agent_nodes(self) -> list[AgentNode]:
        """按最近心跳倒序返回节点。"""

        with self._lock:
            return sorted(
                self._agent_nodes.values(),
                key=lambda item: item.last_heartbeat_at,
                reverse=True,
            )

    def save_monitored_asset(self, asset: MonitoredAsset) -> None:
        """保存 Agent 实际发现的最新资产状态。"""

        with self._lock:
            self._monitored_assets[asset.id] = asset

    def get_monitored_asset(self, asset_id: str) -> MonitoredAsset | None:
        """按稳定资产 ID 查询真实资产。"""

        with self._lock:
            return self._monitored_assets.get(asset_id)

    def list_monitored_assets(self) -> list[MonitoredAsset]:
        """按资产 ID 返回可重复排序的真实资产列表。"""

        with self._lock:
            return sorted(self._monitored_assets.values(), key=lambda item: item.id)

    def save_monitored_topology(self, edge: MonitoredTopologyEdge) -> None:
        """按起点、终点和关系覆盖拓扑最新状态。"""

        key = (edge.source_asset_id, edge.target_asset_id, edge.relation)
        with self._lock:
            self._monitored_topology[key] = edge

    def list_monitored_topology(self) -> list[MonitoredTopologyEdge]:
        """返回真实环境拓扑快照。"""

        with self._lock:
            return list(self._monitored_topology.values())

    def save_monitor_rule(self, rule: MonitorRule) -> None:
        """保存类型化监测规则。"""

        with self._lock:
            self._monitor_rules[rule.id] = rule

    def list_monitor_rules(self) -> list[MonitorRule]:
        """按规则 ID 返回规则。"""

        with self._lock:
            return sorted(self._monitor_rules.values(), key=lambda item: item.id)

    def save_monitor_evaluation(self, evaluation: MonitorEvaluation) -> None:
        """保存不可变规则评估记录。"""

        with self._lock:
            self._monitor_evaluations[evaluation.id] = evaluation

    def list_monitor_evaluations(
        self, asset_id: str | None = None, limit: int = 200
    ) -> list[MonitorEvaluation]:
        """返回最近评估，并可限定资产。"""

        with self._lock:
            evaluations = list(self._monitor_evaluations.values())
        if asset_id is not None:
            evaluations = [item for item in evaluations if item.asset_id == asset_id]
        evaluations.sort(key=lambda item: item.evaluated_at, reverse=True)
        return evaluations[:limit]

    def run_monitoring_cycle_once(self, callback: Callable[[], None]) -> bool:
        """非阻塞执行单实例评估周期，模拟数据库租约语义。"""

        if not self._monitoring_cycle_lock.acquire(blocking=False):
            return False
        try:
            callback()
            return True
        finally:
            self._monitoring_cycle_lock.release()
