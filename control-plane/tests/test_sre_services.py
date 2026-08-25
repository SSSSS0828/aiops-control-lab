"""SLO、容量与变更风险服务测试。"""

from datetime import UTC, datetime, timedelta

from aiops_control.application.capacity_forecast_service import CapacityForecastService
from aiops_control.application.change_risk_service import ChangeRiskService
from aiops_control.application.slo_service import SLOService
from aiops_control.domain.sre import CapacityPoint, ChangeRiskInput, SLODefinition


def test_fast_error_budget_burn_is_reported() -> None:
    """99.9% SLO 出现 2% 错误时应识别为快速燃烧。"""

    status = SLOService().calculate(SLODefinition("slo-api", "API 可用性", 0.999, 30), 980, 1000)
    assert status.burn_rate > 14.4
    assert status.state == "critical"


def test_capacity_forecast_estimates_threshold_time() -> None:
    """每小时增长 10 的序列应在第四小时达到 50。"""

    now = datetime.now(UTC)
    points = [CapacityPoint(now + timedelta(hours=index), 10.0 + index * 10) for index in range(4)]
    forecast = CapacityForecastService().forecast(points, threshold=50.0)
    assert forecast.slope_per_hour == 10.0
    assert forecast.estimated_exhaustion_at == now + timedelta(hours=4)
    assert forecast.r_squared == 1.0


def test_change_without_rollback_has_explainable_high_risk() -> None:
    """大范围、多组件且不可回滚的变更应获得高风险。"""

    assessment = ChangeRiskService().assess(
        ChangeRiskInput(
            blast_radius=0.9,
            recent_incident_rate=0.6,
            changed_components=8,
            rollback_ready=False,
        )
    )
    assert assessment.level == "high"
    assert "缺少已验证回滚方案" in assessment.reasons
