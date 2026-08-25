"""AIOps 核心领域模型。

输入：来自 Agent、插件或实验室的标准化信号与操作请求。
处理：维护 Incident、修复计划、审批和执行记录的业务不变量。
输出：可由应用层持久化和编排的纯 Python 实体。
副作用：本模块不进行网络、文件或数据库操作。
并发：实体本身不是线程安全的，并发一致性由仓储事务负责。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from aiops_control.domain.enums import ActionStatus, IncidentStatus, PlanStatus, RiskLevel
from aiops_control.domain.errors import InvalidStateTransitionError


def new_id(prefix: str) -> str:
    """生成带语义前缀的实体 ID，便于日志检索和人工排障。"""

    return f"{prefix}_{uuid4().hex}"


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间，避免跨时区比较产生歧义。"""

    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Asset:
    """被管理的主机、容器、服务或 Kubernetes 资源。"""

    id: str
    kind: str
    name: str
    node_id: str
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Signal:
    """Agent 或插件上报的单个标准化观测值。"""

    asset_id: str
    name: str
    value: float
    occurred_at: datetime
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """指向外部指标或日志的不可变证据引用。"""

    id: str
    source: str
    query: str
    started_at: datetime
    ended_at: datetime
    summary: str


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """根因候选及其可解释评分。"""

    asset_id: str
    reason: str
    score: float
    evidence_ids: tuple[str, ...]


@dataclass(slots=True)
class Incident:
    """将相关异常信号聚合成一个可处置事件。"""

    id: str
    title: str
    asset_id: str
    severity: str
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceRef] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)

    def wait_for_approval(self) -> None:
        """将已分析的 Incident 转入等待审批状态。"""

        allowed = {IncidentStatus.OPEN, IncidentStatus.INVESTIGATING}
        if self.status not in allowed:
            raise InvalidStateTransitionError(f"Incident 状态 {self.status} 不能等待审批")
        self.status = IncidentStatus.WAITING_APPROVAL
        self.updated_at = utc_now()

    def start_remediation(self) -> None:
        """在计划获批后标记 Incident 正在修复。"""

        if self.status is not IncidentStatus.WAITING_APPROVAL:
            raise InvalidStateTransitionError(f"Incident 状态 {self.status} 不能开始修复")
        self.status = IncidentStatus.REMEDIATING
        self.updated_at = utc_now()

    def finish(self, succeeded: bool) -> None:
        """根据验证结果结束 Incident。"""

        if self.status is not IncidentStatus.REMEDIATING:
            raise InvalidStateTransitionError(f"Incident 状态 {self.status} 不能结束修复")
        self.status = IncidentStatus.RESOLVED if succeeded else IncidentStatus.FAILED
        self.updated_at = utc_now()

    def resolve_observation(self) -> None:
        """在监测连续恢复后关闭尚未执行动作的观察型 Incident。"""

        allowed = {
            IncidentStatus.OPEN,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.WAITING_APPROVAL,
        }
        if self.status not in allowed:
            raise InvalidStateTransitionError(f"Incident 状态 {self.status} 不能按观察结果恢复")
        self.status = IncidentStatus.RESOLVED
        self.updated_at = utc_now()


@dataclass(frozen=True, slots=True)
class RemediationStep:
    """一个可审计、可验证的类型化修复步骤。"""

    action_type: str
    target: str
    arguments: dict[str, str]
    expected_result: str
    rollback_action: str | None = None
    rollback_arguments: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RemediationPlan:
    """等待人工批准的完整修复计划。"""

    id: str
    incident_id: str
    summary: str
    risk: RiskLevel
    steps: list[RemediationStep]
    created_at: datetime
    expires_at: datetime
    status: PlanStatus = PlanStatus.PENDING_APPROVAL

    def content_hash(self) -> str:
        """计算稳定内容哈希，确保批准内容与执行内容完全一致。

        哈希只覆盖会影响系统状态的语义字段；状态和创建时间不参与计算，
        否则批准后改变状态会使同一计划得到不同哈希。
        """

        # 先把每个步骤转换成字段固定的普通字典，消除对象表示差异。
        steps = [
            {
                "action_type": step.action_type,
                "target": step.target,
                "arguments": step.arguments,
                "expected_result": step.expected_result,
                "rollback_action": step.rollback_action,
                "rollback_arguments": step.rollback_arguments,
            }
            for step in self.steps
        ]
        # sort_keys 保证字典插入顺序不会改变待批准内容的字节表示。
        canonical = json.dumps(
            {
                "incident_id": self.incident_id,
                "summary": self.summary,
                "risk": self.risk.value,
                "steps": steps,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        # SHA-256 的结果会同时写入 Approval 与 ActionRun，供 Agent 二次验证。
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Approval:
    """记录谁在何时批准了哪一份不可变计划。"""

    id: str
    plan_id: str
    approver: str
    approved_hash: str
    approved_at: datetime


@dataclass(slots=True)
class ActionRun:
    """审批通过后产生的一次幂等执行任务。"""

    id: str
    plan_id: str
    incident_id: str
    idempotency_key: str
    approved_hash: str
    status: ActionStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: dict[str, Any] = field(default_factory=dict)
