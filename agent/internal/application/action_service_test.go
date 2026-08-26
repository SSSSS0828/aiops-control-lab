// Package application_test 从公开接口验证审批和幂等边界。
package application_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/aiops-lab/aiops-agent/internal/application"
	"github.com/aiops-lab/aiops-agent/internal/domain"
)

type countingExecutor struct {
	calls int
}

const testSharedSecret = "0123456789abcdef0123456789abcdef"

// newTestService 创建与生产环境同样启用签名验证的动作服务。
func newTestService(t *testing.T, executor *countingExecutor) (*application.ActionService, *application.TaskAuthenticator) {
	t.Helper()
	authenticator, err := application.NewTaskAuthenticator(testSharedSecret)
	if err != nil {
		t.Fatalf("创建测试认证器失败: %v", err)
	}
	return application.NewActionService(executor, authenticator), authenticator
}

// signJob 为测试任务补齐固定格式 nonce 和真实 HMAC，避免绕过生产认证边界。
func signJob(t *testing.T, authenticator *application.TaskAuthenticator, job domain.ActionJob) domain.ActionJob {
	t.Helper()
	job.Nonce = "00112233445566778899aabbccddeeff"
	if err := authenticator.Sign(&job); err != nil {
		t.Fatalf("签名测试任务失败: %v", err)
	}
	return job
}

func (e *countingExecutor) Execute(_ context.Context, job domain.ActionJob) (domain.ActionResult, error) {
	e.calls++
	return domain.ActionResult{JobID: job.ID, Succeeded: true, FinishedAt: time.Now()}, nil
}

func TestExecuteIsIdempotent(t *testing.T) {
	executor := &countingExecutor{}
	service, authenticator := newTestService(t, executor)
	job := signJob(t, authenticator, domain.ActionJob{
		ID:             "job-1",
		IdempotencyKey: "request-1",
		ApprovedHash:   "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ActionType:     "restart_container",
		Target:         "lab-api",
		ExpiresAt:      time.Now().Add(time.Minute),
	})
	first, firstErr := service.Execute(context.Background(), job)
	second, secondErr := service.Execute(context.Background(), job)
	if firstErr != nil || secondErr != nil {
		t.Fatalf("执行不应失败: first=%v second=%v", firstErr, secondErr)
	}
	if first != second {
		t.Fatalf("幂等重试应返回相同结果: first=%+v second=%+v", first, second)
	}
	if executor.calls != 1 {
		t.Fatalf("执行器应只调用一次，实际调用 %d 次", executor.calls)
	}
}

func TestExecuteRejectsHostTarget(t *testing.T) {
	executor := &countingExecutor{}
	service, authenticator := newTestService(t, executor)
	job := signJob(t, authenticator, domain.ActionJob{
		ID:             "job-2",
		IdempotencyKey: "request-2",
		ApprovedHash:   "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		ActionType:     "restart_container",
		Target:         "production-api",
		ExpiresAt:      time.Now().Add(time.Minute),
	})
	_, err := service.Execute(context.Background(), job)
	if err == nil {
		t.Fatal("非实验室目标必须被拒绝")
	}
}

func TestObserveOnlyRejectsRealReadAction(t *testing.T) {
	executor := &countingExecutor{}
	service, authenticator := newTestService(t, executor)
	job := signJob(t, authenticator, domain.ActionJob{
		ID: "job-real-observe", IdempotencyKey: "request-real-observe",
		ApprovedHash: "abababababababababababababababababababababababababababababababab",
		ActionType:   "health_check", Target: "docker/devops-lab/api",
		ExpiresAt: time.Now().Add(time.Minute),
	})
	if _, err := service.Execute(context.Background(), job); err == nil {
		t.Fatal("观察模式必须拒绝真实资产只读动作")
	}
}

func TestApprovalOnlyAllowsReadButRejectsRealRestart(t *testing.T) {
	executor := &countingExecutor{}
	authenticator, err := application.NewTaskAuthenticator(testSharedSecret)
	if err != nil {
		t.Fatalf("创建测试认证器失败: %v", err)
	}
	service := application.NewActionServiceWithMode(executor, authenticator, "approval_only")
	readJob := signJob(t, authenticator, domain.ActionJob{
		ID: "job-real-read", IdempotencyKey: "request-real-read",
		ApprovedHash: "cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
		ActionType:   "health_check", Target: "docker/devops-lab/api",
		ExpiresAt: time.Now().Add(time.Minute),
	})
	if _, err := service.Execute(context.Background(), readJob); err != nil {
		t.Fatalf("人工审批模式应允许真实只读动作: %v", err)
	}
	restartJob := readJob
	restartJob.ID = "job-real-restart"
	restartJob.IdempotencyKey = "request-real-restart"
	restartJob.Nonce = "ffeeddccbbaa99887766554433221100"
	restartJob.ActionType = "restart_container"
	if err := authenticator.Sign(&restartJob); err != nil {
		t.Fatalf("签名真实重启任务失败: %v", err)
	}
	if _, err := service.Execute(context.Background(), restartJob); err == nil {
		t.Fatal("首道门禁不能允许真实容器重启")
	}
}

