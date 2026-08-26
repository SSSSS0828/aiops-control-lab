// Package procfs 从 Linux /proc 文件系统读取低开销主机指标。
package procfs

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/aiops-lab/aiops-agent/internal/domain"
)

// Collector 不依赖第三方库，适合资源受限的单机 Agent。
type Collector struct {
	root        string
	mu          sync.Mutex
	previousCPU cpuCounters
}

type cpuCounters struct {
	total uint64
	idle  uint64
}

// NewCollector 允许测试传入临时 proc 根目录，生产环境传入 /proc。
func NewCollector(root string) *Collector {
	return &Collector{root: root}
}

// Collect 读取负载和内存快照。
func (c *Collector) Collect(_ context.Context) (domain.HostSnapshot, error) {
	load, err := c.readLoadAverage()
	if err != nil {
		return domain.HostSnapshot{}, err
	}
	total, available, err := c.readMemory()
	if err != nil {
		return domain.HostSnapshot{}, err
	}
	cpuPercent, err := c.readCPUPercent()
	if err != nil {
		return domain.HostSnapshot{}, err
	}
	diskTotal, diskAvailable, err := readDiskUsage("/")
	if err != nil {
		return domain.HostSnapshot{}, err
	}
	return domain.HostSnapshot{
		LoadOneMinute:       load,
		CPUPercent:          cpuPercent,
		MemoryTotalBytes:    total,
		MemoryAvailableByte: available,
		DiskTotalBytes:      diskTotal,
		DiskAvailableBytes:  diskAvailable,
		CollectedAt:         time.Now().UTC(),
	}, nil
}

func (c *Collector) readCPUPercent() (float64, error) {
	data, err := os.ReadFile(c.root + "/stat")
	if err != nil {
		return 0, fmt.Errorf("读取 CPU stat 失败: %w", err)
	}
	fields := strings.Fields(strings.SplitN(string(data), "\n", 2)[0])
	if len(fields) < 5 || fields[0] != "cpu" {
		return 0, fmt.Errorf("CPU stat 首行格式无效")
	}
	var values []uint64
	for _, field := range fields[1:] {
		value, parseErr := strconv.ParseUint(field, 10, 64)
		if parseErr != nil {
			return 0, fmt.Errorf("解析 CPU stat 失败: %w", parseErr)
		}
		values = append(values, value)
	}
	current := cpuCounters{idle: values[3]}
	if len(values) > 4 {
		current.idle += values[4]
	}
	for _, value := range values {
		current.total += value
	}

	// CPU 百分比必须由相邻两次累计计数求差，锁保证并发健康检查不会打乱基线。
	c.mu.Lock()
	previous := c.previousCPU
	c.previousCPU = current
	c.mu.Unlock()
	if previous.total == 0 || current.total <= previous.total {
		return 0, nil
	}
	totalDelta := current.total - previous.total
	idleDelta := current.idle - previous.idle
	return float64(totalDelta-idleDelta) / float64(totalDelta) * 100, nil
}

func (c *Collector) readLoadAverage() (float64, error) {
	data, err := os.ReadFile(c.root + "/loadavg")
	if err != nil {
		return 0, fmt.Errorf("读取 loadavg 失败: %w", err)
	}
	fields := strings.Fields(string(data))
	if len(fields) == 0 {
		return 0, fmt.Errorf("loadavg 内容为空")
	}
	value, err := strconv.ParseFloat(fields[0], 64)
	if err != nil {
		return 0, fmt.Errorf("解析一分钟负载失败: %w", err)
	}
	return value, nil
}

func (c *Collector) readMemory() (uint64, uint64, error) {
	file, err := os.Open(c.root + "/meminfo")
	if err != nil {
		return 0, 0, fmt.Errorf("读取 meminfo 失败: %w", err)
	}
	defer file.Close()

	values := make(map[string]uint64)
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		if len(fields) < 2 {
			continue
		}
		key := strings.TrimSuffix(fields[0], ":")
		if key != "MemTotal" && key != "MemAvailable" {
			continue
		}
		kilobytes, parseErr := strconv.ParseUint(fields[1], 10, 64)
		if parseErr != nil {
			return 0, 0, fmt.Errorf("解析 %s 失败: %w", key, parseErr)
		}
		values[key] = kilobytes * 1024
	}
	if err := scanner.Err(); err != nil {
		return 0, 0, fmt.Errorf("扫描 meminfo 失败: %w", err)
	}
	if values["MemTotal"] == 0 {
		return 0, 0, fmt.Errorf("meminfo 缺少 MemTotal")
	}
	return values["MemTotal"], values["MemAvailable"], nil
}
