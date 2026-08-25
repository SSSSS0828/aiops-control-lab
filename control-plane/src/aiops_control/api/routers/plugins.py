"""独立进程插件管理与 RPC 路由。"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from aiops_control.api.security import ContainerDependency, require_admin
from aiops_control.domain.errors import DomainError, EntityNotFoundError

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


@router.get("")
async def list_plugins(container: ContainerDependency) -> Any:
    """列出当前已经健康注册的独立进程插件。"""

    if container.plugin_runtime is None:
        return []
    manifests = container.plugin_runtime.list_plugins()
    return jsonable_encoder([asdict(item) for item in manifests])


@router.post("/{plugin_id}/install", dependencies=[Depends(require_admin)])
async def install_plugin(
    plugin_id: str,
    container: ContainerDependency,
) -> Any:
    """从固定插件根目录安装或原子升级指定插件。"""

    if container.plugin_runtime is None or container.plugin_root is None:
        raise EntityNotFoundError("当前环境没有配置插件目录")
    if not plugin_id.replace("-", "").replace("_", "").isalnum():
        raise DomainError("插件 ID 格式无效")
    manifest_path = Path(container.plugin_root) / plugin_id / "plugin.yaml"
    manifest = container.plugin_runtime.install(manifest_path)
    return jsonable_encoder(asdict(manifest))


@router.post("/{plugin_id}/rpc/{method}", dependencies=[Depends(require_admin)])
async def call_plugin(
    plugin_id: str,
    method: str,
    payload: dict[str, Any],
    container: ContainerDependency,
) -> dict[str, Any]:
    """为开发和演示调用插件白名单 RPC。"""

    if container.plugin_runtime is None:
        raise EntityNotFoundError("当前环境没有配置插件运行时")
    try:
        return container.plugin_runtime.call(plugin_id, method, payload)
    except KeyError as error:
        raise EntityNotFoundError(str(error)) from error
    except ValueError as error:
        raise DomainError(str(error)) from error
