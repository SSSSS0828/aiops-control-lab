"""故障实验室的五类真值场景定义。

输入：访客提交的稳定场景 ID。
处理：从不可变目录读取资产、指标、基线、真实根因和注入方式。
输出：应用层可直接生成 Signal，评测层可导出 ground truth 的场景对象。
副作用：无；本模块不执行任何故障操作，也不依赖 FastAPI。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FaultScenario:
    """一个可重复故障的输入特征、根因和期望修复。"""

    id: str
    title: str
    asset_id: str
    metric_name: str
    current_value: float
    baseline: tuple[float, ...]
    root_cause_asset: str
    root_cause: str
    injection_kind: str
    expected_remediation: str


# 真值目录是代码评审边界：只有这里注册的场景才能从公网实验入口触发。
FAULT_SCENARIOS: tuple[FaultScenario, ...] = (
    FaultScenario(
        id="container_cpu_spike",
        title="API 容器 CPU 突增",
        asset_id="lab-api",
        metric_name="container_cpu_percent",
        current_value=98.0,
        baseline=(10.0, 10.2, 9.8, 10.1, 9.9, 10.0),
        root_cause_asset="lab-api",
        root_cause="实验 API 内的限时计算负载",
        injection_kind="application_control",
        expected_remediation="重启 lab-api 并验证容器运行状态",
    ),
    FaultScenario(
        id="dependency_unavailable",
        title="Redis 依赖不可用",
        asset_id="lab-redis",
        metric_name="service_health",
        current_value=0.0,
        baseline=(1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        root_cause_asset="lab-redis",
        root_cause="Agent 停止 Redis 实验容器",
        injection_kind="container_stop",
        expected_remediation="重启 lab-redis 并验证容器运行状态",
    ),
    FaultScenario(
        id="api_container_exit",
        title="API 容器退出",
        asset_id="lab-api",
        metric_name="service_health",
        current_value=0.0,
        baseline=(1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        root_cause_asset="lab-api",
        root_cause="Agent 停止 API 实验容器",
        injection_kind="container_stop",
        expected_remediation="重启 lab-api 并验证容器运行状态",
    ),
    FaultScenario(
        id="request_latency",
        title="API 请求延迟",
        asset_id="lab-api",
        metric_name="http_request_duration_seconds",
        current_value=2.5,
        baseline=(0.05, 0.06, 0.04, 0.05, 0.05, 0.06),
        root_cause_asset="lab-api",
        root_cause="实验 API 注入固定响应等待",
        injection_kind="application_control",
        expected_remediation="重启 lab-api 清除故障状态并验证容器",
    ),
    FaultScenario(
        id="http_5xx",
        title="API 持续返回 HTTP 5xx",
        asset_id="lab-api",
        metric_name="http_5xx_rate",
        current_value=1.0,
        baseline=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        root_cause_asset="lab-api",
        root_cause="实验 API 注入受控 503 响应",
        injection_kind="application_control",
        expected_remediation="重启 lab-api 清除故障状态并验证容器",
    ),
)


def get_fault_scenario(scenario_id: str) -> FaultScenario | None:
    """按稳定 ID 查找场景；未知值返回 None，调用方必须显式拒绝。"""

    return next((scenario for scenario in FAULT_SCENARIOS if scenario.id == scenario_id), None)
