// AppShell 只负责全站导航、私有访问提示和页面内容插槽。
import type { ReactNode } from "react";

import { navigationGroups, resolvePageId } from "./navigation";

interface AppShellProps {
  path: string;
  children: ReactNode;
}

export function AppShell({ path, children }: AppShellProps) {
  const activePage = resolvePageId(path);
  return (
    <div className="console-shell">
      <aside className="sidebar">
        <a className="console-brand" href="#/overview">
          <span>A·</span>
          <div>
            <strong>AIOPS CONTROL</strong>
            <small>PRIVATE CONSOLE</small>
          </div>
        </a>
        <nav aria-label="控制台导航">
          {navigationGroups.map((group) => (
            <section className="nav-group" key={group.label}>
              <span>{group.label}</span>
              {group.items.map((item) => (
                <a
                  className={activePage === item.id ? "active" : ""}
                  href={`#${item.path}`}
                  key={item.id}
                >
                  <i>{item.icon}</i>
                  {item.label}
                </a>
              ))}
            </section>
          ))}
        </nav>
        <div className="private-access-note">
          <span className="live-dot" />
          仅回环监听
          <small>通过 SSH 端口转发访问</small>
        </div>
      </aside>
      <div className="console-main">
        <div className="console-topbar">
          <span>NODE / TENCENT-LAB-01</span>
          <span>人工审批默认开启 · AI 无权直接执行</span>
        </div>
        <div className="global-observe-bar">
          REAL ENVIRONMENT · OBSERVE ONLY · 真实资产写操作已关闭
        </div>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
