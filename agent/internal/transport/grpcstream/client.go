// Package grpcstream 实现 Agent 主动连接控制面的 mTLS 双向流。
//
// 输入：证书路径、控制面回环地址、节点身份和遥测应用服务。
// 处理：首帧发送身份，随后按固定周期发送带序列号批次并等待确认；断线指数退避。
// 输出：遥测批次和获批动作结果。
// 安全：证书链与 server_name 必须全部校验，绝不提供跳过 TLS 校验的配置。
package grpcstream

import (
	"context"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"log/slog"
	"os"
	"time"

	agentv1 "github.com/aiops-lab/aiops-agent/gen/agent/v1"
	"github.com/aiops-lab/aiops-agent/internal/application"
	"github.com/aiops-lab/aiops-agent/internal/domain"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
)

// Configuration 集中保存不可缺省的安全连接参数。
type Configuration struct {
	Endpoint        string
	NodeID          string
	AgentVersion    string
	ServerName      string
	CAFile          string
	CertificateFile string
	KeyFile         string
	Interval        time.Duration
}

// Client 在同一连接上复用遥测与类型化动作通道。
type Client struct {
	config    Configuration
	telemetry *application.TelemetryService
	actions   *application.ActionService
	logger    *slog.Logger
	instance  string
	startedAt time.Time
}

// New 创建客户端并生成仅在本进程生命周期有效的 instance_id。
func New(config Configuration, telemetry *application.TelemetryService, actions *application.ActionService, logger *slog.Logger) (*Client, error) {
	instance, err := randomInstanceID()
	if err != nil {
		return nil, err
	}
	if config.Interval <= 0 {
		config.Interval = 15 * time.Second
	}
	return &Client{config: config, telemetry: telemetry, actions: actions, logger: logger, instance: instance, startedAt: time.Now().UTC()}, nil
}

// Run 一直重连到上下文取消；退避上限防止控制面故障时形成连接风暴。
func (c *Client) Run(ctx context.Context) error {
	sequence := uint64(1)
	backoff := time.Second
	for ctx.Err() == nil {
		err := c.runConnection(ctx, &sequence)
		if ctx.Err() != nil {
			return nil
		}
		c.logger.Warn("Agent gRPC 连接中断，等待重连", "error", err, "backoff", backoff)
		select {
		case <-ctx.Done():
			return nil
		case <-time.After(backoff):
		}
		backoff *= 2
		if backoff > 30*time.Second {
			backoff = 30 * time.Second
		}
	}
	return nil
}

