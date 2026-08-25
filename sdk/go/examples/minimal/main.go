// Command minimal 展示一个只实现 Describe、Health 和 Analyze 的最小 Go 插件。
package main

import (
	"context"
	"errors"
	"log"
	"os"
	"os/signal"
	"syscall"

	sdk "github.com/aiops-lab/aiops-plugin-sdk-go"
)

func main() {
	socketPath := os.Getenv("AIOPS_PLUGIN_SOCKET")
	if socketPath == "" {
		log.Fatal("缺少 AIOPS_PLUGIN_SOCKET")
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	handlers := sdk.WithDefaults(describe, health)
	handlers.Analyze = analyze
	// SDK 只监听控制面分配的 Unix Socket，不创建任何公网 TCP 端口。
	if err := sdk.ServeUnix(ctx, socketPath, handlers); err != nil && !errors.Is(
		err,
		context.Canceled,
	) {
		log.Fatalf("Go 插件异常退出: %v", err)
	}
}

func describe(_ context.Context, _ map[string]any) (map[string]any, error) {
	return map[string]any{
		"id":           "go-minimal",
		"version":      "0.1.0",
		"capabilities": []any{"Analyzer"},
	}, nil
}

func health(_ context.Context, _ map[string]any) (map[string]any, error) {
	return map[string]any{"status": "ok"}, nil
}

func analyze(_ context.Context, payload map[string]any) (map[string]any, error) {
	target, _ := payload["target"].(string)
	return map[string]any{
		"healthy": true,
		"summary": "Go 示例插件已分析目标 " + target,
	}, nil
}
