"""RAG 诊断和模型降级状态路由。"""

import asyncio
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from aiops_control.api.schemas import DiagnosticQueryRequest
from aiops_control.api.security import ContainerDependency

router = APIRouter(prefix="/api/v1/diagnostics", tags=["diagnostics"])


@router.get("/status")
async def diagnostic_status(container: ContainerDependency) -> dict[str, Any]:
    """说明当前使用云模型还是规则降级，避免界面误导用户。"""

    return {
        "provider": "openai-compatible" if container.llm_enabled else "rule-based",
        "model": container.llm_model_name if container.llm_enabled else "deterministic-rules",
        "rag": "hybrid-keyword-hashing-embedding",
        "degraded": not container.llm_enabled,
    }


@router.post("/query")
async def query_diagnostics(
    payload: DiagnosticQueryRequest,
    container: ContainerDependency,
) -> Any:
    """用经过长度限制的证据执行 RAG 诊断，不执行任何模型建议。"""

    answer = await asyncio.to_thread(
        container.diagnostic_service.diagnose,
        payload.question,
        payload.evidence,
    )
    return jsonable_encoder(asdict(answer))
