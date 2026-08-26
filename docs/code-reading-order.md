# 代码文件阅读顺序

本顺序以“先理解安全边界和数据流，再看框架适配”为原则。自动生成的 Protobuf 文件不适合
作为入口；先阅读 `proto/agent/v1/agent.proto`，需要排查序列化问题时再进入 `gen/generated`。

## 第一条主线：真实环境监测

1. `proto/agent/v1/agent.proto`：AgentHello、TelemetryBatch、序列确认和动作字段。
2. `agent/internal/domain/telemetry.go`：Go 侧与 gRPC 无关的遥测实体。
3. `agent/internal/adapters/procfs/collector.go`：主机 CPU、负载和内存采集。
4. `agent/internal/adapters/docker/collector.go`：只发现 devops-lab 白名单容器。
5. `agent/internal/application/telemetry_service.go`：稳定资产 ID、指标标签与拓扑组装。
6. `agent/internal/transport/grpcstream/client.go`：mTLS、序列确认、重连和任务结果。
7. `control-plane/src/aiops_control/domain/monitoring.py`：真实监测领域模型。
8. `control-plane/src/aiops_control/application/agent_ingestion_service.py`：双重身份和去重。
9. `control-plane/src/aiops_control/adapters/agent_metric_store.py`：最新指标与 Prometheus 文本。
10. `control-plane/src/aiops_control/application/monitoring_service.py`：规则迟滞和 Incident。
11. `control-plane/src/aiops_control/application/monitoring_scheduler.py`：一分钟周期和数据库租约。
12. `control-plane/src/aiops_control/api/routers/monitoring.py`：真实资产只读 API。
13. `web/src/features/monitoring/types.ts` 与 `api.ts`：前端契约边界。
14. `web/src/pages/AssetsPage.tsx`、`TopologyPage.tsx`、`TelemetryPage.tsx`：真实控制台。

## 第二条主线：审批、执行与回滚

1. `control-plane/src/aiops_control/domain/models.py`：Incident、计划、审批和 ActionRun 状态。
2. `control-plane/src/aiops_control/application/incident_service.py`：异常到计划，观察模式不产计划。
3. `control-plane/src/aiops_control/application/real_action_policy.py`：真实动作门禁。
4. `control-plane/src/aiops_control/application/remediation_service.py`：哈希、审批、执行和补偿。
5. `control-plane/src/aiops_control/security/task_signing.py`：Python HMAC 规范化签名。
6. `agent/internal/application/task_authenticator.go`：Go 侧同一签名算法。
7. `agent/internal/application/action_service.go`：时效、nonce、幂等和目标范围。
8. `agent/internal/adapters/docker/executor.go`：类型化 Docker API 映射。

## 第三条主线：AI、RAG 与根因分析

1. `control-plane/src/aiops_control/application/root_cause_service.py`
2. `control-plane/src/aiops_control/application/hybrid_retrieval_service.py`
3. `control-plane/src/aiops_control/application/diagnostic_assistant_service.py`
4. `control-plane/src/aiops_control/application/tool_registry.py`
5. `control-plane/src/aiops_control/adapters/openai_compatible_llm.py`
6. `control-plane/src/aiops_control/adapters/rule_based_diagnosis.py`
7. `web/src/pages/DiagnosticsPage.tsx`

## 第四条主线：插件热插拔

1. `proto/plugin/v1/plugin.proto`
2. `sdk/README.md`
3. `sdk/python/aiops_plugin_sdk/manifest.py`
4. `control-plane/src/aiops_control/adapters/grpc_plugin_runtime.py`
5. `plugins/http-nginx/plugin.yaml`
6. `plugins/http-nginx/plugin.py`
7. `control-plane/tests/test_plugin_contract.py`

## 部署与验证

最后阅读 `control-plane/src/aiops_control/api/container.py` 理解组合根，再看
`deployments/compose.yaml`、`deployments/compose.lite.yaml`、systemd 单元和阶段 README。
测试建议顺序为领域单元测试、协议契约测试、API 集成测试、前端测试、云端非扰动验收。
