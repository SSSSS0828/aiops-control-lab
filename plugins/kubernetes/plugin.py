"""Kubernetes/k3s 独立进程插件。

输入：命名空间、资源名、获批动作及参数。
处理：使用 ServiceAccount Token 直接调用 Kubernetes HTTPS API。
输出：节点/工作负载资产、Warning 事件、计划、执行与验证结果。
安全：写操作仅限环境变量允许的命名空间和 Deployment；不执行 kubectl 或 Shell。
"""

import json
import os
import re
import ssl
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from aiops_plugin_sdk import PluginHandlers, serve

TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class KubernetesClient:
    """阶段三使用的最小 Kubernetes API 客户端。"""

    def __init__(self) -> None:
        host = os.getenv("KUBERNETES_SERVICE_HOST", "127.0.0.1")
        port = os.getenv("KUBERNETES_SERVICE_PORT", "6443")
        self._base_url = os.getenv("AIOPS_KUBERNETES_URL", f"https://{host}:{port}")
        self._token_path = Path(os.getenv("AIOPS_KUBERNETES_TOKEN_PATH", str(TOKEN_PATH)))
        ca_path = Path(os.getenv("AIOPS_KUBERNETES_CA_PATH", str(CA_PATH)))
        ca_file = str(ca_path) if ca_path.exists() else None
        self._ssl_context = ssl.create_default_context(cafile=ca_file)
        configured = os.getenv("AIOPS_KUBERNETES_NAMESPACES", "aiops-lab")
        self.allowed_namespaces = frozenset(
            namespace.strip() for namespace in configured.split(",") if namespace.strip()
        )

    def get(self, path: str) -> dict[str, Any]:
        """读取 Kubernetes JSON 资源。"""

        return self._request(path, "GET", None)

    def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """使用 JSON Merge Patch 更新允许的工作负载字段。"""

        return self._request(path, "PATCH", body)

    def deployment_path(self, namespace: str, name: str, suffix: str = "") -> str:
        """验证命名空间和资源名后构造 Deployment API 路径。"""

        if namespace not in self.allowed_namespaces:
            raise ValueError(f"命名空间 {namespace!r} 不在允许范围内")
        if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", name):
            raise ValueError("Deployment 名称格式无效")
        return (
            f"/apis/apps/v1/namespaces/{quote(namespace)}/deployments/{quote(name)}{suffix}"
        )

    def _request(
        self,
        path: str,
        method: str,
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self._token_path.is_file():
            raise RuntimeError("找不到 Kubernetes ServiceAccount Token")
        token = self._token_path.read_text(encoding="utf-8").strip()
        request = Request(
            f"{self._base_url}{path}",
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/merge-patch+json",
            },
            method=method,
        )
        # 地址只能来自类型化集群配置，并使用服务账户 CA 校验，禁止接收模型生成的 URL。
        with urlopen(request, timeout=8, context=self._ssl_context) as response:
            return json.load(response)


client = KubernetesClient()


def describe(_: dict[str, object]) -> dict[str, object]:
    """返回插件版本、能力和当前允许命名空间。"""

    return {
        "id": "kubernetes",
        "version": "0.1.0",
        "capabilities": ["DiscoveryProvider", "TelemetryProvider", "Analyzer", "ActionProvider"],
        "allowed_namespaces": sorted(client.allowed_namespaces),
    }


def health(_: dict[str, object]) -> dict[str, object]:
    """仅检查插件进程配置；集群连通性由 Analyze 显式报告。"""

    configured = bool(client.allowed_namespaces)
    return {"status": "ok" if configured else "misconfigured"}


def discover(payload: dict[str, object]) -> dict[str, object]:
    """发现节点、Pod 和 Deployment，并转换为标准资产。"""

    namespace = str(payload.get("namespace", next(iter(client.allowed_namespaces), "")))
    if namespace not in client.allowed_namespaces:
        raise ValueError("请求的命名空间不在允许范围内")
    nodes = client.get("/api/v1/nodes").get("items", [])
    pods = client.get(f"/api/v1/namespaces/{quote(namespace)}/pods").get("items", [])
    deployments = client.get(f"/apis/apps/v1/namespaces/{quote(namespace)}/deployments").get(
        "items", []
    )
    assets = [
        {
            "id": f"k8s:node:{item['metadata']['name']}",
            "kind": "k8s_node",
            "name": item["metadata"]["name"],
        }
        for item in nodes
    ]
    assets.extend(
        {
            "id": f"k8s:{namespace}:pod:{item['metadata']['name']}",
            "kind": "k8s_pod",
            "name": item["metadata"]["name"],
        }
        for item in pods
    )
    assets.extend(
        {
            "id": f"k8s:{namespace}:deployment:{item['metadata']['name']}",
            "kind": "k8s_deployment",
            "name": item["metadata"]["name"],
        }
        for item in deployments
    )
    return {"assets": assets}


