"""指标与日志查询端口。

应用层只使用稳定领域对象，不感知 Prometheus/Loki URL、认证或 JSON 返回格式。
"""

from datetime import datetime
from typing import Protocol

from aiops_control.domain.telemetry import LogRecord, MetricSample


class MetricQueryPort(Protocol):
    """查询一个 PromQL 时间窗口。"""

    def query_range(
        self,
        query: str,
        started_at: datetime,
        ended_at: datetime,
        step_seconds: int,
    ) -> tuple[MetricSample, ...]: ...


class LogQueryPort(Protocol):
    """查询一个 LogQL 时间窗口。"""

    def query_range(
        self,
        query: str,
        started_at: datetime,
        ended_at: datetime,
        limit: int,
    ) -> tuple[LogRecord, ...]: ...
