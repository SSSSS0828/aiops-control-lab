"""控制面到 Agent 的任务签名契约测试。"""

from aiops_control.security import task_signing


def test_task_signature_is_stable_across_languages(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """固定向量必须与 Go 测试一致，防止两端规范化规则悄悄漂移。"""

    monkeypatch.setattr(
        task_signing.secrets,
        "token_hex",
        lambda _: "00112233445566778899aabbccddeeff",
    )
    payload = {
        "id": "job-vector",
        "idempotency_key": "request-vector",
        "approved_hash": "a" * 64,
        "action_type": "restart_container",
        "target": "lab-api",
        "arguments": {"grace_seconds": "10", "说明": "安全重启"},
        "expires_at": "2030-01-02T03:04:05Z",
    }
    signed = task_signing.sign_task_payload(payload, "0123456789abcdef0123456789abcdef")
    assert signed["nonce"] == "00112233445566778899aabbccddeeff"
    assert signed["signature"] == (
        "f1a8dddd27efa5d933a227e0e24f560282517b843b0cfb118ab51eeb999b3009"
    )


def test_task_signature_changes_after_target_is_modified(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """任何状态变更字段被修改后，都不能继续复用原签名。"""

    monkeypatch.setattr(task_signing.secrets, "token_hex", lambda _: "0" * 32)
    payload = {
        "id": "job-1",
        "idempotency_key": "request-1",
        "approved_hash": "b" * 64,
        "action_type": "health_check",
        "target": "lab-api",
        "arguments": {},
        "expires_at": "2030-01-02T03:04:05Z",
    }
    signed = task_signing.sign_task_payload(payload, "0123456789abcdef0123456789abcdef")
    modified = dict(signed)
    modified["target"] = "lab-redis"
    assert (
        task_signing._calculate_signature(  # noqa: SLF001
            modified, "0123456789abcdef0123456789abcdef"
        )
        != signed["signature"]
    )
