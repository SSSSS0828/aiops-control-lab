"""访客故障实验室路由。"""

import asyncio
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder

from aiops_control.api.client_identity import visitor_identity
from aiops_control.api.container import ApplicationContainer
from aiops_control.api.schemas import LabInjectionRequest
from aiops_control.api.security import ContainerDependency
from aiops_control.domain.fault_scenarios import (
    FAULT_SCENARIOS,
    LabObservation,
    get_fault_scenario,
)
from aiops_control.domain.models import Signal

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/labs", tags=["fault-lab"])


@router.get("/scenarios")
async def list_lab_scenarios() -> Any:
    """返回公开真值目录，便于界面和评测使用同一份场景定义。"""

    return jsonable_encoder([asdict(scenario) for scenario in FAULT_SCENARIOS])


@router.post("/inject")
async def inject_lab_fault(
    payload: LabInjectionRequest,
    request: Request,
    container: ContainerDependency,
) -> Any:
    """按访客限流并注入确定性实验故障。"""

    visitor_key = visitor_identity(request, container.trust_proxy_client_ip)
    if not container.lab_rate_limiter.allow(visitor_key):
        raise HTTPException(status_code=429, detail="故障注入过于频繁，请稍后再试")

    scenario = get_fault_scenario(payload.scenario)
    if scenario is None:
        raise HTTPException(status_code=422, detail="故障场景未注册")

    observation = LabObservation(
        source="scenario-fixture",
        target=scenario.asset_id,
        healthy=scenario.current_value > 0,
        status_code=0,
        latency_ms=0,
        observed_at=datetime.now(UTC),
    )
    if container.fault_injector is not None:
        target = await asyncio.to_thread(container.fault_injector.inject, payload.scenario)
        if target is not None:
            _schedule_reset(container, target)
        if payload.scenario == "dependency_unavailable" and container.lab_health_probe is not None:
            observation = await asyncio.to_thread(container.lab_health_probe.observe_failure)
            if observation.healthy:
                if target is not None:
                    await asyncio.to_thread(container.fault_injector.reset, target)
                raise HTTPException(status_code=502, detail="Redis 停止后 API 健康探针仍然正常")
    current_value = _observed_value(scenario.metric_name, scenario.current_value, observation)
    signal = Signal(
        scenario.asset_id,
        scenario.metric_name,
        current_value,
        observation.observed_at,
    )
    outcome = container.incident_service.evaluate_signal(signal, scenario.baseline)
    response = asdict(outcome)
    # ground_truth 与算法输出并列返回，离线评测无需从标题反推真实根因。
    response["ground_truth"] = asdict(scenario)
    response["observation"] = asdict(observation)
    return jsonable_encoder(response)


def _observed_value(metric_name: str, fallback: float, observation: LabObservation) -> float:
    """将真实健康探测转换为检测器使用的标准化指标值。"""

    if observation.source == "scenario-fixture":
        return fallback
    if metric_name == "service_health":
        return 1.0 if observation.healthy else 0.0
    if metric_name == "http_5xx_rate":
        return 0.0 if observation.healthy else 1.0
    if metric_name == "http_request_duration_seconds":
        return observation.latency_ms / 1_000
    return fallback


def _schedule_reset(container: ApplicationContainer, target: str) -> None:
    """登记两分钟后的实验资产自动恢复任务。"""

    async def reset_after_timeout() -> None:
        await asyncio.sleep(120)
        try:
            if container.fault_injector is not None:
                await asyncio.to_thread(container.fault_injector.reset, target)
        except Exception:  # noqa: BLE001 - 后台恢复失败必须记录但不能结束 API
            LOGGER.exception("实验资产自动恢复失败", extra={"target": target})

    task = asyncio.create_task(reset_after_timeout())
    container.background_tasks.add(task)
    task.add_done_callback(container.background_tasks.discard)
