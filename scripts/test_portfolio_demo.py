"""对运行中的 Compose 环境执行 Redis 故障闭环验收。"""

import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8088"


def request_json(path: str, payload: dict[str, Any] | None = None) -> Any:
    """向本地演示入口发送 JSON 请求。"""

    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def wait_until_ready() -> None:
    """等待反向代理和控制面健康。"""

    for _ in range(60):
        try:
            with urlopen(f"{BASE_URL}/healthz", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError, TimeoutError):
            time.sleep(2)
    raise RuntimeError("AIOps Compose 环境在 120 秒内未就绪")


def main() -> None:
    """验证真实 503、规则降级、审批恢复和最终 Incident 状态。"""

    wait_until_ready()
    status = request_json("/api/v1/diagnostics/status")
    assert status["degraded"] is True

    injected = request_json(
        "/api/v1/labs/inject",
        {"scenario": "dependency_unavailable"},
    )
    observation = injected["observation"]
    assert observation["source"] == "http-health-probe"
    assert observation["status_code"] == 503
    assert observation["healthy"] is False

    plan = request_json(f"/api/v1/plans/{injected['plan']['id']}")
    diagnosis = request_json(
        "/api/v1/diagnostics/query",
        {
            "question": "Redis 依赖不可用导致 API 健康检查失败，应该如何排查？",
            "evidence": [
                f"{observation['target']} 返回 HTTP {observation['status_code']}",
                injected["detection"]["reason"],
            ],
        },
    )
    assert diagnosis["degraded"] is True

    approved = request_json(
        f"/api/v1/plans/{plan['id']}/approve",
        {
            "approver": "compose-ci",
            "approved_hash": plan["content_hash"],
            "idempotency_key": f"compose-{plan['id']}",
        },
    )
    assert approved["status"] == "succeeded"
    assert approved["output"]["verification"]["healthy"] is True
    assert approved["output"]["verification"]["status_code"] == 200

    incidents = request_json("/api/v1/incidents")
    assert incidents[0]["status"] == "resolved"
    print("portfolio demo passed: Redis 503 -> diagnosis -> approval -> HTTP 200")


if __name__ == "__main__":
    main()
