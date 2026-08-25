"""指数加权移动平均异常检测器。

EWMA 对近期样本赋予更高权重，比固定窗口均值更快适应缓慢变化的系统负载。
该实现同时递推均值和方差，保持 O(n) 时间、O(1) 额外空间。
"""

from collections.abc import Sequence
from math import sqrt

from aiops_control.ports.detectors import DetectionResult


class EWMADetector:
    """使用指数加权均值和方差检测突发偏离。"""

    def __init__(
        self,
        alpha: float = 0.3,
        threshold: float = 3.0,
        minimum_samples: int = 5,
    ) -> None:
        if not 0 < alpha <= 1:
            raise ValueError("alpha 必须位于 (0, 1] 区间")
        if threshold <= 0:
            raise ValueError("阈值必须大于 0")
        self._alpha = alpha
        self._threshold = threshold
        self._minimum_samples = minimum_samples

    def detect(self, history: Sequence[float], current: float) -> DetectionResult:
        """根据历史递推基线计算当前标准化残差。"""

        if len(history) < self._minimum_samples:
            return DetectionResult(False, 0.0, "历史样本不足，暂不进行 EWMA 判断")

        # 第一个样本作为递推起点，不人为引入零值基线。
        mean = history[0]
        variance = 0.0
        for value in history[1:]:
            # 必须先保存更新前残差；方差更新需要描述样本相对旧基线的偏离。
            residual = value - mean
            # 均值向当前样本移动 alpha 比例，越大的 alpha 对突变越敏感。
            mean += self._alpha * residual
            # 递推方差使用前后均值共同校正，避免简单平方残差产生系统性偏差。
            variance = (1 - self._alpha) * (variance + self._alpha * residual * residual)

        standard_deviation = sqrt(max(variance, 0.0))
        if standard_deviation == 0:
            anomalous = current != mean
            return DetectionResult(
                anomalous,
                float("inf") if anomalous else 0.0,
                "EWMA 稳定基线发生变化" if anomalous else "当前值与 EWMA 基线一致",
            )

        score = abs(current - mean) / standard_deviation
        direction = "高于" if current > mean else "低于"
        return DetectionResult(
            score >= self._threshold,
            score,
            f"当前值{direction} EWMA 基线，标准化残差={score:.2f}",
        )
