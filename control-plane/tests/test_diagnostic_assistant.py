"""RAG 诊断与模型降级测试。"""

from aiops_control.adapters.hashing_embeddings import HashingEmbeddingProvider
from aiops_control.adapters.rule_based_diagnosis import RuleBasedDiagnosticModel
from aiops_control.application.diagnostic_assistant_service import DiagnosticAssistantService
from aiops_control.application.hybrid_retrieval_service import HybridRetrievalService
from aiops_control.domain.diagnostics import GeneratedDiagnosis
from aiops_control.domain.knowledge import KnowledgeDocument


class FailingModel:
    """模拟云模型超时的测试替身。"""

    def diagnose(self, question: str, trusted_context: str) -> GeneratedDiagnosis:
        raise TimeoutError(f"模拟超时: {question} {len(trusted_context)}")


def test_model_failure_uses_rule_fallback_and_keeps_citation() -> None:
    """云模型失败时仍应返回规则诊断和知识引用。"""

    documents = [
        KnowledgeDocument(
            "redis-runbook",
            "Redis 故障 Runbook",
            "Redis 连接失败时检查容器、端口和连接数。",
            "docs/runbooks/redis.md",
        )
    ]
    retrieval = HybridRetrievalService(documents, HashingEmbeddingProvider())
    service = DiagnosticAssistantService(retrieval, FailingModel(), RuleBasedDiagnosticModel())
    answer = service.diagnose("Redis 为什么连接失败？", ["lab-redis health=0"])
    assert answer.degraded is True
    assert answer.diagnosis.confidence == 0.55
    assert answer.citations == ("[Redis 故障 Runbook](docs/runbooks/redis.md)",)
