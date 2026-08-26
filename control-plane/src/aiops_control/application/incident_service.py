"""异常信号到 Incident 和修复计划的应用服务。

输入：标准化指标、历史窗口和目标资产。
数据流：检测器 -> 证据引用 -> Incident -> 根因候选 -> 修复计划 -> 仓储。
输出：检测结果，以及异常时创建的 Incident 与计划。
副作用：只通过仓储端口保存实体，不直接访问数据库或 Agent。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from aiops_control.application.incident_correlation_service import IncidentCorrelationService
from aiops_control.domain.enums import IncidentStatus, RiskLevel
from aiops_control.domain.models import (
    EvidenceRef,
    Hypothesis,
    Incident,
    RemediationPlan,
    RemediationStep,
    Signal,
    new_id,
    utc_now,
)
from aiops_control.domain.topology import TopologyEdge
from aiops_control.ports.detectors import AnomalyDetector, DetectionResult
from aiops_control.ports.repositories import (
    ChangeEventRepository,
    IncidentRepository,
    RemediationRepository,
)


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    """一次信号评估的完整结果。"""

    detection: DetectionResult
    incident: Incident | None
    plan: RemediationPlan | None


class IncidentApplicationService:
    """把低层异常分数转换为可解释、可处置的运维事件。"""

    def __init__(
        self,
        detector: AnomalyDetector,
        incident_repository: IncidentRepository,
        remediation_repository: RemediationRepository,
        *,
        correlation_service: IncidentCorrelationService | None = None,
        change_repository: ChangeEventRepository | None = None,
        topology_edges: tuple[TopologyEdge, ...] = (),
        real_actions_mode: str = "observe_only",
    ) -> None:
        self._detector = detector
        self._incidents = incident_repository
        self._remediations = remediation_repository
        self._correlation = correlation_service
        self._changes = change_repository
        self._topology_edges = topology_edges
        self._real_actions_mode = real_actions_mode

    def evaluate_signal(
        self,
        signal: Signal,
        history: Sequence[float],
    ) -> EvaluationOutcome:
        """检测信号，并在异常时创建等待审批的处置上下文。"""

        # 检测器只负责数学判断，避免算法代码承担告警和存储职责。
        detection = self._detector.detect(history, signal.value)
        # 正常信号直接返回，防止无意义 Incident 污染事件列表。
        if not detection.anomalous:
            return EvaluationOutcome(detection=detection, incident=None, plan=None)

        now = utc_now()
        # EvidenceRef 只保存外部查询和摘要，不复制高体积原始遥测数据。
        evidence = EvidenceRef(
            id=new_id("evi"),
            source="prometheus",
            query=f'{signal.name}{{asset_id="{signal.asset_id}"}}',
            started_at=signal.occurred_at - timedelta(minutes=5),
            ended_at=signal.occurred_at,
            summary=detection.reason,
        )
        change_evidence = (
            self._correlation.change_evidence(
                signal,
                self._changes.list_change_events(signal.asset_id) if self._changes else [],
            )
            if self._correlation
            else []
        )
        match = (
            self._correlation.find_match(
                signal,
                self._incidents.list_incidents(),
                list(self._topology_edges),
            )
            if self._correlation
            else None
        )
        if match is not None:
            incident = match.incident
            # 指标证据保留每次独立窗口；变更事件按不可变查询 ID 去重。
            existing_queries = {item.query for item in incident.evidence}
            incident.evidence.append(evidence)
            incident.evidence.extend(
                item for item in change_evidence if item.query not in existing_queries
            )
            if all(item.asset_id != signal.asset_id for item in incident.hypotheses):
                incident.hypotheses.append(
                    Hypothesis(
                        asset_id=signal.asset_id,
                        reason=f"{match.reason}：{signal.name} 同时异常",
                        score=min(detection.score / 10.0, 1.0) * match.score,
                        evidence_ids=(evidence.id,),
                    )
                )
            incident.updated_at = now
            self._incidents.save_incident(incident)
            plan = self._remediations.get_plan_by_incident(incident.id)
            return EvaluationOutcome(detection=detection, incident=incident, plan=plan)

        # 阶段一只有单信号根因，后续图算法仍可复用同一 Hypothesis 结构。
        hypothesis = Hypothesis(
            asset_id=signal.asset_id,
            reason=f"资产 {signal.asset_id} 的 {signal.name} 指标异常",
            score=min(detection.score / 10.0, 1.0),
            evidence_ids=(evidence.id,),
        )
        incident = Incident(
            id=new_id("inc"),
            title=f"{signal.asset_id} 出现 {signal.name} 异常",
            asset_id=signal.asset_id,
            severity="high" if detection.score >= 5 else "medium",
            status=IncidentStatus.OPEN,
            created_at=now,
            updated_at=now,
            evidence=[evidence, *change_evidence],
            hypotheses=[hypothesis],
        )
        if _is_real_asset(signal.asset_id) and self._real_actions_mode == "observe_only":
            # 观察模式只建立证据与 Incident，绝不为真实资产生成任何写计划。
            self._incidents.save_incident(incident)
            return EvaluationOutcome(detection=detection, incident=incident, plan=None)
        # 默认计划使用类型化容器重启动作，Agent 会再次校验动作与目标范围。
        plan = RemediationPlan(
            id=new_id("plan"),
            incident_id=incident.id,
            summary=f"重启 {signal.asset_id} 并验证健康状态",
            risk=RiskLevel.MEDIUM,
            steps=[
                RemediationStep(
                    action_type="restart_container",
                    target=signal.asset_id,
                    arguments={"grace_seconds": "10"},
                    expected_result="容器恢复运行且 HTTP 健康检查通过",
                    # 容器重启无法恢复重启前的内存状态，因此不能伪造一个无效回滚动作。
                    rollback_action=None,
                ),
                RemediationStep(
                    action_type="health_check",
                    target=signal.asset_id,
                    arguments={},
                    expected_result="容器状态为 running",
                ),
            ],
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        # Incident 只有形成可执行计划后才进入等待审批，防止出现空审批页面。
        incident.wait_for_approval()
        self._incidents.save_incident(incident)
        self._remediations.save_plan(plan)
        return EvaluationOutcome(detection=detection, incident=incident, plan=plan)


def _is_real_asset(asset_id: str) -> bool:
    """识别真实主机和 devops-lab 资产，实验室仍使用独立 lab-* 命名空间。"""

    return asset_id.startswith(("host/", "docker/devops-lab/"))
