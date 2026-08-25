"""PostgreSQL 真实监测仓储混入实现。

高频原始指标不写 PostgreSQL；这里只保存节点心跳、资产/拓扑最新状态、规则和紧凑评估。
每类对象使用独立表，JSONB 保留向后兼容扩展空间，稳定 ID 与时间仍建立普通索引。
"""

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from aiops_control.domain.monitoring import (
    AgentNode,
    MonitoredAsset,
    MonitoredTopologyEdge,
    MonitorEvaluation,
    MonitorRule,
)

MonitoringEntity = (
    AgentNode | MonitoredAsset | MonitoredTopologyEdge | MonitorEvaluation | MonitorRule
)


class PostgresMonitoringRepositoryMixin:
    """为主 PostgreSQL 仓储补充真实监测读写能力。"""

    _database_url: str

    def save_agent_node(self, node: AgentNode) -> None:
        """保存节点最新心跳。"""

        self._monitor_upsert("agent_nodes", node.id, node.last_heartbeat_at, node)

    def list_agent_nodes(self) -> list[AgentNode]:
        """读取全部已登记 Agent。"""

        return [AgentNode(**item) for item in self._monitor_payloads("agent_nodes")]

    def save_monitored_asset(self, asset: MonitoredAsset) -> None:
        """保存真实资产最新状态。"""

        self._monitor_upsert("assets", asset.id, asset.last_seen_at, asset)

    def get_monitored_asset(self, asset_id: str) -> MonitoredAsset | None:
        """按稳定 ID 读取真实资产。"""

        payload = self._monitor_payload("assets", asset_id)
        return MonitoredAsset(**payload) if payload else None

    def list_monitored_assets(self) -> list[MonitoredAsset]:
        """读取全部真实资产。"""

        return [MonitoredAsset(**item) for item in self._monitor_payloads("assets")]

    def save_monitored_topology(self, edge: MonitoredTopologyEdge) -> None:
        """保存一条最新拓扑边。"""

        edge_id = f"{edge.source_asset_id}|{edge.relation}|{edge.target_asset_id}"
        self._monitor_upsert("topology_edges", edge_id, edge.last_seen_at, edge)

    def list_monitored_topology(self) -> list[MonitoredTopologyEdge]:
        """读取真实拓扑。"""

        return [MonitoredTopologyEdge(**item) for item in self._monitor_payloads("topology_edges")]

    def save_monitor_rule(self, rule: MonitorRule) -> None:
        """保存监测规则。"""

        self._monitor_upsert("monitor_rules", rule.id, datetime.now().astimezone(), rule)

    def list_monitor_rules(self) -> list[MonitorRule]:
        """读取监测规则。"""

        return [MonitorRule(**item) for item in self._monitor_payloads("monitor_rules")]

    def save_monitor_evaluation(self, evaluation: MonitorEvaluation) -> None:
        """追加一条不可变评估记录。"""

        self._monitor_upsert(
            "monitor_evaluations", evaluation.id, evaluation.evaluated_at, evaluation
        )

    def list_monitor_evaluations(
        self, asset_id: str | None = None, limit: int = 200
    ) -> list[MonitorEvaluation]:
        """读取最近评估；asset_id 在 JSONB 表达式索引上过滤。"""

        query = "SELECT payload FROM monitor_evaluations"
        parameters: tuple[object, ...]
        if asset_id is None:
            parameters = (limit,)
        else:
            query += " WHERE payload ->> 'asset_id' = %s"
            parameters = (asset_id, limit)
        query += " ORDER BY observed_at DESC LIMIT %s"
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [MonitorEvaluation(**_restore_dates(row["payload"])) for row in rows]

    def run_monitoring_cycle_once(self, callback: Callable[[], None]) -> bool:
        """使用 PostgreSQL 会话级 advisory lock 保证多进程只评估一次。"""

        # 锁与持有它的数据库会话绑定；整个 callback 期间连接保持打开。
        with psycopg.connect(self._database_url) as connection:
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s)", (8_400_600,)
            ).fetchone()
            if acquired is None or not bool(acquired[0]):
                return False
            try:
                callback()
                return True
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (8_400_600,))

    def _monitor_upsert(
        self, table: str, entity_id: str, observed_at: datetime, entity: MonitoringEntity
    ) -> None:
        # table 只来自本类固定调用点；实体值全部使用绑定参数。
        query = f"""
            INSERT INTO {table} (id, observed_at, payload)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (id) DO UPDATE
            SET observed_at = EXCLUDED.observed_at, payload = EXCLUDED.payload
        """
        payload = json.dumps(asdict(entity), ensure_ascii=False, default=_json_default)
        with psycopg.connect(self._database_url) as connection:
            connection.execute(query, (entity_id, observed_at, payload))

    def _monitor_payload(self, table: str, entity_id: str) -> dict[str, Any] | None:
        query = f"SELECT payload FROM {table} WHERE id = %s"
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            row = connection.execute(query, (entity_id,)).fetchone()
        return _restore_dates(row["payload"]) if row else None

    def _monitor_payloads(self, table: str) -> list[dict[str, Any]]:
        query = f"SELECT payload FROM {table} ORDER BY observed_at DESC"
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            rows = connection.execute(query).fetchall()
        return [_restore_dates(row["payload"]) for row in rows]


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"监测实体包含不可序列化类型 {type(value)!r}")


def _restore_dates(payload: dict[str, Any]) -> dict[str, Any]:
    """只恢复监测模型中已登记的时间字段，避免猜测普通字符串。"""

    restored = dict(payload)
    for key in ("connected_at", "last_heartbeat_at", "last_seen_at", "evaluated_at"):
        value = restored.get(key)
        if isinstance(value, str):
            restored[key] = datetime.fromisoformat(value)
    return restored
