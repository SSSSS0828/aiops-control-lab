"""真实指标规则评估、Incident 创建和连续恢复编排。

每分钟读取 Agent 最新值；阈值必须连续命中指定周期才告警，告警后必须连续三个周期正常
才恢复。该迟滞状态避免容器短抖动反复开关 Incident。观察模式从不生成修复计划。
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch

from aiops_control.domain.enums import IncidentStatus
from aiops_control.domain.models import EvidenceRef, Hypothesis, Incident, new_id
from aiops_control.domain.monitoring import LatestMetric, MonitorEvaluation, MonitorRule
from aiops_control.ports.metric_store import LatestMetricStore
from aiops_control.ports.monitoring_repository import MonitoringRepository
from aiops_control.ports.repositories import IncidentRepository


@dataclass(slots=True)
class _RuleState:
    """单规则单资产的内存迟滞状态。"""

    breach_streak: int = 0
    recovery_streak: int = 0
    alerting: bool = False


class MonitoringService:
    """评估注册规则并维护观察型 Incident。"""

    def __init__(
        self,
        repository: MonitoringRepository,
        incidents: IncidentRepository,
        metric_store: LatestMetricStore,
    ) -> None:
        self._repository = repository
        self._incidents = incidents
        self._metric_store = metric_store
        self._states: dict[tuple[str, str], _RuleState] = defaultdict(_RuleState)
        self._history: dict[tuple[str, str], deque[tuple[datetime, float]]] = defaultdict(deque)

    def ensure_default_rules(self) -> None:
        """首次启动写入可审计默认规则；已有规则不会被静默覆盖。"""

        if self._repository.list_monitor_rules():
            return
        for rule in default_monitor_rules():
            self._repository.save_monitor_rule(rule)

    def evaluate_all(self) -> list[MonitorEvaluation]:
        """完成一轮规则评估，并返回本轮紧凑事实。"""

        now = datetime.now(UTC)
        evaluations: list[MonitorEvaluation] = []
        for rule in self._repository.list_monitor_rules():
            if not rule.enabled:
                continue
            for metric in self._metric_store.list_metrics(metric_name=rule.metric_name):
                asset_id = metric.labels.get("asset_id", "")
                if not fnmatch(asset_id, rule.asset_selector):
                    continue
                value = self._rule_value(rule, metric, now)
                evaluation = self._evaluate_one(rule, asset_id, value, now)
                self._repository.save_monitor_evaluation(evaluation)
                evaluations.append(evaluation)
                self._update_incident(rule, evaluation, now)
        return evaluations

    def _rule_value(self, rule: MonitorRule, metric: LatestMetric, now: datetime) -> float:
        if rule.operator != "increase_gte":
            return metric.value
        key = (rule.id, metric.labels.get("asset_id", ""))
        history = self._history[key]
        history.append((now, metric.value))
        boundary = now - timedelta(seconds=rule.window_seconds)
        while len(history) > 1 and history[0][0] < boundary:
            history.popleft()
        return metric.value - history[0][1]

    def _evaluate_one(
        self, rule: MonitorRule, asset_id: str, value: float, now: datetime
    ) -> MonitorEvaluation:
        key = (rule.id, asset_id)
        state = self._states[key]
        breached = _compare(value, rule.operator, rule.threshold)
        if breached:
            state.breach_streak += 1
            state.recovery_streak = 0
            if state.breach_streak >= rule.consecutive_cycles:
                state.alerting = True
        else:
            state.breach_streak = 0
            if state.alerting:
                state.recovery_streak += 1
                if state.recovery_streak >= rule.recovery_cycles:
                    state.alerting = False
            else:
                state.recovery_streak = min(state.recovery_streak + 1, rule.recovery_cycles)
        state_name = "alerting" if state.alerting else ("pending" if breached else "healthy")
        return MonitorEvaluation(
            id=new_id("eval"),
            rule_id=rule.id,
            asset_id=asset_id,
            value=value,
            state=state_name,
            breach_streak=state.breach_streak,
            recovery_streak=state.recovery_streak,
            message=f"{rule.name}：当前值 {value:.2f}，阈值 {rule.operator} {rule.threshold:.2f}",
            evaluated_at=now,
        )

    def _update_incident(
        self, rule: MonitorRule, evaluation: MonitorEvaluation, now: datetime
    ) -> None:
        query = f"registered://monitor-rules/{rule.id}"
        active = next(
            (
                item
                for item in self._incidents.list_incidents()
                if item.asset_id == evaluation.asset_id
                and item.status not in {IncidentStatus.RESOLVED, IncidentStatus.FAILED}
                and any(evidence.query == query for evidence in item.evidence)
            ),
            None,
        )
        if evaluation.state == "alerting" and active is None:
            evidence = EvidenceRef(
                id=new_id("evi"),
                source="monitor-rule",
                query=query,
                started_at=now - timedelta(seconds=rule.window_seconds),
                ended_at=now,
                summary=evaluation.message,
            )
            incident = Incident(
                id=new_id("inc"),
                title=f"{evaluation.asset_id} 触发 {rule.name}",
                asset_id=evaluation.asset_id,
                severity=rule.severity,
                status=IncidentStatus.OPEN,
                created_at=now,
                updated_at=now,
                evidence=[evidence],
                hypotheses=[
                    Hypothesis(
                        asset_id=evaluation.asset_id,
                        reason=f"规则 {rule.name} 连续命中，优先检查该资产及其上游依赖",
                        score=0.8,
                        evidence_ids=(evidence.id,),
                    )
                ],
            )
            self._incidents.save_incident(incident)
        elif (
            active is not None
            and evaluation.state == "healthy"
            and evaluation.recovery_streak >= rule.recovery_cycles
        ):
            active.resolve_observation()
            self._incidents.save_incident(active)


def _compare(value: float, operator: str, threshold: float) -> bool:
    """执行允许列表中的比较运算，未知运算符安全失败。"""

    if operator in {"gt", "increase_gte"}:
        return value > threshold if operator == "gt" else value >= threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    return False


def default_monitor_rules() -> tuple[MonitorRule, ...]:
    """返回阶段六真实环境默认规则，周期按每分钟调度计算。"""

    return (
        MonitorRule(
            "host-cpu-high",
            "主机 CPU 持续过高",
            "aiops_host_cpu_percent",
            "host/tencent-lab-01",
            "gt",
            85,
            5,
            3,
            "high",
            300,
        ),
        MonitorRule(
            "host-memory-low",
            "主机可用内存不足",
            "aiops_host_memory_available_percent",
            "host/tencent-lab-01",
            "lt",
            10,
            5,
            3,
            "high",
            300,
        ),
        MonitorRule(
            "host-disk-warning",
            "根盘使用率偏高",
            "aiops_host_disk_used_percent",
            "host/tencent-lab-01",
            "gt",
            80,
            1,
            3,
            "medium",
            60,
        ),
        MonitorRule(
            "host-disk-critical",
            "根盘使用率严重",
            "aiops_host_disk_used_percent",
            "host/tencent-lab-01",
            "gt",
            90,
            1,
            3,
            "high",
            60,
        ),
        MonitorRule(
            "container-down",
            "真实容器停止",
            "aiops_container_up",
            "docker/devops-lab/*",
            "lt",
            1,
            2,
            3,
            "high",
            120,
        ),
        MonitorRule(
            "container-restart-loop",
            "容器十分钟频繁重启",
            "aiops_container_restart_count",
            "docker/devops-lab/*",
            "increase_gte",
            3,
            1,
            3,
            "high",
            600,
        ),
    )
