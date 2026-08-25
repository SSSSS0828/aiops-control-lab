"""Loki HTTP API 查询适配器。

输入：应用层给出的 LogQL、UTC 时间窗口和数量上限。
处理：编码查询、校验 streams 响应、将纳秒时间戳转换为 UTC 时间。
输出：按时间排序的短生命周期 LogRecord；原始日志不会进入 Incident。
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aiops_control.domain.errors import ExternalSourceError
from aiops_control.domain.telemetry import LogRecord

JsonReader = Callable[[str, float], dict[str, Any]]


class LokiRangeQuery:
    """通过 `/loki/api/v1/query_range` 实现日志查询端口。"""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 8.0,
        reader: JsonReader | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._reader = reader or _read_json

    def query_range(
        self,
        query: str,
        started_at: datetime,
        ended_at: datetime,
        limit: int,
    ) -> tuple[LogRecord, ...]:
        """查询并解析一个 LogQL 时间窗口。"""

        parameters = urlencode(
            {
                "query": query,
                # Loki 使用 Unix 纳秒；整数转换避免科学计数法造成兼容性差异。
                "start": int(started_at.timestamp() * 1_000_000_000),
                "end": int(ended_at.timestamp() * 1_000_000_000),
                "limit": limit,
                "direction": "backward",
            }
        )
        payload = self._reader(
            f"{self._base_url}/loki/api/v1/query_range?{parameters}",
            self._timeout_seconds,
        )
        if payload.get("status") != "success":
            raise ExternalSourceError(f"Loki 查询失败：{payload.get('error', '未知错误')}")
        data = payload.get("data")
        if not isinstance(data, dict) or data.get("resultType") != "streams":
            raise ExternalSourceError("Loki 返回的结果类型不是 streams")

        records: list[LogRecord] = []
        result = data.get("result", [])
        if not isinstance(result, list):
            raise ExternalSourceError("Loki 返回的 result 不是列表")
        for stream in result:
            if not isinstance(stream, dict):
                continue
            labels = _string_labels(stream.get("stream"))
            values = stream.get("values")
            if not isinstance(values, list):
                continue
            for pair in values:
                record = _parse_record(pair, labels)
                if record is not None:
                    records.append(record)
        return tuple(sorted(records, key=lambda item: item.occurred_at))


def _string_labels(raw: object) -> dict[str, str]:
    """把 Loki stream 标签收敛为字符串字典。"""

    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _parse_record(raw: object, labels: dict[str, str]) -> LogRecord | None:
    """解析 Loki 的 `[纳秒时间戳, 日志文本]`。"""

    if not isinstance(raw, list) or len(raw) != 2:
        return None
    try:
        nanoseconds = int(raw[0])
    except (TypeError, ValueError):
        return None
    if nanoseconds < 0 or not isinstance(raw[1], str):
        return None
    occurred_at = datetime.fromtimestamp(nanoseconds / 1_000_000_000, UTC)
    return LogRecord(occurred_at, raw[1], labels.copy())


def _read_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    """执行 Loki 只读 JSON 请求，并归一化网络错误。"""

    request = Request(url, headers={"User-Agent": "aiops-control-plane/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise ExternalSourceError(f"Loki 不可用：{error}") from error
    if not isinstance(payload, dict):
        raise ExternalSourceError("Loki 响应不是 JSON 对象")
    return payload
