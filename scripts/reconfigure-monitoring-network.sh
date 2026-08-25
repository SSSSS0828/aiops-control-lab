#!/usr/bin/env bash
# 把本次部署试建的动态网络替换为固定私有网段；只操作明确命名的新增网络连接。
set -euo pipefail

# aiops-lab_default 是本次诊断临时追加给 Prometheus 的网络，不是其原始 devops 网络。
docker network disconnect aiops-lab_default devops-prometheus 2>/dev/null || true
docker network disconnect aiops-monitoring devops-prometheus 2>/dev/null || true
docker network disconnect aiops-monitoring aiops-lab-control-plane-1 2>/dev/null || true
docker network rm aiops-monitoring >/dev/null 2>&1 || true
docker network create --subnet 172.30.0.0/24 \
  --label purpose=aiops-real-monitoring aiops-monitoring >/dev/null

cd /home/ubuntu/aiops
docker compose --env-file .env \
  -f deployments/compose.yaml -f deployments/compose.lite.yaml \
  up -d --no-deps control-plane

for _ in $(seq 1 30); do
  STATUS=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' aiops-lab-control-plane-1)
  [[ "$STATUS" == "healthy" ]] && break
  sleep 2
done
[[ "$STATUS" == "healthy" ]]
docker inspect --format '{{(index .NetworkSettings.Networks "aiops-monitoring").IPAddress}}' \
  aiops-lab-control-plane-1
