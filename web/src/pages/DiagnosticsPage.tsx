// AI 诊断页明确区分模型建议和可执行动作，回答不会直接发送给 Agent。
import { FormEvent, useCallback, useState } from "react";

import { askDiagnostic, getDiagnosticStatus } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";
import type { DiagnosticAnswer } from "../shared/types/console";

export function DiagnosticsPage() {
  const loader = useCallback(() => getDiagnosticStatus(), []);
  const { data: status, error, loading } = useApiResource(loader);
  const [question, setQuestion] = useState("lab-api CPU 异常时应该如何排查？");
  const [evidence, setEvidence] = useState("container_cpu_percent 高于历史基线");
  const [answer, setAnswer] = useState<DiagnosticAnswer>();
  const [asking, setAsking] = useState(false);
  if (loading && !status) return <LoadingState />;
  if (error && !status) return <ErrorState message={error} />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setAsking(true);
    try {
      setAnswer(await askDiagnostic(question, evidence.split("\n").filter(Boolean)));
    } finally {
      setAsking(false);
    }
  }

  return (
    <>
      <PageHeader
        description="先检索受信 Runbook，再生成结构化诊断；模型输出只能成为计划输入，不能绕过策略和审批。"
        eyebrow="RAG DIAGNOSTIC ASSISTANT"
        title="AI 诊断助手"
      />
      <div className="model-status-bar">
        <span className={`state-badge ${status!.degraded ? "degraded" : "online"}`}>
          {status!.degraded ? "规则降级" : "模型在线"}
        </span>
        <strong>{status!.model}</strong>
        <small>{status!.rag}</small>
      </div>
      <section className="diagnostic-grid">
        <form className="console-card diagnostic-form" onSubmit={(event) => void submit(event)}>
          <label>
            诊断问题
            <textarea onChange={(event) => setQuestion(event.target.value)} value={question} />
          </label>
          <label>
            可信证据摘要
            <textarea onChange={(event) => setEvidence(event.target.value)} value={evidence} />
          </label>
          <button disabled={asking} type="submit">
            {asking ? "正在检索与分析…" : "生成只读诊断"}
          </button>
        </form>
        <article className="console-card diagnostic-answer">
          {!answer && (
            <p className="inline-empty">提交问题后，这里会展示根因、建议、置信度和引用。</p>
          )}
          {answer && (
            <>
              <span className="eyebrow">STRUCTURED ANSWER</span>
              <h2>{answer.diagnosis.summary}</h2>
              <dl>
                <div>
                  <dt>根因判断</dt>
                  <dd>{answer.diagnosis.root_cause}</dd>
                </div>
                <div>
                  <dt>建议动作</dt>
                  <dd>{answer.diagnosis.recommended_action}</dd>
                </div>
                <div>
                  <dt>置信度</dt>
                  <dd>{Math.round(answer.diagnosis.confidence * 100)}%</dd>
                </div>
              </dl>
              <h3>证据引用</h3>
              {answer.citations.map((citation) => (
                <code key={citation}>{citation}</code>
              ))}
              <p className="safety-note">该回答不会直接执行，必须转成类型化计划并经过人工审批。</p>
            </>
          )}
        </article>
      </section>
    </>
  );
}
