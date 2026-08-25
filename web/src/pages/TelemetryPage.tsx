// 可观测性页展示真实 Agent 数据新鲜度、固定健康探针、规则状态与主机趋势。
import { useCallback } from "react";

import {
  getAssetMetrics,
  getMonitoringHealth,
  listMonitorEvaluations,
  listMonitorRules,
  listRealAssets,
} from "../features/monitoring/api";
import { MetricSparkline } from "../features/monitoring/MetricSparkline";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function TelemetryPage() {
  const loader = useCallback(async () => {
    const [health, rules, evaluations, assets] = await Promise.all([
      getMonitoringHealth(),
      listMonitorRules(),
      listMonitorEvaluations(),
      listRealAssets(),
    ]);
    const host = assets.find((item) => item.kind === "linux_host");
    const cpu = host
      ? await getAssetMetrics(host.id, "aiops_host_cpu_percent").catch(() => undefined)
      : undefined;
    return { health, rules, evaluations, cpu };
  }, []);
  const { data, error, loading, refresh } = useApiResource(loader);
  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState message={error} />;
  const { health, rules, evaluations, cpu } = data!;
  const latestCPU = cpu?.latest[0]?.value;
  return (
    <>
      <PageHeader
        actions={<button onClick={() => void refresh()}>刷新监测状态</button>}
        description="Agent 每 15 秒推送最新值，Prometheus 保存时序；控制面每分钟评估一次确定性规则。"
        eyebrow="REAL TELEMETRY"
        title="真实指标与健康"
      />
      <section className="metric-grid">
        <Metric label="Agent 节点" value={String(health.node_count)} tone="cyan" />
        <Metric label="数据延迟" value={formatLag(health.metric_lag_seconds)} tone="green" />
        <Metric
          label="主机 CPU"
          value={latestCPU === undefined ? "--" : `${latestCPU.toFixed(1)}%`}
          tone="violet"
        />
        <Metric
          label="告警规则"
          value={String(rules.filter((item) => item.enabled).length)}
          tone="amber"
        />
      </section>
      <section className="two-column-grid telemetry-grid">
        <article className="console-card telemetry-chart-card">
          <div className="card-heading">
            <div>
              <span>HOST CPU / 30 MIN</span>
              <h2>主机 CPU 趋势</h2>
            </div>
          </div>
          <MetricSparkline points={cpu?.history ?? []} />
          <small>历史查询仅使用注册指标名和已发现资产 ID；页面不能提交任意 PromQL。</small>
        </article>
        <article className="console-card">
          <div className="card-heading">
            <div>
              <span>REGISTERED HEALTH TARGETS</span>
              <h2>固定健康探针</h2>
            </div>
          </div>
          <div className="health-target-list">
            {health.targets.map((target) => (
              <div key={target.id}>
                <span className={`state-badge ${target.healthy ? "healthy" : "failed"}`}>
                  {target.healthy ? "healthy" : "failed"}
                </span>
                <strong>{target.id}</strong>
                <small>
                  HTTP {target.status_code || "--"} · {target.latency_ms} ms
                </small>
              </div>
            ))}
          </div>
        </article>
      </section>
      <section className="two-column-grid telemetry-grid">
        <article className="console-card">
          <div className="card-heading">
            <div>
              <span>MONITOR RULES</span>
              <h2>在线规则</h2>
            </div>
          </div>
          <div className="rule-list">
            {rules.map((rule) => (
              <div key={rule.id}>
                <span className={`state-badge ${rule.enabled ? "online" : "disabled"}`}>
                  {rule.enabled ? "online" : "disabled"}
                </span>
                <strong>{rule.name}</strong>
                <code>
                  {rule.metric_name} {rule.operator} {rule.threshold}
                </code>
                <small>
                  命中 {rule.consecutive_cycles} 次告警 / 正常 {rule.recovery_cycles} 次恢复
                </small>
              </div>
            ))}
          </div>
        </article>
        <article className="console-card">
          <div className="card-heading">
            <div>
              <span>LATEST EVALUATIONS</span>
              <h2>最近评估</h2>
            </div>
          </div>
          <div className="rule-list">
            {evaluations.slice(0, 12).map((evaluation) => (
              <div key={evaluation.id}>
                <span className={`state-badge ${evaluation.state}`}>{evaluation.state}</span>
                <strong>{evaluation.asset_id}</strong>
                <code>{evaluation.value.toFixed(2)}</code>
                <small>{new Date(evaluation.evaluated_at).toLocaleString()}</small>
              </div>
            ))}
            {!evaluations.length && <p className="inline-empty">等待首轮规则评估。</p>}
          </div>
        </article>
      </section>
    </>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <article className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function formatLag(value: number | null) {
  if (value === null) return "--";
  return value < 60 ? `${Math.round(value)}s` : `${Math.round(value / 60)}m`;
}
