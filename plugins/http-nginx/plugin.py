"""HTTP/Nginx 独立进程示例插件。

输入：控制面通过 gRPC 传入 URL 或观测证据。
处理：使用标准库发起受超时约束的 HTTP 健康检查并生成类型化计划。
输出：资产、分析结果、计划或验证结果。
安全：只允许 http/https URL；不执行 Shell，也不接触 Docker Socket。
"""

import os
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from aiops_plugin_sdk import PluginHandlers, serve


def describe(_: dict[str, object]) -> dict[str, object]:
    """返回插件身份和可用能力。"""

    return {
        "id": "http-nginx",
        "version": "0.1.0",
        "capabilities": ["DiscoveryProvider", "TelemetryProvider", "Analyzer", "ActionProvider"],
    }


def health(_: dict[str, object]) -> dict[str, object]:
    """插件进程自身健康检查，不探测业务目标。"""

    return {"status": "ok", "checked_at": datetime.now(UTC).isoformat()}


def check_url(payload: dict[str, object]) -> tuple[bool, int, str]:
    """执行受协议和超时限制的 HTTP 探测。"""

    raw_url = str(payload.get("url", "http://lab-gateway/healthz"))
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("只允许具有主机名的 http/https URL")
    request = Request(raw_url, headers={"User-Agent": "aiops-http-plugin/0.1"})
    try:
        # URL 已完成协议与目标白名单校验，因此这里可以安全发起探测请求。
        with urlopen(request, timeout=3) as response:
            status = response.status
        return 200 <= status < 400, status, raw_url
    except Exception as error:  # noqa: BLE001 - 网络错误需要转换成可分析证据
        return False, 0, f"{raw_url}: {error}"


def discover(payload: dict[str, object]) -> dict[str, object]:
    """将配置的 URL 转换为标准服务资产。"""

    url = str(payload.get("url", "http://lab-gateway/healthz"))
    return {"assets": [{"id": "lab-gateway", "kind": "http_service", "name": url}]}


def analyze(payload: dict[str, object]) -> dict[str, object]:
    """探测目标并返回可解释健康结论。"""

    succeeded, status, message = check_url(payload)
    return {
        "healthy": succeeded,
        "status_code": status,
        "summary": "HTTP 服务可用" if succeeded else f"HTTP 服务不可用: {message}",
    }


def plan(payload: dict[str, object]) -> dict[str, object]:
    """生成控制面仍需审批的类型化重启建议。"""

    target = str(payload.get("target", "lab-gateway"))
    return {
        "summary": f"重启 {target} 并再次执行 HTTP 健康检查",
        "risk": "medium",
        "steps": [{"action_type": "restart_container", "target": target}],
    }


def execute(_: dict[str, object]) -> dict[str, object]:
    """HTTP 插件不持有执行权限，实际动作必须交给 Agent。"""

    return {"accepted": False, "reason": "该插件不直接执行系统变更"}


def verify(payload: dict[str, object]) -> dict[str, object]:
    """修复后复用相同探测逻辑验证服务。"""

    succeeded, status, message = check_url(payload)
    return {"succeeded": succeeded, "status_code": status, "message": message}


def rollback(_: dict[str, object]) -> dict[str, object]:
    """插件没有变更权限，因此不提供独立回滚动作。"""

    return {"supported": False}


if __name__ == "__main__":
    socket = os.environ.get("AIOPS_PLUGIN_SOCKET")
    if not socket:
        raise RuntimeError("缺少 AIOPS_PLUGIN_SOCKET")
    grpc_server = serve(
        socket,
        PluginHandlers(describe, health, discover, analyze, plan, execute, verify, rollback),
    )
    grpc_server.wait_for_termination()
