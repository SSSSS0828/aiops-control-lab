import { describe, expect, it } from "vitest";

import { buildDiagnosticEvidence } from "../features/demo/evidence";
import type { EvaluationOutcome } from "../features/incidents/types";

describe("buildDiagnosticEvidence", () => {
  it("把真实 HTTP 探测结果整理为诊断证据", () => {
    const outcome = {
      detection: { anomalous: true, score: 8, reason: "service_health 偏离基线" },
      incident: { asset_id: "lab-redis" },
      plan: null,
      observation: {
        source: "http-health-probe",
        target: "http://lab-api:8080/healthz",
        healthy: false,
        status_code: 503,
        latency_ms: 12.5,
        observed_at: "2026-08-25T00:00:00Z",
      },
    } as EvaluationOutcome;

    expect(buildDiagnosticEvidence(outcome)).toContain(
      "固定健康探针 http://lab-api:8080/healthz 返回 HTTP 503，延迟 12.5ms",
    );
  });
});
