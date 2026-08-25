// 审计页把动作执行和 CI/CD 变更并列，便于复盘故障与变更的时间关系。
import { useCallback } from "react";

import { listChangeEvents, listExecutions } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function AuditPage() {
  const loader = useCallback(async () => Promise.all([listExecutions(), listChangeEvents()]), []);
  const { data, error, loading } = useApiResource(loader);
  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState message={error} />;
  const [executions, changes] = data!;
  return (
    <>
      <PageHeader
        description="记录计划哈希、幂等键、开始与结束时间、步骤输出、回滚结果及相关发布变更。"
        eyebrow="EXECUTION & AUDIT"
        title="执行与审计"
      />
      <section className="two-column-grid audit-grid">
        <article className="console-card">
          <div className="card-heading">
            <div>
              <span>ACTION RUNS</span>
              <h2>动作执行记录</h2>
            </div>
          </div>
          <div className="audit-list">
            {executions.map((run) => (
              <div key={run.id}>
                <span className={`state-badge ${run.status}`}>{run.status}</span>
                <strong>{run.id}</strong>
                <small>Incident：{run.incident_id}</small>
                <code>幂等键：{run.idempotency_key}</code>
                <time>{new Date(run.created_at).toLocaleString()}</time>
              </div>
            ))}
            {!executions.length && <p className="inline-empty">尚无执行记录。</p>}
          </div>
        </article>
        <article className="console-card">
          <div className="card-heading">
            <div>
              <span>CHANGE EVENTS</span>
              <h2>变更时间线</h2>
            </div>
          </div>
          <div className="audit-list">
            {changes.map((change) => (
              <div key={change.id}>
                <span className="state-badge experiment">{change.provider}</span>
                <strong>
                  {change.service} · {change.event_type}
                </strong>
                <code>{change.revision}</code>
                <time>{new Date(change.occurred_at).toLocaleString()}</time>
              </div>
            ))}
            {!changes.length && <p className="inline-empty">尚未接收 Git 或 CI/CD 变更事件。</p>}
          </div>
        </article>
      </section>
    </>
  );
}
