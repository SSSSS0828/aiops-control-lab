// Package aiopspluginsdk_test 从公开 API 验证 Go 插件的 gRPC 线协议。
package aiopspluginsdk_test

import (
	"context"
	"errors"
	"net"
	"testing"
	"time"

	sdk "github.com/aiops-lab/aiops-plugin-sdk-go"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/types/known/structpb"
)

const bufferSize = 1024 * 1024

func TestHealthContractAndDefaultCapability(t *testing.T) {
	// bufconn 在内存中运行真实 HTTP/2 gRPC，Windows 和 Linux 使用同一契约测试。
	handlers := sdk.WithDefaults(
		func(_ context.Context, _ map[string]any) (map[string]any, error) {
			return map[string]any{"id": "go-example"}, nil
		},
		func(_ context.Context, _ map[string]any) (map[string]any, error) {
			return map[string]any{"status": "ok"}, nil
		},
	)
	server, err := sdk.NewGRPCServer(handlers)
	if err != nil {
		t.Fatalf("创建插件服务失败: %v", err)
	}
	listener := bufconn.Listen(bufferSize)
	go func() {
		_ = server.Serve(listener)
	}()
	defer server.Stop()

	connection := dialBuffer(t, listener)
	defer connection.Close()
	health := invoke(t, connection, "Health")
	if health.AsMap()["status"] != "ok" {
		t.Fatalf("健康契约不匹配: %+v", health.AsMap())
	}
	defaultAnalyze := invoke(t, connection, "Analyze")
	if defaultAnalyze.AsMap()["supported"] != false {
		t.Fatalf("未实现能力必须显式返回不支持: %+v", defaultAnalyze.AsMap())
	}
}

func TestHandlerErrorIsIsolated(t *testing.T) {
	handlers := sdk.WithDefaults(
		func(_ context.Context, _ map[string]any) (map[string]any, error) {
			return nil, errors.New("模拟插件内部密钥错误")
		},
		func(_ context.Context, _ map[string]any) (map[string]any, error) {
			return map[string]any{"status": "ok"}, nil
		},
	)
	server, err := sdk.NewGRPCServer(handlers)
	if err != nil {
		t.Fatalf("创建插件服务失败: %v", err)
	}
	listener := bufconn.Listen(bufferSize)
	go func() { _ = server.Serve(listener) }()
	defer server.Stop()
	connection := dialBuffer(t, listener)
	defer connection.Close()

	request, _ := structpb.NewStruct(map[string]any{})
	response := new(structpb.Struct)
	err = connection.Invoke(
		context.Background(),
		"/aiops.plugin.v1.PluginService/Describe",
		request,
		response,
	)
	if status.Code(err) != codes.Internal {
		t.Fatalf("插件异常必须归一化为 INTERNAL，实际: %v", err)
	}
	if status.Convert(err).Message() != "插件处理失败" {
		t.Fatalf("传输错误不得泄露插件内部信息: %v", err)
	}
}

func dialBuffer(t *testing.T, listener *bufconn.Listener) *grpc.ClientConn {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	connection, err := grpc.NewClient(
		"passthrough:///bufnet",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) {
			return listener.Dial()
		}),
	)
	if err != nil {
		t.Fatalf("连接内存 gRPC 服务失败: %v", err)
	}
	connection.Connect()
	select {
	case <-ctx.Done():
		// Invoke 自身仍会给出更准确错误，因此这里只限制测试不会永久等待。
	default:
	}
	return connection
}

func invoke(t *testing.T, connection *grpc.ClientConn, method string) *structpb.Struct {
	t.Helper()
	request, _ := structpb.NewStruct(map[string]any{})
	response := new(structpb.Struct)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := connection.Invoke(
		ctx,
		"/aiops.plugin.v1.PluginService/"+method,
		request,
		response,
	); err != nil {
		t.Fatalf("调用 %s 失败: %v", method, err)
	}
	return response
}
