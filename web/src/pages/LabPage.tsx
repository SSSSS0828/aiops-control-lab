// 故障实验室只允许固定场景，控制面负责限流、自动恢复和真值记录。
import { useCallback, useState } from "react";

import { injectFault, listFaultScenarios } from "../features/lab/api";
import type { EvaluationOutcome } from "../features/incidents/types";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function LabPage() {
  const loader = useCallback(() => listFaultScenarios(), []);
  const { data = [], error, loading } = useApiResource(loader);
  const [running, setRunning] = useState<string>();
  const [outcome, setOutcome] = useState<EvaluationOutcome>();
  if (loading && !data.length) return <LoadingState />;
  if (error && !data.length) return <ErrorState message={error} />;

  async function inject(id: string) {
    setRunning(id);
    try {
      setOutcome(await injectFault(id));
    } finally {
      setRunning(undefined);
    }
  }

  return (
    <>
      <PageHeader
        description="五类场景携带不可变真值，可验证检测、根因排序、审批、幂等执行、恢复和回滚。"
        eyebrow="CONTROLLED FAULT LAB"
        title="故障实验室"
      />
      <div className="safety-note">
        仅影响 lab-* 实验容器；场景受频率限制并自动重置，不能传入任意命令或目标。
      </div>
      <section className="lab-scenario-grid">
        {data.map((scenario) => (
          <article className="console-card scenario-card" key={scenario.id}>
            <span className="eyebrow">{scenario.injection_kind}</span>
            <h2>{scenario.title}</h2>
            <dl>
              <div>
                <dt>目标</dt>
                <dd>{scenario.asset_id}</dd>
              </div>
              <div>
                <dt>指标</dt>
                <dd>{scenario.metric_name}</dd>
              </div>
            </dl>
            <p>
              <strong>真值根因：</strong>
              {scenario.root_cause}
            </p>
            <p>
              <strong>预期修复：</strong>
              {scenario.expected_remediation}
            </p>
            <button disabled={Boolean(running)} onClick={() => void inject(scenario.id)}>
              {running === scenario.id ? "正在注入并检测…" : "注入该故障"}
            </button>
          </article>
        ))}
      </section>
      {outcome && (
        <article className="console-card outcome-card">
          <span className={`state-badge ${outcome.detection.anomalous ? "degraded" : "online"}`}>
            {outcome.detection.anomalous ? "检测到异常" : "未判定异常"}
          </span>
          <h2>{outcome.detection.reason}</h2>
          <p>检测分数：{outcome.detection.score ?? "无"}</p>
          {outcome.incident && <a href="#/approvals">进入审批中心处理 {outcome.incident.id} →</a>}
        </article>
      )}
    </>
  );
}
