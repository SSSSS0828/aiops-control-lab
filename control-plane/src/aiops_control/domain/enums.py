"""领域状态枚举。

集中定义状态名称可以避免 API、数据库和执行器分别使用不一致的字符串。
状态迁移规则仍由领域实体维护，而不是放在枚举中。
"""

from enum import StrEnum


class IncidentStatus(StrEnum):
    """Incident 从发现到关闭的生命周期状态。"""

    OPEN = "open"
    INVESTIGATING = "investigating"
    WAITING_APPROVAL = "waiting_approval"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    FAILED = "failed"


class PlanStatus(StrEnum):
    """修复计划的审批及执行状态。"""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class ActionStatus(StrEnum):
    """一次动作执行记录的状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RiskLevel(StrEnum):
    """动作风险等级，用于审批策略和界面提示。"""

    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
