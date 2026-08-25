"""真实资产动作模式与类型化允许列表策略。

策略位于应用层安全边界，HTTP、AI 工具规划和未来队列消费者都必须经过同一判断，避免
只在页面按钮上禁用造成绕过。观察模式拒绝所有真实动作；approval_only 首门只允许只读动作。
"""

from aiops_control.domain.errors import IntegrityViolationError
from aiops_control.domain.models import RemediationPlan

REAL_ASSET_PREFIXES = ("host/", "docker/devops-lab/")
FIRST_GATE_READ_ONLY_ACTIONS = {"health_check", "collect_logs", "inspect_container"}


class RealActionPolicy:
    """校验真实资产计划是否符合当前人工门禁阶段。"""

    def __init__(self, mode: str) -> None:
        self._mode = mode

    def validate(self, plan: RemediationPlan) -> None:
        """在保存 Approval 前完成全计划校验，禁止部分步骤先执行。"""

        real_steps = [step for step in plan.steps if step.target.startswith(REAL_ASSET_PREFIXES)]
        if not real_steps:
            return
        if self._mode == "observe_only":
            raise IntegrityViolationError("真实资产当前为只观察模式，禁止执行变更")
        denied = [
            step.action_type
            for step in real_steps
            if step.action_type not in FIRST_GATE_READ_ONLY_ACTIONS
        ]
        if denied:
            raise IntegrityViolationError(
                f"真实资产首道门禁只允许只读动作，拒绝：{', '.join(sorted(set(denied)))}"
            )
