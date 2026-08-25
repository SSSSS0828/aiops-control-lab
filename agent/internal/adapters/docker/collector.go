// Package docker 通过只读 Docker Engine API 发现 devops-lab 容器并采集资源状态。
//
// 输入：Docker Unix Socket，以及允许采集的 Compose 项目名。
// 处理：先列出容器，再只对项目内白名单服务读取一次非流式 stats。
// 输出：稳定资产 ID、运行状态、CPU、内存和重启次数。
// 安全：不接受控制面传入的过滤条件，不读取环境变量、日志正文或容器密钥。
package docker

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/aiops-lab/aiops-agent/internal/domain"
)

var monitoredServices = map[string]struct{}{
	"nginx": {}, "api": {}, "prometheus": {}, "grafana": {}, "alertmanager": {},
}

// Collector 仅持有连接 Docker Socket 的受限 HTTP 客户端。
type Collector struct {
	client  *http.Client
	project string
}

// NewCollector 创建真实容器采集器。
func NewCollector(socketPath string, project string) *Collector {
	transport := &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", socketPath)
		},
	}
	return &Collector{
		client:  &http.Client{Transport: transport, Timeout: 10 * time.Second},
		project: project,
	}
}

type listedContainer struct {
	ID     string            `json:"Id"`
	Names  []string          `json:"Names"`
	Image  string            `json:"Image"`
	State  string            `json:"State"`
	Labels map[string]string `json:"Labels"`
}

type statsPayload struct {
	CPUStats struct {
		CPUUsage struct {
			TotalUsage uint64 `json:"total_usage"`
		} `json:"cpu_usage"`
		SystemUsage uint64 `json:"system_cpu_usage"`
		OnlineCPUs  uint64 `json:"online_cpus"`
	} `json:"cpu_stats"`
	PreCPUStats struct {
		CPUUsage struct {
			TotalUsage uint64 `json:"total_usage"`
		} `json:"cpu_usage"`
		SystemUsage uint64 `json:"system_cpu_usage"`
	} `json:"precpu_stats"`
	MemoryStats struct {
		Usage uint64 `json:"usage"`
		Limit uint64 `json:"limit"`
	} `json:"memory_stats"`
	NumProcs uint64 `json:"num_procs"`
}

// Collect 返回目标 Compose 项目的真实容器快照。
func (c *Collector) Collect(ctx context.Context) ([]domain.ContainerSnapshot, error) {
	containers, err := c.list(ctx)
	if err != nil {
		return nil, err
	}
	result := make([]domain.ContainerSnapshot, 0, len(containers))
	for _, container := range containers {
		service := container.Labels["com.docker.compose.service"]
		if container.Labels["com.docker.compose.project"] != c.project {
			continue
		}
		if _, allowed := monitoredServices[service]; !allowed {
			continue
		}
		snapshot, collectErr := c.snapshot(ctx, container, service)
		if collectErr != nil {
			return nil, collectErr
		}
		result = append(result, snapshot)
	}
	return result, nil
}

func (c *Collector) list(ctx context.Context) ([]listedContainer, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://docker/containers/json?all=1", nil)
	if err != nil {
		return nil, fmt.Errorf("创建容器发现请求失败: %w", err)
	}
	response, err := c.client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("列出 Docker 容器失败: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("Docker 容器列表返回状态 %d", response.StatusCode)
	}
	var containers []listedContainer
	if err := json.NewDecoder(response.Body).Decode(&containers); err != nil {
		return nil, fmt.Errorf("解析 Docker 容器列表失败: %w", err)
	}
	return containers, nil
}

func (c *Collector) snapshot(ctx context.Context, item listedContainer, service string) (domain.ContainerSnapshot, error) {
	stats, err := c.stats(ctx, item.ID)
	if err != nil && item.State == "running" {
		return domain.ContainerSnapshot{}, err
	}
	name := service
	if len(item.Names) > 0 {
		name = strings.TrimPrefix(item.Names[0], "/")
	}
	return domain.ContainerSnapshot{
		AssetID:      fmt.Sprintf("docker/%s/%s", c.project, service),
		Name:         name,
		Service:      service,
		Image:        item.Image,
		Status:       item.State,
		CPUPercent:   cpuPercent(stats),
		MemoryBytes:  stats.MemoryStats.Usage,
		MemoryLimit:  stats.MemoryStats.Limit,
		RestartCount: c.restartCount(ctx, item.ID),
		CollectedAt:  time.Now().UTC(),
	}, nil
}

func (c *Collector) stats(ctx context.Context, containerID string) (statsPayload, error) {
	endpoint := "http://docker/containers/" + url.PathEscape(containerID) + "/stats?stream=false"
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return statsPayload{}, fmt.Errorf("创建容器 stats 请求失败: %w", err)
	}
	response, err := c.client.Do(request)
	if err != nil {
		return statsPayload{}, fmt.Errorf("读取容器 stats 失败: %w", err)
	}
	defer response.Body.Close()
	var payload statsPayload
	if response.StatusCode != http.StatusOK {
		return payload, fmt.Errorf("容器 stats 返回状态 %d", response.StatusCode)
	}
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return payload, fmt.Errorf("解析容器 stats 失败: %w", err)
	}
	return payload, nil
}

func (c *Collector) restartCount(ctx context.Context, containerID string) uint64 {
	endpoint := "http://docker/containers/" + url.PathEscape(containerID) + "/json"
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return 0
	}
	response, err := c.client.Do(request)
	if err != nil {
		return 0
	}
	defer response.Body.Close()
	var payload struct {
		RestartCount uint64 `json:"RestartCount"`
	}
	if json.NewDecoder(response.Body).Decode(&payload) != nil {
		return 0
	}
	return payload.RestartCount
}

func cpuPercent(stats statsPayload) float64 {
	cpuDelta := stats.CPUStats.CPUUsage.TotalUsage - stats.PreCPUStats.CPUUsage.TotalUsage
	systemDelta := stats.CPUStats.SystemUsage - stats.PreCPUStats.SystemUsage
	if cpuDelta == 0 || systemDelta == 0 {
		return 0
	}
	cores := stats.CPUStats.OnlineCPUs
	if cores == 0 {
		cores = 1
	}
	return float64(cpuDelta) / float64(systemDelta) * float64(cores) * 100
}
