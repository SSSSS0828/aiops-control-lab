"""同季节位置基线检测器。

调用方应传入相同分钟、小时或星期位置的历史样本，例如最近四周每周一 09:00 的值。
算法接口保持与在线检测器一致，季节窗口选择由特征管道负责。
"""

from collections.abc import Sequence
from math import fsum, sqrt

from aiops_control.ports.detectors import DetectionResult


class SeasonalBaselineDetector:
    """使用中位数风格容错带检测同季节位置异常。"""

    def __init__(self, threshold: float = 3.5, minimum_samples: int = 4) -> None:
        self._threshold = threshold
        self._minimum_samples = minimum_samples

    def detect(self, history: Sequence[float], current: float) -> DetectionResult:
        """用同季节样本的均值和标准差判断异常。"""

        if len(history) < self._minimum_samples:
            return DetectionResult(False, 0.0, "同季节样本不足")
        mean = fsum(history) / len(history)
        variance = fsum((value - mean) ** 2 for value in history) / len(history)
        deviation = sqrt(variance)
        if deviation == 0:
            changed = current != mean
            return DetectionResult(
                changed,
                float("inf") if changed else 0.0,
                "同季节稳定基线发生变化" if changed else "当前值符合季节基线",
            )
        score = abs(current - mean) / deviation
        return DetectionResult(
            score >= self._threshold,
            score,
            f"当前值相对同季节基线偏离 {score:.2f} 个标准差",
        )
