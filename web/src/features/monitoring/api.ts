// 真实监测 API 适配器只构造已登记资产路径，不允许页面提交 PromQL 或任意健康 URL。
import { requestJson } from "../../shared/api/client";
import type {
  AgentNode,
  AssetMetrics,
  MonitorEvaluation,
  MonitoringHealth,
  MonitorRule,
  RealAsset,
  RealTopology,
} from "./types";

export const listAgentNodes = () => requestJson<AgentNode[]>("/api/v1/nodes");
export const listRealAssets = () => requestJson<RealAsset[]>("/api/v1/assets");
export const getRealTopology = () => requestJson<RealTopology>("/api/v1/topology");
export const listMonitorRules = () => requestJson<MonitorRule[]>("/api/v1/monitoring/rules");
export const listMonitorEvaluations = () =>
  requestJson<MonitorEvaluation[]>("/api/v1/monitoring/evaluations?limit=100");
export const getMonitoringHealth = () => requestJson<MonitoringHealth>("/api/v1/monitoring/health");

export function getAssetMetrics(assetId: string, metricName?: string) {
  const safePath = assetId.split("/").map(encodeURIComponent).join("/");
  const query = metricName ? `?metric_name=${encodeURIComponent(metricName)}&minutes=30` : "";
  return requestJson<AssetMetrics>(`/api/v1/assets/${safePath}/metrics${query}`);
}
