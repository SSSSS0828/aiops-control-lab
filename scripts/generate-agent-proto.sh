#!/usr/bin/env sh
# 从唯一 agent.proto 生成 Go 与 Python 协议代码；生成目录不编写业务规则。
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-"$PROJECT_ROOT/.venv/bin/python"}

cd "$PROJECT_ROOT"
mkdir -p control-plane/src/aiops_control/generated agent/gen/agent/v1

"$PYTHON_BIN" -m grpc_tools.protoc -I proto \
  --python_out=control-plane/src/aiops_control/generated \
  --grpc_python_out=control-plane/src/aiops_control/generated \
  proto/agent/v1/agent.proto

# grpc_tools 按 proto package 生成绝对导入，这里改为项目实际 Python 包前缀。
sed -i \
  's/from agent.v1 import agent_pb2/from aiops_control.generated.agent.v1 import agent_pb2/' \
  control-plane/src/aiops_control/generated/agent/v1/agent_pb2_grpc.py

"$PYTHON_BIN" -m grpc_tools.protoc -I proto \
  --go_out=agent --go_opt=module=github.com/aiops-lab/aiops-agent \
  --go-grpc_out=agent --go-grpc_opt=module=github.com/aiops-lab/aiops-agent \
  proto/agent/v1/agent.proto

gofmt -w agent/gen
echo "Agent Go/Python Protobuf 代码已重新生成。"
