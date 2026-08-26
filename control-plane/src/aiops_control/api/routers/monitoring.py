"""真实节点、资产、拓扑、规则、指标和健康状态只读 API。"""

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from aiops_control.api.security import ContainerDependency
from aiops_control.application.metric_registry import REGISTERED_METRICS

router = APIRouter(prefix="/api/v1", tags=["real-monitoring"])


@router.get("/nodes")
async def list_nodes(container: ContainerDependency) -> Any:
    """返回 Agent 版本、证书身份和最近心跳。"""

    return jsonable_encoder([asdict(item) for item in container.repository.list_agent_nodes()])


@router.get("/assets")
async def list_assets(container: ContainerDependency) -> Any:
    """返回 Agent 实际发现的真实资产。"""

    return jsonable_encoder([asdict(item) for item in container.repository.list_monitored_assets()])


@router.get("/topology")
async def get_topology(container: ContainerDependency) -> Any:
    """返回真实资产节点和带类型、权重的拓扑边。"""

    return jsonable_encoder(
        {
            "nodes": [asdict(item) for item in container.repository.list_monitored_assets()],
            "edges": [asdict(item) for item in container.repository.list_monitored_topology()],
        }
    )


@router.get("/monitoring/rules")
async def list_rules(container: ContainerDependency) -> Any:
    """列出当前启用和停用的确定性规则。"""

    return jsonable_encoder([asdict(item) for item in container.repository.list_monitor_rules()])


@router.get("/monitoring/evaluations")
async def list_evaluations(
    container: ContainerDependency,
    asset_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> Any:
    """返回紧凑评估事实，不复制原始时序。"""

    values = container.repository.list_monitor_evaluations(asset_id=asset_id, limit=limit)
    return jsonable_encoder([asdict(item) for item in values])


@router.get("/monitoring/health")
async def monitoring_health(container: ContainerDependency) -> Any:
    """汇总数据新鲜度、Agent 心跳、固定 HTTP 探针与安全模式。"""

    nodes = container.repository.list_agent_nodes()
    metrics = container.metric_store.list_metrics()
    now = datetime.now(UTC)
    latest = max((item.collected_at for item in metrics), default=None)
    targets = await asyncio.to_thread(container.health_checker.check_all)
    return jsonable_encoder(
        {
            "status": "healthy" if nodes and latest else "waiting_for_agent",
            "real_actions_mode": container.real_actions_mode,
            "node_count": len(nodes),
            "latest_metric_at": latest,
            "metric_lag_seconds": (now - latest).total_seconds() if latest else None,
            "targets": targets,
        }
    )


@router.get("/assets/{asset_id:path}/metrics")
async def get_asset_metrics(
    asset_id: str,
    container: ContainerDependency,
    metric_name: str | None = None,
    minutes: int = Query(default=30, ge=1, le=1440),
) -> Any:
    """查询注册指标；存在 Prometheus 时附带受控历史窗口。"""

    _require_asset(asset_id, container)
    if metric_name is not None and metric_name not in REGISTERED_METRICS:
        raise HTTPException(status_code=400, detail="指标未在控制面注册")
    latest = container.metric_store.list_metrics(asset_id=asset_id, metric_name=metric_name)
    history: list[dict[str, Any]] = []
    if metric_name is not None and container.metric_query is not None:
        # 指标名来自注册表，资产 ID 来自仓储；双引号和反斜线仍显式转义。
        escaped_asset = asset_id.replace("\\", "\\\\").replace('"', '\\"')
        query = f'{metric_name}{{asset_id="{escaped_asset}"}}'
        ended_at = datetime.now(UTC)
        samples = await asyncio.to_thread(
            container.metric_query.query_range,
            query,
            ended_at - timedelta(minutes=minutes),
            ended_at,
            15,
        )
        history = [asdict(item) for item in samples]
    return jsonable_encoder(
        {
            "asset_id": asset_id,
            "definitions": [asdict(REGISTERED_METRICS[item.name]) for item in latest],
            "latest": [asdict(item) for item in latest],
            "history": history,
        }
    )


@router.get("/assets/{asset_id:path}/incidents")
async def get_asset_incidents(asset_id: str, container: ContainerDependency) -> Any:
    """按真实资产返回相关 Incident。"""

    _require_asset(asset_id, container)
    incidents = [
        asdict(item) for item in container.repository.list_incidents() if item.asset_id == asset_id
    ]
    return jsonable_encoder(incidents)


@router.get("/assets/{asset_id:path}")
async def get_asset(asset_id: str, container: ContainerDependency) -> Any:
    """返回单个真实资产详情。"""

    return jsonable_encoder(asdict(_require_asset(asset_id, container)))


def _require_asset(asset_id: str, container: ContainerDependency) -> Any:
    asset = container.repository.get_monitored_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="真实资产不存在")
    return asset
