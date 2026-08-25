"""Embedding 生成端口。"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """将文本转换为定长向量，允许本地算法和云模型互换。"""

    def embed(self, text: str) -> tuple[float, ...]: ...
