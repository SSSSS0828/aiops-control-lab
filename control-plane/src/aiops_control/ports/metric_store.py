"""高频最新指标存储端口。"""

from typing import Protocol

from aiops_control.domain.monitoring import LatestMetric


class LatestMetricStore(Protocol):
    """应用层接受批次和读取注册指标所需的最小协议。"""

    def accept_batch(
        self,
        node_id: str,
        instance_id: str,
        sequence: int,
        metrics: list[LatestMetric],
    ) -> bool: ...

    def list_metrics(
        self, asset_id: str | None = None, metric_name: str | None = None
    ) -> list[LatestMetric]: ...

    def prometheus_text(self) -> str: ...
