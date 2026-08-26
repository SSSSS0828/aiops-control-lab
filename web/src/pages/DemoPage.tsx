// 求职演示页将现有故障、诊断、审批接口串成一条可复现主线。
import { useCallback, useState } from "react";

import { buildDiagnosticEvidence } from "../features/demo/evidence";
import { injectFault } from "../features/lab/api";
import { approvePlan, loadPlan } from "../features/incidents/api";
import type { ActionRun, EvaluationOutcome, RemediationPlan } from "../features/incidents/types";
import { askDiagnostic, getDiagnosticStatus } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";
import type { DiagnosticAnswer } from "../shared/types/console";

type DemoPhase = "ready" | "injecting" | "diagnosed" | "approving" | "resolved" | "failed";

const phases: Array<{ id: DemoPhase; label: string }> = [
  { id: "ready", label: "健康基线" },
  { id: "injecting", label: "停止 Redis" },
  { id: "diagnosed", label: "诊断与审批" },
  { id: "approving", label: "执行修复" },
  { id: "resolved", label: "恢复验证" },
];

export function DemoPage() {
  const statusLoader = useCallback(() => getDiagnosticStatus(), []);
  const { data: modelStatus, error: statusError, loading } = useApiResource(statusLoader);
  const [phase, setPhase] = useState<DemoPhase>("ready");
  const [outcome, setOutcome] = useState<EvaluationOutcome>();
  const [plan, setPlan] = useState<RemediationPlan>();
  const [diagnosis, setDiagnosis] = useState<DiagnosticAnswer>();
  const [actionRun, setActionRun] = useState<ActionRun>();
  const [error, setError] = useState<string>();

  if (loading && !modelStatus) return <LoadingState />;
  if (statusError && !modelStatus) return <ErrorState message={statusError} />;

  async function runDemo() {
    setError(undefined);
    setActionRun(undefined);
    setPhase("injecting");
    try {
      const injected = await injectFault("dependency_unavailable");
      setOutcome(injected);
      const [loadedPlan, answer] = await Promise.all([
        injected.plan ? loadPlan(injected.plan.id) : Promise.resolve(undefined),
        askDiagnostic(
          "Redis 依赖不可用导致 API 健康检查失败，应该如何排查？",
          buildDiagnosticEvidence(injected),
        ),
      ]);
      setPlan(loadedPlan);
      setDiagnosis(answer);
      setPhase("diagnosed");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "故障演练失败");
      setPhase("failed");
    }
  }

  async function approve() {
    if (!plan) return;
    setError(undefined);
    setPhase("approving");
    try {
      const run = await approvePlan(plan);
      setActionRun(run);
      setPhase(
        run.status === "succeeded" && run.output.verification?.healthy ? "resolved" : "failed",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "修复执行失败");
      setPhase("failed");
    }
  }

  const currentIndex = phases.findIndex((item) => item.id === phase);
  return (
    <>
      <PageHeader
        description="用一个真实、可恢复的依赖故障展示探测、诊断、审批、执行和复检全过程。"
        eyebrow="5 MINUTE PORTFOLIO DEMO"
        title="Redis 依赖故障闭环"
      />
      <section className="demo-flow" aria-label="演练进度">
        {phases.map((item, index) => (
          <div className={index <= currentIndex ? "active" : ""} key={item.id}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{item.label}</strong>
          </div>
        ))}
      </section>
      <div className="demo-status-row">
        <span className={`state-badge ${modelStatus!.degraded ? "degraded" : "online"}`}>
          {modelStatus!.degraded ? "无模型密钥：规则降级" : `模型在线：${modelStatus!.model}`}
        </span>
        <span>实验目标固定为 lab-redis，不接受任意命令或地址。</span>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <section className="demo-grid">
        <article className="console-card demo-action-card">
          <span className="eyebrow">CONTROLLED FAILURE</span>
          <h2>下游依赖不可用</h2>
          <p>停止 Redis 后，API 进程仍存活，但依赖健康端点应返回 HTTP 503。</p>
          <button
            disabled={phase === "injecting" || phase === "approving"}
            onClick={() => void runDemo()}
          >
            {phase === "injecting" ? "正在停止并探测…" : "开始演练"}
          </button>
          {outcome?.observation && (
            <dl className="demo-facts">
              <div>
                <dt>探测地址</dt>
                <dd>{outcome.observation.target}</dd>
              </div>
              <div>
                <dt>HTTP 状态</dt>
                <dd>{outcome.observation.status_code}</dd>
              </div>
              <div>
                <dt>探测延迟</dt>
                <dd>{outcome.observation.latency_ms} ms</dd>
              </div>
            </dl>
          )}
        </article>
        <article className="console-card demo-diagnosis-card">
          <span className="eyebrow">READ-ONLY DIAGNOSIS</span>
          <h2>{diagnosis?.diagnosis.summary ?? "等待真实证据"}</h2>
          {diagnosis ? (
            <>
              <p>
                <strong>根因：</strong>
                {diagnosis.diagnosis.root_cause}
              </p>
              <p>
                <strong>建议：</strong>
                {diagnosis.diagnosis.recommended_action}
              </p>
              <p>
                <strong>置信度：</strong>
                {Math.round(diagnosis.diagnosis.confidence * 100)}%
              </p>
            </>
          ) : (
            <p>平台只把固定健康探针的结果交给模型或规则引擎，不让 AI 直接执行操作。</p>
          )}
        </article>
        <article className="console-card demo-recovery-card">
          <span className="eyebrow">APPROVED RECOVERY</span>
          <h2>{actionRun ? `执行结果：${actionRun.status}` : "人工审批后恢复"}</h2>
          <p>{plan?.summary ?? "检测到异常后才会生成类型化修复计划。"}</p>
          {plan && !actionRun && (
            <button disabled={phase !== "diagnosed"} onClick={() => void approve()}>
              批准恢复 Redis
            </button>
          )}
          {actionRun?.output.verification && (
            <dl className="demo-facts">
              <div>
                <dt>容器动作</dt>
                <dd>{actionRun.output.steps?.[0]?.message}</dd>
              </div>
              <div>
                <dt>API 复检</dt>
                <dd>HTTP {actionRun.output.verification.status_code}</dd>
              </div>
              <div>
                <dt>最终状态</dt>
                <dd>{actionRun.output.verification.healthy ? "已恢复" : "需要人工处理"}</dd>
              </div>
            </dl>
          )}
        </article>
      </section>
    </>
  );
}