func (c *Client) runConnection(ctx context.Context, sequence *uint64) error {
	credentialsValue, err := c.transportCredentials()
	if err != nil {
		return err
	}
	connection, err := grpc.NewClient(c.config.Endpoint, grpc.WithTransportCredentials(credentialsValue))
	if err != nil {
		return fmt.Errorf("创建 gRPC 连接失败: %w", err)
	}
	defer connection.Close()
	stream, err := agentv1.NewControlPlaneGatewayClient(connection).Connect(ctx)
	if err != nil {
		return fmt.Errorf("建立遥测流失败: %w", err)
	}
	if err := stream.Send(&agentv1.AgentMessage{Payload: &agentv1.AgentMessage_Hello{Hello: c.hello()}}); err != nil {
		return fmt.Errorf("发送 Agent 身份失败: %w", err)
	}
	ticker := time.NewTicker(c.config.Interval)
	defer ticker.Stop()
	for {
		if err := c.sendTelemetry(ctx, stream, sequence); err != nil {
			return err
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

func (c *Client) sendTelemetry(ctx context.Context, stream grpc.BidiStreamingClient[agentv1.AgentMessage, agentv1.ControlMessage], sequence *uint64) error {
	snapshot, err := c.telemetry.Collect(ctx)
	if err != nil {
		return fmt.Errorf("采集真实遥测失败: %w", err)
	}
	batch := telemetryMessage(*sequence, snapshot)
	if err := stream.Send(batch); err != nil {
		return fmt.Errorf("发送遥测批次失败: %w", err)
	}
	response, err := stream.Recv()
	if err != nil {
		return fmt.Errorf("等待遥测确认失败: %w", err)
	}
	if response.AcknowledgedSequence >= *sequence {
		*sequence = response.AcknowledgedSequence + 1
	}
	for _, task := range response.Tasks {
		c.executeTask(ctx, stream, task)
	}
	return nil
}

func (c *Client) executeTask(ctx context.Context, stream grpc.BidiStreamingClient[agentv1.AgentMessage, agentv1.ControlMessage], task *agentv1.ActionTask) {
	job := domain.ActionJob{
		ID: task.TaskId, IdempotencyKey: task.IdempotencyKey, ApprovedHash: task.ApprovedHash,
		ActionType: task.ActionType, Target: task.Target, Arguments: task.Arguments,
		ExpiresAt: time.UnixMilli(task.ExpiresUnixMs).UTC(), Nonce: task.Nonce, Signature: task.Signature,
	}
	result, err := c.actions.Execute(ctx, job)
	message := &agentv1.ActionResult{TaskId: task.TaskId, FinishedUnixMs: time.Now().UTC().UnixMilli()}
	if err != nil {
		message.Message = err.Error()
	} else {
		message.Succeeded = result.Succeeded
		message.Message = result.Message
		message.FinishedUnixMs = result.FinishedAt.UnixMilli()
	}
	if sendErr := stream.Send(&agentv1.AgentMessage{Payload: &agentv1.AgentMessage_ActionResult{ActionResult: message}}); sendErr != nil {
		c.logger.Error("发送动作结果失败", "task_id", task.TaskId, "error", sendErr)
	}
}

func (c *Client) hello() *agentv1.AgentHello {
	return &agentv1.AgentHello{NodeId: c.config.NodeID, AgentVersion: c.config.AgentVersion, InstanceId: c.instance, StartedUnixMs: c.startedAt.UnixMilli()}
}

func (c *Client) transportCredentials() (credentials.TransportCredentials, error) {
	certificate, err := tls.LoadX509KeyPair(c.config.CertificateFile, c.config.KeyFile)
	if err != nil {
		return nil, fmt.Errorf("读取 Agent 客户端证书失败: %w", err)
	}
	caData, err := os.ReadFile(c.config.CAFile)
	if err != nil {
		return nil, fmt.Errorf("读取 Agent CA 失败: %w", err)
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caData) {
		return nil, fmt.Errorf("Agent CA 文件不包含有效证书")
	}
	return credentials.NewTLS(&tls.Config{
		MinVersion: tls.VersionTLS13, RootCAs: roots, Certificates: []tls.Certificate{certificate}, ServerName: c.config.ServerName,
	}), nil
}

func randomInstanceID() (string, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", fmt.Errorf("生成 Agent 实例 ID 失败: %w", err)
	}
	return fmt.Sprintf("%x", buffer), nil
}

func telemetryMessage(sequence uint64, snapshot domain.TelemetrySnapshot) *agentv1.AgentMessage {
	batch := &agentv1.TelemetryBatch{Sequence: sequence, CollectedUnixMs: snapshot.Collected.UnixMilli()}
	for _, metric := range snapshot.Metrics {
		batch.Metrics = append(batch.Metrics, &agentv1.MetricPoint{Name: metric.Name, Value: metric.Value, Labels: metric.Labels, CollectedUnixMs: metric.CollectedAt.UnixMilli()})
	}
	for _, asset := range snapshot.Assets {
		batch.Assets = append(batch.Assets, &agentv1.AssetSnapshot{AssetId: asset.ID, NodeId: asset.NodeID, Kind: asset.Kind, Name: asset.Name, Status: asset.Status, Attributes: asset.Attributes})
	}
	for _, edge := range snapshot.Topology {
		batch.Topology = append(batch.Topology, &agentv1.TopologyLink{SourceAssetId: edge.SourceAssetID, TargetAssetId: edge.TargetAssetID, Relation: edge.Relation, Weight: edge.Weight, Source: edge.Source})
	}
	return &agentv1.AgentMessage{Payload: &agentv1.AgentMessage_Telemetry{Telemetry: batch}}
}
