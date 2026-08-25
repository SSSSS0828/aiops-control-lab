// Package application 编排主机与 Docker 采集，并生成稳定的真实资产遥测批次。
package application

import (
	"context"
	"time"

	"github.com/aiops-lab/aiops-agent/internal/domain"
	"github.com/aiops-lab/aiops-agent/internal/ports"
)

// TelemetryService 不依赖 gRPC，使采集规则可用普通单元测试验证。
type TelemetryService struct {
	nodeID     string
	host       ports.SnapshotCollector
	containers ports.ContainerCollector
}

// NewTelemetryService 创建真实遥测编排服务。
func NewTelemetryService(nodeID string, host ports.SnapshotCollector, containers ports.ContainerCollector) *TelemetryService {
	return &TelemetryService{nodeID: nodeID, host: host, containers: containers}
}

// Collect 先采主机再采容器，任一来源失败都不发送不完整批次。
func (s *TelemetryService) Collect(ctx context.Context) (domain.TelemetrySnapshot, error) {
	host, err := s.host.Collect(ctx)
	if err != nil {
		return domain.TelemetrySnapshot{}, err
	}
	containers, err := s.containers.Collect(ctx)
	if err != nil {
		return domain.TelemetrySnapshot{}, err
	}
	collectedAt := time.Now().UTC()
	metrics := hostMetrics(s.nodeID, host)
	assets := []domain.AssetSnapshot{{
		ID: "host/" + s.nodeID, NodeID: s.nodeID, Kind: "linux_host",
		Name: s.nodeID, Status: "running",
		Attributes: map[string]string{"environment": "real", "source": "agent"},
	}}
	for _, container := range containers {
		metrics = append(metrics, containerMetrics(container)...)
		assets = append(assets, domain.AssetSnapshot{
			ID: container.AssetID, NodeID: s.nodeID, Kind: "docker_container",
			Name: container.Name, Status: container.Status,
			Attributes: map[string]string{
				"environment": "real", "source": "docker", "image": container.Image,
				"service": container.Service, "compose_project": "devops-lab",
			},
		})
	}
	return domain.TelemetrySnapshot{
		Metrics: metrics, Assets: assets, Topology: devopsTopology(), Collected: collectedAt,
	}, nil
}

func hostMetrics(nodeID string, snapshot domain.HostSnapshot) []domain.MetricPoint {
	labels := map[string]string{"asset_id": "host/" + nodeID, "node_id": nodeID, "environment": "real"}
	memoryAvailablePercent := 0.0
	if snapshot.MemoryTotalBytes > 0 {
		memoryAvailablePercent = float64(snapshot.MemoryAvailableByte) / float64(snapshot.MemoryTotalBytes) * 100
	}
	diskUsedPercent := 0.0
	if snapshot.DiskTotalBytes > 0 {
		diskUsedPercent = float64(snapshot.DiskTotalBytes-snapshot.DiskAvailableBytes) / float64(snapshot.DiskTotalBytes) * 100
	}
	return []domain.MetricPoint{
		{Name: "aiops_host_load1", Value: snapshot.LoadOneMinute, Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_host_cpu_percent", Value: snapshot.CPUPercent, Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_host_memory_total_bytes", Value: float64(snapshot.MemoryTotalBytes), Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_host_memory_available_bytes", Value: float64(snapshot.MemoryAvailableByte), Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_host_memory_available_percent", Value: memoryAvailablePercent, Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_host_disk_total_bytes", Value: float64(snapshot.DiskTotalBytes), Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_host_disk_available_bytes", Value: float64(snapshot.DiskAvailableBytes), Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_host_disk_used_percent", Value: diskUsedPercent, Labels: labels, CollectedAt: snapshot.CollectedAt},
	}
}

func containerMetrics(snapshot domain.ContainerSnapshot) []domain.MetricPoint {
	labels := map[string]string{
		"asset_id": snapshot.AssetID, "service": snapshot.Service, "environment": "real",
	}
	up := 0.0
	if snapshot.Status == "running" {
		up = 1
	}
	return []domain.MetricPoint{
		{Name: "aiops_container_up", Value: up, Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_container_cpu_percent", Value: snapshot.CPUPercent, Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_container_memory_usage_bytes", Value: float64(snapshot.MemoryBytes), Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_container_memory_limit_bytes", Value: float64(snapshot.MemoryLimit), Labels: labels, CollectedAt: snapshot.CollectedAt},
		{Name: "aiops_container_restart_count", Value: float64(snapshot.RestartCount), Labels: labels, CollectedAt: snapshot.CollectedAt},
	}
}

func devopsTopology() []domain.TopologyLink {
	asset := func(service string) string { return "docker/devops-lab/" + service }
	return []domain.TopologyLink{
		{SourceAssetID: asset("nginx"), TargetAssetID: asset("api"), Relation: "depends_on", Weight: 1.0, Source: "declared"},
		{SourceAssetID: asset("grafana"), TargetAssetID: asset("prometheus"), Relation: "queries", Weight: 0.55, Source: "declared"},
		{SourceAssetID: asset("prometheus"), TargetAssetID: asset("api"), Relation: "observes", Weight: 0.35, Source: "declared"},
		{SourceAssetID: asset("prometheus"), TargetAssetID: asset("alertmanager"), Relation: "notifies", Weight: 0.45, Source: "declared"},
	}
}
