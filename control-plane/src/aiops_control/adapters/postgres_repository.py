"""PostgreSQL 领域聚合仓储。

阶段一使用 JSONB 保存完整聚合，使领域结构保持集中且迁移简单；ID、创建时间和
幂等键仍是独立索引列。后续需要跨聚合查询时再把稳定字段规范化，避免过早拆表。
"""

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import Any

import psycopg
from psycopg.rows import dict_row

from aiops_control.adapters.postgres_monitoring_repository import (
    PostgresMonitoringRepositoryMixin,
)
from aiops_control.domain.changes import ChangeEvent
from aiops_control.domain.enums import ActionStatus, IncidentStatus, PlanStatus, RiskLevel
from aiops_control.domain.models import (
    ActionRun,
    Approval,
    EvidenceRef,
    Hypothesis,
    Incident,
    RemediationPlan,
    RemediationStep,
)


def _json_default(value: object) -> str:
    """把领域时间和枚举转换为稳定 JSON 值。"""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError(f"不支持序列化类型 {type(value)!r}")


def _payload(entity: Any) -> str:
    """将 dataclass 聚合转换为可写入 JSONB 的字符串。"""

    return json.dumps(asdict(entity), default=_json_default, ensure_ascii=False)


class PostgresRepository(PostgresMonitoringRepositoryMixin):
    """实现 IncidentRepository 与 RemediationRepository 的持久化适配器。"""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def save_incident(self, incident: Incident) -> None:
        """以 Incident ID 为键原子新增或覆盖聚合。"""

        self._upsert("incidents", incident.id, incident.created_at, _payload(incident))

    def get_incident(self, incident_id: str) -> Incident | None:
        """按 ID 读取并恢复 Incident 领域实体。"""

        payload = self._read_payload("incidents", incident_id)
        return _incident_from_payload(payload) if payload else None

    def list_incidents(self) -> list[Incident]:
        """按创建时间倒序返回 Incident。"""

        return [_incident_from_payload(item) for item in self._list_payloads("incidents")]

    def save_plan(self, plan: RemediationPlan) -> None:
        """保存修复计划聚合。"""

        self._upsert("remediation_plans", plan.id, plan.created_at, _payload(plan))

    def get_plan(self, plan_id: str) -> RemediationPlan | None:
        """按 ID 读取修复计划。"""

        payload = self._read_payload("remediation_plans", plan_id)
        return _plan_from_payload(payload) if payload else None

    def get_plan_by_incident(self, incident_id: str) -> RemediationPlan | None:
        """按 Incident ID 返回最新修复计划。"""

        query = """
            SELECT payload
            FROM remediation_plans
            WHERE payload ->> 'incident_id' = %s
            ORDER BY created_at DESC
            LIMIT 1
        """
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            row = connection.execute(query, (incident_id,)).fetchone()
        return _plan_from_payload(row["payload"]) if row else None

    def save_approval(self, approval: Approval) -> None:
        """保存不可变审批事实。"""

        self._upsert("approvals", approval.id, approval.approved_at, _payload(approval))

    def save_action_run(self, action_run: ActionRun) -> None:
        """保存执行记录并维护数据库级幂等键。"""

        query = """
            INSERT INTO action_runs (id, idempotency_key, created_at, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload
        """
        with psycopg.connect(self._database_url) as connection:
            connection.execute(
                query,
                (
                    action_run.id,
                    action_run.idempotency_key,
                    action_run.created_at,
                    _payload(action_run),
                ),
            )

    def get_action_run_by_key(self, idempotency_key: str) -> ActionRun | None:
        """按唯一幂等键查找已有执行记录。"""

        query = "SELECT payload FROM action_runs WHERE idempotency_key = %s"
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            row = connection.execute(query, (idempotency_key,)).fetchone()
        return _action_run_from_payload(row["payload"]) if row else None

    def list_action_runs(self) -> list[ActionRun]:
        """按创建时间倒序返回执行审计记录。"""

        return [_action_run_from_payload(item) for item in self._list_payloads("action_runs")]

    def save_change_event(self, event: ChangeEvent) -> None:
        """保存通用 Git、CI/CD 或部署事件。"""

        self._upsert("change_events", event.id, event.occurred_at, _payload(event))

    def list_change_events(self, service: str | None = None) -> list[ChangeEvent]:
        """按时间倒序读取变更事件，并可按服务过滤。"""

        events = [_change_event_from_payload(item) for item in self._list_payloads("change_events")]
        return [event for event in events if event.service == service] if service else events

    def _upsert(self, table: str, entity_id: str, created_at: datetime, payload: str) -> None:
        # table 只由类内固定调用点提供，不能接受任何用户输入。
        query = f"""
            INSERT INTO {table} (id, created_at, payload)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload
        """
        with psycopg.connect(self._database_url) as connection:
            connection.execute(query, (entity_id, created_at, payload))

    def _read_payload(self, table: str, entity_id: str) -> dict[str, Any] | None:
        # 参数值使用绑定变量，表名仍只来自类内固定调用点。
        query = f"SELECT payload FROM {table} WHERE id = %s"
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            row = connection.execute(query, (entity_id,)).fetchone()
        return row["payload"] if row else None

    def _list_payloads(self, table: str) -> list[dict[str, Any]]:
        query = f"SELECT payload FROM {table} ORDER BY created_at DESC"
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            rows = connection.execute(query).fetchall()
        return [row["payload"] for row in rows]


