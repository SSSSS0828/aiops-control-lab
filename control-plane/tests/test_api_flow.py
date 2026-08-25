"""阶段一 HTTP API 垂直闭环测试。"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from aiops_control.api.app import create_app
from aiops_control.domain.fault_scenarios import LabObservation


class RecordingFaultInjector:
    """模拟真实故障注入器，并记录未通过探测时的恢复调用。"""

    def __init__(self) -> None:
        self.reset_targets: list[str] = []

    def inject(self, scenario: str) -> str:
        assert scenario == "dependency_unavailable"
        return "container:lab-redis"

    def reset(self, target: str) -> None:
        self.reset_targets.append(target)


class FailedDependencyProbe:
    """返回来自固定 HTTP 端点的真实式故障观测。"""

    def observe_failure(self) -> LabObservation:
        return LabObservation(
            source="http-health-probe",
            target="http://lab-api:8080/healthz",
            healthy=False,
            status_code=503,
            latency_ms=12.5,
            observed_at=datetime.now(UTC),
        )


def test_fault_to_approved_recovery_flow() -> None:
    """故障注入、计划读取、审批执行和 Incident 恢复应形成完整链路。"""

    with TestClient(create_app()) as client:
        injected = client.post(
            "/api/v1/labs/inject",
            json={"scenario": "container_cpu_spike"},
        )
        assert injected.status_code == 200
        outcome = injected.json()
        assert outcome["detection"]["anomalous"] is True
        assert outcome["incident"]["status"] == "waiting_approval"

        plan_id = outcome["plan"]["id"]
        plan_response = client.get(f"/api/v1/plans/{plan_id}")
        assert plan_response.status_code == 200
        plan = plan_response.json()
        assert len(plan["content_hash"]) == 64

        approved = client.post(
            f"/api/v1/plans/{plan_id}/approve",
            json={
                "approver": "test-admin",
                "approved_hash": plan["content_hash"],
                "idempotency_key": "api-test-request-001",
            },
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "succeeded"

        incidents = client.get("/api/v1/incidents").json()
        assert incidents[0]["status"] == "resolved"


def test_dependency_fault_uses_observed_health_instead_of_fixture() -> None:
    """Redis 故障必须返回固定健康端点的实际观测字段。"""

    app = create_app()
    app.state.container.fault_injector = RecordingFaultInjector()
    app.state.container.lab_health_probe = FailedDependencyProbe()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/labs/inject",
            json={"scenario": "dependency_unavailable"},
        )
    assert response.status_code == 200
    observation = response.json()["observation"]
    assert observation["source"] == "http-health-probe"
    assert observation["status_code"] == 503
    assert observation["healthy"] is False


def test_change_webhook_is_normalized_and_queryable(monkeypatch: MonkeyPatch) -> None:
    """通用 CI/CD 事件应写入标准模型并支持按服务查询。"""

    monkeypatch.setenv("AIOPS_ADMIN_TOKEN", "test-admin-token")
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/integrations/events",
            headers={"Authorization": "Bearer test-admin-token"},
            json={
                "provider": "github-actions",
                "event_type": "deployment",
                "service": "lab-api",
                "revision": "abc123",
                "status": "succeeded",
                "occurred_at": datetime.now(UTC).isoformat(),
                "attributes": {"environment": "lab"},
            },
        )
        assert response.status_code == 200
        events = client.get("/api/v1/integrations/events?service=lab-api").json()
        assert events[0]["provider"] == "github-actions"
        assert events[0]["revision"] == "abc123"


def test_admin_endpoint_is_closed_without_token() -> None:
    """未配置管理员令牌时，插件安装接口必须安全关闭。"""

    with TestClient(create_app()) as client:
        response = client.post("/api/v1/plugins/http-nginx/install")
        assert response.status_code == 503


def test_public_http_mode_rejects_admin_token(monkeypatch: MonkeyPatch) -> None:
    """明文 HTTP 演示模式必须从服务端关闭管理员写操作。"""

    monkeypatch.setenv("AIOPS_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("AIOPS_ADMIN_ACTIONS_ENABLED", "false")
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/plugins/http-nginx/install",
            headers={"Authorization": "Bearer test-admin-token"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "当前公网 HTTP 模式已关闭管理员写接口"


def test_guest_fault_injection_is_rate_limited() -> None:
    """同一访客在一分钟内第四次注入故障必须被拒绝。"""

    with TestClient(create_app()) as client:
        statuses = [
            client.post(
                "/api/v1/labs/inject",
                json={"scenario": "container_cpu_spike"},
            ).status_code
            for _ in range(4)
        ]
        assert statuses == [200, 200, 200, 429]


def test_forwarded_for_cannot_bypass_fault_rate_limit() -> None:
    """伪造不同 X-Forwarded-For 首项也必须命中同一个连接身份限流桶。"""

    with TestClient(create_app()) as client:
        statuses = [
            client.post(
                "/api/v1/labs/inject",
                headers={"X-Forwarded-For": f"198.51.100.{index}"},
                json={"scenario": "container_cpu_spike"},
            ).status_code
            for index in range(1, 5)
        ]
        assert statuses == [200, 200, 200, 429]


def test_real_ip_header_is_ignored_without_trusted_proxy_mode() -> None:
    """默认直连模式下伪造 X-Real-IP 也不能创建多个限流身份。"""

    with TestClient(create_app()) as client:
        statuses = [
            client.post(
                "/api/v1/labs/inject",
                headers={"X-Real-IP": f"203.0.113.{index}"},
                json={"scenario": "container_cpu_spike"},
            ).status_code
            for index in range(1, 5)
        ]
        assert statuses == [200, 200, 200, 429]


def test_fault_catalog_contains_five_ground_truth_scenarios() -> None:
    """公开目录和注入结果必须携带不少于五类可评测真值。"""

    with TestClient(create_app()) as client:
        scenarios = client.get("/api/v1/labs/scenarios").json()
        assert {item["id"] for item in scenarios} == {
            "container_cpu_spike",
            "dependency_unavailable",
            "api_container_exit",
            "request_latency",
            "http_5xx",
        }
        injected = client.post(
            "/api/v1/labs/inject",
            json={"scenario": "request_latency"},
        ).json()
        assert injected["ground_truth"]["root_cause_asset"] == "lab-api"
        assert injected["ground_truth"]["injection_kind"] == "application_control"


def test_unknown_fault_scenario_is_rejected() -> None:
    """未知场景不能再静默回退成 CPU 故障。"""

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/labs/inject",
            json={"scenario": "arbitrary_command"},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "故障场景未注册"


def test_guest_cannot_approve_non_lab_target() -> None:
    """即使构造异常计划，访客也不能对真实目标执行动作。"""

    with TestClient(create_app()) as client:
        evaluated = client.post(
            "/api/v1/signals/evaluate",
            json={
                "asset_id": "production-api",
                "metric_name": "cpu",
                "current": 99,
                "history": [10, 10, 10, 10, 10, 10],
            },
        ).json()
        plan_id = evaluated["plan"]["id"]
        plan = client.get(f"/api/v1/plans/{plan_id}").json()
        approved = client.post(
            f"/api/v1/plans/{plan_id}/approve",
            json={
                "approver": "guest",
                "approved_hash": plan["content_hash"],
                "idempotency_key": "guest-production-request",
            },
        )
        assert approved.status_code == 403
