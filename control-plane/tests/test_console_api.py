"""多页面控制台查询与 AI 诊断 API 测试。"""

from fastapi.testclient import TestClient

from aiops_control.api.app import create_app


def test_console_exposes_assets_topology_and_safe_settings() -> None:
    """控制台应返回真实实验拓扑，且设置响应绝不能包含密钥。"""

    with TestClient(create_app()) as client:
        assets = client.get("/api/v1/console/assets")
        topology = client.get("/api/v1/console/topology")
        settings = client.get("/api/v1/console/settings")

    assert assets.status_code == 200
    assert {item["id"] for item in assets.json()} >= {"aiops-agent", "lab-api", "lab-redis"}
    assert topology.json()["edges"] == [
        {
            "source_asset_id": "lab-gateway",
            "target_asset_id": "lab-api",
            "relation": "depends_on",
        },
        {
            "source_asset_id": "lab-api",
            "target_asset_id": "lab-redis",
            "relation": "depends_on",
        },
    ]
    assert settings.json()["access_mode"] == "private-forward"
    assert settings.json()["secrets_exposed"] is False
    assert "api_key" not in settings.text.lower()
    assert "token" not in settings.text.lower()


def test_console_context_joins_incident_plan_and_execution() -> None:
    """审批页面应通过一次查询得到事件、内容哈希和执行记录。"""

    with TestClient(create_app()) as client:
        injected = client.post(
            "/api/v1/labs/inject", json={"scenario": "container_cpu_spike"}
        ).json()
        contexts = client.get("/api/v1/console/incident-contexts").json()

    current = next(
        item for item in contexts if item["incident"]["id"] == injected["incident"]["id"]
    )
    assert current["plan"]["id"] == injected["plan"]["id"]
    assert len(current["plan"]["content_hash"]) == 64
    assert current["executions"] == []


def test_diagnostic_query_uses_rag_and_rule_fallback() -> None:
    """未配置云模型时仍应返回结构化诊断和受信 Runbook 引用。"""

    with TestClient(create_app()) as client:
        status = client.get("/api/v1/diagnostics/status").json()
        response = client.post(
            "/api/v1/diagnostics/query",
            json={
                "question": "Redis 连接失败应该如何处理？",
                "evidence": ["lab-api 无法连接 lab-redis"],
            },
        )

    assert status["provider"] == "rule-based"
    assert status["degraded"] is True
    assert response.status_code == 200
    assert response.json()["diagnosis"]["confidence"] > 0
    assert response.json()["citations"]
    assert response.json()["degraded"] is True
