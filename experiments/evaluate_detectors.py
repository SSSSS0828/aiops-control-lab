"""在同一带真值数据集上比较阶段一和阶段二检测器。"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "control-plane" / "src"))

from aiops_control.adapters.ewma_detector import EWMADetector
from aiops_control.adapters.isolation_forest_detector import (
    IsolationForestDetector,
)
from aiops_control.adapters.rolling_zscore import RollingZScoreDetector
from aiops_control.application.evaluation_service import (
    DetectorEvaluationService,
)
from fault_dataset import generate_samples


def main() -> None:
    """运行算法对比并写出稳定 JSON 报告。"""

    samples = generate_samples()
    values = [sample.value for sample in samples]
    labels = [sample.anomalous for sample in samples]
    detectors = {
        "rolling_zscore": RollingZScoreDetector(threshold=3.0),
        "ewma": EWMADetector(alpha=0.25, threshold=3.0),
        "isolation_forest": IsolationForestDetector(seed=42),
    }
    evaluator = DetectorEvaluationService()
    results = [
        evaluator.evaluate(name, detector, values, labels, 60, "fault-series-v1")
        for name, detector in detectors.items()
    ]
    output = Path(__file__).parent / "results" / "detector-comparison-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"评测结果已写入：{output}")


if __name__ == "__main__":
    main()
