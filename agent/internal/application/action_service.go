// Package application 编排 Agent 领域对象和外部执行端口。
package application

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"regexp"
	"sync"
	"time"

	"github.com/aiops-lab/aiops-agent/internal/domain"
	"github.com/aiops-lab/aiops-agent/internal/ports"
)

var sha256Pattern = regexp.MustCompile(`^[a-f0-9]{64}$`)

// ActionService 在进入 Docker 或 systemd 适配器前执行统一安全校验。
type ActionService struct {
	executor        ports.ActionExecutor
	auth            *TaskAuthenticator
	realActionsMode string
	now             func() time.Time
	mu              sync.Mutex
	records         map[string]*executionRecord
	nonces          map[string]nonceRecord
}

// executionRecord 让同一幂等键的并发请求等待首个任务完成。
type executionRecord struct {
	done        chan struct{}
	result      domain.ActionResult
	fingerprint string
	completedAt time.Time
}

// nonceRecord 把一次性随机数绑定到原始幂等键；相同请求可安全重试，改投其他任务会被拒绝。
type nonceRecord struct {
	idempotencyKey string
	expiresAt      time.Time
}

// NewActionService 创建一个无全局可变状态的动作服务。
func NewActionService(executor ports.ActionExecutor, authenticator *TaskAuthenticator) *ActionService {
	return NewActionServiceWithMode(executor, authenticator, "observe_only")
}

// NewActionServiceWithMode 显式设置真实资产门禁；未知模式按观察模式处理。
func NewActionServiceWithMode(executor ports.ActionExecutor, authenticator *TaskAuthenticator, mode string) *ActionService {
	return &ActionService{
		executor:        executor,
		auth:            authenticator,
		realActionsMode: mode,
		now:             time.Now,
		records:         make(map[string]*executionRecord),
		nonces:          make(map[string]nonceRecord),
	}
}

// Execute 验证审批、范围、时效和幂等性后执行任务。
func (s *ActionService) Execute(ctx context.Context, job domain.ActionJob) (domain.ActionResult, error) {
	// Agent 必须先证明任务来自受信控制面，随后才解析审批和目标等业务字段。
	if s.auth == nil || s.auth.Verify(job) != nil {
		return domain.ActionResult{}, ErrTaskAuthentication
	}
	// 审批哈希必须是完整的小写 SHA-256，空值或截断值一律拒绝。
	if !sha256Pattern.MatchString(job.ApprovedHash) {
		return domain.ActionResult{}, errors.New("批准内容哈希格式无效")
	}
	// 以 Agent 本机时间判断任务时效，避免执行控制面队列中滞留的旧命令。
	if !job.ExpiresAt.After(s.now()) {
		return domain.ActionResult{}, errors.New("动作任务已经过期")
	}
	// 实验资产始终使用 lab-* 命名空间；真实资产必须再通过模式和只读动作双重门禁。
	if !isLabTarget(job.Target) && !s.realReadOnlyActionAllowed(job) {
		return domain.ActionResult{}, fmt.Errorf("目标 %q 或动作 %q 不在当前允许范围内", job.Target, job.ActionType)
	}

	// 锁同时保护查询和创建记录，防止两个并发请求都进入真实执行器。
	s.mu.Lock()
	// 先清理已经过期的 nonce，避免常驻 Agent 因历史任务无限增长内存。
	s.pruneExpiredNoncesLocked(s.now())
	if used, exists := s.nonces[job.Nonce]; exists && used.idempotencyKey != job.IdempotencyKey {
		s.mu.Unlock()
		return domain.ActionResult{}, ErrTaskAuthentication
	}
	s.nonces[job.Nonce] = nonceRecord{job.IdempotencyKey, job.ExpiresAt}
	fingerprint := taskFingerprint(job)
	record, exists := s.records[job.IdempotencyKey]
	if exists {
		// 幂等键只能代表一个不可变任务，禁止用相同键替换动作、目标或参数。
		if record.fingerprint != fingerprint {
			s.mu.Unlock()
			return domain.ActionResult{}, errors.New("幂等键已绑定到不同动作任务")
		}
		s.mu.Unlock()
		// 重复请求必须等待首个任务完成，不能读取尚未完成的半成品结果。
		select {
		case <-record.done:
			return record.result, nil
		case <-ctx.Done():
			return domain.ActionResult{}, ctx.Err()
		}
	}
	// 无缓冲完成信号会在最终结果写入后关闭，唤醒所有等待的重复请求。
	record = &executionRecord{done: make(chan struct{}), fingerprint: fingerprint}
	s.records[job.IdempotencyKey] = record
	s.mu.Unlock()

	// 系统调用在锁外执行，避免一个耗时重启阻塞所有其他幂等键查询。
	result, err := s.executor.Execute(ctx, job)
	if err != nil {
		result = domain.ActionResult{
			JobID:      job.ID,
			Succeeded:  false,
			Message:    err.Error(),
			FinishedAt: s.now().UTC(),
		}
	}

	// 先写最终结果再关闭信号，Go 的 happens-before 保证等待方看到完整结果。
	s.mu.Lock()
	record.result = result
	record.completedAt = s.now()
	close(record.done)
	s.mu.Unlock()
	return result, nil
}

func isLabTarget(target string) bool {
	return len(target) >= 4 && target[:4] == "lab-"
}

func (s *ActionService) realReadOnlyActionAllowed(job domain.ActionJob) bool {
	if s.realActionsMode != "approval_only" {
		return false
	}
	if len(job.Target) < len("docker/devops-lab/") || job.Target[:len("docker/devops-lab/")] != "docker/devops-lab/" {
		return false
	}
	return job.ActionType == "health_check" || job.ActionType == "inspect_container" || job.ActionType == "collect_logs"
}

// pruneExpiredNoncesLocked 只能在持有 s.mu 时调用。
func (s *ActionService) pruneExpiredNoncesLocked(now time.Time) {
	for nonce, record := range s.nonces {
		if !record.expiresAt.After(now) {
			delete(s.nonces, nonce)
		}
	}
}

// taskFingerprint 检测同一幂等键下的内容替换；签名本身不参与，允许重新签发安全重试。
func taskFingerprint(job domain.ActionJob) string {
	// 重新签发同一语义任务时 job ID、截止时间和 nonce 会变化，不能把它们算入幂等语义。
	semanticJob := job
	semanticJob.ID = job.IdempotencyKey
	semanticJob.ExpiresAt = time.Date(2000, 1, 1, 0, 0, 0, 0, time.UTC)
	semanticJob.Nonce = "00000000000000000000000000000000"
	message, err := canonicalTaskMessage(semanticJob)
	if err != nil {
		return ""
	}
	digest := sha256.Sum256(message)
	return fmt.Sprintf("%x", digest)
}
