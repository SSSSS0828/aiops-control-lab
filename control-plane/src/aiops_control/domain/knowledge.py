"""Runbook、复盘和历史 Incident 的知识检索模型。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """可以被混合检索并形成引用的知识文档。"""

    id: str
    title: str
    body: str
    source: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """包含关键词、语义和综合分数的检索结果。"""

    document: KnowledgeDocument
    score: float
    keyword_score: float
    semantic_score: float
    citation: str
