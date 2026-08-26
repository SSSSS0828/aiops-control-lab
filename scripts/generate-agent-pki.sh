#!/usr/bin/env sh
# 为阶段六生成独立 CA、控制面服务端证书与节点 Agent 客户端证书。
# 私钥只写入被 .gitignore 排除的 runtime/pki，不会进入镜像、Git 或示例配置。
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "证书私钥需要设置给 systemd 与容器专用 UID，请使用 sudo 运行本脚本。" >&2
  exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PKI_ROOT="$PROJECT_ROOT/runtime/pki"
CONTROL_DIR="$PKI_ROOT/control-plane"
AGENT_DIR="$PKI_ROOT/agent"

if [ -e "$CONTROL_DIR/server.key" ] || [ -e "$AGENT_DIR/agent.key" ]; then
  echo "PKI 已存在；为避免意外轮换，本脚本拒绝覆盖。" >&2
  exit 1
fi

umask 077
mkdir -p "$CONTROL_DIR" "$AGENT_DIR"

# CA 私钥仅用于签发，部署时不挂载到任何运行中容器或 Agent 服务。
openssl genrsa -out "$PKI_ROOT/ca.key" 3072
openssl req -x509 -new -sha256 -days 3650 \
  -key "$PKI_ROOT/ca.key" -out "$PKI_ROOT/ca.crt" \
  -subj "/CN=aiops-stage6-local-ca"

openssl genrsa -out "$CONTROL_DIR/server.key" 2048
openssl req -new -key "$CONTROL_DIR/server.key" -out "$CONTROL_DIR/server.csr" \
  -subj "/CN=aiops-control-plane"
printf '%s\n' \
  'subjectAltName=DNS:aiops-control-plane,IP:127.0.0.1' \
  'extendedKeyUsage=serverAuth' > "$CONTROL_DIR/server.ext"
openssl x509 -req -sha256 -days 825 \
  -in "$CONTROL_DIR/server.csr" -CA "$PKI_ROOT/ca.crt" -CAkey "$PKI_ROOT/ca.key" \
  -CAcreateserial -out "$CONTROL_DIR/server.crt" -extfile "$CONTROL_DIR/server.ext"

openssl genrsa -out "$AGENT_DIR/agent.key" 2048
openssl req -new -key "$AGENT_DIR/agent.key" -out "$AGENT_DIR/agent.csr" \
  -subj "/CN=aiops-agent-tencent-lab-01"
printf '%s\n' 'extendedKeyUsage=clientAuth' > "$AGENT_DIR/agent.ext"
openssl x509 -req -sha256 -days 825 \
  -in "$AGENT_DIR/agent.csr" -CA "$PKI_ROOT/ca.crt" -CAkey "$PKI_ROOT/ca.key" \
  -CAcreateserial -out "$AGENT_DIR/agent.crt" -extfile "$AGENT_DIR/agent.ext"

cp "$PKI_ROOT/ca.crt" "$CONTROL_DIR/ca.crt"
cp "$PKI_ROOT/ca.crt" "$AGENT_DIR/ca.crt"
rm -f "$CONTROL_DIR/server.csr" "$CONTROL_DIR/server.ext" \
  "$AGENT_DIR/agent.csr" "$AGENT_DIR/agent.ext" "$PKI_ROOT/ca.srl"

# 控制面容器以 UID 10001 运行；仅该 UID 能读取服务端私钥。
chown 10001:10001 "$CONTROL_DIR" \
  "$CONTROL_DIR/server.key" "$CONTROL_DIR/server.crt" "$CONTROL_DIR/ca.crt"
chmod 0500 "$CONTROL_DIR"
chmod 0400 "$CONTROL_DIR/server.key" "$AGENT_DIR/agent.key" "$PKI_ROOT/ca.key"
chmod 0444 "$CONTROL_DIR/server.crt" "$CONTROL_DIR/ca.crt" "$AGENT_DIR/agent.crt" "$AGENT_DIR/ca.crt"
echo "阶段六 mTLS PKI 已生成到 $PKI_ROOT"
