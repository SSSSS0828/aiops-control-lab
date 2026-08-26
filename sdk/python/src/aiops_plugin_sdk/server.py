"""通用 gRPC 插件服务器。

输入：控制面通过 Unix Socket 发来的 protobuf Struct。
处理：按固定 RPC 名称分发给插件实现。
输出：protobuf Struct；插件异常会转换为 gRPC INTERNAL 状态。
并发：gRPC 线程池可能并发调用处理函数，插件应避免无锁共享可变状态。
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent import futures
from dataclasses import dataclass
from typing import Any

import grpc
from google.protobuf import struct_pb2

Payload = dict[str, Any]
Handler = Callable[[Payload], Payload]
MAX_PLUGIN_MESSAGE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PluginHandlers:
    """插件生命周期与能力处理函数集合。"""

    describe: Handler
    health: Handler
    discover: Handler
    analyze: Handler
    plan: Handler
    execute: Handler
    verify: Handler
    rollback: Handler

    @classmethod
    def with_defaults(cls, describe: Handler, health: Handler) -> PluginHandlers:
        """用显式“不支持”响应补齐可选能力，降低最小插件样板量。"""

        def unsupported(_: Payload) -> Payload:
            return {"supported": False}

        return cls(
            describe=describe,
            health=health,
            discover=unsupported,
            analyze=unsupported,
            plan=unsupported,
            execute=unsupported,
            verify=unsupported,
            rollback=unsupported,
        )


def _deserialize(data: bytes) -> struct_pb2.Struct:
    """将 gRPC 请求字节解析为 protobuf Struct。"""

    message = struct_pb2.Struct()
    message.ParseFromString(data)
    return message


def _serialize(message: struct_pb2.Struct) -> bytes:
    """将 protobuf Struct 序列化为 gRPC 响应字节。"""

    return message.SerializeToString()


def _wrap(
    handler: Handler,
) -> Callable[[struct_pb2.Struct, grpc.ServicerContext], struct_pb2.Struct]:
    """把普通字典处理函数适配为 gRPC unary-unary 处理器。"""

    def invoke(
        request: struct_pb2.Struct, context: grpc.ServicerContext
    ) -> struct_pb2.Struct:
        # protobuf Struct 可直接转换成普通映射，插件代码无需感知传输细节。
        payload = dict(request)
        try:
            result = handler(payload)
        except Exception as error:  # noqa: BLE001 - 插件边界必须隔离任意实现异常
            # 只把简短错误返回控制面，完整堆栈由插件自己的结构化日志保存。
            context.abort(grpc.StatusCode.INTERNAL, str(error))
        if not isinstance(result, dict):
            context.abort(grpc.StatusCode.INTERNAL, "插件处理函数必须返回字典")
        response = struct_pb2.Struct()
        response.update(result)
        return response

    return invoke


def _rpc_method(
    handler: Handler,
) -> grpc.RpcMethodHandler[struct_pb2.Struct, struct_pb2.Struct]:
    """用统一序列化配置创建一个 unary-unary RPC 方法。"""

    return grpc.unary_unary_rpc_method_handler(
        _wrap(handler),
        request_deserializer=_deserialize,
        response_serializer=_serialize,
    )


def build_server(handlers: PluginHandlers, max_workers: int = 4) -> grpc.Server:
    """构造已注册服务但暂不监听，供契约测试和高级嵌入使用。"""

    if max_workers < 1 or max_workers > 32:
        raise ValueError("插件工作线程数必须在 1 到 32 之间")

    method_handlers: dict[
        str,
        grpc.RpcMethodHandler[struct_pb2.Struct, struct_pb2.Struct],
    ] = {
        "Describe": _rpc_method(handlers.describe),
        "Health": _rpc_method(handlers.health),
        "Discover": _rpc_method(handlers.discover),
        "Analyze": _rpc_method(handlers.analyze),
        "Plan": _rpc_method(handlers.plan),
        "Execute": _rpc_method(handlers.execute),
        "Verify": _rpc_method(handlers.verify),
        "Rollback": _rpc_method(handlers.rollback),
    }
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=(
            ("grpc.max_receive_message_length", MAX_PLUGIN_MESSAGE_BYTES),
            ("grpc.max_send_message_length", MAX_PLUGIN_MESSAGE_BYTES),
        ),
    )
    generic_handler = grpc.method_handlers_generic_handler(
        "aiops.plugin.v1.PluginService",
        method_handlers,
    )
    server.add_generic_rpc_handlers((generic_handler,))
    return server


def serve(
    socket_path: str, handlers: PluginHandlers, max_workers: int = 4
) -> grpc.Server:
    """在 Unix Socket 上启动插件服务并返回可等待的服务器对象。"""

    server = build_server(handlers, max_workers)
    # unix: 前缀要求插件与控制面位于同一主机，并避免暴露 TCP 监听端口。
    bound_port = server.add_insecure_port(f"unix:{socket_path}")
    if bound_port == 0:
        raise RuntimeError(f"无法监听插件 Unix Socket: {socket_path}")
    server.start()
    return server
