"""Runbook 与历史事件的关键词/向量混合检索。

关键词分数擅长保留容器名、错误码等精确运维词；Embedding 分数容忍自然语言改写。
两类分数分别输出，便于实验调权和解释检索结果。
"""

import re
from collections import Counter
from math import log, sqrt

from aiops_control.domain.knowledge import KnowledgeDocument, RetrievalHit
from aiops_control.ports.embeddings import EmbeddingProvider

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_./:-]+|[\u4e00-\u9fff]")


class HybridRetrievalService:
    """在小规模单机知识库上执行内存混合检索。"""

    def __init__(
        self,
        documents: list[KnowledgeDocument],
        embedding_provider: EmbeddingProvider,
        semantic_weight: float = 0.45,
    ) -> None:
        if not 0 <= semantic_weight <= 1:
            raise ValueError("语义权重必须位于 0..1")
        self._documents = documents
        self._embedding_provider = embedding_provider
        self._semantic_weight = semantic_weight
        self._document_vectors = {
            document.id: embedding_provider.embed(self._searchable_text(document))
            for document in documents
        }

    def search(self, query: str, limit: int = 5) -> list[RetrievalHit]:
        """按综合分数返回带稳定引用的知识片段。"""

        if not query.strip() or limit < 1:
            return []
        query_tokens = self._tokens(query)
        query_vector = self._embedding_provider.embed(query)
        document_frequencies = Counter(
            token
            for document in self._documents
            for token in set(self._tokens(self._searchable_text(document)))
        )
        hits: list[RetrievalHit] = []

        for document in self._documents:
            document_tokens = self._tokens(self._searchable_text(document))
            keyword_score = self._keyword_score(
                query_tokens,
                document_tokens,
                document_frequencies,
            )
            semantic_score = max(
                self._cosine(query_vector, self._document_vectors[document.id]),
                0.0,
            )
            score = (
                1 - self._semantic_weight
            ) * keyword_score + self._semantic_weight * semantic_score
            hits.append(
                RetrievalHit(
                    document=document,
                    score=score,
                    keyword_score=keyword_score,
                    semantic_score=semantic_score,
                    citation=f"[{document.title}]({document.source})",
                )
            )
        return sorted(hits, key=lambda item: item.score, reverse=True)[:limit]

    def _keyword_score(
        self,
        query_tokens: list[str],
        document_tokens: list[str],
        document_frequencies: Counter[str],
    ) -> float:
        """计算带 IDF 和长度归一化的轻量关键词分数。"""

        if not query_tokens or not document_tokens:
            return 0.0
        term_counts = Counter(document_tokens)
        document_count = max(len(self._documents), 1)
        raw_score = 0.0
        for token in set(query_tokens):
            frequency = term_counts[token]
            if frequency == 0:
                continue
            inverse_document_frequency = log(1 + document_count / (1 + document_frequencies[token]))
            raw_score += (frequency / (frequency + 1.2)) * inverse_document_frequency
        # 压缩到 0..1，保证可与余弦相似度稳定加权。
        return raw_score / (1 + raw_score)

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        """计算等长向量余弦相似度。"""

        left_norm = sqrt(sum(value * value for value in left))
        right_norm = sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        dot_product = sum(a * b for a, b in zip(left, right, strict=True))
        return dot_product / (left_norm * right_norm)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        """提取运维标识符、英文词和中文字符。"""

        return TOKEN_PATTERN.findall(text.lower())

    @staticmethod
    def _searchable_text(document: KnowledgeDocument) -> str:
        """将标题、正文和标签合并为统一检索文本。"""

        return " ".join((document.title, document.body, *document.tags))
