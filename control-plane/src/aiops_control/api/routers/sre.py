"""SLO、容量预测和变更风险路由。"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from aiops_control.api.schemas import (
    CapacityForecastRequest,
    ChangeRiskRequest,
    SLOEvaluationRequest,
)
from aiops_control.application.capacity_forecast_service import CapacityForecastService
from aiops_control.application.change_risk_service import ChangeRiskService
from aiops_control.application.slo_service import SLOService
from aiops_control.domain.sre import CapacityPoint, ChangeRiskInput, SLODefinition

router = APIRouter(prefix="/api/v1/sre", tags=["sre"])


@router.post("/slo/evaluate")
async def evaluate_slo(payload: SLOEvaluationRequest) -> Any:
    """计算 SLI、剩余错误预算与燃烧速率。"""

    definition = SLODefinition("api-request", payload.name, payload.objective, payload.window_days)
    status = SLOService().calculate(definition, payload.good_events, payload.total_events)
    return jsonable_encoder(asdict(status))


@router.post("/capacity/forecast")
async def forecast_capacity(payload: CapacityForecastRequest) -> Any:
    """使用线性趋势估计容量阈值时间。"""

    points = [CapacityPoint(item.occurred_at, item.value) for item in payload.points]
    forecast = CapacityForecastService().forecast(points, payload.threshold)
    return jsonable_encoder(asdict(forecast))


@router.post("/changes/assess")
async def assess_change(payload: ChangeRiskRequest) -> Any:
    """计算发布变更风险及分项解释。"""

    assessment = ChangeRiskService().assess(
        ChangeRiskInput(
            payload.blast_radius,
            payload.recent_incident_rate,
            payload.changed_components,
            payload.rollback_ready,
        )
    )
    return jsonable_encoder(asdict(assessment))
