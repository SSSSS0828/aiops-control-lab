"""多页面控制台所需的只读聚合路由。"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from aiops_control.api.security import ContainerDependency

router = APIRouter(prefix="/api/v1/console", tags=["console"])


@router.get("/overview")
async def get_overview(container: ContainerDependency) -> Any:
    """返回首页统计，避免浏览器并发拼接多个仓储快照。"""

    plugin_count = len(container.plugin_runtime.list_plugins()) if container.plugin_runtime else 0
    return jsonable_encoder(asdict(container.console_service.overview(plugin_count)))


@router.get("/assets")
async def list_assets(container: ContainerDependency) -> Any:
    """列出当前受控节点、Agent 和实验服务资产。"""

    return jsonable_encoder([asdict(item) for item in container.console_service.assets()])


@router.get("/topology")
async def get_topology(container: ContainerDependency) -> Any:
    """返回服务节点和依赖方向。"""

    return jsonable_encoder(container.console_service.topology())


@router.get("/incident-contexts")
async def list_incident_contexts(container: ContainerDependency) -> Any:
    """返回审批中心所需的事件、计划和执行关联视图。"""

    return jsonable_encoder(container.console_service.incident_contexts())


@router.get("/executions")
async def list_executions(container: ContainerDependency) -> Any:
    """返回按时间倒序排列的动作执行审计记录。"""

    return jsonable_encoder([asdict(item) for item in container.repository.list_action_runs()])


@router.get("/capabilities")
async def list_capabilities(container: ContainerDependency) -> Any:
    """展示真实启用状态、降级能力和仅离线实验的算法。"""

    capabilities = container.console_service.capabilities(
        llm_enabled=container.llm_enabled,
        loki_enabled=container.loki_enabled,
    )
    return jsonable_encoder([asdict(item) for item in capabilities])


@router.get("/settings")
async def get_safe_settings(container: ContainerDependency) -> dict[str, Any]:
    """只返回无密钥的运行边界，前端永远无法读取服务端凭据。"""

    return {
        "access_mode": container.access_mode,
        "admin_actions_enabled": container.admin_actions_enabled,
        "trust_proxy_client_ip": container.trust_proxy_client_ip,
        "prometheus_enabled": container.prometheus_enabled,
        "loki_enabled": container.loki_enabled,
        "llm_enabled": container.llm_enabled,
        "plugin_runtime_enabled": container.plugin_runtime is not None,
        "real_actions_mode": container.real_actions_mode,
        "agent_grpc_enabled": container.agent_gateway is not None,
        "secrets_exposed": False,
    }
