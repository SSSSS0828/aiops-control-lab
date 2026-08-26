"""SLO、容量与变更风险领域模型。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SLODefinition:
    """以好事件比例描述的服务级别目标。"""

    id: str
    name: str
    objective: float
    window_days: int


@dataclass(frozen=True, slots=True)
class ErrorBudgetStatus:
    """当前 SLI、预算消耗和燃烧速率。"""

    sli: float
    bad_events: int
    allowed_bad_events: float
    remaining_ratio: float
    burn_rate: float
    state: str


@dataclass(frozen=True, slots=True)
class CapacityPoint:
    """容量预测使用的带时间观测点。"""

    occurred_at: datetime
    value: float


@dataclass(frozen=True, slots=True)
class CapacityForecast:
    """线性趋势、拟合质量和预计阈值时间。"""

    slope_per_hour: float
    r_squared: float
    threshold: float
    estimated_exhaustion_at: datetime | None
    state: str


@dataclass(frozen=True, slots=True)
class ChangeRiskInput:
    """变更发布前可解释的风险特征。"""

    blast_radius: float
    recent_incident_rate: float
    changed_components: int
    rollback_ready: bool


@dataclass(frozen=True, slots=True)
class ChangeRiskAssessment:
    """变更综合风险与分项解释。"""

    score: float
    level: str
    reasons: tuple[str, ...]
