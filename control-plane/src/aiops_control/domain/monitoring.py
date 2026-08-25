"""真实环境持续监测领域模型。

输入：Agent 身份、资产快照、注册指标和预定义规则。
处理：保存连接状态、规则连续命中/恢复状态和不可变评估事实。
输出：供应用层持久化、生成 Incident 和前端展示的纯 Python 实体。
副作用：无；数据库、gRPC 与 Prometheus 均由外层适配器负责。
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AgentNode:
    """已通过 mTLS 身份校验的 Agent 节点。"""

    id: str
    version: str
    instance_id: str
    certificate_identity: str
    status: str
    connected_at: datetime
    last_heartbeat_at: datetime


@dataclass(frozen=True, slots=True)
class MonitoredAsset:
    """由 Agent 实际发现的主机或容器资产。"""

    id: str
    node_id: str
    kind: str
    name: str
    status: str
    environment: str
    source: str
    last_seen_at: datetime
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MonitoredTopologyEdge:
    """带 RCA 权重和发现来源的真实拓扑边。"""

    source_asset_id: str
    target_asset_id: str
    relation: str
    weight: float
    source: str
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class MonitorRule:
    """只能查询注册指标的确定性监测规则。"""

    id: str
    name: str
    metric_name: str
    asset_selector: str
    operator: str
    threshold: float
    consecutive_cycles: int
    recovery_cycles: int
    severity: str
    window_seconds: int
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class MonitorEvaluation:
    """一次规则评估事实及跨周期状态。"""

    id: str
    rule_id: str
    asset_id: str
    value: float
    state: str
    breach_streak: int
    recovery_streak: int
    message: str
    evaluated_at: datetime


@dataclass(frozen=True, slots=True)
class LatestMetric:
    """控制面内存中用于暴露和评估的最新指标值。"""

    name: str
    value: float
    labels: dict[str, str]
    collected_at: datetime


@dataclass(frozen=True, slots=True)
class IncidentResolution:
    """连续正常后自动恢复 Incident 的审计说明。"""

    incident_id: str
    rule_id: str
    normal_cycles: int
    reason: str
    resolved_at: datetime
