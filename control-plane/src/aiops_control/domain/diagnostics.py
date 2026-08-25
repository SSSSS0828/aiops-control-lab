"""AI 诊断与受约束工具调用领域模型。"""

from dataclasses import dataclass

from aiops_control.domain.enums import RiskLevel


@dataclass(frozen=True, slots=True)
class GeneratedDiagnosis:
    """模型或规则引擎输出的结构化诊断。"""

    summary: str
    root_cause: str
    recommended_action: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """LLM 可以建议、但不能绕过审批直接执行的工具定义。"""

    name: str
    description: str
    required_arguments: tuple[str, ...]
    allowed_arguments: tuple[str, ...]
    risk: RiskLevel


@dataclass(frozen=True, slots=True)
class PlannedToolCall:
    """经过工具注册表校验后的动作建议。"""

    tool_name: str
    target: str
    arguments: dict[str, str]
    risk: RiskLevel
