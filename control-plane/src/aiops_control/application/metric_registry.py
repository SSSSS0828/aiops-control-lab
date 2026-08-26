"""真实监测指标注册表。

所有展示、规则和 Prometheus 暴露都只能引用这里的固定名称。该注册表阻止浏览器或
LLM 注入任意 PromQL，同时让单位、中文名称和默认图表保持一致。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """一个允许进入在线监测链路的指标定义。"""

    name: str
    display_name: str
    unit: str
    description: str


METRIC_DEFINITIONS = (
    MetricDefinition("aiops_host_load1", "主机一分钟负载", "load", "Linux 一分钟平均负载"),
    MetricDefinition("aiops_host_cpu_percent", "主机 CPU", "percent", "相邻采集周期 CPU 使用率"),
    MetricDefinition("aiops_host_memory_total_bytes", "主机总内存", "bytes", "Linux 可见总内存"),
    MetricDefinition(
        "aiops_host_memory_available_bytes", "主机可用内存", "bytes", "Linux MemAvailable"
    ),
    MetricDefinition(
        "aiops_host_memory_available_percent", "主机可用内存比例", "percent", "可用内存占总内存比例"
    ),
    MetricDefinition("aiops_host_disk_total_bytes", "根盘总容量", "bytes", "根文件系统总容量"),
    MetricDefinition(
        "aiops_host_disk_available_bytes", "根盘可用容量", "bytes", "非特权用户可用容量"
    ),
    MetricDefinition(
        "aiops_host_disk_used_percent", "根盘使用率", "percent", "根文件系统已用容量比例"
    ),
    MetricDefinition("aiops_container_up", "容器运行状态", "boolean", "运行中为 1，否则为 0"),
    MetricDefinition(
        "aiops_container_cpu_percent", "容器 CPU", "percent", "Docker 非流式 stats CPU"
    ),
    MetricDefinition(
        "aiops_container_memory_usage_bytes", "容器内存", "bytes", "Docker 当前内存使用"
    ),
    MetricDefinition(
        "aiops_container_memory_limit_bytes", "容器内存上限", "bytes", "Docker 内存限制"
    ),
    MetricDefinition(
        "aiops_container_restart_count", "容器重启次数", "count", "Docker 累计重启次数"
    ),
)

REGISTERED_METRICS = {item.name: item for item in METRIC_DEFINITIONS}
