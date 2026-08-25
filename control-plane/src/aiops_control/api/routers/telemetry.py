"""真实遥测证据查询路由。

路由只转换 HTTP 输入输出；查询边界、摘要和 Incident 更新由应用服务负责。
管理员接口在明文公网模式下由统一安全依赖关闭。
"""

import asyncio
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from aiops_control.api.schemas import LogEvidenceRequest, MetricEvidenceRequest
from aiops_control.api.security import ContainerDependency, require_admin

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["telemetry-evidence"],
    dependencies=[Depends(require_admin)],
)


@router.post("/{incident_id}/evidence/metrics")
async def attach_metric_evidence(
    incident_id: str,
    payload: MetricEvidenceRequest,
    container: ContainerDependency,
) -> Any:
    """查询 Prometheus，并把紧凑证据引用附加到 Incident。"""

    evidence = await asyncio.to_thread(
        container.evidence_service.attach_metric_evidence,
        incident_id,
        payload.query,
        payload.started_at,
        payload.ended_at,
        payload.step_seconds,
    )
    return jsonable_encoder(asdict(evidence))


@router.post("/{incident_id}/evidence/logs")
async def attach_log_evidence(
    incident_id: str,
    payload: LogEvidenceRequest,
    container: ContainerDependency,
) -> Any:
    """查询 Loki，并把无原文的日志摘要附加到 Incident。"""

    evidence = await asyncio.to_thread(
        container.evidence_service.attach_log_evidence,
        incident_id,
        payload.query,
        payload.started_at,
        payload.ended_at,
        payload.limit,
    )
    return jsonable_encoder(asdict(evidence))
