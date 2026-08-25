// Package httpserver 暴露 Agent 的本地健康、指标和动作接口。
package httpserver

import (
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/aiops-lab/aiops-agent/internal/application"
	"github.com/aiops-lab/aiops-agent/internal/domain"
	"github.com/aiops-lab/aiops-agent/internal/ports"
)

// Server 将 HTTP 数据转换为应用层实体，不包含 Docker 业务。
type Server struct {
	actions   *application.ActionService
	collector ports.SnapshotCollector
	logger    *slog.Logger
	mux       *http.ServeMux
}

// New 创建具有独立路由表的 Agent HTTP 传输层。
func New(actions *application.ActionService, collector ports.SnapshotCollector, logger *slog.Logger) *Server {
	server := &Server{actions: actions, collector: collector, logger: logger, mux: http.NewServeMux()}
	server.routes()
	return server
}

// Handler 返回只读路由处理器，便于 httptest 覆盖。
func (s *Server) Handler() http.Handler {
	return s.mux
}

func (s *Server) routes() {
	s.mux.HandleFunc("GET /healthz", s.health)
	s.mux.HandleFunc("GET /metrics", s.metrics)
	s.mux.HandleFunc("POST /v1/actions/execute", s.execute)
}

func (s *Server) health(writer http.ResponseWriter, _ *http.Request) {
	writeJSON(writer, http.StatusOK, map[string]string{"status": "ok", "service": "agent"})
}

func (s *Server) metrics(writer http.ResponseWriter, request *http.Request) {
	snapshot, err := s.collector.Collect(request.Context())
	if err != nil {
		writeJSON(writer, http.StatusServiceUnavailable, map[string]string{"error": err.Error()})
		return
	}
	writer.Header().Set("Content-Type", "text/plain; version=0.0.4")
	writer.WriteHeader(http.StatusOK)
	// Prometheus 文本格式保持指标名稳定，标签由后续资产注册流程补充。
	_, _ = fmt.Fprintf(writer, "aiops_host_load1 %f\n", snapshot.LoadOneMinute)
	_, _ = fmt.Fprintf(writer, "aiops_host_cpu_percent %f\n", snapshot.CPUPercent)
	_, _ = fmt.Fprintf(writer, "aiops_host_memory_total_bytes %d\n", snapshot.MemoryTotalBytes)
	_, _ = fmt.Fprintf(writer, "aiops_host_memory_available_bytes %d\n", snapshot.MemoryAvailableByte)
	_, _ = fmt.Fprintf(writer, "aiops_host_disk_total_bytes %d\n", snapshot.DiskTotalBytes)
	_, _ = fmt.Fprintf(writer, "aiops_host_disk_available_bytes %d\n", snapshot.DiskAvailableBytes)
}

func (s *Server) execute(writer http.ResponseWriter, request *http.Request) {
	var job domain.ActionJob
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 64*1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&job); err != nil {
		writeJSON(writer, http.StatusBadRequest, map[string]string{"error": "动作请求格式无效"})
		return
	}
	result, err := s.actions.Execute(request.Context(), job)
	if err != nil {
		s.logger.Warn("动作被安全策略拒绝", "job_id", job.ID, "error", err)
		if errors.Is(err, application.ErrTaskAuthentication) {
			// 认证失败不透露是 nonce、格式还是 HMAC 错误，降低外部探测价值。
			writeJSON(writer, http.StatusUnauthorized, map[string]string{"error": "动作任务认证失败"})
			return
		}
		writeJSON(writer, http.StatusConflict, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}
