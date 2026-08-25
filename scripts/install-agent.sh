#!/usr/bin/env sh
# 在 Linux 主机编译并安装 Agent。脚本不自动开放防火墙端口。
set -eu

# 必须由管理员明确执行，因为目标目录和 systemd 都需要 root 权限。
if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 sudo 运行该脚本" >&2
  exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SOURCE_PKI="$PROJECT_ROOT/runtime/pki/agent"

if [ ! -f "$SOURCE_PKI/ca.crt" ] || [ ! -f "$SOURCE_PKI/agent.crt" ] || [ ! -f "$SOURCE_PKI/agent.key" ]; then
  echo "缺少 Agent mTLS 文件，请先以普通用户运行 scripts/generate-agent-pki.sh" >&2
  exit 1
fi

# 云主机没有 Go 工具链时可传入本地交叉编译产物；两条路径都先写临时文件再原子替换。
if [ -n "${AIOPS_AGENT_BINARY:-}" ]; then
  install -m 0755 "$AIOPS_AGENT_BINARY" /tmp/aiops-agent.new
elif command -v go >/dev/null 2>&1; then
  cd "$PROJECT_ROOT/agent"
  go build -trimpath -o /tmp/aiops-agent.new ./cmd/aiops-agent
else
  echo "服务器没有 Go，请通过 AIOPS_AGENT_BINARY 指定 Linux amd64 构建产物" >&2
  exit 1
fi
install -m 0755 /tmp/aiops-agent.new /usr/local/bin/aiops-agent
rm -f /tmp/aiops-agent.new

# 首次安装生成独立的 256 位共享密钥；已有文件保持不变，避免升级使控制面突然失联。
install -d -m 0700 /etc/aiops
if [ ! -f /etc/aiops/agent.env ]; then
  AGENT_SECRET_VALUE=${AIOPS_AGENT_SHARED_SECRET:-}
  if [ "${#AGENT_SECRET_VALUE}" -lt 32 ]; then
    echo "首次安装必须通过环境变量传入与控制面相同的 AIOPS_AGENT_SHARED_SECRET" >&2
    exit 1
  fi
  umask 077
  printf 'AIOPS_AGENT_SHARED_SECRET=%s\n' "$AGENT_SECRET_VALUE" > /etc/aiops/agent.env
fi
chmod 0600 /etc/aiops/agent.env

# Agent 证书仅允许 root 服务读取；安装使用原子覆盖所需的 install 语义。
install -d -m 0700 /etc/aiops/pki
install -m 0444 "$SOURCE_PKI/ca.crt" /etc/aiops/pki/ca.crt
install -m 0444 "$SOURCE_PKI/agent.crt" /etc/aiops/pki/agent.crt
install -m 0400 "$SOURCE_PKI/agent.key" /etc/aiops/pki/agent.key

# 安装服务单元并让 systemd 重新加载配置。
install -m 0644 "$PROJECT_ROOT/deployments/systemd/aiops-agent.service" \
  /etc/systemd/system/aiops-agent.service
systemctl daemon-reload
systemctl enable --now aiops-agent
systemctl --no-pager status aiops-agent
