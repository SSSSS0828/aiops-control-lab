"""内置 Runbook 知识目录。

阶段二先以少量经过审查的只读文档验证 RAG 数据流。文档来源使用仓库内稳定路径，
模型回答只能引用这些内容；未来替换 PostgreSQL 或向量库时不影响诊断应用服务。
"""

from aiops_control.domain.knowledge import KnowledgeDocument


def build_builtin_documents() -> list[KnowledgeDocument]:
    """返回适用于五类实验故障的最小可信知识集。"""

    return [
        KnowledgeDocument(
            id="runbook-container-cpu",
            title="容器 CPU 突增处置",
            body=(
                "先确认 CPU 异常持续时间与目标容器，再检查进程和限额。"
                "实验环境可以重启 lab-api，执行后必须验证网关健康检查；失败时停止自动操作。"
            ),
            source="docs/runbooks/container-cpu.md",
            tags=("cpu", "container", "lab-api"),
        ),
        KnowledgeDocument(
            id="runbook-redis-unavailable",
            title="Redis 依赖不可用处置",
            body=(
                "确认 lab-redis 容器状态、连接错误和依赖拓扑。"
                "恢复 Redis 后验证 API 与网关；不得通过删除数据目录处理连接故障。"
            ),
            source="docs/runbooks/redis-unavailable.md",
            tags=("redis", "dependency", "connection"),
        ),
        KnowledgeDocument(
            id="runbook-http-errors",
            title="HTTP 延迟与 5xx 排查",
            body=(
                "对比网关状态码、请求延迟和最近变更，先恢复实验故障开关。"
                "如果健康检查仍失败，再检查 API 容器和 Redis 依赖，不直接执行任意 Shell。"
            ),
            source="docs/runbooks/http-errors.md",
            tags=("http", "latency", "5xx", "nginx"),
        ),
    ]
