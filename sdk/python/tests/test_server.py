"""Python SDK 的真实 gRPC 线协议与默认能力测试。"""

from typing import Any

import grpc
from aiops_plugin_sdk import PluginHandlers, build_server
from google.protobuf import struct_pb2


def _invoke(channel: grpc.Channel, method: str) -> dict[str, Any]:
    """通过公共方法路径调用 Struct RPC。"""

    request = struct_pb2.Struct()
    rpc = channel.unary_unary(
        f"/aiops.plugin.v1.PluginService/{method}",
        request_serializer=struct_pb2.Struct.SerializeToString,
        response_deserializer=struct_pb2.Struct.FromString,
    )
    return dict(rpc(request, timeout=3))


def test_real_grpc_health_and_default_capability() -> None:
    """最小插件必须健康，未实现能力必须明确返回 supported=false。"""

    handlers = PluginHandlers.with_defaults(
        describe=lambda _: {"id": "python-example"},
        health=lambda _: {"status": "ok"},
    )
    server = build_server(handlers)
    port = server.add_insecure_port("127.0.0.1:0")
    assert port > 0
    server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    try:
        assert _invoke(channel, "Health")["status"] == "ok"
        assert _invoke(channel, "Analyze")["supported"] is False
    finally:
        channel.close()
        server.stop(grace=0).wait(timeout=3)


def test_worker_count_has_hard_boundary() -> None:
    """无边界线程池配置必须在启动前被拒绝。"""

    handlers = PluginHandlers.with_defaults(lambda _: {}, lambda _: {"status": "ok"})
    try:
        build_server(handlers, max_workers=0)
    except ValueError as error:
        assert "1 到 32" in str(error)
    else:
        raise AssertionError("零工作线程必须被拒绝")
