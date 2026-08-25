"""异常检测器端口。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """检测器输出的统一结构。"""

    anomalous: bool
    score: float
    reason: str


class AnomalyDetector(Protocol):
    """所有在线异常检测算法必须实现的接口。"""

    def detect(self, history: Sequence[float], current: float) -> DetectionResult: ...
