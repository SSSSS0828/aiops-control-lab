// 插件中心展示已经健康注册的独立进程插件和最小权限声明。
import { useCallback } from "react";

import { listPlugins } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function PluginsPage() {
  const loader = useCallback(() => listPlugins(), []);
  const { data = [], error, loading, refresh } = useApiResource(loader);
  if (loading && !data.length) return <LoadingState />;
  if (error && !data.length) return <ErrorState message={error} />;
  return (
    <>
      <PageHeader
        actions={<button onClick={() => void refresh()}>健康检查</button>}
        description="插件以独立进程通过 Unix Socket/gRPC 工作，升级失败不会带崩控制面，并应恢复旧版本。"
        eyebrow="HOT-PLUG ECOSYSTEM"
        title="插件中心"
      />
      {!data.length && (
        <EmptyState>当前没有健康注册的插件；清单仍保存在服务器插件目录中。</EmptyState>
      )}
      <section className="plugin-grid">
        {data.map((plugin) => (
          <article className="console-card plugin-card" key={plugin.plugin_id}>
            <header>
              <span className="state-badge online">healthy</span>
              <code>v{plugin.version}</code>
            </header>
            <h2>{plugin.name}</h2>
            <small>
              {plugin.plugin_id} · API {plugin.api_version}
            </small>
            <h3>能力</h3>
            <div className="tag-list">
              {plugin.capabilities.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
            <h3>权限</h3>
            <div className="tag-list permissions">
              {plugin.permissions.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          </article>
        ))}
      </section>
      <div className="safety-note">
        安装、升级和 RPC 调用属于管理员写操作；控制台不会把任意本地路径发送给插件运行时。
      </div>
    </>
  );
}
