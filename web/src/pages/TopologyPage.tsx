// 拓扑页展示 Agent 上报的真实依赖、查询、观测和通知关系。
import { useCallback } from "react";

import { getRealTopology } from "../features/monitoring/api";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function TopologyPage() {
  const loader = useCallback(() => getRealTopology(), []);
  const { data, error, loading } = useApiResource(loader);
  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState message={error} />;
  const nodeMap = new Map(data!.nodes.map((node) => [node.id, node]));
  return (
    <>
      <PageHeader
        description="业务依赖的 RCA 权重高于观测关系；箭头从调用或观察方指向被依赖资产。"
        eyebrow="REAL SERVICE GRAPH"
        title="真实服务拓扑"
      />
      <article className="console-card topology-canvas">
        <div className="topology-node-grid">
          {data!.nodes.map((node) => (
            <div
              className={`topology-node ${node.status === "running" ? "healthy" : "degraded"}`}
              key={node.id}
            >
              <span>{node.kind}</span>
              <strong>{node.name}</strong>
              <code>{node.id}</code>
            </div>
          ))}
        </div>
        <div className="edge-list">
          {data!.edges.map((edge) => (
            <div key={`${edge.source_asset_id}-${edge.relation}-${edge.target_asset_id}`}>
              <strong>{nodeMap.get(edge.source_asset_id)?.name ?? edge.source_asset_id}</strong>
              <span>
                {edge.relation} · {edge.weight.toFixed(2)}
              </span>
              <strong>{nodeMap.get(edge.target_asset_id)?.name ?? edge.target_asset_id}</strong>
            </div>
          ))}
          {!data!.edges.length && <p className="inline-empty">等待 Agent 上报真实拓扑。</p>}
        </div>
      </article>
    </>
  );
}
