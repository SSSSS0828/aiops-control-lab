// Package domain 定义 Agent 侧不依赖传输和 Docker SDK 的核心实体。
package domain

import "time"

// ActionJob 是控制面批准后下发给 Agent 的不可变任务。
type ActionJob struct {
	ID             string            `json:"id"`
	IdempotencyKey string            `json:"idempotency_key"`
	ApprovedHash   string            `json:"approved_hash"`
	ActionType     string            `json:"action_type"`
	Target         string            `json:"target"`
	Arguments      map[string]string `json:"arguments"`
	ExpiresAt      time.Time         `json:"expires_at"`
	// Nonce 由控制面为每次下发生成，用于识别跨幂等键重放。
	Nonce string `json:"nonce"`
	// Signature 覆盖任务全部安全字段，Agent 在执行前使用共享密钥验证。
	Signature string `json:"signature"`
}

// ActionResult 记录一次动作的最终结果，供控制面审计和验证。
type ActionResult struct {
	JobID      string    `json:"job_id"`
	Succeeded  bool      `json:"succeeded"`
	Message    string    `json:"message"`
	FinishedAt time.Time `json:"finished_at"`
}

// HostSnapshot 是 Agent 当前采集到的轻量主机指标。
type HostSnapshot struct {
	LoadOneMinute       float64   `json:"load_one_minute"`
	CPUPercent          float64   `json:"cpu_percent"`
	MemoryTotalBytes    uint64    `json:"memory_total_bytes"`
	MemoryAvailableByte uint64    `json:"memory_available_bytes"`
	DiskTotalBytes      uint64    `json:"disk_total_bytes"`
	DiskAvailableBytes  uint64    `json:"disk_available_bytes"`
	CollectedAt         time.Time `json:"collected_at"`
}
