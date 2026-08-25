"""FastAPI 应用入口。

本文件只承担应用生命周期、异常映射和 Router 注册。具体业务路由已经按
Incident、实验室、插件、SRE 和集成拆分，避免入口演变成巨型文件。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aiops_control.api.container import build_container
from aiops_control.api.routers import (
    console,
    diagnostics,
    incidents,
    integrations,
    internal_metrics,
    lab,
    monitoring,
    plugins,
    sre,
    telemetry,
)
from aiops_control.domain.errors import DomainError, EntityNotFoundError, ExternalSourceError


def create_app() -> FastAPI:
    """创建具有显式组合根和可测试生命周期的应用实例。"""

    container = build_container()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """确保插件子进程和后台恢复任务随控制面一起结束。"""

        await container.start()
        yield
        await container.close()

    app = FastAPI(
        title="AIOps Control Plane",
        version="0.1.0",
        description="单机热插拔 AIOps 学习项目控制面",
        lifespan=lifespan,
    )
    app.state.container = container
    # 保留阶段一测试和调试使用的直接引用，业务 Router 统一从 container 读取。
    app.state.repository = container.repository
    app.state.incident_service = container.incident_service
    app.state.remediation_service = container.remediation_service
    app.state.plugin_runtime = container.plugin_runtime

    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, error: DomainError) -> JSONResponse:
        """将可预期领域异常映射为稳定 JSON，而不泄露调用栈。"""

        if isinstance(error, EntityNotFoundError):
            status_code = 404
        elif isinstance(error, ExternalSourceError):
            status_code = 502
        else:
            status_code = 409
        return JSONResponse(status_code=status_code, content={"error": str(error)})

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """供容器编排和反向代理调用的轻量健康检查。"""

        return {"status": "ok", "service": "control-plane"}

    app.include_router(incidents.router)
    app.include_router(lab.router)
    app.include_router(plugins.router)
    app.include_router(sre.router)
    app.include_router(integrations.router)
    app.include_router(telemetry.router)
    app.include_router(console.router)
    app.include_router(diagnostics.router)
    app.include_router(monitoring.router)
    app.include_router(internal_metrics.router)
    return app


app = create_app()
