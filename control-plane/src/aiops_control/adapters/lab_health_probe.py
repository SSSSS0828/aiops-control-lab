"""故障实验室固定健康端点探测器。

探测目标由部署配置生成，HTTP 请求不能传入任意 URL。Redis 故障通过
lab-api 的依赖健康端点观察，因此能够区分“API 进程存活”和“服务可用”。
"""

import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aiops_control.domain.fault_scenarios import LabObservation


class HttpLabHealthProbe:
    """轮询实验 API 健康端点，并支持故障出现与恢复两个方向的等待。"""

    def __init__(
        self,
        lab_api_url: str,
        *,
        attempts: int = 10,
        interval_seconds: float = 0.25,
        timeout_seconds: float = 2.0,
    ) -> None:
        if not lab_api_url:
            raise ValueError("实验健康探针必须配置固定 API 地址")
        self._endpoint = f"{lab_api_url.rstrip('/')}/healthz"
        self._attempts = attempts
        self._interval_seconds = interval_seconds
        self._timeout_seconds = timeout_seconds

    def observe_failure(self) -> LabObservation:
        """等待依赖故障反映到 API 健康端点。"""

        return self._wait_for(expected_healthy=False)

    def verify(self, target: str) -> dict[str, object]:
        """等待 Redis 恢复后 API 健康端点重新可用。"""

        observation = self._wait_for(expected_healthy=True)
        return {
            "source": observation.source,
            "target": target,
            "probe_target": observation.target,
            "healthy": observation.healthy,
            "status_code": observation.status_code,
            "latency_ms": observation.latency_ms,
            "observed_at": observation.observed_at.isoformat(),
        }

    def _wait_for(self, *, expected_healthy: bool) -> LabObservation:
        last = self._probe_once()
        for _ in range(self._attempts - 1):
            if last.healthy is expected_healthy:
                return last
            time.sleep(self._interval_seconds)
            last = self._probe_once()
        return last

    def _probe_once(self) -> LabObservation:
        started = time.monotonic()
        request = Request(self._endpoint, headers={"User-Agent": "aiops-lab-probe/0.2"})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                status_code = response.status
        except HTTPError as error:
            status_code = error.code
        except (OSError, URLError, TimeoutError):
            status_code = 0
        return LabObservation(
            source="http-health-probe",
            target=self._endpoint,
            healthy=200 <= status_code < 400,
            status_code=status_code,
            latency_ms=round((time.monotonic() - started) * 1_000, 2),
            observed_at=datetime.now(UTC),
        )
