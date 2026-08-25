// Package procfs 验证 Linux 累计计数到主机瞬时指标的转换。
package procfs

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestCollectorReadsHostSnapshotAndCPUDelta(t *testing.T) {
	root := t.TempDir()
	writeFixture(t, root, "loadavg", "1.25 0.80 0.50 1/100 42\n")
	writeFixture(t, root, "meminfo", "MemTotal: 4096 kB\nMemAvailable: 1024 kB\n")
	writeFixture(t, root, "stat", "cpu  100 0 100 800 0 0 0 0 0 0\n")
	collector := NewCollector(root)

	first, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatalf("首次采集失败: %v", err)
	}
	if first.LoadOneMinute != 1.25 || first.MemoryTotalBytes != 4096*1024 {
		t.Fatalf("主机基础值错误: %+v", first)
	}

	// 第二次累计计数增加 100，其中非空闲增加 50，因此 CPU 应为 50%%。
	writeFixture(t, root, "stat", "cpu  125 0 125 850 0 0 0 0 0 0\n")
	second, err := collector.Collect(context.Background())
	if err != nil {
		t.Fatalf("第二次采集失败: %v", err)
	}
	if second.CPUPercent != 50 {
		t.Fatalf("CPU 差值计算应为 50，实际为 %.2f", second.CPUPercent)
	}
}

func writeFixture(t *testing.T, root string, name string, content string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(root, name), []byte(content), 0o600); err != nil {
		t.Fatalf("写入测试夹具 %s 失败: %v", name, err)
	}
}
