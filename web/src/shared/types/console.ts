// 控制台公共类型只描述跨页面查询结果，业务写操作仍留在各功能切片中。
import type { ActionRun, Incident, RemediationPlan } from "../../features/incidents/types";

export interface ConsoleOverview {
  incident_count: number;
  active_incident_count: number;
  resolved_incident_count: number;
  execution_count: number;
  successful_execution_count: number;
  asset_count: number;
  plugin_count: number;
  access_mode: string;
}

export interface ManagedAsset {
  id: string;
  name: string;
  kind: string;
  node_id: string;
  status: "healthy" | "degraded" | string;
  address: string;
  responsibilities: string[];
}

export interface TopologyEdge {
  source_asset_id: string;
  target_asset_id: string;
  relation: string;
}

export interface TopologySnapshot {
  nodes: ManagedAsset[];
  edges: TopologyEdge[];
}

export interface IncidentContext {
  incident: Incident;
  plan: RemediationPlan | null;
  executions: ActionRun[];
}

export interface Capability {
  id: string;
  name: string;
  category: string;
  state: "online" | "degraded" | "experiment" | "disabled" | string;
  description: string;
}

export interface SafeSettings {
  access_mode: string;
  admin_actions_enabled: boolean;
  trust_proxy_client_ip: boolean;
  prometheus_enabled: boolean;
  loki_enabled: boolean;
  llm_enabled: boolean;
  plugin_runtime_enabled: boolean;
  real_actions_mode: string;
  agent_grpc_enabled: boolean;
  secrets_exposed: boolean;
}

export interface DiagnosticStatus {
  provider: string;
  model: string;
  rag: string;
  degraded: boolean;
}

export interface DiagnosticAnswer {
  diagnosis: {
    summary: string;
    root_cause: string;
    recommended_action: string;
    confidence: number;
  };
  citations: string[];
  degraded: boolean;
}

export interface PluginManifest {
  plugin_id: string;
  name: string;
  version: string;
  api_version: string;
  capabilities: string[];
  permissions: string[];
}

export interface ChangeEvent {
  id: string;
  provider: string;
  event_type: string;
  service: string;
  revision: string;
  status: string;
  occurred_at: string;
}
