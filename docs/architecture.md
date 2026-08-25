# 架构与数据流

## 组件边界

控制面负责认知和决策，Agent 负责靠近系统的采集和动作，插件负责厂商或协议适配，Prometheus/Loki 负责保存高体积遥测。任何一个组件都不能同时承担“算法决策”和“绕过审批执行系统命令”。

```mermaid
flowchart TB
    subgraph Node["被管理 Linux 节点"]
      Proc["/proc"] --> Agent["Go Agent"]
      Docker["Docker Engine"] <--> Agent
      Lab["故障实验容器"] <--> Docker
      Real["devops-lab 真实容器"] --> Docker
    end

    subgraph Platform["AIOps 控制面"]
      API["API 边界"] --> UseCase["应用用例"]
      UseCase --> Domain["领域实体与状态机"]
      UseCase --> Ports["端口"]
      Adapters["数据库/算法/Agent/插件适配器"] --> Ports
    end

    Agent -->|"mTLS gRPC 主动遥测"| Platform
    Platform -->|"注册最新指标"| Prometheus
    Platform --> Prometheus
    Platform --> Loki
    Platform --> PostgreSQL
Platform <--> Plugin["独立插件进程"]
```

真实资产与实验资产使用互斥命名空间：`host/*` 和 `docker/devops-lab/*` 属于真实环境，
`lab-*` 属于自动重置故障实验。`AIOPS_REAL_ACTIONS_MODE=observe_only` 时，控制面应用策略与
Agent 都拒绝真实动作；页面上的禁用提示不是安全边界。

## 真实监测数据流

```mermaid
flowchart LR
    Sources["/proc / statfs / Docker API"] --> Agent["systemd Agent"]
    Agent -->|"TelemetryBatch + sequence"| Gateway["mTLS Gateway"]
    Gateway --> Ingestion["身份绑定与去重"]
    Ingestion --> Latest["最新指标内存"]
    Ingestion --> State[("节点/资产/拓扑")]
    Latest --> Export["Prometheus 文本端点"]
    Prometheus[("现有 Prometheus")] --> Export
    Scheduler["60 秒规则调度"] --> Latest
    Scheduler --> Evaluation[("评估与 Incident")]
    Web["真实监测控制台"] --> State
    Web --> Evaluation
    Web -->|"注册指标历史"| Prometheus
```

详细安全、部署和回滚见阶段六 README 与 ADR-003。

## Incident 数据流

```mermaid
sequenceDiagram
    participant A as Agent/实验室
    participant C as 控制面
    participant D as 异常检测器
    participant P as PostgreSQL
    participant U as 用户
    participant E as Agent执行器

    A->>C: Signal + 历史窗口
    C->>D: detect(history,current)
    D-->>C: DetectionResult
    C->>P: EvidenceRef + Incident + Plan
    C-->>U: 等待审批
    U->>C: plan_id + content_hash + idempotency_key
    C->>C: 校验状态、时效和哈希
    C->>P: 先保存 Approval 与 ActionRun
    C->>E: 类型化动作 + approved_hash
    E->>E: 校验范围、时效、幂等键
    E-->>C: 执行和健康验证结果
    C->>P: 完成 ActionRun 与 Incident
    C-->>U: 审计结果
```

## 插件升级数据流

```mermaid
sequenceDiagram
    participant U as 管理员
    participant M as 插件管理器
    participant N as 候选插件
    participant O as 当前插件

    U->>M: 安装 plugin.yaml
    M->>M: 验证目录、API、能力、SHA-256
    M->>N: 启动独立进程和 Unix Socket
    loop 健康检查窗口
      M->>N: Health
      N-->>M: status=ok
    end
    M->>M: 锁内原子替换注册表引用
    M->>O: 终止旧进程并清理 Socket
    M-->>U: 返回已注册清单
```

候选插件在健康之前不会替换旧版本；启动失败、进程提前退出或健康超时只清理候选版本。控制面与旧插件继续提供服务。
