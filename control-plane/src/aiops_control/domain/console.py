"""控制台只读视图模型。

输入：领域仓储中的 Incident、修复计划、执行记录以及部署时声明的组件能力。
处理：只描述控制台需要展示的稳定字段，不包含数据库或 HTTP 细节。
输出：资产状态、系统能力和汇总指标等不可变查询结果。
副作用：无；所有状态推导均由应用层完成。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ManagedAssetView:
    """控制台展示的资产及其当前健康摘要。"""

    id: str
    name: str
    kind: str
    node_id: str
    status: str
    address: str
    responsibilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapabilityView:
    """一个可学习、可观察但不夸大完成度的系统能力。"""

    id: str
    name: str
    category: str
    state: str
    description: str


@dataclass(frozen=True, slots=True)
class ConsoleOverview:
    """首页使用的轻量聚合统计。"""

    incident_count: int
    active_incident_count: int
    resolved_incident_count: int
    execution_count: int
    successful_execution_count: int
    asset_count: int
    plugin_count: int
    access_mode: str
