// Package application 中的本文件负责验证控制面签发的动作任务。
//
// 输入：反序列化后的 ActionJob 和仅由部署环境注入的共享密钥。
// 处理：按跨语言规范计算 HMAC-SHA256，并使用常量时间比较验证签名。
// 输出：验证成功返回 nil，失败统一返回 ErrTaskAuthentication。
// 副作用：无；nonce 的状态化防重放由 ActionService 在锁内完成。
package application

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"

	"github.com/aiops-lab/aiops-agent/internal/domain"
)

const signatureVersion = "aiops-action-v1"

var (
	// ErrTaskAuthentication 对外隐藏具体失败字段，避免给攻击者提供签名探针。
	ErrTaskAuthentication = errors.New("动作任务认证失败")
	noncePattern          = regexp.MustCompile(`^[a-f0-9]{32}$`)
	signaturePattern      = regexp.MustCompile(`^[a-f0-9]{64}$`)
)

// TaskAuthenticator 使用部署时共享密钥验证任务来源和内容完整性。
type TaskAuthenticator struct {
	secret []byte
}

// NewTaskAuthenticator 创建认证器；空密钥会让 Agent 启动失败，而不是降级为匿名执行。
func NewTaskAuthenticator(sharedSecret string) (*TaskAuthenticator, error) {
	if len(sharedSecret) < 32 {
		return nil, errors.New("Agent 共享密钥至少需要 32 个字符")
	}
	return &TaskAuthenticator{secret: []byte(sharedSecret)}, nil
}

// Verify 验证 nonce、签名格式及 HMAC，任何失败都返回统一认证错误。
func (a *TaskAuthenticator) Verify(job domain.ActionJob) error {
	if !noncePattern.MatchString(job.Nonce) || !signaturePattern.MatchString(job.Signature) {
		return ErrTaskAuthentication
	}
	message, err := canonicalTaskMessage(job)
	if err != nil {
		return ErrTaskAuthentication
	}
	provided, err := hex.DecodeString(job.Signature)
	if err != nil {
		return ErrTaskAuthentication
	}

	// HMAC 必须使用常量时间比较，普通字符串比较会泄露前缀匹配耗时。
	mac := hmac.New(sha256.New, a.secret)
	_, _ = mac.Write(message)
	if !hmac.Equal(provided, mac.Sum(nil)) {
		return ErrTaskAuthentication
	}
	return nil
}

// Sign 为 SDK、契约测试和受信控制面生成签名；Agent 运行路径只调用 Verify。
func (a *TaskAuthenticator) Sign(job *domain.ActionJob) error {
	if !noncePattern.MatchString(job.Nonce) {
		return errors.New("任务 nonce 必须是 32 位小写十六进制字符串")
	}
	message, err := canonicalTaskMessage(*job)
	if err != nil {
		return err
	}
	mac := hmac.New(sha256.New, a.secret)
	_, _ = mac.Write(message)
	job.Signature = hex.EncodeToString(mac.Sum(nil))
	return nil
}

// canonicalTaskMessage 与 Python 控制面的 task_signing.py 保持逐字段一致。
func canonicalTaskMessage(job domain.ActionJob) ([]byte, error) {
	if job.ID == "" || job.IdempotencyKey == "" || job.ApprovedHash == "" ||
		job.ActionType == "" || job.Target == "" || job.ExpiresAt.IsZero() || job.Nonce == "" {
		return nil, errors.New("任务签名字段不完整")
	}
	argumentsJSON, err := encodeCanonicalArguments(job.Arguments)
	if err != nil {
		return nil, err
	}
	fields := []string{
		job.ID,
		job.IdempotencyKey,
		job.ApprovedHash,
		job.ActionType,
		job.Target,
		job.ExpiresAt.UTC().Format("2006-01-02T15:04:05Z"),
		job.Nonce,
		string(argumentsJSON),
	}
	digests := make([]string, 0, len(fields))
	for _, field := range fields {
		digest := sha256.Sum256([]byte(field))
		digests = append(digests, hex.EncodeToString(digest[:]))
	}
	return []byte(signatureVersion + "\n" + strings.Join(digests, "\n")), nil
}

// encodeCanonicalArguments 禁用 HTML 转义，并移除 Encoder 自动追加的换行符。
func encodeCanonicalArguments(arguments map[string]string) ([]byte, error) {
	if arguments == nil {
		arguments = map[string]string{}
	}
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(arguments); err != nil {
		return nil, fmt.Errorf("规范化动作参数失败: %w", err)
	}
	return bytes.TrimSuffix(buffer.Bytes(), []byte("\n")), nil
}
