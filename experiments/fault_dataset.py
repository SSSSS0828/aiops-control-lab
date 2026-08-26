"""生成带真值的轻量时序故障数据集并导出 Parquet。

在线检测器对比继续使用单指标 CPU 序列；Parquet 真值集额外覆盖 CPU、依赖退出、
API 退出、请求延迟和 HTTP 5xx 五类故障。固定随机种子保证评测可复现。
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random


@dataclass(frozen=True, slots=True)
class FaultSample:
    """一个带时间、指标、真值和场景标签的实验样本。"""

    timestamp: str
    asset_id: str
    metric_name: str
    value: float
    anomalous: bool
    scenario: str
    root_cause_asset: str
    injection_kind: str


@dataclass(frozen=True, slots=True)
class ScenarioSeries:
    """生成一条故障指标序列所需的稳定配置。"""

    id: str
    asset_id: str
    metric_name: str
    normal_value: float
    fault_value: float
    noise_standard_deviation: float
    root_cause_asset: str
    injection_kind: str


SCENARIO_SERIES: tuple[ScenarioSeries, ...] = (
    ScenarioSeries(
        "container_cpu_spike",
        "lab-api",
        "container_cpu_percent",
        20.0,
        85.0,
        0.8,
        "lab-api",
        "application_control",
    ),
    ScenarioSeries(
        "dependency_unavailable",
        "lab-redis",
        "service_health",
        1.0,
        0.0,
        0.0,
        "lab-redis",
        "container_stop",
    ),
    ScenarioSeries(
        "api_container_exit",
        "lab-api",
        "service_health",
        1.0,
        0.0,
        0.0,
        "lab-api",
        "container_stop",
    ),
    ScenarioSeries(
        "request_latency",
        "lab-api",
        "http_request_duration_seconds",
        0.05,
        2.5,
        0.005,
        "lab-api",
        "application_control",
    ),
    ScenarioSeries(
        "http_5xx",
        "lab-api",
        "http_5xx_rate",
        0.0,
        1.0,
        0.0,
        "lab-api",
        "application_control",
    ),
)


def generate_samples(seed: int = 42, count: int = 720) -> list[FaultSample]:
    """生成十二分钟的一秒级 CPU 序列，并在固定区间注入异常。"""

    random = Random(seed)
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    samples: list[FaultSample] = []
    for index in range(count):
        # 正常基线包含轻微趋势和高斯噪声，避免算法只学习常量序列。
        baseline = 20 + index * 0.003 + random.gauss(0, 0.8)
        in_cpu_fault = 300 <= index < 340
        value = baseline + (65 if in_cpu_fault else 0)
        samples.append(
            FaultSample(
                timestamp=(started_at + timedelta(seconds=index)).isoformat(),
                asset_id="lab-api",
                metric_name="container_cpu_percent",
                value=value,
                anomalous=in_cpu_fault,
                scenario="cpu_spike" if in_cpu_fault else "normal",
                root_cause_asset="lab-api",
                injection_kind="application_control" if in_cpu_fault else "none",
            )
        )
    return samples


def generate_ground_truth_samples(
    seed: int = 42,
    count_per_scenario: int = 180,
) -> list[FaultSample]:
    """为五个在线场景分别生成三分钟一秒级真值序列。"""

    if count_per_scenario < 120:
        raise ValueError("每个场景至少需要 120 个样本，才能保留训练基线和故障窗口")
    random = Random(seed)
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    samples: list[FaultSample] = []
    for series_index, series in enumerate(SCENARIO_SERIES):
        # 故障固定出现在序列后 1/3 区域，前段可作为无标签泄漏的训练基线。
        fault_started = count_per_scenario * 2 // 3
        fault_ended = min(fault_started + 30, count_per_scenario)
        for index in range(count_per_scenario):
            anomalous = fault_started <= index < fault_ended
            center = series.fault_value if anomalous else series.normal_value
            noise = random.gauss(0, series.noise_standard_deviation)
            timestamp_offset = series_index * count_per_scenario + index
            samples.append(
                FaultSample(
                    timestamp=(
                        started_at + timedelta(seconds=timestamp_offset)
                    ).isoformat(),
                    asset_id=series.asset_id,
                    metric_name=series.metric_name,
                    value=center + noise,
                    anomalous=anomalous,
                    scenario=series.id if anomalous else "normal",
                    root_cause_asset=series.root_cause_asset,
                    injection_kind=series.injection_kind if anomalous else "none",
                )
            )
    return samples


def export_parquet(samples: list[FaultSample], output: Path) -> None:
    """使用列式 Parquet 保存真值数据，供 Notebook 和 CI 实验复用。"""

    # PyArrow 只在导出时加载，普通算法评测无需安装重量级实验依赖。
    import pyarrow as pa
    import pyarrow.parquet as pq

    output.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([asdict(sample) for sample in samples])
    pq.write_table(table, output, compression="zstd")


if __name__ == "__main__":
    destination = Path(__file__).parent / "data" / "fault-scenarios-v2.parquet"
    export_parquet(generate_ground_truth_samples(), destination)
    print(f"已生成数据集：{destination}")
