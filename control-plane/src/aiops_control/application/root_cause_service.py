"""基于拓扑、时间和异常强度的可解释根因评分。

输入：服务依赖边和同一 Incident 内的异常观测。
处理：计算异常强度、发生先后和向下游传播覆盖率三个独立分量。
输出：按综合分数排序的 Hypothesis，不直接修改 Incident。
"""

from collections import defaultdict, deque

from aiops_control.domain.models import Hypothesis
from aiops_control.domain.topology import ObservedAnomaly, TopologyEdge


class RootCauseAnalysisService:
    """阶段二无需训练数据的图拓扑根因分析器。"""

    def rank(
        self,
        edges: list[TopologyEdge],
        anomalies: list[ObservedAnomaly],
        limit: int = 3,
    ) -> list[Hypothesis]:
        """计算并返回最可能的根因资产。"""

        if not anomalies or limit < 1:
            return []
        # 反向邻接表从依赖方指向调用方，便于统计故障可能传播到哪些下游消费者。
        dependents: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            if edge.relation == "depends_on":
                dependents[edge.target_asset_id].add(edge.source_asset_id)

        anomaly_by_asset = {item.asset_id: item for item in anomalies}
        earliest = min(item.occurred_at for item in anomalies)
        latest = max(item.occurred_at for item in anomalies)
        span_seconds = max((latest - earliest).total_seconds(), 1.0)
        results: list[Hypothesis] = []

        for anomaly in anomalies:
            # 异常检测器分数量纲不同，因此在 RCA 边界压缩到 0..1。
            severity_score = min(max(anomaly.score, 0.0) / 5.0, 1.0)
            # 更早出现的异常更可能是原因，而不是上游故障传播后的结果。
            elapsed = (anomaly.occurred_at - earliest).total_seconds()
            temporal_score = 1.0 - min(max(elapsed / span_seconds, 0.0), 1.0)
            # 能解释更多异常下游节点的候选具有更高传播覆盖率。
            reachable = self._reachable_dependents(anomaly.asset_id, dependents)
            explained = len(reachable.intersection(anomaly_by_asset))
            propagation_score = explained / max(len(anomalies) - 1, 1)
            # 权重显式固定，实验报告可以逐项消融而不是隐藏在提示词中。
            total_score = 0.45 * severity_score + 0.30 * temporal_score + 0.25 * propagation_score
            reason = (
                f"异常强度={severity_score:.2f}，时间领先={temporal_score:.2f}，"
                f"传播覆盖={propagation_score:.2f}"
            )
            results.append(
                Hypothesis(
                    asset_id=anomaly.asset_id,
                    reason=reason,
                    score=total_score,
                    evidence_ids=(anomaly.evidence_id,),
                )
            )

        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def _reachable_dependents(
        self,
        root: str,
        dependents: dict[str, set[str]],
    ) -> set[str]:
        """使用广度优先搜索查找根节点可以影响的所有调用方。"""

        visited: set[str] = set()
        queue: deque[str] = deque(dependents.get(root, set()))
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            queue.extend(dependents.get(current, set()))
        return visited