def _incident_from_payload(raw: dict[str, Any]) -> Incident:
    """从 JSONB 恢复 Incident 及其嵌套证据和根因。"""

    evidence = [
        EvidenceRef(
            id=item["id"],
            source=item["source"],
            query=item["query"],
            started_at=datetime.fromisoformat(item["started_at"]),
            ended_at=datetime.fromisoformat(item["ended_at"]),
            summary=item["summary"],
        )
        for item in raw["evidence"]
    ]
    hypotheses = [
        Hypothesis(
            asset_id=item["asset_id"],
            reason=item["reason"],
            score=float(item["score"]),
            evidence_ids=tuple(item["evidence_ids"]),
        )
        for item in raw["hypotheses"]
    ]
    return Incident(
        id=raw["id"],
        title=raw["title"],
        asset_id=raw["asset_id"],
        severity=raw["severity"],
        status=IncidentStatus(raw["status"]),
        created_at=datetime.fromisoformat(raw["created_at"]),
        updated_at=datetime.fromisoformat(raw["updated_at"]),
        evidence=evidence,
        hypotheses=hypotheses,
    )


def _plan_from_payload(raw: dict[str, Any]) -> RemediationPlan:
    """从 JSONB 恢复修复计划及其有序步骤。"""

    steps = [RemediationStep(**item) for item in raw["steps"]]
    return RemediationPlan(
        id=raw["id"],
        incident_id=raw["incident_id"],
        summary=raw["summary"],
        risk=RiskLevel(raw["risk"]),
        steps=steps,
        created_at=datetime.fromisoformat(raw["created_at"]),
        expires_at=datetime.fromisoformat(raw["expires_at"]),
        status=PlanStatus(raw["status"]),
    )


def _action_run_from_payload(raw: dict[str, Any]) -> ActionRun:
    """从 JSONB 恢复动作执行记录。"""

    return ActionRun(
        id=raw["id"],
        plan_id=raw["plan_id"],
        incident_id=raw["incident_id"],
        idempotency_key=raw["idempotency_key"],
        approved_hash=raw["approved_hash"],
        status=ActionStatus(raw["status"]),
        created_at=datetime.fromisoformat(raw["created_at"]),
        started_at=datetime.fromisoformat(raw["started_at"]) if raw["started_at"] else None,
        finished_at=datetime.fromisoformat(raw["finished_at"]) if raw["finished_at"] else None,
        output=raw["output"],
    )


def _change_event_from_payload(raw: dict[str, Any]) -> ChangeEvent:
    """从 JSONB 恢复标准变更事件。"""

    return ChangeEvent(
        id=raw["id"],
        provider=raw["provider"],
        event_type=raw["event_type"],
        service=raw["service"],
        revision=raw["revision"],
        status=raw["status"],
        occurred_at=datetime.fromisoformat(raw["occurred_at"]),
        attributes=raw["attributes"],
    )
