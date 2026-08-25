"""AIOps Python 插件 SDK。

SDK 使用标准 protobuf Struct 作为阶段一信封，插件仍通过真正的 gRPC 通信。
后续新增强类型消息时可保持 RPC 名称和生命周期不变。
"""

from aiops_plugin_sdk.server import PluginHandlers, build_server, serve

__all__ = ["PluginHandlers", "build_server", "serve"]
