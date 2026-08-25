"""SLO 与错误预算计算服务。"""

from aiops_control.domain.sre import ErrorBudgetStatus, SLODefinition


class SLOService:
    """使用请求好事件比例计算错误预算和燃烧速率。"""

    def calculate(
        self,
        definition: SLODefinition,
        good_events: int,
        total_events: int,
    ) -> ErrorBudgetStatus:
        """计算一个统计窗口内的 SLO 状态。"""

        if not 0 < definition.objective < 1:
            raise ValueError("SLO objective 必须位于 (0, 1)")
        if total_events <= 0 or not 0 <= good_events <= total_events:
            raise ValueError("好事件和总事件数量无效")

        bad_events = total_events - good_events
        sli = good_events / total_events
        allowed_bad_events = total_events * (1 - definition.objective)
        consumed_ratio = bad_events / allowed_bad_events
        remaining_ratio = max(1 - consumed_ratio, 0.0)
        # 燃烧速率 1 表示正好按预算允许的速度消耗，超过 1 会提前耗尽预算。
        actual_bad_ratio = bad_events / total_events
        burn_rate = actual_bad_ratio / (1 - definition.objective)
        if burn_rate >= 14.4:
            state = "critical"
        elif burn_rate >= 6:
            state = "fast_burn"
        elif burn_rate > 1:
            state = "over_budget_rate"
        else:
            state = "healthy"
        return ErrorBudgetStatus(
            sli=sli,
            bad_events=bad_events,
            allowed_bad_events=allowed_bad_events,
            remaining_ratio=remaining_ratio,
            burn_rate=burn_rate,
            state=state,
        )
