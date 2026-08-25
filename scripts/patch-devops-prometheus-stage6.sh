#!/usr/bin/env bash
# 为现有 devops-lab Prometheus 增加 AIOps 注册指标抓取；先验证临时配置再原子替换。
set -euo pipefail

CONFIG=/srv/devops-lab/monitoring/prometheus.yml
EXPECTED=/srv/devops-lab/monitoring/prometheus.yml

if [[ "$(readlink -f "$CONFIG")" != "$EXPECTED" ]]; then
  echo "Prometheus 配置目标路径校验失败" >&2
  exit 1
fi
if grep -q 'job_name: "aiops-real-agent"' "$CONFIG"; then
  if docker exec devops-prometheus \
    grep -q 'job_name: "aiops-real-agent"' /etc/prometheus/prometheus.yml; then
    echo "aiops-real-agent 抓取任务已经存在，无需重复修改。"
    exit 0
  fi
  echo "宿主机与容器 bind mount inode 不一致，请单独重建 Prometheus 后重试。" >&2
  exit 2
fi

# 旧 Prometheus 容器的 Docker DNS 已失效，因此追加独立私网固定地址而不重启容器。
docker network connect --ip 172.30.0.3 aiops-monitoring devops-prometheus 2>/dev/null || true

# 先证明固定私网和指标端点确实可达。
docker exec devops-prometheus \
  wget -qO- http://172.30.0.2:8000/internal/metrics/agent >/dev/null

TEMP_CONFIG=$(mktemp)
trap 'rm -f "$TEMP_CONFIG"' EXIT
cp "$CONFIG" "$TEMP_CONFIG"
cat >> "$TEMP_CONFIG" <<'YAML'

  # AIOps 控制面只暴露 systemd Agent 的注册最新值，原始时序由本 Prometheus 保存。
  - job_name: "aiops-real-agent"
    metrics_path: /internal/metrics/agent
    static_configs:
      - targets:
          - "172.30.0.2:8000"
YAML

# 临时文件先进入容器执行与生产版本相同的 promtool，失败时原配置完全不变。
chmod 0644 "$TEMP_CONFIG"
docker cp "$TEMP_CONFIG" devops-prometheus:/tmp/prometheus-stage6.yml
docker exec devops-prometheus \
  promtool check config /tmp/prometheus-stage6.yml

STAMP=$(date +%Y%m%d-%H%M%S)
sudo cp "$CONFIG" "$CONFIG.pre-stage6-$STAMP"
# 写入原 inode 让只读 bind mount 继续看到同一个文件；不能使用会替换 inode 的 install。
sudo dd if="$TEMP_CONFIG" of="$CONFIG" conv=fsync status=none
docker kill --signal=HUP devops-prometheus >/dev/null
sleep 3
docker exec devops-prometheus \
  promtool check config /etc/prometheus/prometheus.yml
echo "backup=$CONFIG.pre-stage6-$STAMP"
