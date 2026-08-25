"""检测器评测指标测试。"""

from aiops_control.application.evaluation_service import DetectorEvaluationService
from aiops_control.ports.detectors import DetectionResult


class ThresholdDetector:
    """大于 10 即异常的确定性测试检测器。"""

    def detect(self, history: list[float], current: float) -> DetectionResult:
        del history
        return DetectionResult(current > 10, current / 10, "测试阈值")


def test_evaluation_computes_confusion_metrics_without_future_leakage() -> None:
    """已知预测序列应得到精确率和召回率 1。"""

    evaluation = DetectorEvaluationService().evaluate(
        detector_name="threshold",
        detector=ThresholdDetector(),
        values=[1, 1, 1, 12, 2, 15],
        labels=[False, False, False, True, False, True],
        history_size=2,
        dataset_version="test-v1",
    )
    assert evaluation.metrics.precision == 1.0
    assert evaluation.metrics.recall == 1.0
    assert evaluation.metrics.false_positive_rate == 0.0
