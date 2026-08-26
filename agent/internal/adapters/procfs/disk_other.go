//go:build !linux

// Package procfs 为非 Linux 开发机提供可编译的磁盘采集替身。
package procfs

// readDiskUsage 在非 Linux 单元测试环境返回零值；生产 Agent 只支持 Linux。
func readDiskUsage(_ string) (uint64, uint64, error) {
	return 0, 0, nil
}
