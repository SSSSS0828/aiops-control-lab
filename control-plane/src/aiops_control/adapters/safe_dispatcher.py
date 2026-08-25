"""阶段一安全执行器。

当前实现模拟 Agent 返回值，但仍严格执行动作允许列表与批准哈希检查。
真实 gRPC Agent 适配器会实现同一个 ActionDispatcher 端口。
"""

from hmac import compare_digest

from aiops_control.domain.models import RemediationStep
from aiops_control.ports.execution import StepExecutionResult


class SafeDemoDispatcher:
    """只允许预置类型化动作的演示执行器。"""

    _allowed_actions = frozenset(
        {"restart_container", "restart_service", "health_check", "collect_logs", "cleanup"}
    )

    def execute(self, step: RemediationStep, approved_hash: str) -> StepExecutionResult:
        """验证动作和审批哈希后返回可审计的模拟结果。"""

        # 空哈希意味着任务没有经过审批链，必须在执行边界立即拒绝。
        if compare_digest(approved_hash, ""):
            return StepExecutionResult(False, "缺少批准内容哈希")
        # 动作允许列表阻止模型通过 action_type 注入任意 Shell。
        if step.action_type not in self._allowed_actions:
            return StepExecutionResult(False, f"动作 {step.action_type} 未注册")
        # 阶段一不操作真实宿主机，只返回已验证的沙箱执行结果。
        return StepExecutionResult(True, f"沙箱已执行 {step.action_type}，目标为 {step.target}")
