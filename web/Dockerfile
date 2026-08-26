# 前端构建阶段执行类型检查并生成静态资源。
FROM node:24-alpine AS build
ARG VITE_BASE_PATH=/
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
# Corepack 使用锁文件指定的依赖树，避免镜像构建随 latest 标签意外漂移。
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
# 路径前缀由部署环境传入；类型检查与 Vite 构建必须在同一层失败退出。
RUN pnpm exec tsc --noEmit && pnpm exec vite build --base="${VITE_BASE_PATH}"

# Caddy 同时提供静态资源、HTTPS 和同源 API 反向代理。
FROM caddy:2.9-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 80 443
