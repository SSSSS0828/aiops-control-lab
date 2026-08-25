// IncidentDetail 展示证据、根因、修复计划和审批入口。
import type { ActionRun, Incident, RemediationPlan } from "./types";

interface IncidentDetailProps {
  incident?: Incident;
  plan?: RemediationPlan;
  actionRun?: ActionRun;
  approving: boolean;
  onApprove: () => void;
}

export function IncidentDetail({
  incident,
  plan,
  actionRun,
  approving,
  onApprove,
}: IncidentDetailProps) {
  if (!incident) {
    return (
      <div className="detail-placeholder">
        <span>INCIDENT WORKBENCH</span>
        <h2>选择一个事件查看诊断链路</h2>
        <p>证据引用、根因评分和获批动作会在这里形成可审计视图。</p>
      </div>
    );
  }

  const primaryHypothesis = incident.hypotheses[0];
  return (
    <article className="incident-detail">
      <header>
        <div>
          <span className="eyebrow">{incident.id}</span>
          <h2>{incident.title}</h2>
        </div>
        <span className={`status-pill ${incident.status}`}>{incident.status}</span>
      </header>

      <section className="detail-section">
        <span className="section-number">01</span>
        <div>
          <h3>检测证据</h3>
          {incident.evidence.map((evidence) => (
            <div className="evidence-card" key={evidence.id}>
              <span>{evidence.source}</span>
              <strong>{evidence.summary}</strong>
              <code>{evidence.query}</code>
            </div>
          ))}
        </div>
      </section>

      <section className="detail-section">
        <span className="section-number">02</span>
        <div>
          <h3>根因假设</h3>
          {primaryHypothesis && (
            <div className="hypothesis">
              <div className="score">{Math.round(primaryHypothesis.score * 100)}%</div>
              <div>
                <strong>{primaryHypothesis.asset_id}</strong>
                <p>{primaryHypothesis.reason}</p>
              </div>
            </div>
          )}
        </div>
      </section>

      {plan && (
        <section className="detail-section approval-section">
          <span className="section-number">03</span>
          <div>
            <h3>受控修复计划</h3>
            <p>{plan.summary}</p>
            {plan.steps.map((step) => (
              <div className="action-preview" key={`${step.action_type}-${step.target}`}>
                <span>{step.action_type}</span>
                <code>{step.target}</code>
                <small>预期：{step.expected_result}</small>
                <small>回滚：{step.rollback_action ?? "该动作不可逆，失败时转人工接管"}</small>
              </div>
            ))}
            {incident.status === "waiting_approval" && (
              <button
                className="approve-button"
                disabled={approving}
                onClick={onApprove}
                type="button"
              >
                {approving ? "正在执行并验证…" : "批准并执行修复"}
              </button>
            )}
            {actionRun && (
              <div className={`run-result ${actionRun.status}`}>
                <strong>执行结果：{actionRun.status}</strong>
                <span>{actionRun.output.steps?.[0]?.message}</span>
                {actionRun.output.rollback?.map((rollback, index) => (
                  <span key={`${rollback.message}-${index}`}>
                    回滚 {rollback.succeeded ? "成功" : "失败"}：{rollback.message}
                  </span>
                ))}
              </div>
            )}
          </div>
        </section>
      )}
    </article>
  );
}
