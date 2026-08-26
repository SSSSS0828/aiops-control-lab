// Package ports 声明 Agent 应用层需要的外部能力。
package ports

import (
	"context"

	"github.com/aiops-lab/aiops-agent/internal/domain"
)

// ActionExecutor 负责把类型化动作转换为具体系统调用。
type ActionExecutor interface {
	Execute(ctx context.Context, job domain.ActionJob) (domain.ActionResult, error)
}

// SnapshotCollector 负责采集一份主机状态快照。
type SnapshotCollector interface {
	Collect(ctx context.Context) (domain.HostSnapshot, error)
}

// ContainerCollector 发现允许项目中的容器并读取轻量资源快照。
type ContainerCollector interface {
	Collect(ctx context.Context) ([]domain.ContainerSnapshot, error)
}

// TelemetryCollector 生成一个可以安全重试的完整遥测批次。
type TelemetryCollector interface {
	Collect(ctx context.Context) (domain.TelemetrySnapshot, error)
}
