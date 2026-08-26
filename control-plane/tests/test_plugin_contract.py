"""插件进程契约测试：真实启动官方插件并验证 Unix Socket gRPC 健康协议。"""

from pathlib import Path

import pytest

from aiops_control.adapters.grpc_plugin_runtime import GrpcPluginRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = PROJECT_ROOT / "plugins"
TEST_RUNTIME_ROOT = PROJECT_ROOT / "runtime" / "t"


@pytest.mark.parametrize("plugin_id", ["http-nginx", "kubernetes", "webhook-notifier"])
def test_official_plugin_satisfies_health_contract(plugin_id: str) -> None:
    """每个官方插件都必须通过清单校验、独立启动和标准健康检查。"""

    # Windows 的 pytest 临时目录可能超过 Unix Socket 路径上限，因此使用仓库内固定短目录。
    # Socket 文件名包含插件身份哈希，三个参数化用例不会互相覆盖。
    runtime = GrpcPluginRuntime(PLUGIN_ROOT, TEST_RUNTIME_ROOT)
    try:
        manifest = runtime.install(PLUGIN_ROOT / plugin_id / "plugin.yaml")
        health = runtime.call(plugin_id, "Health", {})
        description = runtime.call(plugin_id, "Describe", {})

        assert manifest.plugin_id == plugin_id
        assert manifest.config_schema["type"] == "object"
        assert health["status"] == "ok"
        assert description["id"] == plugin_id
    finally:
        # 即使用例断言失败，也必须清理插件进程，避免污染后续契约测试。
        runtime.close()
