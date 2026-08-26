"""RAG 检索、大模型诊断和规则回退的应用编排。"""

from dataclasses import dataclass

from aiops_control.application.hybrid_retrieval_service import HybridRetrievalService
from aiops_control.domain.diagnostics import GeneratedDiagnosis
from aiops_control.domain.knowledge import RetrievalHit
from aiops_control.ports.language_model import DiagnosticLanguageModel


@dataclass(frozen=True, slots=True)
class DiagnosticAnswer:
    """返回给 API 的诊断、引用和模型降级状态。"""

    diagnosis: GeneratedDiagnosis
    citations: tuple[str, ...]
    degraded: bool


class DiagnosticAssistantService:
    """先检索可信知识，再调用模型；失败时自动使用规则引擎。"""

    def __init__(
        self,
        retrieval: HybridRetrievalService,
        primary_model: DiagnosticLanguageModel,
        fallback_model: DiagnosticLanguageModel,
        primary_enabled: bool = True,
    ) -> None:
        self._retrieval = retrieval
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._primary_enabled = primary_enabled

    def diagnose(self, question: str, evidence: list[str]) -> DiagnosticAnswer:
        """构造有引用上下文，并保证模型故障不会阻断诊断。"""

        hits = self._retrieval.search(question, limit=4)
        context = self._build_context(evidence, hits)
        # 没有配置云模型时直接进入规则诊断，并准确标记 degraded。
        # 规则只读取问题和运行证据，不能让检索到的其他 Runbook 关键词污染根因判断。
        if not self._primary_enabled:
            diagnosis = self._fallback_model.diagnose(question, "\n".join(evidence))
            return DiagnosticAnswer(
                diagnosis=diagnosis,
                citations=tuple(hit.citation for hit in hits),
                degraded=True,
            )
        try:
            diagnosis = self._primary_model.diagnose(question, context)
            degraded = False
        except Exception:  # noqa: BLE001 - 模型供应商异常必须统一降级
            # 云模型失败后的确定性规则同样只读取运行证据，避免知识文档互相污染。
            diagnosis = self._fallback_model.diagnose(question, "\n".join(evidence))
            degraded = True
        return DiagnosticAnswer(
            diagnosis=diagnosis,
            citations=tuple(hit.citation for hit in hits),
            degraded=degraded,
        )

    @staticmethod
    def _build_context(evidence: list[str], hits: list[RetrievalHit]) -> str:
        """将运行证据与检索文档分区，降低来源混淆风险。"""

        evidence_section = "\n".join(f"- {item}" for item in evidence[:20])
        knowledge_section = "\n\n".join(
            f"来源：{hit.citation}\n{hit.document.body[:2_000]}" for hit in hits
        )
        return f"【运行证据】\n{evidence_section}\n\n【知识库】\n{knowledge_section}"
