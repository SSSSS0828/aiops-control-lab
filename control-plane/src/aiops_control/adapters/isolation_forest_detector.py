"""面向单变量在线指标的轻量 Isolation Forest。

输入：历史窗口和当前观测。
处理：从历史样本构建多棵随机隔离树，以当前值的平均路径长度计算异常分数。
输出：0 到 1 的 Isolation Forest 分数和可解释结论。
副作用：无；随机数使用固定种子以保证实验和测试可复现。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, log, log2
from random import Random

from aiops_control.ports.detectors import DetectionResult

EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True, slots=True)
class _IsolationNode:
    """一维隔离树节点；叶节点只保存未被继续隔离的样本数。"""

    size: int
    split: float | None = None
    left: _IsolationNode | None = None
    right: _IsolationNode | None = None


def _average_unsuccessful_path(sample_count: int) -> float:
    """估计二叉搜索树失败查找的平均路径长度 c(n)。"""

    if sample_count <= 1:
        return 0.0
    if sample_count == 2:
        return 1.0
    return 2 * (log(sample_count - 1) + EULER_GAMMA) - 2 * (sample_count - 1) / sample_count


class IsolationForestDetector:
    """无需异常标签的随机隔离检测器。"""

    def __init__(
        self,
        tree_count: int = 48,
        sample_size: int = 64,
        threshold: float = 0.57,
        seed: int = 42,
    ) -> None:
        if tree_count < 1 or sample_size < 4:
            raise ValueError("树数量必须为正且采样数不能小于 4")
        if not 0 < threshold < 1:
            raise ValueError("Isolation Forest 阈值必须位于 (0, 1)")
        self._tree_count = tree_count
        self._sample_size = sample_size
        self._threshold = threshold
        self._seed = seed

    def detect(self, history: Sequence[float], current: float) -> DetectionResult:
        """构建森林并计算当前观测的平均隔离路径。"""

        if len(history) < 8:
            return DetectionResult(False, 0.0, "历史样本不足，暂不训练 Isolation Forest")

        # 每次检测重新使用固定种子，使相同窗口获得完全相同的评测结果。
        random = Random(self._seed)
        actual_sample_size = min(self._sample_size, len(history))
        maximum_depth = ceil(log2(actual_sample_size))
        paths: list[float] = []

        for _ in range(self._tree_count):
            # 每棵树无放回采样，减少树之间相关性。
            samples = random.sample(list(history), actual_sample_size)
            # 随机切分只从历史正常窗口学习，不把待检测值泄漏进模型。
            tree = self._build_tree(samples, 0, maximum_depth, random)
            # 异常点通常更快落入小叶节点，因此路径会更短。
            paths.append(self._path_length(current, tree, 0))

        average_path = sum(paths) / len(paths)
        normalization = _average_unsuccessful_path(actual_sample_size)
        # 原始论文分数 2^(-E(h(x))/c(n)) 将不同样本数的路径归一到 0..1。
        score = 2 ** (-average_path / normalization) if normalization > 0 else 0.0
        anomalous = score >= self._threshold
        reason = f"Isolation Forest 分数={score:.3f}，平均路径={average_path:.2f}"
        return DetectionResult(anomalous, score, reason)

    def _build_tree(
        self,
        samples: list[float],
        depth: int,
        maximum_depth: int,
        random: Random,
    ) -> _IsolationNode:
        """递归构造一棵随机隔离树。"""

        minimum = min(samples)
        maximum = max(samples)
        # 到达深度上限、只剩一个样本或所有值相同都必须停止切分。
        if depth >= maximum_depth or len(samples) <= 1 or minimum == maximum:
            return _IsolationNode(size=len(samples))

        # 一维实现只随机选择切分值；多维版本还会随机选择特征列。
        split = random.uniform(minimum, maximum)
        left_samples = [value for value in samples if value < split]
        right_samples = [value for value in samples if value >= split]
        # 浮点边界理论上可能产生空分支，此时作为叶节点安全结束。
        if not left_samples or not right_samples:
            return _IsolationNode(size=len(samples))
        return _IsolationNode(
            size=len(samples),
            split=split,
            left=self._build_tree(left_samples, depth + 1, maximum_depth, random),
            right=self._build_tree(right_samples, depth + 1, maximum_depth, random),
        )

    def _path_length(self, value: float, node: _IsolationNode, depth: int) -> float:
        """返回观测值在树中的路径长度，并修正提前结束的大叶节点。"""

        if node.split is None or node.left is None or node.right is None:
            return depth + _average_unsuccessful_path(node.size)
        child = node.left if value < node.split else node.right
        return self._path_length(value, child, depth + 1)
