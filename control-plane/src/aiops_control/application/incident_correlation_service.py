"""告警去重、拓扑关联和变更证据关联服务。

输入：新异常信号、活跃 Incident、服务拓扑边和标准化变更事件。
处理：先按同资产去重，再计算直接拓扑邻接；变更只关联故障前三十分钟的事件。
输出：可复用 Incident 的相关性结论，以及不包含任意 attributes 的变更证据引用。
副作用：本服务不修改 Incident、不访问仓储，便于单元测试和权重演进。
"""

from dataclasses import dataclass
from datetime import timedelta

from aiops_control.domain.changes import ChangeEvent
from aiops_control.domain.enums import IncidentStatus
from aiops_control.domain.models import EvidenceRef, Incident, Signal, new_id
from aiops_control.domain.topology import TopologyEdge

CORRELATION_WINDOW = timedelta(minutes=5)
CHANGE_WINDOW = timedelta(minutes=30)
ACTIVE_STATUSES = frozenset(
    {
        IncidentStatus.OPEN,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.WAITING_APPROVAL,
    }
)


@dataclass(frozen=True, slots=True)
class CorrelationMatch:
    """新信号与一个既有 Incident 的可解释相关性。"""

    incident: Incident
    score: float
    reason: str


class IncidentCorrelationService:
    """执行确定性时间窗口去重与一跳拓扑关联。"""

    def find_match(
        self,
        signal: Signal,
        incidents: list[Incident],
        edges: list[TopologyEdge],
    ) -> CorrelationMatch | None:
        """返回五分钟窗口内分数最高的活跃 Incident。"""

        adjacent_pairs = {
            frozenset((edge.source_asset_id, edge.target_asset_id))
            for edge in edges
            if edge.relation == "depends_on"
        }
        candidates: list[CorrelationMatch] = []
        for incident in incidents:
            if incident.status not in ACTIVE_STATUSES:
                continue
            # 使用绝对差容忍节点间轻微时钟偏差，但仍严格限制在五分钟内。
            if abs(signal.occurred_at - incident.updated_at) > CORRELATION_WINDOW:
                continue
            if incident.asset_id == signal.asset_id:
                candidates.append(CorrelationMatch(incident, 1.0, "同资产时间窗口去重"))
                continue
            pair = frozenset((incident.asset_id, signal.asset_id))
            if pair in adjacent_pairs:
                candidates.append(CorrelationMatch(incident, 0.7, "直接依赖拓扑关联"))

        if not candidates:
            return None
        # 分数优先；同分时选择最近更新的 Incident，避免旧事件吞并新故障。
        return max(candidates, key=lambda item: (item.score, item.incident.updated_at))

    def change_evidence(
        self,
        signal: Signal,
        events: list[ChangeEvent],
    ) -> list[EvidenceRef]:
        """把故障前相关变更转换成最多三条不可变证据引用。"""

        matched: list[ChangeEvent] = []
        for event in events:
            age = signal.occurred_at - event.occurred_at
            if event.service == signal.asset_id and timedelta(0) <= age <= CHANGE_WINDOW:
                matched.append(event)
        matched.sort(key=lambda item: item.occurred_at, reverse=True)

        evidence: list[EvidenceRef] = []
        for event in matched[:3]:
            # attributes 可能含提交者、分支或外部载荷，不复制进审计摘要。
            summary = (
                f"故障前变更：{event.provider}/{event.event_type}，"
                f"revision={event.revision}，status={event.status}"
            )
            evidence.append(
                EvidenceRef(
                    id=new_id("evi"),
                    source="change_event",
                    query=f"change_event_id={event.id}",
                    started_at=event.occurred_at,
                    ended_at=signal.occurred_at,
                    summary=summary,
                )
            )
        return evidence
