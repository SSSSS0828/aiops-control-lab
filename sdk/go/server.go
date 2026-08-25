// Package aiopspluginsdk 中的本文件实现跨语言一致的 gRPC PluginService。
//
// 输入：控制面发送的 protobuf Struct 和插件作者注册的八个处理函数。
// 处理：限制消息大小、转换为 Go map、分发处理函数并归一化错误。
// 输出：protobuf Struct；处理函数错误转成 gRPC INTERNAL，不会导致进程崩溃。
// 副作用：ServeUnix 创建权限为 0600 的 Unix Socket，并在退出时清理。
// 并发：gRPC 会并发调用处理函数，插件作者必须自行保护共享可变状态。
package aiopspluginsdk

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/structpb"
)

const maxPluginMessageBytes = 1 << 20

// Handler 是插件业务函数，不暴露 gRPC 传输对象。
type Handler func(context.Context, map[string]any) (map[string]any, error)

// Handlers 集中声明稳定的八个生命周期与能力 RPC。
type Handlers struct {
	Describe Handler
	Health   Handler
	Discover Handler
	Analyze  Handler
	Plan     Handler
	Execute  Handler
	Verify   Handler
	Rollback Handler
}

// WithDefaults 用不支持响应补齐可选能力，Describe 与 Health 仍必须显式实现。
func WithDefaults(describe Handler, health Handler) Handlers {
	unsupported := func(_ context.Context, _ map[string]any) (map[string]any, error) {
		return map[string]any{"supported": false}, nil
	}
	return Handlers{
		Describe: describe,
		Health:   health,
		Discover: unsupported,
		Analyze:  unsupported,
		Plan:     unsupported,
		Execute:  unsupported,
		Verify:   unsupported,
		Rollback: unsupported,
	}
}

// NewGRPCServer 创建已注册 PluginService 的服务，可配合 bufconn 做跨平台契约测试。
func NewGRPCServer(handlers Handlers) (*grpc.Server, error) {
	if err := validateHandlers(handlers); err != nil {
		return nil, err
	}
	server := grpc.NewServer(
		grpc.MaxRecvMsgSize(maxPluginMessageBytes),
		grpc.MaxSendMsgSize(maxPluginMessageBytes),
	)
	implementation := &pluginService{handlers: handlers}
	server.RegisterService(&pluginServiceDescription, implementation)
	return server, nil
}

// ServeUnix 在绝对 Unix Socket 路径上阻塞服务，直到上下文取消或服务异常。
func ServeUnix(ctx context.Context, socketPath string, handlers Handlers) error {
	if !filepath.IsAbs(socketPath) {
		return errors.New("插件 Unix Socket 必须使用绝对路径")
	}
	if len([]byte(socketPath)) > 100 {
		return errors.New("插件 Unix Socket 路径超过安全长度")
	}
	if err := removeStaleSocket(socketPath); err != nil {
		return err
	}
	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		return fmt.Errorf("监听插件 Unix Socket 失败: %w", err)
	}
	defer listener.Close()
	defer os.Remove(socketPath)
	if err := os.Chmod(socketPath, 0o600); err != nil {
		return fmt.Errorf("限制插件 Unix Socket 权限失败: %w", err)
	}
	server, err := NewGRPCServer(handlers)
	if err != nil {
		return err
	}
	go func() {
		<-ctx.Done()
		server.GracefulStop()
	}()
	if err := server.Serve(listener); err != nil && !errors.Is(err, grpc.ErrServerStopped) {
		return fmt.Errorf("插件 gRPC 服务异常退出: %w", err)
	}
	return nil
}

// removeStaleSocket 只删除旧 Socket，绝不覆盖普通文件或符号链接。
func removeStaleSocket(path string) error {
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("检查插件 Socket 失败: %w", err)
	}
	if info.Mode()&os.ModeSocket == 0 {
		return errors.New("插件 Socket 路径已被非 Socket 文件占用")
	}
	if err := os.Remove(path); err != nil {
		return fmt.Errorf("清理旧插件 Socket 失败: %w", err)
	}
	return nil
}

func validateHandlers(handlers Handlers) error {
	all := []Handler{
		handlers.Describe, handlers.Health, handlers.Discover, handlers.Analyze,
		handlers.Plan, handlers.Execute, handlers.Verify, handlers.Rollback,
	}
	for _, handler := range all {
		if handler == nil {
			return errors.New("八个插件 RPC 都必须注册处理函数")
		}
	}
	return nil
}

type pluginService struct {
	handlers Handlers
}

func (s *pluginService) invoke(
	ctx context.Context,
	request *structpb.Struct,
	handler Handler,
) (*structpb.Struct, error) {
	result, err := handler(ctx, request.AsMap())
	if err != nil {
		return nil, status.Error(codes.Internal, "插件处理失败")
	}
	response, err := structpb.NewStruct(result)
	if err != nil {
		return nil, status.Error(codes.Internal, "插件返回了非法 Struct 数据")
	}
	return response, nil
}

type methodSelector func(Handlers) Handler

const pluginServiceName = "aiops.plugin.v1.PluginService"

// makeMethodHandler 统一实现解码、拦截器和业务分发，避免八份生成式样板漂移。
func makeMethodHandler(
	fullMethod string,
	selector methodSelector,
) grpc.MethodHandler {
	return func(
		server any,
		ctx context.Context,
		decoder func(any) error,
		interceptor grpc.UnaryServerInterceptor,
	) (any, error) {
		request := new(structpb.Struct)
		if err := decoder(request); err != nil {
			return nil, status.Error(codes.InvalidArgument, "插件请求不是合法 Struct")
		}
		implementation := server.(*pluginService)
		invoke := func(callContext context.Context, rawRequest any) (any, error) {
			return implementation.invoke(
				callContext,
				rawRequest.(*structpb.Struct),
				selector(implementation.handlers),
			)
		}
		if interceptor == nil {
			return invoke(ctx, request)
		}
		return interceptor(ctx, request, &grpc.UnaryServerInfo{
			Server:     server,
			FullMethod: fullMethod,
		}, invoke)
	}
}

// methodDescription 统一拼接完整方法名，让协议名称只维护一处。
func methodDescription(name string, selector methodSelector) grpc.MethodDesc {
	return grpc.MethodDesc{
		MethodName: name,
		Handler:    makeMethodHandler("/"+pluginServiceName+"/"+name, selector),
	}
}

var pluginServiceDescription = grpc.ServiceDesc{
	ServiceName: pluginServiceName,
	HandlerType: (*interface{})(nil),
	Methods: []grpc.MethodDesc{
		methodDescription("Describe", func(h Handlers) Handler { return h.Describe }),
		methodDescription("Health", func(h Handlers) Handler { return h.Health }),
		methodDescription("Discover", func(h Handlers) Handler { return h.Discover }),
		methodDescription("Analyze", func(h Handlers) Handler { return h.Analyze }),
		methodDescription("Plan", func(h Handlers) Handler { return h.Plan }),
		methodDescription("Execute", func(h Handlers) Handler { return h.Execute }),
		methodDescription("Verify", func(h Handlers) Handler { return h.Verify }),
		methodDescription("Rollback", func(h Handlers) Handler { return h.Rollback }),
	},
}
