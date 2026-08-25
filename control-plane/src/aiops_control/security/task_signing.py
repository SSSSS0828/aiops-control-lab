"""Agent 动作任务的 HMAC-SHA256 签名。

输入：控制面准备下发的任务字典和部署时注入的共享密钥。
处理：规范化截止时间和参数，逐字段计算摘要，再生成 HMAC。
输出：带一次性 nonce 与签名的全新任务字典。
副作用：只使用系统安全随机源产生 nonce，不进行网络或文件访问。
异常路径：密钥为空、字段缺失或字段类型错误时立即拒绝构造任务。

这里使用明确版本号和逐字段摘要，而不是直接签名任意 JSON。这样 Go 与
Python 不会因字典顺序、空格或 Unicode 转义差异算出不同签名。
"""

from __future__ import annotations

import json
import secrets
from hashlib import sha256
from hmac import new as new_hmac
from typing import Any

SIGNATURE_VERSION = "aiops-action-v1"


def sign_task_payload(payload: dict[str, Any], shared_secret: str) -> dict[str, Any]:
    """返回带 nonce 和签名的任务副本，原始字典不会被修改。"""

    if not shared_secret:
        raise ValueError("Agent 共享密钥不能为空")

    # 每次下发都产生 128 位随机 nonce；即使业务字段完全相同，签名也不相同。
    signed_payload = dict(payload)
    signed_payload["nonce"] = secrets.token_hex(16)
    # 签名字段不参与自身摘要，避免循环依赖。
    signed_payload["signature"] = _calculate_signature(signed_payload, shared_secret)
    return signed_payload


def _calculate_signature(payload: dict[str, Any], shared_secret: str) -> str:
    """计算与 Go Agent 完全一致的十六进制 HMAC-SHA256。"""

    canonical = _canonical_message(payload)
    return new_hmac(shared_secret.encode("utf-8"), canonical, sha256).hexdigest()


def _canonical_message(payload: dict[str, Any]) -> bytes:
    """把允许签名的字段转换为跨语言稳定字节序列。"""

    required_string_fields = (
        "id",
        "idempotency_key",
        "approved_hash",
        "action_type",
        "target",
        "expires_at",
        "nonce",
    )
    values: list[str] = []
    for field_name in required_string_fields:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"任务字段 {field_name} 必须是非空字符串")
        # 对可变长度字段先做摘要，避免换行符造成字段边界歧义。
        values.append(sha256(value.encode("utf-8")).hexdigest())

    arguments = payload.get("arguments")
    if not isinstance(arguments, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in arguments.items()
    ):
        raise ValueError("任务 arguments 必须是字符串到字符串的映射")
    # sort_keys 和紧凑分隔符确保参数插入顺序不会改变摘要。
    arguments_json = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    values.append(sha256(arguments_json.encode("utf-8")).hexdigest())
    return (SIGNATURE_VERSION + "\n" + "\n".join(values)).encode("utf-8")
