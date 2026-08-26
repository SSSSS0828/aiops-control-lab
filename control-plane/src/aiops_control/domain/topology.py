"""服务拓扑与异常观测领域模型。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TopologyEdge:
    """调用方到依赖方的有向关系，例如 gateway depends_on api。"""

    source_asset_id: str
    target_asset_id: str
    relation: str = "depends_on"


@dataclass(frozen=True, slots=True)
class ObservedAnomaly:
    """进入根因分析器的资产异常及其证据。"""

    asset_id: str
    score: float
    occurred_at: datetime
    evidence_id: str