func TestConcurrentDuplicateWaitsForFirstResult(t *testing.T) {
	executor := &countingExecutor{}
	service, authenticator := newTestService(t, executor)
	job := signJob(t, authenticator, domain.ActionJob{
		ID:             "job-concurrent",
		IdempotencyKey: "request-concurrent",
		ApprovedHash:   "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
		ActionType:     "restart_container",
		Target:         "lab-api",
		ExpiresAt:      time.Now().Add(time.Minute),
	})

	var waitGroup sync.WaitGroup
	results := make(chan domain.ActionResult, 2)
	for range 2 {
		waitGroup.Add(1)
		go func() {
			defer waitGroup.Done()
			result, err := service.Execute(context.Background(), job)
			if err != nil {
				t.Errorf("并发幂等请求不应失败: %v", err)
				return
			}
			results <- result
		}()
	}
	waitGroup.Wait()
	close(results)
	for result := range results {
		if !result.Succeeded {
			t.Fatalf("重复请求必须得到最终成功结果: %+v", result)
		}
	}
	if executor.calls != 1 {
		t.Fatalf("并发重复任务应只调用一次执行器，实际调用 %d 次", executor.calls)
	}
}

func TestExecuteRejectsModifiedSignedTask(t *testing.T) {
	// 先签名再篡改目标，用于证明签名覆盖了会影响系统状态的字段。
	executor := &countingExecutor{}
	service, authenticator := newTestService(t, executor)
	job := signJob(t, authenticator, domain.ActionJob{
		ID:             "job-signed",
		IdempotencyKey: "request-signed",
		ApprovedHash:   "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
		ActionType:     "restart_container",
		Target:         "lab-api",
		Arguments:      map[string]string{"grace_seconds": "10"},
		ExpiresAt:      time.Now().UTC().Truncate(time.Second).Add(time.Minute),
	})
	job.Target = "lab-redis"
	_, err := service.Execute(context.Background(), job)
	if !errors.Is(err, application.ErrTaskAuthentication) {
		t.Fatalf("篡改后的任务必须认证失败，实际错误: %v", err)
	}
	if executor.calls != 0 {
		t.Fatal("认证失败的任务不得进入执行器")
	}
}

func TestNonceCannotMoveToAnotherIdempotencyKey(t *testing.T) {
	// 即使攻击者持有合法签名环境，同一 nonce 也不能被绑定到另一项业务请求。
	executor := &countingExecutor{}
	service, authenticator := newTestService(t, executor)
	first := signJob(t, authenticator, domain.ActionJob{
		ID:             "job-first",
		IdempotencyKey: "request-first",
		ApprovedHash:   "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
		ActionType:     "health_check",
		Target:         "lab-api",
		Arguments:      map[string]string{},
		ExpiresAt:      time.Now().UTC().Truncate(time.Second).Add(time.Minute),
	})
	if _, err := service.Execute(context.Background(), first); err != nil {
		t.Fatalf("首个任务不应失败: %v", err)
	}
	second := first
	second.ID = "job-second"
	second.IdempotencyKey = "request-second"
	if err := authenticator.Sign(&second); err != nil {
		t.Fatalf("重签第二个任务失败: %v", err)
	}
	_, err := service.Execute(context.Background(), second)
	if !errors.Is(err, application.ErrTaskAuthentication) {
		t.Fatalf("跨幂等键重放 nonce 必须被拒绝，实际错误: %v", err)
	}
}

func TestAuthenticatorMatchesPythonVector(t *testing.T) {
	// 该固定向量与 control-plane/tests/test_task_signing.py 完全相同。
	authenticator, err := application.NewTaskAuthenticator(testSharedSecret)
	if err != nil {
		t.Fatalf("创建认证器失败: %v", err)
	}
	job := domain.ActionJob{
		ID:             "job-vector",
		IdempotencyKey: "request-vector",
		ApprovedHash:   "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		ActionType:     "restart_container",
		Target:         "lab-api",
		Arguments:      map[string]string{"grace_seconds": "10", "说明": "安全重启"},
		ExpiresAt:      time.Date(2030, 1, 2, 3, 4, 5, 0, time.UTC),
		Nonce:          "00112233445566778899aabbccddeeff",
	}
	if err := authenticator.Sign(&job); err != nil {
		t.Fatalf("签名固定向量失败: %v", err)
	}
	const expected = "f1a8dddd27efa5d933a227e0e24f560282517b843b0cfb118ab51eeb999b3009"
	if job.Signature != expected {
		t.Fatalf("Go/Python 签名契约不一致: got=%s want=%s", job.Signature, expected)
	}
}
