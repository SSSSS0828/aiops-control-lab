"""修复动作执行端口。"""

from dataclasses import dataclass
from typing import Protocol

from aiops_control.domain.models import RemediationStep


@dataclass(frozen=True, slots=True)
class StepExecutionResult:
    """一个修复步骤的执行与验证结果。"""

    succeeded: bool
    message: str


class ActionDispatcher(Protocol):
    """将获批步骤交给 Agent 或安全执行器。"""

    def execute(self, step: RemediationStep, approved_hash: str) -> StepExecutionResult: ...
