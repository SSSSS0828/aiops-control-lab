"""真实监测持久化端口；应用层不依赖 PostgreSQL 或内存实现。"""

from collections.abc import Callable
from typing import Protocol

from aiops_control.domain.monitoring import (
    AgentNode,
    MonitoredAsset,
    MonitoredTopologyEdge,
    MonitorEvaluation,
    MonitorRule,
)


class MonitoringRepository(Protocol):
    """节点、资产、拓扑、规则和评估的组合仓储协议。"""

    def save_agent_node(self, node: AgentNode) -> None: ...

    def list_agent_nodes(self) -> list[AgentNode]: ...

    def save_monitored_asset(self, asset: MonitoredAsset) -> None: ...

    def get_monitored_asset(self, asset_id: str) -> MonitoredAsset | None: ...

    def list_monitored_assets(self) -> list[MonitoredAsset]: ...

    def save_monitored_topology(self, edge: MonitoredTopologyEdge) -> None: ...

    def list_monitored_topology(self) -> list[MonitoredTopologyEdge]: ...

    def save_monitor_rule(self, rule: MonitorRule) -> None: ...

    def list_monitor_rules(self) -> list[MonitorRule]: ...

    def save_monitor_evaluation(self, evaluation: MonitorEvaluation) -> None: ...

    def list_monitor_evaluations(
        self, asset_id: str | None = None, limit: int = 200
    ) -> list[MonitorEvaluation]: ...

    def run_monitoring_cycle_once(self, callback: Callable[[], None]) -> bool: ...
