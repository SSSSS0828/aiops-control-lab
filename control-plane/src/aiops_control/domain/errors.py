"""领域异常。

应用层只抛出这些稳定异常，API 层负责将其映射为 HTTP 状态码，
从而避免 HTTP 语义泄漏到业务逻辑。
"""


class DomainError(Exception):
    """所有可预期业务错误的基类。"""


class EntityNotFoundError(DomainError):
    """请求的领域实体不存在。"""


class InvalidStateTransitionError(DomainError):
    """实体当前状态不允许执行目标操作。"""


class ApprovalExpiredError(DomainError):
    """审批请求已超过有效期。"""


class IntegrityViolationError(DomainError):
    """批准内容与实际待执行内容不一致。"""


class ExternalSourceError(DomainError):
    """外部遥测、模型或执行数据源不可用或返回非法数据。"""
