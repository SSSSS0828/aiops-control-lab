"""Agent mTLS gRPC 网关。

网关仅负责传输身份、Protobuf/领域转换和流生命周期；规则评估、Incident 与动作策略不在
此层。服务在容器内监听 0.0.0.0，由 Compose 只发布到宿主机 127.0.0.1:9443。
"""

from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import grpc

from aiops_control.application.agent_ingestion_service import (
    AgentIdentityError,
    AgentIngestionService,
)
from aiops_control.domain.monitoring import LatestMetric, MonitoredAsset, MonitoredTopologyEdge
from aiops_control.generated.agent.v1 import agent_pb2, agent_pb2_grpc


@dataclass(frozen=True, slots=True)
class GrpcGatewayConfiguration:
    """gRPC 服务监听地址与 mTLS 文件位置。"""

    listen: str
    certificate_file: Path
    key_file: Path
    client_ca_file: Path


class AgentGatewayServicer(agent_pb2_grpc.ControlPlaneGatewayServicer):
    """一个流只允许声明一个通过证书绑定的 Agent 身份。"""

    def __init__(self, ingestion: AgentIngestionService) -> None:
        self._ingestion = ingestion

    async def Connect(  # noqa: N802
        self,
        request_iterator: AsyncIterator[Any],
        context: grpc.aio.ServicerContext[Any, Any],
    ) -> AsyncIterator[Any]:
        """校验首帧后逐批确认；收到旧序列也返回确认，使 Agent 可以继续前进。"""

        certificate_identity = _certificate_identity(context.auth_context())
        node = None
        async for message in request_iterator:
            if message.HasField("hello"):
                if node is not None:
                    await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "连接不能重复 hello")
                try:
                    node = self._ingestion.connect(
                        message.hello.node_id,
                        message.hello.agent_version,
                        message.hello.instance_id,
                        certificate_identity,
                    )
                except AgentIdentityError as error:
                    await context.abort(grpc.StatusCode.PERMISSION_DENIED, str(error))
                continue
            if node is None:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "首帧必须是 AgentHello")
            if message.HasField("telemetry"):
                batch = message.telemetry
                observed_at = datetime.fromtimestamp(batch.collected_unix_ms / 1000, UTC)
                metrics = [
                    LatestMetric(
                        name=item.name,
                        value=item.value,
                        labels=dict(item.labels),
                        collected_at=datetime.fromtimestamp(item.collected_unix_ms / 1000, UTC),
                    )
                    for item in batch.metrics
                ]
                assets = [
                    MonitoredAsset(
                        id=item.asset_id,
                        node_id=item.node_id,
                        kind=item.kind,
                        name=item.name,
                        status=item.status,
                        environment=item.attributes.get("environment", "real"),
                        source=item.attributes.get("source", "agent"),
                        last_seen_at=observed_at,
                        attributes=dict(item.attributes),
                    )
                    for item in batch.assets
                ]
                topology = [
                    MonitoredTopologyEdge(
                        source_asset_id=item.source_asset_id,
                        target_asset_id=item.target_asset_id,
                        relation=item.relation,
                        weight=item.weight,
                        source=item.source,
                        last_seen_at=observed_at,
                    )
                    for item in batch.topology
                ]
                self._ingestion.ingest(node, batch.sequence, metrics, assets, topology)
                yield agent_pb2.ControlMessage(  # type: ignore[attr-defined]
                    acknowledged_sequence=batch.sequence,
                    message="遥测批次已确认",
                )


class GrpcAgentGateway:
    """管理安全 gRPC Server 的启动和优雅停止。"""

    def __init__(
        self, configuration: GrpcGatewayConfiguration, ingestion: AgentIngestionService
    ) -> None:
        self._configuration = configuration
        self._ingestion = ingestion
        # aio Server 必须在 Uvicorn 最终事件循环中创建，不能在模块导入阶段提前绑定。
        self._server: grpc.aio.Server | None = None

    async def start(self) -> None:
        """读取服务端证书和客户端 CA，并强制验证客户端证书。"""

        self._server = grpc.aio.server()
        agent_pb2_grpc.add_ControlPlaneGatewayServicer_to_server(  # type: ignore[no-untyped-call]
            AgentGatewayServicer(self._ingestion), self._server
        )
        certificate = self._configuration.certificate_file.read_bytes()
        private_key = self._configuration.key_file.read_bytes()
        client_ca = self._configuration.client_ca_file.read_bytes()
        credentials = grpc.ssl_server_credentials(
            [(private_key, certificate)],
            root_certificates=client_ca,
            require_client_auth=True,
        )
        bound_port = self._server.add_secure_port(self._configuration.listen, credentials)
        if bound_port == 0:
            raise RuntimeError(f"gRPC 无法绑定 {self._configuration.listen}")
        await self._server.start()

    async def close(self) -> None:
        """给在途批次最多三秒完成，随后关闭服务。"""

        if self._server is not None:
            await self._server.stop(grace=3)


def _certificate_identity(auth_context: Mapping[str, Iterable[bytes]]) -> str:
    """从 gRPC 认证上下文提取证书 CN；缺失时按未认证处理。"""

    values = list(auth_context.get("x509_common_name", []))
    return values[0].decode("utf-8") if values else ""
