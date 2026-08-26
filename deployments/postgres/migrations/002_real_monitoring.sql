-- 阶段六在线迁移：为真实 Agent、资产、拓扑、规则和评估增加低频状态表。
-- 该脚本使用 IF NOT EXISTS，可在已有 PostgreSQL 数据卷上安全重复执行。
CREATE TABLE IF NOT EXISTS agent_nodes (
    id TEXT PRIMARY KEY, observed_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY, observed_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS assets_observed_at_idx ON assets (observed_at DESC);
CREATE TABLE IF NOT EXISTS topology_edges (
    id TEXT PRIMARY KEY, observed_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS monitor_rules (
    id TEXT PRIMARY KEY, observed_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS monitor_evaluations (
    id TEXT PRIMARY KEY, observed_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS monitor_evaluations_observed_at_idx
ON monitor_evaluations (observed_at DESC);
CREATE INDEX IF NOT EXISTS monitor_evaluations_asset_id_idx
ON monitor_evaluations ((payload ->> 'asset_id'));