def analyze(payload: dict[str, object]) -> dict[str, object]:
    """读取命名空间 Warning 事件作为 Kubernetes 诊断证据。"""

    namespace = str(payload.get("namespace", next(iter(client.allowed_namespaces), "")))
    if namespace not in client.allowed_namespaces:
        raise ValueError("请求的命名空间不在允许范围内")
    path = f"/api/v1/namespaces/{quote(namespace)}/events?fieldSelector=type%3DWarning"
    events = client.get(path).get("items", [])
    evidence = [
        {
            "reason": item.get("reason", "Unknown"),
            "message": item.get("message", ""),
            "asset": item.get("involvedObject", {}).get("name", ""),
        }
        for item in events[-20:]
    ]
    return {"healthy": not evidence, "warning_events": evidence}


def plan(payload: dict[str, object]) -> dict[str, object]:
    """为 Deployment 生成受命名空间限制的类型化计划。"""

    namespace = str(payload.get("namespace", ""))
    name = str(payload.get("name", ""))
    client.deployment_path(namespace, name)
    action = str(payload.get("action", "rollout_restart"))
    if action not in {"rollout_restart", "scale"}:
        raise ValueError("只允许 rollout_restart 或 scale")
    return {
        "summary": f"对 {namespace}/{name} 执行 {action}",
        "risk": "medium",
        "steps": [{"action_type": action, "target": f"k8s:{namespace}:deployment:{name}"}],
    }


def execute(payload: dict[str, object]) -> dict[str, object]:
    """审批哈希有效时执行 rollout restart 或受限 scale。"""

    approved_hash = str(payload.get("approved_hash", ""))
    if not HASH_PATTERN.fullmatch(approved_hash):
        raise ValueError("缺少合法批准哈希")
    namespace = str(payload.get("namespace", ""))
    name = str(payload.get("name", ""))
    action = str(payload.get("action", ""))
    if action == "rollout_restart":
        path = client.deployment_path(namespace, name)
        restarted_at = datetime.now(UTC).isoformat()
        body = {
            "spec": {
                "template": {"metadata": {"annotations": {"aiops/restartedAt": restarted_at}}}
            }
        }
    elif action == "scale":
        replicas = int(payload.get("replicas", -1))
        if not 0 <= replicas <= 10:
            raise ValueError("实验环境副本数必须在 0 到 10 之间")
        path = client.deployment_path(namespace, name, "/scale")
        body = {"spec": {"replicas": replicas}}
    else:
        raise ValueError("动作不在 Kubernetes 允许列表内")
    result = client.patch(path, body)
    resource_version = result.get("metadata", {}).get("resourceVersion", "")
    return {"succeeded": True, "resource_version": resource_version}


def verify(payload: dict[str, object]) -> dict[str, object]:
    """检查 Deployment 可用副本是否达到目标副本。"""

    namespace = str(payload.get("namespace", ""))
    name = str(payload.get("name", ""))
    deployment = client.get(client.deployment_path(namespace, name))
    desired = int(deployment.get("spec", {}).get("replicas", 0))
    available = int(deployment.get("status", {}).get("availableReplicas", 0))
    return {"succeeded": available >= desired, "desired": desired, "available": available}


def rollback(payload: dict[str, object]) -> dict[str, object]:
    """只允许恢复控制面事先捕获的副本数。"""

    restored = dict(payload)
    restored["action"] = "scale"
    restored["replicas"] = int(payload.get("previous_replicas", -1))
    return execute(restored)


if __name__ == "__main__":
    socket = os.environ.get("AIOPS_PLUGIN_SOCKET")
    if not socket:
        raise RuntimeError("缺少 AIOPS_PLUGIN_SOCKET")
    handlers = PluginHandlers(describe, health, discover, analyze, plan, execute, verify, rollback)
    server = serve(socket, handlers)
    server.wait_for_termination()
