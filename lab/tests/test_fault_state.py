"""实验故障状态的过期、清理和白名单测试。"""

import sys
from pathlib import Path

import pytest

# 测试不安装实验镜像，把单一模块目录显式加入导入路径。
sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

from fault_state import FaultState


def test_fault_expires_by_monotonic_deadline() -> None:
    """到达截止点后场景必须自动失效，不依赖后台清理任务。"""

    now = [100.0]
    state = FaultState(clock=lambda: now[0])
    state.activate("request_latency", 10)
    assert state.active("request_latency") is True
    now[0] = 110.0
    assert state.active("request_latency") is False


def test_fault_clear_is_idempotent() -> None:
    """重复清理不得报错，保证自动恢复任务可以安全重试。"""

    state = FaultState()
    state.activate("http_5xx", 10)
    state.clear("http_5xx")
    state.clear("http_5xx")
    assert state.active("http_5xx") is False


def test_unknown_fault_is_rejected() -> None:
    """未注册场景不能借控制端点演变成任意故障工具。"""

    with pytest.raises(ValueError, match="未注册"):
        FaultState().activate("arbitrary_shell", 10)
