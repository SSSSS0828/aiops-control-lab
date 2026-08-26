#!/usr/bin/env bash
# 在已完成源码备份后部署阶段六控制面与 systemd Agent；不修改现有 Prometheus 配置。
set -euo pipefail

PROJECT_ROOT=/home/ubuntu/aiops
AGENT_BINARY=/tmp/aiops-agent-linux-amd64
cd "$PROJECT_ROOT"

if [[ "$(readlink -f .)" != "$PROJECT_ROOT" || ! -f "$AGENT_BINARY" ]]; then
  echo "项目路径或预编译 Agent 二进制校验失败" >&2
  exit 1
fi

if ! sudo test -f runtime/pki/control-plane/server.key; then
  sudo ./scripts/generate-agent-pki.sh
fi

COMPOSE=(docker compose --env-file .env -f deployments/compose.yaml -f deployments/compose.lite.yaml)

# 独立私网不发布端口；固定控制面地址仅用于已有 Prometheus 的私有抓取。
if ! docker network inspect aiops-monitoring >/dev/null 2>&1; then
  docker network create --subnet 172.30.0.0/24 \
    --label purpose=aiops-real-monitoring aiops-monitoring >/dev/null
fi
"${COMPOSE[@]}" config --quiet

# 迁移使用 IF NOT EXISTS 且 ON_ERROR_STOP，任何 SQL 错误都会在重建控制面之前停止。
"${COMPOSE[@]}" exec -T postgres \
  psql -v ON_ERROR_STOP=1 -U aiops -d aiops \
  < deployments/postgres/migrations/002_real_monitoring.sql

# 构建阶段不影响正在运行的旧容器；成功后才逐个替换控制面和 Web。
"${COMPOSE[@]}" build control-plane web
"${COMPOSE[@]}" up -d --no-deps control-plane

for _ in $(seq 1 30); do
  STATUS=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' aiops-lab-control-plane-1)
  if [[ "$STATUS" == "healthy" ]]; then
    break
  fi
  sleep 2
done
if [[ "$STATUS" != "healthy" ]]; then
  "${COMPOSE[@]}" logs --tail=100 control-plane >&2
  exit 1
fi

"${COMPOSE[@]}" up -d --no-deps web

# 从原有 .env 读取同一 HMAC 密钥但不输出；首次安装写入 root-only EnvironmentFile。
set -a
# shellcheck disable=SC1091
. ./.env
set +a
sudo env \
  AIOPS_AGENT_BINARY="$AGENT_BINARY" \
  AIOPS_AGENT_SHARED_SECRET="$AIOPS_AGENT_SHARED_SECRET" \
  ./scripts/install-agent.sh

curl --fail --silent http://127.0.0.1:8088/healthz >/dev/null
curl --fail --silent http://127.0.0.1:8088/api/v1/monitoring/health
