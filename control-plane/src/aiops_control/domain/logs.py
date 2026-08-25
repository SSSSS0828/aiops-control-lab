"""日志智能领域模型。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LogEvent:
    """经过来源标记和脱敏前的单条日志事件。"""

    id: str
    asset_id: str
    message: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class LogTemplate:
    """将动态变量归一化后的稳定日志模板。"""

    id: str
    template: str
    tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LogCluster:
    """共享同一模板的一组日志统计。"""

    template: LogTemplate
    count: int
    example_event_ids: tuple[str, ...]
