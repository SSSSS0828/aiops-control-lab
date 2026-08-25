"""无需模型下载的哈希 Embedding。

它不是通用语义模型，而是阶段二离线回退和测试替身：英文单词、数字及中文双字片段
会稳定映射到向量维度。生产配置可以通过同一端口替换成云 Embedding API。
"""

import re
from hashlib import sha256
from math import sqrt

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


class HashingEmbeddingProvider:
    """使用特征哈希生成定长归一化稀疏向量。"""

    def __init__(self, dimensions: int = 192) -> None:
        if dimensions < 32:
            raise ValueError("向量维度不能小于 32")
        self._dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        """对词元和中文双字片段执行带符号特征哈希。"""

        base_tokens = TOKEN_PATTERN.findall(text.lower())
        chinese = [token for token in base_tokens if "\u4e00" <= token <= "\u9fff"]
        bigrams = [f"{left}{right}" for left, right in zip(chinese, chinese[1:], strict=False)]
        vector = [0.0] * self._dimensions
        for token in [*base_tokens, *bigrams]:
            digest = sha256(token.encode("utf-8")).digest()
            # 前八字节选择维度，第九字节提供符号以减轻哈希碰撞偏差。
            index = int.from_bytes(digest[:8], "big") % self._dimensions
            direction = 1.0 if digest[8] & 1 else -1.0
            vector[index] += direction
        norm = sqrt(sum(value * value for value in vector))
        if norm == 0:
            return tuple(vector)
        return tuple(value / norm for value in vector)
