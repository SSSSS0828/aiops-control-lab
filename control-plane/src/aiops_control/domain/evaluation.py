"""算法离线评测领域模型。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DetectorMetrics:
    """异常检测器的混淆矩阵和派生指标。"""

    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    false_positive_rate: float


@dataclass(frozen=True, slots=True)
class DetectorEvaluation:
    """一个算法及其参数在固定数据集上的评测结果。"""

    detector_name: str
    dataset_version: str
    metrics: DetectorMetrics
    average_score: float
