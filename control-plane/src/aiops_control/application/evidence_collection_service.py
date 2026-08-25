"""从真实遥测源收集并附加 Incident 证据。

输入：Incident ID、受边界约束的 PromQL/LogQL 和时间窗口。
数据流：应用校验 -> 查询端口 -> 内存摘要 -> EvidenceRef -> Incident 仓储。
输出：不可变证据引用；原始样本和日志在方法返回前释放，不写入 PostgreSQL。
副作用：成功查询后更新 Incident；外部源失败时不产生半成品证据。
"""

from datetime import datetime, timedelta

from aiops_control.domain.errors import EntityNotFoundError, ExternalSourceError
from aiops_control.domain.models import EvidenceRef, Incident, new_id
from aiops_control.ports.repositories import IncidentRepository
from aiops_control.ports.telemetry import LogQueryPort, MetricQueryPort

MAX_WINDOW = timedelta(hours=6)
MAX_QUERY_LENGTH = 1_024


class EvidenceCollectionService:
    """编排遥测查询、摘要和 Incident 更新。"""

    def __init__(
        self,
        incident_repository: IncidentRepository,
        metric_query: MetricQueryPort | None,
        log_query: LogQueryPort | None,
    ) -> None:
        self._incidents = incident_repository
        self._metrics = metric_query
        self._logs = log_query

    def attach_metric_evidence(
        self,
        incident_id: str,
        query: str,
        started_at: datetime,
        ended_at: datetime,
        step_seconds: int,
    ) -> EvidenceRef:
        """查询 Prometheus、生成统计摘要并附加证据引用。"""

        self._validate_query(query, started_at, ended_at)
        if self._metrics is None:
            raise ExternalSourceError("当前环境没有配置 Prometheus 查询源")
        incident = self._get_incident(incident_id)
        # 查询发生在修改聚合之前；超时或解析失败不会留下无效 EvidenceRef。
        samples = self._metrics.query_range(query, started_at, ended_at, step_seconds)
        if samples:
            values = [sample.value for sample in samples]
            summary = (
                f"Prometheus 返回 {len(values)} 个样本；"
                f"最小值 {min(values):.4g}，最大值 {max(values):.4g}，"
                f"最新值 {values[-1]:.4g}"
            )
        else:
            summary = "Prometheus 在指定窗口没有返回样本"
        evidence = EvidenceRef(
            id=new_id("evi"),
            source="prometheus",
            query=query,
            started_at=started_at,
            ended_at=ended_at,
            summary=summary,
        )
        incident.evidence.append(evidence)
        self._incidents.save_incident(incident)
        return evidence

    def attach_log_evidence(
        self,
        incident_id: str,
        query: str,
        started_at: datetime,
        ended_at: datetime,
        limit: int,
    ) -> EvidenceRef:
        """查询 Loki 并只持久化数量和标签范围摘要。"""

        self._validate_query(query, started_at, ended_at)
        if self._logs is None:
            raise ExternalSourceError("当前环境没有配置 Loki 查询源")
        incident = self._get_incident(incident_id)
        records = self._logs.query_range(query, started_at, ended_at, limit)
        # 摘要只记录标签键，不保存消息正文，降低秘密和个人信息进入审计库的风险。
        label_keys = sorted({key for record in records for key in record.labels})
        labels_summary = ", ".join(label_keys[:10]) if label_keys else "无标签"
        summary = f"Loki 返回 {len(records)} 条日志；标签字段：{labels_summary}"
        evidence = EvidenceRef(
            id=new_id("evi"),
            source="loki",
            query=query,
            started_at=started_at,
            ended_at=ended_at,
            summary=summary,
        )
        incident.evidence.append(evidence)
        self._incidents.save_incident(incident)
        return evidence

    def _get_incident(self, incident_id: str) -> Incident:
        """读取 Incident，并将不存在转换为稳定领域错误。"""

        incident = self._incidents.get_incident(incident_id)
        if incident is None:
            raise EntityNotFoundError(f"Incident {incident_id} 不存在")
        return incident

    def _validate_query(
        self,
        query: str,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        """统一限制查询文本和窗口，避免公网或模型产生无边界扫描。"""

        if not query.strip() or len(query) > MAX_QUERY_LENGTH:
            raise ExternalSourceError("遥测查询不能为空且不能超过 1024 个字符")
        if started_at.tzinfo is None or ended_at.tzinfo is None:
            raise ExternalSourceError("遥测时间必须包含时区")
        if started_at >= ended_at:
            raise ExternalSourceError("遥测窗口开始时间必须早于结束时间")
        if ended_at - started_at > MAX_WINDOW:
            raise ExternalSourceError("单次遥测查询窗口不能超过 6 小时")
