// 资产页展示 Agent 实际发现结果，实验资产不再冒充真实环境状态。
import { useCallback } from "react";

import { getMonitoringHealth, listAgentNodes, listRealAssets } from "../features/monitoring/api";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function AssetsPage() {
  const loader = useCallback(
    () => Promise.all([listAgentNodes(), listRealAssets(), getMonitoringHealth()]),
    [],
  );
  const { data, error, loading, refresh } = useApiResource(loader);
  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState message={error} />;
  const [nodes, assets, health] = data!;
  return (
    <>
      <PageHeader
        actions={<button onClick={() => void refresh()}>刷新发现结果</button>}
        description="这里显示 systemd Agent 从当前腾讯云主机和 devops-lab Docker 项目实际发现的资产。"
        eyebrow="REAL ASSET INVENTORY"
        title="真实资产与 Agent"
      />
      <div className="observe-banner">
        <strong>真实环境：{health.real_actions_mode}</strong>
        <span>当前默认只观察，不自动注入故障，也不生成或执行真实写操作。</span>
      </div>
      <section className="node-strip">
        {nodes.map((node) => (
          <article className="console-card node-card" key={node.id}>
            <span className={`state-badge ${node.status}`}>{node.status}</span>
            <div>
              <strong>{node.id}</strong>
              <small>Agent {node.version}</small>
            </div>
            <code>{new Date(node.last_heartbeat_at).toLocaleString()}</code>
            <small>mTLS / {node.certificate_identity}</small>
          </article>
        ))}
        {!nodes.length && (
          <p className="inline-empty console-card">等待 systemd Agent 首次连接。</p>
        )}
      </section>
      <section className="asset-grid">
        {assets.map((asset) => (
          <article className="console-card asset-card" key={asset.id}>
            <header>
              <span className="asset-kind">{asset.kind}</span>
              <span className={`state-badge ${asset.status === "running" ? "healthy" : "failed"}`}>
                {asset.status}
              </span>
            </header>
            <h2>{asset.name}</h2>
            <code>{asset.id}</code>
            <dl>
              <div>
                <dt>所属节点</dt>
                <dd>{asset.node_id}</dd>
              </div>
              <div>
                <dt>数据来源</dt>
                <dd>{asset.source}</dd>
              </div>
              <div>
                <dt>最后发现</dt>
                <dd>{new Date(asset.last_seen_at).toLocaleTimeString()}</dd>
              </div>
            </dl>
            <footer>
              <span>{asset.environment === "real" ? "真实环境" : "实验沙箱"}</span>
              {asset.attributes.service && <span>{asset.attributes.service}</span>}
              {asset.attributes.image && <span>{asset.attributes.image}</span>}
            </footer>
          </article>
        ))}
        {!assets.length && <p className="inline-empty console-card">尚未收到真实资产批次。</p>}
      </section>
    </>
  );
}
