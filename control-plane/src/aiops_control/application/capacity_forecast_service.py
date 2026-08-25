"""基于最小二乘线性趋势的容量预测服务。"""

from datetime import timedelta
from math import fsum

from aiops_control.domain.sre import CapacityForecast, CapacityPoint


class CapacityForecastService:
    """预测磁盘、内存或连接数何时达到配置阈值。"""

    def forecast(
        self,
        points: list[CapacityPoint],
        threshold: float,
    ) -> CapacityForecast:
        """拟合时间趋势并估计阈值到达时间。"""

        if len(points) < 3:
            raise ValueError("容量预测至少需要三个观测点")
        ordered = sorted(points, key=lambda item: item.occurred_at)
        origin = ordered[0].occurred_at
        # 使用小时为自变量，使斜率可直接解释为“每小时增长量”。
        x_values = [(item.occurred_at - origin).total_seconds() / 3600 for item in ordered]
        y_values = [item.value for item in ordered]
        x_mean = fsum(x_values) / len(x_values)
        y_mean = fsum(y_values) / len(y_values)
        denominator = fsum((value - x_mean) ** 2 for value in x_values)
        if denominator == 0:
            raise ValueError("容量观测时间不能全部相同")
        slope = (
            fsum(
                (x_value - x_mean) * (y_value - y_mean)
                for x_value, y_value in zip(x_values, y_values, strict=True)
            )
            / denominator
        )
        intercept = y_mean - slope * x_mean
        predictions = [intercept + slope * value for value in x_values]
        residual_sum = fsum(
            (actual - predicted) ** 2
            for actual, predicted in zip(y_values, predictions, strict=True)
        )
        total_sum = fsum((value - y_mean) ** 2 for value in y_values)
        r_squared = 1 - residual_sum / total_sum if total_sum > 0 else 1.0

        latest = ordered[-1]
        if latest.value >= threshold:
            exhaustion_at = latest.occurred_at
            state = "exhausted"
        elif slope <= 0:
            exhaustion_at = None
            state = "stable"
        else:
            threshold_hour = (threshold - intercept) / slope
            exhaustion_at = origin + timedelta(hours=threshold_hour)
            state = "forecast" if r_squared >= 0.6 else "low_confidence"
        return CapacityForecast(
            slope_per_hour=slope,
            r_squared=max(min(r_squared, 1.0), 0.0),
            threshold=threshold,
            estimated_exhaustion_at=exhaustion_at,
            state=state,
        )
