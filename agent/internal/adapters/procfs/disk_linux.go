//go:build linux

// Package procfs 提供 Linux 主机磁盘容量采集。
package procfs

import (
	"fmt"
	"syscall"
)

func readDiskUsage(path string) (uint64, uint64, error) {
	var statistics syscall.Statfs_t
	if err := syscall.Statfs(path, &statistics); err != nil {
		return 0, 0, fmt.Errorf("读取根文件系统容量失败: %w", err)
	}
	blockSize := uint64(statistics.Bsize)
	return statistics.Blocks * blockSize, statistics.Bavail * blockSize, nil
}
