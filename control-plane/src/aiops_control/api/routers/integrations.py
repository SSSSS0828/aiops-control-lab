"""Git、CI/CD 与发布 Webhook 标准化路由。"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from aiops_control.api.schemas import ChangeEventRequest
from aiops_control.api.security import ContainerDependency, require_admin
from aiops_control.domain.changes import ChangeEvent
from aiops_control.domain.models import new_id

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.post("/events", dependencies=[Depends(require_admin)])
async def ingest_change_event(
    payload: ChangeEventRequest,
    container: ContainerDependency,
) -> Any:
    """接收已经由管理员边界鉴权的标准 Git/CI/CD 变更事件。"""

    event = ChangeEvent(
        id=new_id("change"),
        provider=payload.provider,
        event_type=payload.event_type,
        service=payload.service,
        revision=payload.revision,
        status=payload.status,
        occurred_at=payload.occurred_at,
        attributes=payload.attributes,
    )
    container.repository.save_change_event(event)
    return jsonable_encoder(asdict(event))


@router.get("/events")
async def list_change_events(
    container: ContainerDependency,
    service: str | None = None,
) -> Any:
    """按时间倒序读取全部或指定服务的变更事件。"""

    events = container.repository.list_change_events(service)
    return jsonable_encoder([asdict(event) for event in events])
