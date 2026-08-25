"""HTTP 管理员身份与访客权限边界。"""

from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from aiops_control.api.container import ApplicationContainer


def get_container(request: Request) -> ApplicationContainer:
    """从应用状态读取显式依赖容器。"""

    container: ApplicationContainer = request.app.state.container
    return container


# Annotated 依赖别名避免每个 Router 使用函数调用作为默认参数。
ContainerDependency = Annotated[ApplicationContainer, Depends(get_container)]


def is_admin(request: Request, container: ApplicationContainer) -> bool:
    """使用恒定时间比较检查管理员 Bearer Token。"""

    if not container.admin_token:
        return False
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    supplied = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
    return compare_digest(supplied, container.admin_token)


def require_admin(request: Request) -> None:
    """保护插件和外部事件等会改变配置或证据的接口。"""

    container = get_container(request)
    # HTTP 公网演示只开放访客沙箱；即使请求者知道令牌，也不能调用管理写接口。
    # 这样可以从服务端消除误传明文 Bearer Token 的可能，而不是只依赖文档提醒。
    if not container.admin_actions_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前公网 HTTP 模式已关闭管理员写接口",
        )
    if not container.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="管理员接口尚未配置令牌",
        )
    if not is_admin(request, container):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要管理员令牌",
        )
