// 设置页只读取非敏感运行边界，任何密钥都不会进入浏览器。
import { useCallback } from "react";

import { getSafeSettings } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function SettingsPage() {
  const loader = useCallback(() => getSafeSettings(), []);
  const { data, error, loading } = useApiResource(loader);
  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState message={error} />;
  const settings = data!;
  const rows: Array<[string, boolean | string, string]> = [
    ["访问模式", settings.access_mode, "private-forward 表示仅经 SSH 隧道访问"],
    ["管理员写动作", settings.admin_actions_enabled, "控制审批、遥测附加和插件变更"],
    ["信任代理来源地址", settings.trust_proxy_client_ip, "私有直连模式应保持关闭"],
    ["Prometheus", settings.prometheus_enabled, "在线指标查询数据源"],
    ["Loki", settings.loki_enabled, "轻量服务器可关闭以节省内存"],
    ["云端 LLM", settings.llm_enabled, "关闭时自动使用规则诊断"],
    ["插件运行时", settings.plugin_runtime_enabled, "独立进程 Unix Socket/gRPC"],
    ["真实资产动作模式", settings.real_actions_mode, "observe_only 表示禁止生成和执行真实写计划"],
    ["Agent mTLS 通道", settings.agent_grpc_enabled, "宿主机 Agent 主动连接控制面回环端口"],
    ["浏览器可见密钥", settings.secrets_exposed, "必须永远为 false"],
  ];
  return (
    <>
      <PageHeader
        description="展示部署能力和安全边界，不显示、编辑或回传 Agent、管理员、实验室及模型密钥。"
        eyebrow="SAFE RUNTIME SETTINGS"
        title="系统设置"
      />
      <article className="console-card settings-card">
        {rows.map(([name, value, detail]) => (
          <div key={name}>
            <span>
              <strong>{name}</strong>
              <small>{detail}</small>
            </span>
            <code className={value === false ? "off" : "on"}>{String(value)}</code>
          </div>
        ))}
      </article>
      <article className="console-card tunnel-guide">
        <span className="eyebrow">SSH PORT FORWARD</span>
        <h2>临时访问方式</h2>
        <code>ssh -L 8088:127.0.0.1:8088 ubuntu@&lt;服务器公网 IP&gt;</code>
        <p>保持 SSH 会话后，在本机打开 http://127.0.0.1:8088。云安全组不需要开放 8088。</p>
      </article>
    </>
  );
}
