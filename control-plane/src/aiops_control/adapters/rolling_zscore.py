"""滚动 Z-Score 异常检测器。

输入：历史观测序列和当前值。
处理：使用历史均值与总体标准差计算当前值偏离程度。
输出：统一 DetectionResult，不直接创建告警或 Incident。
异常：样本不足或零方差时采用显式降级逻辑，不产生除零错误。
"""

from collections.abc import Sequence
from math import fsum, sqrt

from aiops_control.ports.detectors import DetectionResult


class RollingZScoreDetector:
    """适合阶段一在线演示的轻量统计检测器。"""

    def __init__(self, threshold: float = 3.0, minimum_samples: int = 5) -> None:
        if threshold <= 0:
            raise ValueError("阈值必须大于 0")
        if minimum_samples < 2:
            raise ValueError("最少样本数不能小于 2")
        self._threshold = threshold
        self._minimum_samples = minimum_samples

    def detect(self, history: Sequence[float], current: float) -> DetectionResult:
        """判断当前值是否显著偏离历史窗口。

        关键计算逐步展开，便于学习时对应均值、方差和标准分数公式。
        """

        # 样本不足时不猜测异常，防止服务刚启动就产生大量误报。
        if len(history) < self._minimum_samples:
            return DetectionResult(False, 0.0, "历史样本不足，暂不进行异常判断")

        # fsum 比普通 sum 在大量浮点数累加时更稳定。
        mean = fsum(history) / len(history)
        # 逐个计算离均差平方，得到总体方差；历史窗口被视为当前总体基线。
        variance = fsum((value - mean) ** 2 for value in history) / len(history)
        # 标准差恢复到原始量纲，后续才能计算无量纲 Z-Score。
        standard_deviation = sqrt(variance)

        # 当历史值完全相同时标准差为零，任何明显变化都应被视为异常。
        if standard_deviation == 0:
            anomalous = current != mean
            score = float("inf") if anomalous else 0.0
            reason = "稳定基线发生变化" if anomalous else "当前值与稳定基线一致"
            return DetectionResult(anomalous, score, reason)

        # 取绝对值同时识别突增和突降，方向信息由 reason 保留。
        score = abs(current - mean) / standard_deviation
        # 只有达到配置阈值才输出异常，调用方可继续执行告警聚合。
        anomalous = score >= self._threshold
        direction = "高于" if current > mean else "低于"
        reason = f"当前值{direction}历史均值，Z-Score={score:.2f}"
        return DetectionResult(anomalous, score, reason)
