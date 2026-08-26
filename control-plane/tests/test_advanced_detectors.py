"""阶段二异常检测算法测试。"""

from aiops_control.adapters.ewma_detector import EWMADetector
from aiops_control.adapters.isolation_forest_detector import IsolationForestDetector
from aiops_control.adapters.seasonal_detector import SeasonalBaselineDetector


def test_ewma_detects_sudden_spike() -> None:
    """稳定负载后的突增应得到高标准化残差。"""

    detector = EWMADetector(alpha=0.3, threshold=3.0)
    result = detector.detect([10.0, 10.2, 9.9, 10.1, 10.0, 9.8, 10.2], 80.0)
    assert result.anomalous is True


def test_seasonal_baseline_accepts_expected_value() -> None:
    """当前值符合相同季节位置范围时不应告警。"""

    detector = SeasonalBaselineDetector()
    result = detector.detect([100.0, 101.0, 99.0, 100.5, 99.5], 100.2)
    assert result.anomalous is False


def test_isolation_forest_scores_far_outlier_higher() -> None:
    """远离历史分布的点应比正常点获得更高隔离分数。"""

    history = [10.0 + ((index % 7) - 3) * 0.1 for index in range(80)]
    detector = IsolationForestDetector(tree_count=64, threshold=0.57, seed=7)
    normal = detector.detect(history, 10.1)
    outlier = detector.detect(history, 80.0)
    assert outlier.score > normal.score
    assert outlier.anomalous is True
