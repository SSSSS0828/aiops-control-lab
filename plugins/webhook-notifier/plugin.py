"""通用 Webhook 通知独立进程插件。

输入：获批哈希、目标 URL、Incident 标识、严重度和消息。
处理：校验协议、主机白名单、消息长度和审批哈希后发送固定 JSON。
输出：HTTP 状态码和投递结果；不允许自定义请求头或任意请求体。
"""

import ipaddress
import json
import os
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from aiops_plugin_sdk import PluginHandlers, serve

HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
allowed_hosts = frozenset(
    host.strip().lower()
    for host in os.getenv("AIOPS_WEBHOOK_ALLOWED_HOSTS", "localhost").split(",")
    if host.strip()
)


def _validated_url(payload: dict[str, object]) -> str:
    """验证 URL 协议、主机白名单并拒绝 IP 字面量。"""

    url = str(payload.get("url", ""))
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("Webhook 必须使用 http/https 并包含主机名")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("Webhook 不允许使用 IP 字面量")
    if hostname not in allowed_hosts:
        raise ValueError(f"Webhook 主机 {hostname!r} 不在允许列表内")
    return url


def describe(_: dict[str, object]) -> dict[str, object]:
    """返回插件身份和允许主机。"""

    return {
        "id": "webhook-notifier",
        "version": "0.1.0",
        "capabilities": ["Notifier", "ActionProvider"],
        "allowed_hosts": sorted(allowed_hosts),
    }


def health(_: dict[str, object]) -> dict[str, object]:
    """至少配置一个白名单主机时插件健康。"""

    return {"status": "ok" if allowed_hosts else "misconfigured"}


def discover(_: dict[str, object]) -> dict[str, object]:
    """通知插件不发现基础设施资产。"""

    return {"assets": []}


def analyze(payload: dict[str, object]) -> dict[str, object]:
    """在发送前验证目标 URL。"""

    url = _validated_url(payload)
    return {"valid": True, "target": url}


def plan(payload: dict[str, object]) -> dict[str, object]:
    """生成低风险通知计划，仍由控制面策略决定是否审批。"""

    url = _validated_url(payload)
    return {
        "summary": f"向 {url} 发送 Incident 通知",
        "risk": "low",
        "steps": [{"action_type": "send_webhook", "target": url}],
    }


def execute(payload: dict[str, object]) -> dict[str, object]:
    """发送固定字段通知，阻止模型注入自定义协议字段。"""

    approved_hash = str(payload.get("approved_hash", ""))
    if not HASH_PATTERN.fullmatch(approved_hash):
        raise ValueError("缺少合法批准哈希")
    url = _validated_url(payload)
    message = str(payload.get("message", ""))[:4_000]
    body = {
        "incident_id": str(payload.get("incident_id", ""))[:128],
        "severity": str(payload.get("severity", "unknown"))[:32],
        "message": message,
    }
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "aiops-notifier/0.1"},
        method="POST",
    )
    # URL 已经过协议、主机和 IP 字面量检查，避免通知能力退化为任意 SSRF 通道。
    with urlopen(request, timeout=5) as response:
        status_code = response.status
    return {"succeeded": 200 <= status_code < 300, "status_code": status_code}


def verify(payload: dict[str, object]) -> dict[str, object]:
    """Webhook 是一次性投递，验证结果来自 Execute HTTP 状态。"""

    return {"succeeded": bool(payload.get("delivery_succeeded", False))}


def rollback(_: dict[str, object]) -> dict[str, object]:
    """已发送通知不可撤回。"""

    return {"supported": False, "reason": "Webhook 投递不可逆"}


if __name__ == "__main__":
    socket = os.environ.get("AIOPS_PLUGIN_SOCKET")
    if not socket:
        raise RuntimeError("缺少 AIOPS_PLUGIN_SOCKET")
    handlers = PluginHandlers(describe, health, discover, analyze, plan, execute, verify, rollback)
    server = serve(socket, handlers)
    server.wait_for_termination()
