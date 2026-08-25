// 真实监测类型严格对应阶段六只读 API，不与故障实验室资产混用。
export interface AgentNode {
  id: string;
  version: string;
  instance_id: string;
  certificate_identity: string;
  status: string;
  connected_at: string;
  last_heartbeat_at: string;
}

export interface RealAsset {
  id: string;
  node_id: string;
  kind: string;
  name: string;
  status: string;
  environment: string;
  source: string;
  last_seen_at: string;
  attributes: Record<string, string>;
}

export interface RealTopologyEdge {
  source_asset_id: string;
  target_asset_id: string;
  relation: string;
  weight: number;
  source: string;
  last_seen_at: string;
}

export interface RealTopology {
  nodes: RealAsset[];
  edges: RealTopologyEdge[];
}

export interface MonitorRule {
  id: string;
  name: string;
  metric_name: string;
  asset_selector: string;
  operator: string;
  threshold: number;
  consecutive_cycles: number;
  recovery_cycles: number;
  severity: string;
  window_seconds: number;
  enabled: boolean;
}

export interface MonitorEvaluation {
  id: string;
  rule_id: string;
  asset_id: string;
  value: number;
  state: string;
  breach_streak: number;
  recovery_streak: number;
  message: string;
  evaluated_at: string;
}

export interface HealthTargetResult {
  id: string;
  asset_id: string;
  healthy: boolean;
  status_code: number;
  latency_ms: number;
  error: string;
}

export interface MonitoringHealth {
  status: string;
  real_actions_mode: "observe_only" | "approval_only" | string;
  node_count: number;
  latest_metric_at: string | null;
  metric_lag_seconds: number | null;
  targets: HealthTargetResult[];
}

export interface MetricPoint {
  name: string;
  value: number;
  labels: Record<string, string>;
  collected_at: string;
}

export interface MetricHistoryPoint {
  occurred_at: string;
  value: number;
  labels: Record<string, string>;
}

export interface AssetMetrics {
  asset_id: string;
  definitions: Array<{ name: string; display_name: string; unit: string; description: string }>;
  latest: MetricPoint[];
  history: MetricHistoryPoint[];
}
