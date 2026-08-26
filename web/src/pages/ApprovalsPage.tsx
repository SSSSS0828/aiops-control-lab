// 审批中心只处理具有内容哈希的类型化计划，批准后仍由 Agent 二次校验任务签名。
import { useCallback, useState } from "react";

import { approvePlan } from "../features/incidents/api";
import type { ActionRun } from "../features/incidents/types";
import { listIncidentContexts } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function ApprovalsPage() {
  const loader = useCallback(() => listIncidentContexts(), []);
  const { data = [], error, loading, refresh } = useApiResource(loader);
  const [runningPlan, setRunningPlan] = useState<string>();
  const [lastRun, setLastRun] = useState<ActionRun>();
  const pending = data.filter(
    ({ incident, plan }) =>
      incident.status === "waiting_approval" && plan?.status === "pending_approval",
  );
  if (loading && !data.length) return <LoadingState />;
  if (error && !data.length) return <ErrorState message={error} />;

  async function approve(plan: NonNullable<(typeof data)[number]["plan"]>) {
    setRunningPlan(plan.id);
    try {
      setLastRun(await approvePlan(plan));
      await refresh();
    } finally {
      setRunningPlan(undefined);
    }
  }

  return (
    <>
      <PageHeader
        description="审批对象包含动作、目标、风险、预期结果、回滚定义和 SHA-256 内容哈希。"
        eyebrow="HUMAN APPROVAL GATE"
        title="审批中心"
      />
      {lastRun && (
        <div className="success-banner">
          任务 {lastRun.id} 已提交，当前状态：{lastRun.status}
        </div>
      )}
      {!pending.length && (
        <EmptyState>当前没有等待人工审批的计划，可在故障实验室创建新事件。</EmptyState>
      )}
      <section className="approval-grid">
        {pending.map(
          ({ incident, plan }) =>
            plan && (
              <article className="console-card approval-card" key={plan.id}>
                <header>
                  <span className="state-badge degraded">{plan.risk}</span>
                  <code>{plan.id}</code>
                </header>
                <h2>{incident.title}</h2>
                <p>{plan.summary}</p>
                <div className="hash-box">
                  <span>批准内容哈希</span>
                  <code>{plan.content_hash}</code>
                </div>
                {plan.steps.map((step) => (
                  <div className="approval-step" key={`${step.action_type}-${step.target}`}>
                    <strong>{step.action_type}</strong>
                    <code>{step.target}</code>
                    <small>验证：{step.expected_result}</small>
                    <small>回滚：{step.rollback_action ?? "不可逆，失败后人工接管"}</small>
                  </div>
                ))}
                <button disabled={runningPlan === plan.id} onClick={() => void approve(plan)}>
                  {runningPlan === plan.id ? "执行并验证中…" : "确认内容并批准执行"}
                </button>
              </article>
            ),
        )}
      </section>
    </>
  );
}
