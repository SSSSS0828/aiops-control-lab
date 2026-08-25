// 控制台查询适配器集中维护只读 API，页面不拼接服务器路径。
import type { ActionRun } from "../../features/incidents/types";
import type {
  Capability,
  ChangeEvent,
  ConsoleOverview,
  DiagnosticAnswer,
  DiagnosticStatus,
  IncidentContext,
  ManagedAsset,
  PluginManifest,
  SafeSettings,
  TopologySnapshot,
} from "../types/console";
import { requestJson } from "./client";

export const getOverview = () => requestJson<ConsoleOverview>("/api/v1/console/overview");
export const listAssets = () => requestJson<ManagedAsset[]>("/api/v1/console/assets");
export const getTopology = () => requestJson<TopologySnapshot>("/api/v1/console/topology");
export const listIncidentContexts = () =>
  requestJson<IncidentContext[]>("/api/v1/console/incident-contexts");
export const listExecutions = () => requestJson<ActionRun[]>("/api/v1/console/executions");
export const listCapabilities = () => requestJson<Capability[]>("/api/v1/console/capabilities");
export const getSafeSettings = () => requestJson<SafeSettings>("/api/v1/console/settings");
export const getDiagnosticStatus = () =>
  requestJson<DiagnosticStatus>("/api/v1/diagnostics/status");
export const listPlugins = () => requestJson<PluginManifest[]>("/api/v1/plugins");
export const listChangeEvents = () => requestJson<ChangeEvent[]>("/api/v1/integrations/events");

export function askDiagnostic(question: string, evidence: string[]): Promise<DiagnosticAnswer> {
  return requestJson<DiagnosticAnswer>("/api/v1/diagnostics/query", {
    method: "POST",
    body: JSON.stringify({ question, evidence }),
  });
}

export function evaluateSlo(payload: Record<string, unknown>) {
  return requestJson<Record<string, number | string>>("/api/v1/sre/slo/evaluate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function assessChange(payload: Record<string, unknown>) {
  return requestJson<{ score: number; level: string; reasons: string[] }>(
    "/api/v1/sre/changes/assess",
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function forecastCapacity(payload: Record<string, unknown>) {
  return requestJson<{
    slope_per_hour: number;
    r_squared: number;
    threshold: number;
    estimated_exhaustion_at: string | null;
    state: string;
  }>("/api/v1/sre/capacity/forecast", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
