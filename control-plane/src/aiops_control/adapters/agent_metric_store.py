"""Agent 最新指标的线程安全内存存储与 Prometheus 文本导出。

原始时序由 Prometheus 抓取保存，因此控制面只保留每个标签集的最新值。序列去重按
node_id + instance_id 保存最大已确认序列，重连重发不会产生重复评估或覆盖新批次。
"""

from threading import RLock

from aiops_control.application.metric_registry import REGISTERED_METRICS
from aiops_control.domain.monitoring import LatestMetric


class AgentMetricStore:
    """保存受注册表约束的最新 Agent 指标。"""

    def __init__(self) -> None:
        self._metrics: dict[tuple[str, tuple[tuple[str, str], ...]], LatestMetric] = {}
        self._sequences: dict[tuple[str, str], int] = {}
        self._lock = RLock()

    def accept_batch(
        self,
        node_id: str,
        instance_id: str,
        sequence: int,
        metrics: list[LatestMetric],
    ) -> bool:
        """原子接受新序列；旧序列直接确认但不重复写入。"""

        sequence_key = (node_id, instance_id)
        with self._lock:
            if sequence <= self._sequences.get(sequence_key, 0):
                return False
            for metric in metrics:
                if metric.name not in REGISTERED_METRICS:
                    continue
                labels = tuple(sorted(metric.labels.items()))
                self._metrics[(metric.name, labels)] = metric
            self._sequences[sequence_key] = sequence
        return True

    def list_metrics(
        self, asset_id: str | None = None, metric_name: str | None = None
    ) -> list[LatestMetric]:
        """按注册指标与资产返回最新值。"""

        if metric_name is not None and metric_name not in REGISTERED_METRICS:
            return []
        with self._lock:
            values = list(self._metrics.values())
        if asset_id is not None:
            values = [item for item in values if item.labels.get("asset_id") == asset_id]
        if metric_name is not None:
            values = [item for item in values if item.name == metric_name]
        return sorted(values, key=lambda item: (item.name, sorted(item.labels.items())))

    def prometheus_text(self) -> str:
        """导出 Prometheus 0.0.4 文本；标签经过最小必要转义。"""

        lines: list[str] = []
        grouped: dict[str, list[LatestMetric]] = {}
        for metric in self.list_metrics():
            grouped.setdefault(metric.name, []).append(metric)
        for name, metrics in grouped.items():
            definition = REGISTERED_METRICS[name]
            lines.append(f"# HELP {name} {definition.description}")
            lines.append(f"# TYPE {name} gauge")
            for metric in metrics:
                labels = ",".join(
                    f'{key}="{_escape_label(value)}"'
                    for key, value in sorted(metric.labels.items())
                )
                suffix = f"{{{labels}}}" if labels else ""
                lines.append(f"{name}{suffix} {metric.value}")
        return "\n".join(lines) + "\n"


def _escape_label(value: str) -> str:
    """按 Prometheus 文本格式转义反斜线、换行和双引号。"""

    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
