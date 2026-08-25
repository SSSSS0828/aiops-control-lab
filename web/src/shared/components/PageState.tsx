// PageState 为各业务页面提供一致的加载、错误和空状态反馈。
import type { ReactNode } from "react";

export function LoadingState({ label = "正在读取控制面数据…" }: { label?: string }) {
  return <div className="page-state loading-state">{label}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return <div className="page-state error-state">读取失败：{message}</div>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="page-state empty-state">{children}</div>;
}
