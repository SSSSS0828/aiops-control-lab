"""HTTP API 输入模型。

Pydantic 模型只负责边界校验，不承载 Incident 状态迁移等业务规则。
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SignalEvaluationRequest(BaseModel):
    """提交一个当前指标值及其历史窗口。"""

    asset_id: str = Field(min_length=1, max_length=128)
    metric_name: str = Field(min_length=1, max_length=128)
    current: float
    history: list[float] = Field(min_length=2, max_length=3600)
    occurred_at: datetime | None = None


class ApprovalRequest(BaseModel):
    """批准修复计划所需的不可变字段。"""

    approver: str = Field(min_length=1, max_length=128)
    approved_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)


class LabInjectionRequest(BaseModel):
    """请求注入一个可重复的沙箱故障。"""

    scenario: str = Field(default="container_cpu_spike", max_length=64)


class SLOEvaluationRequest(BaseModel):
    """计算一个好事件 SLO 窗口。"""

    name: str = Field(min_length=1, max_length=128)
    objective: float = Field(gt=0, lt=1)
    window_days: int = Field(default=30, ge=1, le=365)
    good_events: int = Field(ge=0)
    total_events: int = Field(gt=0)


class CapacityPointInput(BaseModel):
    """容量趋势中的单个时间点。"""

    occurred_at: datetime
    value: float


class CapacityForecastRequest(BaseModel):
    """请求对一组容量点执行阈值预测。"""

    points: list[CapacityPointInput] = Field(min_length=3, max_length=10_000)
    threshold: float


class ChangeRiskRequest(BaseModel):
    """发布前变更风险特征。"""

    blast_radius: float = Field(ge=0, le=1)
    recent_incident_rate: float = Field(ge=0, le=1)
    changed_components: int = Field(ge=1, le=10_000)
    rollback_ready: bool


class ChangeEventRequest(BaseModel):
    """Git、CI/CD 或发布系统提交的标准化 Webhook 事件。"""

    provider: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=64)
    service: str = Field(min_length=1, max_length=128)
    revision: str = Field(min_length=1, max_length=256)
    status: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    attributes: dict[str, str] = Field(default_factory=dict)


class MetricEvidenceRequest(BaseModel):
    """从 Prometheus 收集 Incident 指标证据。"""

    query: str = Field(min_length=1, max_length=1_024)
    started_at: datetime
    ended_at: datetime
    step_seconds: int = Field(default=15, ge=1, le=3_600)


class LogEvidenceRequest(BaseModel):
    """从 Loki 收集 Incident 日志证据。"""

    query: str = Field(min_length=1, max_length=1_024)
    started_at: datetime
    ended_at: datetime
    limit: int = Field(default=200, ge=1, le=1_000)


class DiagnosticQueryRequest(BaseModel):
    """提交给只读 AI 诊断器的问题和已经筛选的证据摘要。"""

    question: str = Field(min_length=2, max_length=2_000)
    evidence: list[str] = Field(default_factory=list, max_length=20)
