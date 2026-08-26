"""遥测查询领域值对象。

输入：Prometheus 或 Loki 适配器解析后的标签、时间和值。
输出：与具体 HTTP 响应格式无关的指标样本和日志记录。
约束：对象不可变；原始遥测只在请求生命周期内传递，不进入 Incident 持久化。
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MetricSample:
    """一条带标签的时序指标样本。"""

    occurred_at: datetime
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LogRecord:
    """一条仅在证据摘要阶段短暂存在的日志记录。"""

    occurred_at: datetime
    message: str
    labels: dict[str, str] = field(default_factory=dict)
