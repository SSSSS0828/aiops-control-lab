// Package domain 定义 Agent 侧不依赖传输协议的真实遥测实体。
package domain

import "time"

// ContainerSnapshot 是一次 Docker 容器发现与资源采集结果。
type ContainerSnapshot struct {
	AssetID      string
	Name         string
	Service      string
	Image        string
	Status       string
	CPUPercent   float64
	MemoryBytes  uint64
	MemoryLimit  uint64
	RestartCount uint64
	CollectedAt  time.Time
}

// AssetSnapshot 描述 Agent 本轮确认存在的真实资产。
type AssetSnapshot struct {
	ID         string
	NodeID     string
	Kind       string
	Name       string
	Status     string
	Attributes map[string]string
}

// MetricPoint 是带资产标签的单个瞬时指标。
type MetricPoint struct {
	Name        string
	Value       float64
	Labels      map[string]string
	CollectedAt time.Time
}

// TopologyLink 描述服务间的有向依赖或可观测关系。
type TopologyLink struct {
	SourceAssetID string
	TargetAssetID string
	Relation      string
	Weight        float64
	Source        string
}

// TelemetrySnapshot 是一个完整采集批次，控制面按批次原子更新最新状态。
type TelemetrySnapshot struct {
	Metrics   []MetricPoint
	Assets    []AssetSnapshot
	Topology  []TopologyLink
	Collected time.Time
}
