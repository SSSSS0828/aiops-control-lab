"""Incident、信号、计划、审批和实时事件路由。"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from aiops_control.api.schemas import ApprovalRequest, SignalEvaluationRequest
from aiops_control.api.security import ContainerDependency, is_admin
from aiops_control.domain.errors import EntityNotFoundError
from aiops_control.domain.models import Signal

router = APIRouter(prefix="/api/v1", tags=["incidents"])


@router.get("/incidents")
async def list_incidents(container: ContainerDependency) -> Any:
    """返回按时间倒序排列的 Incident。"""

    incidents = container.repository.list_incidents()
    return jsonable_encoder([asdict(item) for item in incidents])


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: str,
    container: ContainerDependency,
) -> Any:
    """读取计划及浏览器审批时必须提交的内容哈希。"""

    plan = container.repository.get_plan(plan_id)
    if plan is None:
        raise EntityNotFoundError(f"修复计划 {plan_id} 不存在")
    payload = asdict(plan)
    payload["content_hash"] = plan.content_hash()
    return jsonable_encoder(payload)


@router.post("/signals/evaluate")
async def evaluate_signal(
    payload: SignalEvaluationRequest,
    container: ContainerDependency,
) -> Any:
    """检测一个指标点，异常时自动建立待审批处置上下文。"""

    signal = Signal(
        asset_id=payload.asset_id,
        name=payload.metric_name,
        value=payload.current,
        occurred_at=payload.occurred_at or datetime.now(UTC),
    )
    outcome = container.incident_service.evaluate_signal(signal, payload.history)
    return jsonable_encoder(asdict(outcome))


@router.post("/plans/{plan_id}/approve")
async def approve_plan(
    plan_id: str,
    payload: ApprovalRequest,
    request: Request,
    container: ContainerDependency,
) -> Any:
    """批准并执行一份内容未被篡改的修复计划。"""

    plan = container.repository.get_plan(plan_id)
    if plan is None:
        raise EntityNotFoundError(f"修复计划 {plan_id} 不存在")
    real_targets = any(
        step.target.startswith(("host/", "docker/devops-lab/")) for step in plan.steps
    )
    if real_targets and container.real_actions_mode == "observe_only":
        raise HTTPException(status_code=403, detail="真实资产当前为只观察模式，禁止执行变更")
    # 公网访客只能操作实验资源，真实目标必须先通过管理员身份校验。
    if any(not step.target.startswith("lab-") for step in plan.steps) and not is_admin(
        request, container
    ):
        raise HTTPException(status_code=403, detail="访客只能批准实验室修复计划")
    action_run = container.remediation_service.approve_and_execute(
        plan_id=plan_id,
        approver=payload.approver,
        approved_hash=payload.approved_hash,
        idempotency_key=payload.idempotency_key,
    )
    return jsonable_encoder(asdict(action_run))


@router.get("/stream")
async def stream_incidents(container: ContainerDependency) -> StreamingResponse:
    """通过 SSE 周期推送 Incident 快照，阶段一不引入额外消息队列。"""

    async def event_generator() -> AsyncIterator[str]:
        # 每次事件都携带完整轻量快照，断线重连无需恢复复杂游标。
        while True:
            incidents = jsonable_encoder(
                [asdict(item) for item in container.repository.list_incidents()]
            )
            yield f"event: incidents\ndata: {json.dumps(incidents, ensure_ascii=False)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
