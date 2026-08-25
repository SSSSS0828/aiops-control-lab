"""通过 Agent 内部 HTTP 接口执行获批动作。

该适配器用于阶段一单机 Compose 闭环。公共 protobuf 已同时定义 gRPC 接口，
后续切换到主动长连接时应用层和领域层不需要修改。
"""

import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aiops_control.domain.models import RemediationStep, new_id, utc_now
from aiops_control.ports.execution import StepExecutionResult
from aiops_control.security.task_signing import sign_task_payload


class HttpAgentDispatcher:
    """把类型化步骤转换为 Agent 可验证的动作任务。"""

    def __init__(
        self,
        base_url: str,
        shared_secret: str,
        timeout_seconds: float = 35.0,
    ) -> None:
        if not shared_secret:
            raise ValueError("启用真实 Agent 时必须配置共享密钥")
        self._endpoint = f"{base_url.rstrip('/')}/v1/actions/execute"
        self._shared_secret = shared_secret
        self._timeout_seconds = timeout_seconds

    def execute(self, step: RemediationStep, approved_hash: str) -> StepExecutionResult:
        """向内网 Agent 发送短有效期动作并解析审计结果。"""

        now = utc_now()
        expires_at = (now + timedelta(minutes=2)).replace(microsecond=0)
        unsigned_payload = {
            "id": new_id("agent_job"),
            # 计划哈希、动作和目标共同形成稳定键，控制面重试不会重复变更。
            "idempotency_key": f"{approved_hash}:{step.action_type}:{step.target}",
            "approved_hash": approved_hash,
            "action_type": step.action_type,
            "target": step.target,
            "arguments": step.arguments,
            # Agent 不接受长期有效命令，避免网络或队列延迟后执行旧计划。
            # 固定为秒精度和 Z 后缀，确保 Python 与 Go 的规范化表示一致。
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }
        # 所有会影响系统状态的字段都被 HMAC 覆盖，传输中任一字段被改写都会验签失败。
        payload = sign_task_payload(unsigned_payload, self._shared_secret)
        request = Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                result = json.load(response)
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            return StepExecutionResult(False, f"Agent 拒绝动作: {body}")
        except (URLError, TimeoutError) as error:
            return StepExecutionResult(False, f"Agent 不可用: {error}")
        return StepExecutionResult(bool(result.get("succeeded")), str(result.get("message", "")))
