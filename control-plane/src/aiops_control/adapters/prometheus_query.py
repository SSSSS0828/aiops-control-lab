"""Prometheus HTTP API 查询适配器。

输入：应用层给出的 PromQL、UTC 时间窗口和步长。
处理：编码查询参数、限制超时、校验 API 状态并把 matrix 展平为领域样本。
输出：按时间排序的 MetricSample；不复制响应 JSON 到 Incident。
异常：网络错误、非 success 响应或非法数值统一转换为 ExternalSourceError。
"""

import json
import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aiops_control.domain.errors import ExternalSourceError
from aiops_control.domain.telemetry import MetricSample

JsonReader = Callable[[str, float], dict[str, Any]]


class PrometheusRangeQuery:
    """通过 `/api/v1/query_range` 实现指标查询端口。"""

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
        step_seconds: int,
    ) -> tuple[MetricSample, ...]:
        """查询并解析一个 PromQL 时间窗口。"""

        parameters = urlencode(
            {
                "query": query,
                "start": started_at.timestamp(),
                "end": ended_at.timestamp(),
                "step": step_seconds,
            }
        )
        payload = self._reader(
            f"{self._base_url}/api/v1/query_range?{parameters}",
            self._timeout_seconds,
        )
        if payload.get("status") != "success":
            raise ExternalSourceError(f"Prometheus 查询失败：{payload.get('error', '未知错误')}")

        data = payload.get("data")
        if not isinstance(data, dict) or data.get("resultType") != "matrix":
            raise ExternalSourceError("Prometheus 返回的结果类型不是 matrix")
        result = data.get("result")
        if not isinstance(result, list):
            raise ExternalSourceError("Prometheus 返回的 result 不是列表")

        samples: list[MetricSample] = []
        for series in result:
            if not isinstance(series, dict):
                continue
            labels = _string_labels(series.get("metric"))
            values = series.get("values")
            if not isinstance(values, list):
                continue
            for pair in values:
                sample = _parse_sample(pair, labels)
                if sample is not None:
                    samples.append(sample)
        return tuple(sorted(samples, key=lambda item: item.occurred_at))


def _string_labels(raw: object) -> dict[str, str]:
    """只保留字符串标签，阻止任意 JSON 对象泄漏到领域层。"""

    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _parse_sample(raw: object, labels: dict[str, str]) -> MetricSample | None:
    """把 `[Unix 秒, 字符串数值]` 转换为有限浮点样本。"""

    if not isinstance(raw, list) or len(raw) != 2:
        return None
    try:
        timestamp = float(raw[0])
        value = float(raw[1])
    except (TypeError, ValueError):
        return None
    # NaN 和无穷值不能参与摘要统计，否则会污染最大值、最小值和异常分数。
    if not math.isfinite(timestamp) or not math.isfinite(value):
        return None
    return MetricSample(datetime.fromtimestamp(timestamp, UTC), value, labels.copy())


def _read_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    """执行只读 JSON 请求，并把网络与解析错误转换为稳定领域异常。"""

    request = Request(url, headers={"User-Agent": "aiops-control-plane/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise ExternalSourceError(f"Prometheus 不可用：{error}") from error
    if not isinstance(payload, dict):
        raise ExternalSourceError("Prometheus 响应不是 JSON 对象")
    return payload
