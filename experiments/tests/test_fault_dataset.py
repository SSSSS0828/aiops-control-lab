"""五类 Parquet 真值数据生成规则测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from fault_dataset import generate_ground_truth_samples


def test_ground_truth_dataset_contains_five_faults() -> None:
    """每个注册场景必须有固定数量异常点和明确根因资产。"""

    samples = generate_ground_truth_samples(count_per_scenario=150)
    faults = [sample for sample in samples if sample.anomalous]
    scenario_ids = {sample.scenario for sample in faults}
    assert scenario_ids == {
        "container_cpu_spike",
        "dependency_unavailable",
        "api_container_exit",
        "request_latency",
        "http_5xx",
    }
    assert len(faults) == 5 * 30
    assert all(sample.root_cause_asset.startswith("lab-") for sample in faults)


def test_ground_truth_dataset_rejects_too_short_series() -> None:
    """过短序列不能生成看似有效但缺少训练基线的数据集。"""

    with pytest.raises(ValueError, match="至少需要"):
        generate_ground_truth_samples(count_per_scenario=60)
