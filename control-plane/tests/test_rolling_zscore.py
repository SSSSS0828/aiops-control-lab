"""滚动 Z-Score 检测器单元测试。"""

from aiops_control.adapters.rolling_zscore import RollingZScoreDetector


def test_sample_shortage_does_not_raise_alert() -> None:
    """历史样本不足时应选择保守降级而不是误报。"""

    detector = RollingZScoreDetector(minimum_samples=5)
    result = detector.detect([1.0, 1.1], 10.0)
    assert result.anomalous is False


def test_stable_baseline_change_is_anomaly() -> None:
    """零方差基线发生变化时不能被除零逻辑漏报。"""

    detector = RollingZScoreDetector(minimum_samples=5)
    result = detector.detect([10.0] * 6, 98.0)
    assert result.anomalous is True
    assert result.score == float("inf")


def test_normal_value_is_not_anomaly() -> None:
    """正常波动不应超过检测阈值。"""

    detector = RollingZScoreDetector(minimum_samples=5)
    result = detector.detect([9.8, 10.0, 10.2, 9.9, 10.1], 10.0)
    assert result.anomalous is False
