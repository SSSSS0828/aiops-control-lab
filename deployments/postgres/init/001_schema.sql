-- 阶段一使用 JSONB 保存领域聚合，同时为主要查询和幂等键建立独立索引。
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS incidents_created_at_idx ON incidents (created_at DESC);

CREATE TABLE IF NOT EXISTS remediation_plans (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

-- Incident 合并后需要返回既有计划；表达式索引避免扫描全部 JSONB 聚合。
CREATE INDEX IF NOT EXISTS remediation_plans_incident_id_idx
ON remediation_plans ((payload ->> 'incident_id'));

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS action_runs (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS action_runs_created_at_idx ON action_runs (created_at DESC);

-- Git、CI/CD 和发布事件使用统一聚合表，便于与 Incident 时间关联。
CREATE TABLE IF NOT EXISTS change_events (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS change_events_created_at_idx ON change_events (created_at DESC);

-- 阶段六只在 PostgreSQL 保存真实监测的低频状态和紧凑评估；原始指标仍归 Prometheus。
CREATE TABLE IF NOT EXISTS agent_nodes (
    id TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS assets_observed_at_idx ON assets (observed_at DESC);

CREATE TABLE IF NOT EXISTS topology_edges (
    id TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_rules (
    id TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_evaluations (
    id TEXT PRIMARY KEY,
    observed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS monitor_evaluations_observed_at_idx
ON monitor_evaluations (observed_at DESC);
CREATE INDEX IF NOT EXISTS monitor_evaluations_asset_id_idx
ON monitor_evaluations ((payload ->> 'asset_id'));
