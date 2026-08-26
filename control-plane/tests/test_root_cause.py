"""拓扑根因评分测试。"""

from datetime import UTC, datetime, timedelta

from aiops_control.application.root_cause_service import RootCauseAnalysisService
from aiops_control.domain.topology import ObservedAnomaly, TopologyEdge


def test_earliest_shared_dependency_ranks_first() -> None:
    """最早异常且能解释全部下游的 Redis 应排在首位。"""

    now = datetime.now(UTC)
    edges = [
        TopologyEdge("lab-gateway", "lab-api"),
        TopologyEdge("lab-api", "lab-redis"),
    ]
    anomalies = [
        ObservedAnomaly("lab-redis", 4.5, now, "evi-redis"),
        ObservedAnomaly("lab-api", 4.2, now + timedelta(seconds=10), "evi-api"),
        ObservedAnomaly("lab-gateway", 3.8, now + timedelta(seconds=20), "evi-gateway"),
    ]
    hypotheses = RootCauseAnalysisService().rank(edges, anomalies)
    assert hypotheses[0].asset_id == "lab-redis"
    assert hypotheses[0].score > hypotheses[1].score
