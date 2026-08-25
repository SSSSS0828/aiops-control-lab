"""异常检测器离线评测服务。

评测按时间顺序只使用当前样本之前的窗口，防止未来数据泄漏到模型基线。
"""

from collections.abc import Sequence

from aiops_control.domain.evaluation import DetectorEvaluation, DetectorMetrics
from aiops_control.ports.detectors import AnomalyDetector


class DetectorEvaluationService:
    """在同一标注序列上统一计算检测指标。"""

    def evaluate(
        self,
        detector_name: str,
        detector: AnomalyDetector,
        values: Sequence[float],
        labels: Sequence[bool],
        history_size: int,
        dataset_version: str,
    ) -> DetectorEvaluation:
        """执行滚动窗口评测并返回混淆矩阵。"""

        if len(values) != len(labels):
            raise ValueError("观测值和标签数量必须一致")
        if history_size < 2 or len(values) <= history_size:
            raise ValueError("历史窗口无效或数据量不足")

        true_positive = false_positive = true_negative = false_negative = 0
        scores: list[float] = []
        for index in range(history_size, len(values)):
            # 历史窗口严格截止在当前索引之前，保证离线结果可代表在线行为。
            history = values[index - history_size : index]
            result = detector.detect(history, values[index])
            truth = labels[index]
            if result.score != float("inf"):
                scores.append(result.score)
            if result.anomalous and truth:
                true_positive += 1
            elif result.anomalous and not truth:
                false_positive += 1
            elif not result.anomalous and truth:
                false_negative += 1
            else:
                true_negative += 1

        precision = true_positive / max(true_positive + false_positive, 1)
        recall = true_positive / max(true_positive + false_negative, 1)
        false_positive_rate = false_positive / max(false_positive + true_negative, 1)
        metrics = DetectorMetrics(
            true_positive=true_positive,
            false_positive=false_positive,
            true_negative=true_negative,
            false_negative=false_negative,
            precision=precision,
            recall=recall,
            false_positive_rate=false_positive_rate,
        )
        return DetectorEvaluation(
            detector_name=detector_name,
            dataset_version=dataset_version,
            metrics=metrics,
            average_score=sum(scores) / max(len(scores), 1),
        )
