"""大模型诊断端口。"""

from typing import Protocol

from aiops_control.domain.diagnostics import GeneratedDiagnosis


class DiagnosticLanguageModel(Protocol):
    """将已筛选证据转换为结构化诊断，不具备执行系统动作的能力。"""

    def diagnose(self, question: str, trusted_context: str) -> GeneratedDiagnosis: ...
