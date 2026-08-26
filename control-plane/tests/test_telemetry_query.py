"""Prometheus/Loki 适配器和 Incident 证据收集测试。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from aiops_control.adapters.loki_query import LokiRangeQuery
from aiops_control.adapters.memory_repository import InMemoryRepository
from aiops_control.adapters.prometheus_query import PrometheusRangeQuery
from aiops_control.application.evidence_collection_service import EvidenceCollectionService
from aiops_control.domain.enums import IncidentStatus
from aiops_control.domain.errors import ExternalSourceError
from aiops_control.domain.models import Incident
from aiops_control.domain.telemetry import LogRecord, MetricSample


def test_prometheus_matrix_is_converted_to_sorted_samples() -> None:
    """Prometheus matrix 标签、时间和值应转换为稳定领域对象。"""

    captured_url = ""

    def reader(url: str, _: float) -> dict[str, Any]:
        nonlocal captured_url
        captured_url = url
        return {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"job": "agent", "instance": "node-1"},
                        "values": [["1720000015", "2.5"], ["1720000000", "1.5"]],
                    }
                ],
            },
        }

    start = datetime.fromtimestamp(1_720_000_000, UTC)
    samples = PrometheusRangeQuery("http://prometheus:9090", reader=reader).query_range(
        'up{job="agent"}', start, start + timedelta(minutes=1), 15
    )

    assert "query=up%7Bjob%3D%22agent%22%7D" in captured_url
    assert [sample.value for sample in samples] == [1.5, 2.5]
    assert samples[0].labels["instance"] == "node-1"


def test_loki_stream_is_converted_without_losing_nanosecond_order() -> None:
    """Loki streams 应转换为按时间升序排列的短生命周期日志对象。"""

    def reader(_: str, __: float) -> dict[str, Any]:
        return {
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [
                    {
                        "stream": {"service": "lab-api"},
                        "values": [
                            ["1720000002000000000", "second"],
                            ["1720000001000000000", "first"],
                        ],
                    }
                ],
            },
        }

    start = datetime.fromtimestamp(1_720_000_000, UTC)
    records = LokiRangeQuery("http://loki:3100", reader=reader).query_range(
        '{service="lab-api"}', start, start + timedelta(minutes=1), 20
    )

    assert [record.message for record in records] == ["first", "second"]
    assert records[0].labels == {"service": "lab-api"}


class StaticMetricQuery:
    """证据应用服务测试使用的确定性指标端口。"""

    def query_range(
        self,
        _: str,
        started_at: datetime,
        __: datetime,
        ___: int,
    ) -> tuple[MetricSample, ...]:
        return (
            MetricSample(started_at, 1.0, {"job": "agent"}),
            MetricSample(started_at + timedelta(seconds=15), 3.0, {"job": "agent"}),
        )


class StaticLogQuery:
    """证据应用服务测试使用的确定性日志端口。"""

    def query_range(
        self,
        _: str,
        started_at: datetime,
        __: datetime,
        ___: int,
    ) -> tuple[LogRecord, ...]:
        return (LogRecord(started_at, "secret is not persisted", {"service": "lab-api"}),)


def test_evidence_service_persists_summary_but_not_raw_log() -> None:
    """Incident 只能保存查询引用和摘要，不能复制原始日志正文。"""

    repository = InMemoryRepository()
    now = datetime.now(UTC)
    incident = Incident(
        id="inc-telemetry",
        title="遥测测试",
        asset_id="lab-api",
        severity="medium",
        status=IncidentStatus.INVESTIGATING,
        created_at=now,
        updated_at=now,
    )
    repository.save_incident(incident)
    service = EvidenceCollectionService(repository, StaticMetricQuery(), StaticLogQuery())

    metric = service.attach_metric_evidence(incident.id, "up", now - timedelta(minutes=5), now, 15)
    log = service.attach_log_evidence(
        incident.id, '{service="lab-api"}', now - timedelta(minutes=5), now, 20
    )

    stored = repository.get_incident(incident.id)
    assert stored is not None
    assert "最小值 1" in metric.summary
    assert "service" in log.summary
    assert "secret is not persisted" not in repr(stored.evidence)
    assert len(stored.evidence) == 2


def test_evidence_service_rejects_unbounded_window() -> None:
    """超过六小时的查询必须在访问外部数据源前被拒绝。"""

    repository = InMemoryRepository()
    service = EvidenceCollectionService(repository, StaticMetricQuery(), StaticLogQuery())
    now = datetime.now(UTC)
    with pytest.raises(ExternalSourceError, match="不能超过 6 小时"):
        service.attach_metric_evidence("missing", "up", now - timedelta(hours=7), now, 15)
