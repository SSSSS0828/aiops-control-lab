"""日志变量归一化和模板聚类测试。"""

from datetime import UTC, datetime

from aiops_control.adapters.log_template_parser import LogTemplateParser
from aiops_control.domain.logs import LogEvent


def test_dynamic_values_share_same_template() -> None:
    """不同 IP、请求 ID 和延迟不应拆成不同日志模板。"""

    parser = LogTemplateParser()
    first = parser.parse(
        "request 550e8400-e29b-41d4-a716-446655440000 from 10.0.0.1 failed in 120 ms"
    )
    second = parser.parse(
        "request 7b74281a-3e1b-4e85-9f36-6b84dcb72131 from 10.0.0.2 failed in 900 ms"
    )
    assert first.id == second.id
    assert "<UUID>" in first.template
    assert "<IP>" in first.template


def test_cluster_counts_repeated_template() -> None:
    """同一模板事件应聚合并保留示例引用。"""

    now = datetime.now(UTC)
    events = [
        LogEvent("log-1", "lab-api", "worker 12 exited with code 1", now),
        LogEvent("log-2", "lab-api", "worker 98 exited with code 2", now),
    ]
    clusters = LogTemplateParser().cluster(events)
    assert len(clusters) == 1
    assert clusters[0].count == 2
