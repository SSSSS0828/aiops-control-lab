// 总览页聚合运行指标、事件状态和系统边界，不发起任何写操作。
import { useCallback } from "react";

import { getOverview, listCapabilities, listIncidentContexts } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function OverviewPage() {
  const loader = useCallback(
    async () => Promise.all([getOverview(), listIncidentContexts(), listCapabilities()]),
    [],
  );
  const { data, error, loading, refresh } = useApiResource(loader);

  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState message={error} />;
  const [overview, contexts, capabilities] = data!;
  const recent = contexts.slice(0, 5);

  return (
    <>
      <PageHeader
        actions={<button onClick={() => void refresh()}>刷新快照</button>}
        description="从异常发现到验证回滚的运行态势总览，所有数字来自控制面当前仓储快照。"
        eyebrow="OPERATIONS OVERVIEW"
        title="AIOps 运行总览"
      />
      <section className="metric-grid">
        <Metric label="受管资产" value={overview.asset_count} tone="cyan" />
        <Metric label="活跃 Incident" value={overview.active_incident_count} tone="amber" />
        <Metric label="已恢复 Incident" value={overview.resolved_incident_count} tone="green" />
        <Metric label="动作执行" value={overview.execution_count} tone="violet" />
      </section>
      <section className="two-column-grid">
        <article className="console-card">
          <div className="card-heading">
            <div>
              <span>RECENT INCIDENTS</span>
              <h2>最近事件</h2>
            </div>
            <a href="#/incidents">进入工作台 →</a>
          </div>
          <div className="table-list">
            {recent.map(({ incident }) => (
              <a className="table-row" href="#/incidents" key={incident.id}>
                <span className={`status-dot ${incident.status}`} />
                <strong>{incident.title}</strong>
                <small>{incident.asset_id}</small>
                <em>{incident.status}</em>
              </a>
            ))}
            {!recent.length && <p className="inline-empty">尚无 Incident。</p>}
          </div>
        </article>
        <article className="console-card">
          <div className="card-heading">
            <div>
              <span>CAPABILITY STATUS</span>
              <h2>能力运行状态</h2>
            </div>
            <a href="#/algorithms">查看算法 →</a>
          </div>
          <div className="capability-summary">
            {capabilities.slice(0, 6).map((item) => (
              <div key={item.id}>
                <span className={`state-badge ${item.state}`}>{item.state}</span>
                <strong>{item.name}</strong>
                <small>{item.description}</small>
              </div>
            ))}
          </div>
        </article>
      </section>
      <section className="flow-strip">
        {[
          ["01", "采集", "指标、日志与事件"],
          ["02", "分析", "检测、关联与根因"],
          ["03", "决策", "RAG 与修复计划"],
          ["04", "控制", "人工审批与签名"],
          ["05", "恢复", "执行、验证与回滚"],
        ].map(([number, title, detail]) => (
          <div key={number}>
            <b>{number}</b>
            <strong>{title}</strong>
            <small>{detail}</small>
          </div>
        ))}
      </section>
    </>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <article className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
