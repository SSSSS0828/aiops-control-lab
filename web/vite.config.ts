// Vite 开发配置：本地 API 请求代理到 FastAPI，生产环境由 Caddy 同源转发。
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // 允许开发机端口被占用时显式覆盖 API 地址，生产构建仍使用 Caddy 同源代理。
  const environment = loadEnv(mode, ".", "");
  const apiTarget = environment.AIOPS_DEV_API_URL || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": apiTarget,
        "/healthz": apiTarget,
      },
    },
  };
});
