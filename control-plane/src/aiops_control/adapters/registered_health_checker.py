"""真实 devops-lab 固定健康目标检查器。

目标名称和 URL 都由控制面部署配置生成，HTTP API 不接受任意地址，避免把健康检查变成
服务端请求伪造入口。响应正文不会进入日志或数据库，只保留状态码、延迟和错误类别。
"""

import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class HealthTarget:
    """一个只读固定健康探针。"""

    id: str
    asset_id: str
    url: str


DEFAULT_HEALTH_TARGETS = (
    HealthTarget("devops-nginx", "docker/devops-lab/nginx", "http://devops-nginx/"),
    HealthTarget("devops-api", "docker/devops-lab/api", "http://devops-api:8000/health"),
    HealthTarget(
        "devops-prometheus",
        "docker/devops-lab/prometheus",
        "http://devops-prometheus:9090/-/ready",
    ),
    HealthTarget(
        "devops-grafana", "docker/devops-lab/grafana", "http://devops-grafana:3000/api/health"
    ),
    HealthTarget(
        "devops-alertmanager",
        "docker/devops-lab/alertmanager",
        "http://devops-alertmanager:9093/-/ready",
    ),
)


class RegisteredHealthChecker:
    """只检查构造时登记的固定目标。"""

    def __init__(self, targets: tuple[HealthTarget, ...] = DEFAULT_HEALTH_TARGETS) -> None:
        self._targets = targets

    def check_all(self) -> list[dict[str, str | int | float | bool]]:
        """顺序执行少量探针，单目标最多等待两秒。"""

        return [self._check(target) for target in self._targets]

    def _check(self, target: HealthTarget) -> dict[str, str | int | float | bool]:
        started = time.monotonic()
        request = Request(target.url, headers={"User-Agent": "aiops-health-check/0.2"})
        try:
            with urlopen(request, timeout=2) as response:
                status_code = response.status
            error = ""
        except HTTPError as exception:
            status_code = exception.code
            error = "http_error"
        except (OSError, URLError, TimeoutError):
            status_code = 0
            error = "unreachable"
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        return {
            "id": target.id,
            "asset_id": target.asset_id,
            "healthy": 200 <= status_code < 400,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "error": error,
        }
