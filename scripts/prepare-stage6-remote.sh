#!/usr/bin/env bash
# 在云服务器上备份现有项目并安全展开阶段六源码包；不重启服务、不修改数据库。
set -euo pipefail

TARGET=/home/ubuntu/aiops
SOURCE_ARCHIVE=/tmp/aiops-stage6-source.tar.gz

if [[ "$(readlink -f "$TARGET")" != "/home/ubuntu/aiops" ]]; then
  echo "项目目标路径校验失败" >&2
  exit 1
fi
if [[ ! -f "$SOURCE_ARCHIVE" || ! -f "$TARGET/.env" ]]; then
  echo "缺少源码包或现有 .env，拒绝覆盖" >&2
  exit 1
fi
if tar -tzf "$SOURCE_ARCHIVE" | grep -Eq '(^/|\.\./)'; then
  echo "源码包包含越界路径，拒绝展开" >&2
  exit 1
fi

STAMP=$(date +%Y%m%d-%H%M%S)
cd /home/ubuntu
tar --exclude='aiops/runtime' --exclude='aiops/.env' \
  -czf "aiops-pre-stage6-$STAMP.tar.gz" aiops
install -m 0600 "$TARGET/.env" "/home/ubuntu/aiops.env.pre-stage6-$STAMP"
tar -xzf "$SOURCE_ARCHIVE" -C "$TARGET"

chmod +x "$TARGET/scripts/install-agent.sh" \
  "$TARGET/scripts/generate-agent-pki.sh" \
  "$TARGET/scripts/generate-agent-proto.sh"
sh -n "$TARGET/scripts/install-agent.sh"
sh -n "$TARGET/scripts/generate-agent-pki.sh"

echo "backup=/home/ubuntu/aiops-pre-stage6-$STAMP.tar.gz"
echo "env_backup=/home/ubuntu/aiops.env.pre-stage6-$STAMP"
