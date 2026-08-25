"""关键词与向量混合检索测试。"""

from aiops_control.adapters.hashing_embeddings import HashingEmbeddingProvider
from aiops_control.application.hybrid_retrieval_service import HybridRetrievalService
from aiops_control.domain.knowledge import KnowledgeDocument


def test_redis_runbook_is_retrieved_with_citation() -> None:
    """Redis 连接故障查询应优先返回对应 Runbook 并携带引用。"""

    documents = [
        KnowledgeDocument(
            "runbook-redis",
            "Redis 连接失败处理",
            "检查容器状态、连接超时和最大连接数，恢复后执行健康检查。",
            "docs/runbooks/redis.md",
            ("redis", "dependency"),
        ),
        KnowledgeDocument(
            "runbook-cpu",
            "CPU 使用率过高",
            "检查进程 CPU、负载和限额，确认是否存在忙循环。",
            "docs/runbooks/cpu.md",
            ("cpu", "linux"),
        ),
    ]
    service = HybridRetrievalService(documents, HashingEmbeddingProvider())
    hits = service.search("Redis 容器连接失败", limit=2)
    assert hits[0].document.id == "runbook-redis"
    assert hits[0].citation == "[Redis 连接失败处理](docs/runbooks/redis.md)"
