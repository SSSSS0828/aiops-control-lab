"""大模型不可用时的确定性诊断回退。"""

from aiops_control.domain.diagnostics import GeneratedDiagnosis


class RuleBasedDiagnosticModel:
    """从证据关键词提取有限但稳定的诊断。"""

    def diagnose(self, question: str, trusted_context: str) -> GeneratedDiagnosis:
        """根据常见故障关键词返回保守建议。"""

        combined = f"{question} {trusted_context}".lower()
        if "redis" in combined or "连接" in combined:
            return GeneratedDiagnosis(
                summary="依赖服务连接异常",
                root_cause="Redis 不可用、连接超时或连接池耗尽",
                recommended_action="先检查 Redis 容器状态和连接数，再执行健康检查",
                confidence=0.55,
            )
        if "cpu" in combined or "负载" in combined:
            return GeneratedDiagnosis(
                summary="计算资源使用异常",
                root_cause="目标进程 CPU 占用突增或容器配额不足",
                recommended_action="检查进程与容器指标，确认影响后再重启实验容器",
                confidence=0.5,
            )
        return GeneratedDiagnosis(
            summary="证据不足，无法确定单一根因",
            root_cause="需要补充指标、日志和最近变更信息",
            recommended_action="保持只读并扩大证据时间窗口",
            confidence=0.2,
        )
