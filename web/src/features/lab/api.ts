// 故障实验室 API 与 Incident API 分离，避免功能切片相互堆叠职责。
import { requestJson } from "../../shared/api/client";
import type { EvaluationOutcome } from "../incidents/types";
import type { FaultScenario } from "./types";

export function listFaultScenarios(): Promise<FaultScenario[]> {
  return requestJson<FaultScenario[]>("/api/v1/labs/scenarios");
}

export function injectFault(scenario: string): Promise<EvaluationOutcome> {
  return requestJson<EvaluationOutcome>("/api/v1/labs/inject", {
    method: "POST",
    body: JSON.stringify({ scenario }),
  });
}
