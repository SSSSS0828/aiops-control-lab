"""Git、CI/CD 和发布 Webhook 的标准变更事件。"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """将不同 DevOps 工具的事件归一到可关联字段。"""

    id: str
    provider: str
    event_type: str
    service: str
    revision: str
    status: str
    occurred_at: datetime
    attributes: dict[str, str] = field(default_factory=dict)
