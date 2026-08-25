"""受约束 LLM 工具注册表测试。"""

import pytest

from aiops_control.application.tool_registry import ConstrainedToolRegistry
from aiops_control.domain.diagnostics import ToolDefinition
from aiops_control.domain.enums import RiskLevel


def create_registry() -> ConstrainedToolRegistry:
    """构造只允许实验室容器重启的工具注册表。"""

    return ConstrainedToolRegistry(
        [
            ToolDefinition(
                name="restart_container",
                description="重启实验容器",
                required_arguments=("grace_seconds",),
                allowed_arguments=("grace_seconds",),
                risk=RiskLevel.MEDIUM,
            )
        ],
        target_prefixes=("lab-",),
    )


def test_registered_tool_is_converted_to_typed_call() -> None:
    """合法工具建议应变成带风险级别的不可变对象。"""

    call = create_registry().validate(
        {
            "tool_name": "restart_container",
            "target": "lab-api",
            "arguments": {"grace_seconds": 10},
        }
    )
    assert call.tool_name == "restart_container"
    assert call.arguments == {"grace_seconds": "10"}


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "shell", "target": "lab-api", "arguments": {}},
        {
            "tool_name": "restart_container",
            "target": "production-api",
            "arguments": {"grace_seconds": "10"},
        },
        {
            "tool_name": "restart_container",
            "target": "lab-api",
            "arguments": {"grace_seconds": "10", "command": "rm -rf /"},
        },
    ],
)
def test_unregistered_or_out_of_scope_tool_is_rejected(payload: dict[str, object]) -> None:
    """未知工具、真实目标和隐藏参数都必须被拒绝。"""

    with pytest.raises(ValueError):
        create_registry().validate(payload)
