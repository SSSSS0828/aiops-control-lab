# Agent 构建阶段生成静态 Go 二进制，运行镜像不携带编译工具链。
FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
COPY cmd ./cmd
COPY gen ./gen
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/aiops-agent ./cmd/aiops-agent

FROM alpine:3.21
RUN addgroup -S aiops && adduser -S -G aiops aiops
COPY --from=build /out/aiops-agent /usr/local/bin/aiops-agent
# Docker Socket 的权限由部署环境控制；容器自身不安装 Shell 运维脚本。
EXPOSE 9105
ENTRYPOINT ["/usr/local/bin/aiops-agent"]
