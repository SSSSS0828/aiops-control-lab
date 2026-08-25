// Incident 功能使用的稳定前端数据类型，与 API 领域字段一一对应。
export interface Evidence {
  id: string;
  source: string;
  query: string;
  summary: string;
}

export interface Hypothesis {
  asset_id: string;
  reason: string;
  score: number;
  evidence_ids: string[];
}

export interface Incident {
  id: string;
  title: string;
  asset_id: string;
  severity: "medium" | "high";
  status: "waiting_approval" | "remediating" | "resolved" | "failed" | string;
  created_at: string;
  evidence: Evidence[];
  hypotheses: Hypothesis[];
}

export interface RemediationStep {
  action_type: string;
  target: string;
  arguments: Record<string, string>;
  expected_result: string;
  rollback_action: string | null;
  rollback_arguments: Record<string, string>;
}

export interface RemediationPlan {
  id: string;
  incident_id: string;
  summary: string;
  risk: string;
  steps: RemediationStep[];
  status: string;
  content_hash?: string;
}

export interface DetectionResult {
  anomalous: boolean;
  score: number | null;
  reason: string;
}

export interface EvaluationOutcome {
  detection: DetectionResult;
  incident: Incident | null;
  plan: RemediationPlan | null;
  ground_truth?: import("../lab/types").FaultScenario;
  observation?: LabObservation;
}

export interface LabObservation {
  source: string;
  target: string;
  healthy: boolean;
  status_code: number;
  latency_ms: number;
  observed_at: string;
}

export interface ActionRun {
  id: string;
  plan_id: string;
  incident_id: string;
  idempotency_key: string;
  approved_hash: string;
  status: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  output: {
    steps?: Array<{ message: string; succeeded: boolean }>;
    rollback?: Array<{ message: string; succeeded: boolean }>;
    verification?: {
      source: string;
      target: string;
      probe_target: string;
      healthy: boolean;
      status_code: number;
      latency_ms: number;
      observed_at: string;
    } | null;
  };
}
