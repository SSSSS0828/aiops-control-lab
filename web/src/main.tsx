// 前端入口只负责挂载应用，业务状态由功能组件维护。
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles/global.css";
import "./styles/incidents.css";
import "./styles/lab.css";
import "./styles/shell.css";
import "./styles/console.css";
import "./styles/overview.css";
import "./styles/inventory.css";
import "./styles/incident-diagnostics.css";
import "./styles/sre-settings.css";
import "./styles/pages.css";
import "./styles/portfolio-demo.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("页面缺少 root 挂载节点");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
