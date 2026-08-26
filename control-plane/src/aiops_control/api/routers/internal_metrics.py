"""仅供 Prometheus 抓取的 Agent 最新指标端点。"""

from fastapi import APIRouter, Response

from aiops_control.api.security import ContainerDependency

router = APIRouter(tags=["internal-metrics"])


@router.get("/internal/metrics/agent", include_in_schema=False)
async def agent_metrics(container: ContainerDependency) -> Response:
    """返回 Prometheus 文本格式；入口不包含写操作或高基数字段。"""

    return Response(
        content=container.metric_store.prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
