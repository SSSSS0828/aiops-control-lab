// Package application 验证真实资产 ID、指标标签和拓扑关系保持稳定。
package application

import (
	"context"
	"testing"
	"time"

	"github.com/aiops-lab/aiops-agent/internal/domain"
)

type fakeHostCollector struct{}

func (fakeHostCollector) Collect(context.Context) (domain.HostSnapshot, error) {
	return domain.HostSnapshot{
		CPUPercent: 20, MemoryTotalBytes: 100, MemoryAvailableByte: 25,
		DiskTotalBytes: 1000, DiskAvailableBytes: 400, CollectedAt: time.Now().UTC(),
	}, nil
}

type fakeContainerCollector struct{}

func (fakeContainerCollector) Collect(context.Context) ([]domain.ContainerSnapshot, error) {
	return []domain.ContainerSnapshot{{
		AssetID: "docker/devops-lab/api", Name: "devops-api", Service: "api",
		Image: "devops-api:latest", Status: "running", CPUPercent: 12,
		MemoryBytes: 1000, MemoryLimit: 2000, RestartCount: 1, CollectedAt: time.Now().UTC(),
	}}, nil
}

func TestTelemetryServiceBuildsStableRealAssetBatch(t *testing.T) {
	service := NewTelemetryService("tencent-lab-01", fakeHostCollector{}, fakeContainerCollector{})
	snapshot, err := service.Collect(context.Background())
	if err != nil {
		t.Fatalf("遥测编排失败: %v", err)
	}
	if snapshot.Assets[0].ID != "host/tencent-lab-01" {
		t.Fatalf("主机资产 ID 不稳定: %s", snapshot.Assets[0].ID)
	}
	if snapshot.Assets[1].ID != "docker/devops-lab/api" {
		t.Fatalf("容器资产 ID 不稳定: %s", snapshot.Assets[1].ID)
	}
	if len(snapshot.Topology) != 4 {
		t.Fatalf("预期四条真实拓扑关系，实际 %d", len(snapshot.Topology))
	}
}
