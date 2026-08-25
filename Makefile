# 常用开发命令保持跨阶段一致，CI 也复用这些入口。
.PHONY: test lint build docs compose-check

test:
	cd control-plane && ../.venv/bin/python -m pytest
	PYTHONPATH=sdk/python/src .venv/bin/python -m pytest sdk/python/tests lab/tests experiments/tests
	cd agent && go test -race ./...
	cd sdk/go && go test -race ./...
	cd web && pnpm run test

lint:
	.venv/bin/python -m ruff check control-plane sdk plugins lab scripts experiments
	cd control-plane && ../.venv/bin/python -m mypy src
	.venv/bin/python -m mypy --strict sdk/python/src
	test -z "$$(cd agent && gofmt -l .)"
	cd agent && go vet ./...
	test -z "$$(cd sdk/go && gofmt -l .)"
	cd sdk/go && go vet ./...
	cd web && pnpm run lint
	cd web && pnpm run format:check

build:
	cd agent && go build ./cmd/aiops-agent
	cd web && pnpm run build

docs:
	.venv/bin/python scripts/check_chinese_docs.py

compose-check:
	# 以下固定值只用于解析配置，不会启动服务；真实部署必须从 .env 注入随机密钥。
	AIOPS_AGENT_SHARED_SECRET=ci-agent-secret-0123456789abcdef AIOPS_LAB_CONTROL_TOKEN=ci-lab-token-0123456789abcdef docker compose -f deployments/compose.yaml config --quiet
	AIOPS_AGENT_SHARED_SECRET=ci-agent-secret-0123456789abcdef AIOPS_LAB_CONTROL_TOKEN=ci-lab-token-0123456789abcdef docker compose -f deployments/compose.yaml -f deployments/compose.lite.yaml config --quiet
