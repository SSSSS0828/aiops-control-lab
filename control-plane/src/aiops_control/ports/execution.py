"""修复动作执行端口。"""

from dataclasses import dataclass
from typing import Any, Protocol

from aiops_control.domain.models import RemediationStep


@dataclass(frozen=True, slots=True)
class StepExecutionResult:
    """一个修复步骤的执行与验证结果。"""

    succeeded: bool
    message: str


class ActionDispatcher(Protocol):
    """将获批步骤交给 Agent 或安全执行器。"""

    def execute(self, step: RemediationStep, approved_hash: str) -> StepExecutionResult: ...


class RecoveryVerifier(Protocol):
    """在动作执行完成后，从业务健康端点验证依赖是否真正恢复。"""

    def verify(self, target: str) -> dict[str, Any]: ...
