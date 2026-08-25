"""Drain 思想的轻量日志模板解析器。

阶段二先完成变量归一化和模板聚类，不宣称实现完整 Drain 前缀树。
接口与输出已经独立，后续可替换为完整 Drain3 而不影响 Incident 数据模型。
"""

import re
from collections import defaultdict
from hashlib import sha256

from aiops_control.domain.logs import LogCluster, LogEvent, LogTemplate

IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
HEX_PATTERN = re.compile(r"\b(?:0x)?[0-9a-fA-F]{12,}\b")
NUMBER_PATTERN = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
WHITESPACE_PATTERN = re.compile(r"\s+")


class LogTemplateParser:
    """按变量模式归一化并聚合同构日志。"""

    def parse(self, message: str) -> LogTemplate:
        """将动态 IP、UUID、长十六进制和数值替换成稳定占位符。"""

        # 替换顺序很重要：UUID 和 IP 必须先于数字，否则一个变量会被拆碎。
        normalized = UUID_PATTERN.sub("<UUID>", message)
        normalized = IPV4_PATTERN.sub("<IP>", normalized)
        normalized = HEX_PATTERN.sub("<HEX>", normalized)
        normalized = NUMBER_PATTERN.sub("<NUM>", normalized)
        # 合并空白可消除日志格式器对齐宽度造成的无意义模板差异。
        normalized = WHITESPACE_PATTERN.sub(" ", normalized).strip()
        tokens = tuple(normalized.split(" ")) if normalized else ()
        template_id = sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return LogTemplate(id=f"tpl_{template_id}", template=normalized, tokens=tokens)

    def cluster(self, events: list[LogEvent]) -> list[LogCluster]:
        """按模板 ID 聚合日志，并保存少量示例事件引用。"""

        grouped: dict[str, list[LogEvent]] = defaultdict(list)
        templates: dict[str, LogTemplate] = {}
        for event in events:
            template = self.parse(event.message)
            templates[template.id] = template
            grouped[template.id].append(event)
        clusters = [
            LogCluster(
                template=templates[template_id],
                count=len(items),
                example_event_ids=tuple(item.id for item in items[:3]),
            )
            for template_id, items in grouped.items()
        ]
        return sorted(clusters, key=lambda item: item.count, reverse=True)
