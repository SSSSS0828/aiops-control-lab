// Incident API 适配器集中维护路径和请求结构。
import { requestJson } from "../../shared/api/client";
import type { ActionRun, Incident, RemediationPlan } from "./types";

export function listIncidents(): Promise<Incident[]> {
  return requestJson<Incident[]>("/api/v1/incidents");
}

export function loadPlan(planId: string): Promise<RemediationPlan> {
  return requestJson<RemediationPlan>(`/api/v1/plans/${planId}`);
}

export function approvePlan(plan: RemediationPlan): Promise<ActionRun> {
  if (!plan.content_hash) {
    throw new Error("计划缺少审批内容哈希");
  }
  return requestJson<ActionRun>(`/api/v1/plans/${plan.id}/approve`, {
    method: "POST",
    body: JSON.stringify({
      approver: "demo-admin",
      approved_hash: plan.content_hash,
      idempotency_key: `web-${plan.id}`,
    }),
  });
}
