// Package docker 通过 Docker Engine Unix Socket 执行类型化容器动作。
package docker

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/aiops-lab/aiops-agent/internal/domain"
)

// Executor 只实现允许列表中的 Docker 动作，不接受任意 Shell 字符串。
type Executor struct {
	client *http.Client
}

// NewExecutor 创建连接指定 Docker Unix Socket 的执行器。
func NewExecutor(socketPath string) *Executor {
	transport := &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", socketPath)
		},
	}
	return &Executor{client: &http.Client{Transport: transport, Timeout: 30 * time.Second}}
}

// Execute 将类型化动作映射为固定 Docker Engine API 调用。
func (e *Executor) Execute(ctx context.Context, job domain.ActionJob) (domain.ActionResult, error) {
	// 稳定资产 ID 只能映射到固定 devops-lab 容器名，不能被用作任意 Docker API 路径。
	resolvedTarget, err := resolveContainerTarget(job.Target)
	if err != nil {
		return domain.ActionResult{}, err
	}
	target := url.PathEscape(resolvedTarget)
	var method string
	var endpoint string

	switch job.ActionType {
	case "restart_container":
		// 宽限时间来自结构化参数，解析失败时使用安全默认值。
		graceSeconds := 10
		if raw, exists := job.Arguments["grace_seconds"]; exists {
			parsed, err := strconv.Atoi(raw)
			if err != nil || parsed < 0 || parsed > 60 {
				return domain.ActionResult{}, fmt.Errorf("grace_seconds 必须在 0 到 60 之间")
			}
			graceSeconds = parsed
		}
		method = http.MethodPost
		endpoint = fmt.Sprintf("http://docker/containers/%s/restart?t=%d", target, graceSeconds)
	case "stop_container":
		// 故障注入只停止已经通过 lab-* 目标白名单的实验容器。
		method = http.MethodPost
		endpoint = fmt.Sprintf("http://docker/containers/%s/stop?t=2", target)
	case "health_check", "inspect_container":
		method = http.MethodGet
		endpoint = fmt.Sprintf("http://docker/containers/%s/json", target)
	case "collect_logs":
		// 只请求最近 200 行且不跟随流，避免只读动作无限占用连接和内存。
		method = http.MethodGet
		endpoint = fmt.Sprintf("http://docker/containers/%s/logs?stdout=1&stderr=1&tail=200", target)
	default:
		return domain.ActionResult{}, fmt.Errorf("动作 %q 未由 Docker 执行器注册", job.ActionType)
	}

	request, err := http.NewRequestWithContext(ctx, method, endpoint, nil)
	if err != nil {
		return domain.ActionResult{}, fmt.Errorf("创建 Docker 请求失败: %w", err)
	}
	response, err := e.client.Do(request)
	if err != nil {
		return domain.ActionResult{}, fmt.Errorf("调用 Docker Engine 失败: %w", err)
	}
	defer response.Body.Close()

	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return domain.ActionResult{}, fmt.Errorf("Docker Engine 返回状态 %d", response.StatusCode)
	}

	message := fmt.Sprintf("容器 %s 已完成 %s", job.Target, job.ActionType)
	if job.ActionType == "health_check" || job.ActionType == "inspect_container" {
		var inspect struct {
			State struct {
				Status string `json:"Status"`
			} `json:"State"`
		}
		if err := json.NewDecoder(response.Body).Decode(&inspect); err != nil {
			return domain.ActionResult{}, fmt.Errorf("解析容器状态失败: %w", err)
		}
		if !strings.EqualFold(inspect.State.Status, "running") {
			return domain.ActionResult{}, fmt.Errorf("容器状态为 %s", inspect.State.Status)
		}
		message = fmt.Sprintf("容器 %s 状态检查通过", job.Target)
	} else if job.ActionType == "collect_logs" {
		// 日志正文不进入动作消息；后续由专用脱敏遥测通道返回证据引用。
		message = fmt.Sprintf("容器 %s 最近日志已完成受控读取", job.Target)
	}

	return domain.ActionResult{
		JobID:      job.ID,
		Succeeded:  true,
		Message:    message,
		FinishedAt: time.Now().UTC(),
	}, nil
}

func resolveContainerTarget(target string) (string, error) {
	if strings.HasPrefix(target, "lab-") {
		return target, nil
	}
	realTargets := map[string]string{
		"docker/devops-lab/nginx":        "devops-nginx",
		"docker/devops-lab/api":          "devops-api",
		"docker/devops-lab/prometheus":   "devops-prometheus",
		"docker/devops-lab/grafana":      "devops-grafana",
		"docker/devops-lab/alertmanager": "devops-alertmanager",
	}
	resolved, exists := realTargets[target]
	if !exists {
		return "", fmt.Errorf("容器目标 %q 未在稳定资产映射中注册", target)
	}
	return resolved, nil
}
