import type { EvaluationOutcome } from "../incidents/types";

export function buildDiagnosticEvidence(outcome: EvaluationOutcome): string[] {
  const observation = outcome.observation;
  return [
    `资产 ${outcome.incident?.asset_id ?? "lab-redis"} 的依赖健康指标异常`,
    observation
      ? `固定健康探针 ${observation.target} 返回 HTTP ${observation.status_code}，延迟 ${observation.latency_ms}ms`
      : "未获得真实健康探测结果",
    outcome.detection.reason,
  ];
}
