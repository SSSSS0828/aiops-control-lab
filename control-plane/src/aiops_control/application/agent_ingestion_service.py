"""Agent 连接与遥测批次入站编排。

传输层完成 mTLS 后把证书身份和强类型 Protobuf 转成领域值，本服务负责双重身份校验、
序列去重、节点心跳以及资产/拓扑持久化。原始指标只进入最新值存储，等待 Prometheus 抓取。
"""

from datetime import UTC, datetime

from aiops_control.domain.monitoring import (
    AgentNode,
    LatestMetric,
    MonitoredAsset,
    MonitoredTopologyEdge,
)
from aiops_control.ports.metric_store import LatestMetricStore
from aiops_control.ports.monitoring_repository import MonitoringRepository


class AgentIdentityError(ValueError):
    """证书身份与业务节点身份不一致。"""


class AgentIngestionService:
    """维护一个 Agent 流的身份、序列和最新状态。"""

    def __init__(
        self,
        repository: MonitoringRepository,
        metric_store: LatestMetricStore,
        allowed_identities: dict[str, str],
    ) -> None:
        self._repository = repository
        self._metric_store = metric_store
        self._allowed_identities = allowed_identities

    def connect(
        self,
        node_id: str,
        version: str,
        instance_id: str,
        certificate_identity: str,
    ) -> AgentNode:
        """同时校验证书 CN 与 hello.node_id，防止合法证书冒充另一节点。"""

        expected = self._allowed_identities.get(node_id)
        if expected is None or expected != certificate_identity:
            raise AgentIdentityError("Agent 证书身份与登记节点不匹配")
        now = datetime.now(UTC)
        node = AgentNode(
            id=node_id,
            version=version,
            instance_id=instance_id,
            certificate_identity=certificate_identity,
            status="online",
            connected_at=now,
            last_heartbeat_at=now,
        )
        self._repository.save_agent_node(node)
        return node

    def ingest(
        self,
        node: AgentNode,
        sequence: int,
        metrics: list[LatestMetric],
        assets: list[MonitoredAsset],
        topology: list[MonitoredTopologyEdge],
    ) -> bool:
        """先去重再更新低频状态，保证重连重发不产生重复评估输入。"""

        accepted = self._metric_store.accept_batch(node.id, node.instance_id, sequence, metrics)
        if not accepted:
            return False
        now = datetime.now(UTC)
        self._repository.save_agent_node(
            AgentNode(
                id=node.id,
                version=node.version,
                instance_id=node.instance_id,
                certificate_identity=node.certificate_identity,
                status="online",
                connected_at=node.connected_at,
                last_heartbeat_at=now,
            )
        )
        for asset in assets:
            if asset.node_id != node.id:
                raise AgentIdentityError("遥测资产 node_id 不属于当前证书节点")
            self._repository.save_monitored_asset(asset)
        for edge in topology:
            self._repository.save_monitored_topology(edge)
        return True
