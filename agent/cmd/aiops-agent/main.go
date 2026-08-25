// Command aiops-agent 启动节点侧采集与安全执行服务。
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/aiops-lab/aiops-agent/internal/adapters/docker"
	"github.com/aiops-lab/aiops-agent/internal/adapters/procfs"
	"github.com/aiops-lab/aiops-agent/internal/application"
	"github.com/aiops-lab/aiops-agent/internal/transport/grpcstream"
	"github.com/aiops-lab/aiops-agent/internal/transport/httpserver"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	socketPath := environmentOrDefault("AIOPS_DOCKER_SOCKET", "/var/run/docker.sock")
	procRoot := environmentOrDefault("AIOPS_PROC_ROOT", "/proc")
	listenAddress := environmentOrDefault("AIOPS_AGENT_LISTEN", "127.0.0.1:9105")
	sharedSecret := os.Getenv("AIOPS_AGENT_SHARED_SECRET")
	authenticator, err := application.NewTaskAuthenticator(sharedSecret)
	if err != nil {
		logger.Error("Agent 安全配置无效，拒绝启动", "error", err)
		os.Exit(1)
	}

	executor := docker.NewExecutor(socketPath)
	actions := application.NewActionServiceWithMode(
		executor,
		authenticator,
		environmentOrDefault("AIOPS_REAL_ACTIONS_MODE", "observe_only"),
	)
	collector := procfs.NewCollector(procRoot)
	transport := httpserver.New(actions, collector, logger)

	server := &http.Server{
		Addr:              listenAddress,
		Handler:           transport.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	go serveCompatibilityHTTP(server, logger)

	grpcEndpoint := os.Getenv("AIOPS_CONTROL_GRPC_ENDPOINT")
	if grpcEndpoint == "" {
		// 迁移窗口保留旧本地 HTTP；未配置 gRPC 时不意外连接外部地址。
		select {}
	}
	nodeID := environmentOrDefault("AIOPS_NODE_ID", "tencent-lab-01")
	containerCollector := docker.NewCollector(socketPath, environmentOrDefault("AIOPS_MONITORED_COMPOSE_PROJECT", "devops-lab"))
	telemetry := application.NewTelemetryService(nodeID, collector, containerCollector)
	client, err := grpcstream.New(grpcstream.Configuration{
		Endpoint: grpcEndpoint, NodeID: nodeID, AgentVersion: "0.2.0",
		ServerName: environmentOrDefault("AIOPS_CONTROL_GRPC_SERVER_NAME", "aiops-control-plane"),
		CAFile:     os.Getenv("AIOPS_AGENT_CA_FILE"), CertificateFile: os.Getenv("AIOPS_AGENT_CERT_FILE"),
		KeyFile: os.Getenv("AIOPS_AGENT_KEY_FILE"), Interval: 15 * time.Second,
	}, telemetry, actions, logger)
	if err != nil {
		logger.Error("初始化 Agent mTLS 客户端失败", "error", err)
		os.Exit(1)
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	logger.Info("AIOps Agent 主动遥测已启动", "node_id", nodeID, "endpoint", grpcEndpoint)
	if err := client.Run(ctx); err != nil {
		logger.Error("AIOps Agent 遥测客户端异常退出", "error", err)
		os.Exit(1)
	}
}

func serveCompatibilityHTTP(server *http.Server, logger *slog.Logger) {
	logger.Info("Agent 本地兼容接口已启动", "address", server.Addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Error("Agent 本地兼容接口异常退出", "error", err)
		os.Exit(1)
	}
}

func environmentOrDefault(name string, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
