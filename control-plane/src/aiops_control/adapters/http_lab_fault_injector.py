"""通过 Agent 与实验 API 控制端点注入和重置真实故障。

容器退出类故障走已签名 Agent 任务；CPU、延迟和 5xx 走仅在 Compose 私有网络可达、
带独立控制令牌的实验端点。两种路径都只接受代码内注册的场景，不接收任意命令。
"""

import json
from datetime import timedelta
from hashlib import sha256
from urllib.request import Request, urlopen

from aiops_control.domain.models import new_id, utc_now
from aiops_control.security.task_signing import sign_task_payload


class HttpLabFaultInjector:
    """只允许执行五类固定、限时且可自动清理的实验故障。"""

    _container_scenarios = {
        "dependency_unavailable": "lab-redis",
        "api_container_exit": "lab-api",
    }
    _application_scenarios = frozenset({"container_cpu_spike", "request_latency", "http_5xx"})

    def __init__(
        self,
        agent_url: str,
        shared_secret: str,
        lab_api_url: str,
        lab_control_token: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not shared_secret:
            raise ValueError("启用真实故障注入时必须配置 Agent 共享密钥")
        if not lab_api_url or not lab_control_token:
            raise ValueError("启用真实故障注入时必须配置实验 API 地址和控制令牌")
        self._endpoint = f"{agent_url.rstrip('/')}/v1/actions/execute"
        self._lab_api_url = lab_api_url.rstrip("/")
        self._lab_control_token = lab_control_token
        self._shared_secret = shared_secret
        self._timeout_seconds = timeout_seconds

    def inject(self, scenario: str) -> str | None:
        """注入支持的真实故障，纯指标场景返回 None。"""

        target = self._container_scenarios.get(scenario)
        if target is not None:
            succeeded = self._send("stop_container", target, f"inject:{new_id('fault')}")
            if not succeeded:
                raise RuntimeError("Agent 未能停止实验容器")
            return f"container:{target}"
        if scenario in self._application_scenarios:
            # CPU 场景限制为 30 秒，其他状态最长 120 秒并由后台任务再次清理。
            duration_seconds = 30 if scenario == "container_cpu_spike" else 120
            self._set_application_fault(scenario, duration_seconds)
            return f"application:{scenario}"
        return None

    def reset(self, target: str) -> None:
        """超时后恢复实验容器，防止访客离开导致 Demo 长期不可用。"""

        if target.startswith("application:"):
            scenario = target.removeprefix("application:")
            if scenario not in self._application_scenarios:
                raise ValueError("重置目标不是已注册应用故障")
            self._clear_application_fault(scenario)
            return
        if not target.startswith("container:"):
            raise ValueError("重置目标格式无效")
        container_target = target.removeprefix("container:")
        if container_target not in self._container_scenarios.values():
            raise ValueError("重置目标不是已注册实验资产")
        # 用户若已批准修复，健康检查会成功，不再重启一个已经恢复的容器。
        healthy = self._send("health_check", container_target, f"reset-check:{new_id('fault')}")
        if healthy:
            return
        self._send("restart_container", container_target, f"reset:{new_id('fault')}")

    def _set_application_fault(self, scenario: str, duration_seconds: int) -> None:
        """在实验私网内启用有硬超时的应用故障。"""

        body = json.dumps({"duration_seconds": duration_seconds}).encode("utf-8")
        request = Request(
            f"{self._lab_api_url}/__control/faults/{scenario}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Lab-Control-Token": self._lab_control_token,
            },
            method="PUT",
        )
        with urlopen(request, timeout=self._timeout_seconds):  # noqa: S310
            return

    def _clear_application_fault(self, scenario: str) -> None:
        """提前清除应用故障；接口幂等，故障已过期时也返回成功。"""

        request = Request(
            f"{self._lab_api_url}/__control/faults/{scenario}",
            headers={"X-Lab-Control-Token": self._lab_control_token},
            method="DELETE",
        )
        with urlopen(request, timeout=self._timeout_seconds):  # noqa: S310
            return

    def _send(self, action_type: str, target: str, idempotency_key: str) -> bool:
        # 故障注入哈希只证明任务来自控制面内部能力，不冒充人工修复审批。
        approved_hash = sha256(f"lab-fault:{action_type}:{target}".encode()).hexdigest()
        expires_at = (utc_now() + timedelta(minutes=1)).replace(microsecond=0)
        unsigned_payload = {
            "id": new_id("fault_job"),
            "idempotency_key": idempotency_key,
            "approved_hash": approved_hash,
            "action_type": action_type,
            "target": target,
            "arguments": {"grace_seconds": "2"},
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }
        # 故障注入同样属于状态变更，不能绕过正常任务签名边界。
        payload = sign_task_payload(unsigned_payload, self._shared_secret)
        request = Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
            result = json.load(response)
        return bool(result.get("succeeded"))
