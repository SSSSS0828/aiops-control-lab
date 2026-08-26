"""发布变更风险的可解释规则基线。"""

from aiops_control.domain.sre import ChangeRiskAssessment, ChangeRiskInput


class ChangeRiskService:
    """组合爆炸半径、近期故障、范围和回滚准备度。"""

    def assess(self, change: ChangeRiskInput) -> ChangeRiskAssessment:
        """返回 0..1 风险分数和可读原因。"""

        if not 0 <= change.blast_radius <= 1:
            raise ValueError("爆炸半径必须位于 0..1")
        if not 0 <= change.recent_incident_rate <= 1:
            raise ValueError("近期故障率必须位于 0..1")
        if change.changed_components < 1:
            raise ValueError("变更组件数必须为正")

        scope_score = min(change.changed_components / 10, 1.0)
        rollback_score = 0.0 if change.rollback_ready else 1.0
        score = (
            0.35 * change.blast_radius
            + 0.25 * change.recent_incident_rate
            + 0.20 * scope_score
            + 0.20 * rollback_score
        )
        reasons: list[str] = []
        if change.blast_radius >= 0.6:
            reasons.append("变更影响范围较大")
        if change.recent_incident_rate >= 0.4:
            reasons.append("相关服务近期故障率较高")
        if change.changed_components >= 5:
            reasons.append("单次变更涉及多个组件")
        if not change.rollback_ready:
            reasons.append("缺少已验证回滚方案")
        if not reasons:
            reasons.append("未发现显著风险特征")
        level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
        return ChangeRiskAssessment(score=score, level=level, reasons=tuple(reasons))
