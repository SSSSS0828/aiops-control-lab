// 导航目录是页面 ID、地址和中文名称的唯一事实来源。
export type PageId =
  | "overview"
  | "assets"
  | "topology"
  | "telemetry"
  | "incidents"
  | "diagnostics"
  | "approvals"
  | "audit"
  | "plugins"
  | "sre"
  | "lab"
  | "algorithms"
  | "settings";

interface NavigationGroup {
  label: string;
  items: Array<{ id: PageId; path: string; label: string; icon: string }>;
}

export const navigationGroups: NavigationGroup[] = [
  {
    label: "运行态势",
    items: [
      { id: "overview", path: "/overview", label: "总览", icon: "◫" },
      { id: "assets", path: "/assets", label: "资产与节点", icon: "◇" },
      { id: "topology", path: "/topology", label: "服务拓扑", icon: "⌘" },
      { id: "telemetry", path: "/telemetry", label: "指标与日志", icon: "⌁" },
    ],
  },
  {
    label: "事件处置",
    items: [
      { id: "incidents", path: "/incidents", label: "Incident 工作台", icon: "!" },
      { id: "diagnostics", path: "/diagnostics", label: "AI 诊断助手", icon: "✦" },
      { id: "approvals", path: "/approvals", label: "审批中心", icon: "✓" },
      { id: "audit", path: "/audit", label: "执行与审计", icon: "≡" },
    ],
  },
  {
    label: "工程能力",
    items: [
      { id: "plugins", path: "/plugins", label: "插件中心", icon: "⊞" },
      { id: "sre", path: "/sre", label: "SLO 与容量", icon: "◉" },
      { id: "lab", path: "/lab", label: "故障实验室", icon: "+" },
      { id: "algorithms", path: "/algorithms", label: "算法评测", icon: "∿" },
      { id: "settings", path: "/settings", label: "系统设置", icon: "⚙" },
    ],
  },
];

export function resolvePageId(path: string): PageId {
  const item = navigationGroups
    .flatMap((group) => group.items)
    .find((entry) => entry.path === path);
  return item?.id ?? "overview";
}
