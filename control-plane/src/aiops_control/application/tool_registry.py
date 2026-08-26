"""LLM 工具调用的注册、参数和目标边界校验。

模型输出永远只是建议。本模块把不可信字典转换为 PlannedToolCall，之后仍需生成
RemediationPlan、计算哈希并由人工审批，不能直接进入 Agent。
"""

from typing import Any

from aiops_control.domain.diagnostics import PlannedToolCall, ToolDefinition


class ConstrainedToolRegistry:
    """只接受显式注册且参数集合完全匹配的工具调用。"""

    def __init__(self, definitions: list[ToolDefinition], target_prefixes: tuple[str, ...]) -> None:
        self._definitions = {definition.name: definition for definition in definitions}
        self._target_prefixes = target_prefixes

    def validate(self, raw_call: dict[str, Any]) -> PlannedToolCall:
        """逐项校验模型输出，拒绝未知工具、越权目标和隐藏参数。"""

        tool_name = str(raw_call.get("tool_name", ""))
        definition = self._definitions.get(tool_name)
        if definition is None:
            raise ValueError(f"工具 {tool_name!r} 未注册")

        target = str(raw_call.get("target", ""))
        # startswith 接收前缀元组，所有真实目标必须位于配置范围内。
        if not target.startswith(self._target_prefixes):
            raise ValueError(f"目标 {target!r} 超出允许范围")

        raw_arguments = raw_call.get("arguments", {})
        if not isinstance(raw_arguments, dict):
            raise ValueError("工具参数必须是对象")
        arguments = {str(key): str(value) for key, value in raw_arguments.items()}
        argument_names = set(arguments)
        required = set(definition.required_arguments)
        allowed = set(definition.allowed_arguments)
        if not required.issubset(argument_names):
            missing = sorted(required - argument_names)
            raise ValueError(f"工具缺少必填参数: {missing}")
        if not argument_names.issubset(allowed):
            unknown = sorted(argument_names - allowed)
            raise ValueError(f"工具包含未声明参数: {unknown}")
        return PlannedToolCall(tool_name, target, arguments, definition.risk)
