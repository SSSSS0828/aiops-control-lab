// SRE 页通过现有领域服务计算 SLO 和变更风险，表单输入不会直接触发生产变更。
import { useState, type FormEvent } from "react";

import { assessChange, evaluateSlo, forecastCapacity } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";

export function SrePage() {
  const [slo, setSlo] = useState<Record<string, number | string>>();
  const [risk, setRisk] = useState<{ score: number; level: string; reasons: string[] }>();
  const [capacity, setCapacity] = useState<{
    slope_per_hour: number;
    r_squared: number;
    threshold: number;
    estimated_exhaustion_at: string | null;
    state: string;
  }>();

  async function submitSlo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setSlo(
      await evaluateSlo({
        name: values.get("name"),
        objective: Number(values.get("objective")),
        window_days: 30,
        good_events: Number(values.get("good")),
        total_events: Number(values.get("total")),
      }),
    );
  }

  async function submitRisk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setRisk(
      await assessChange({
        blast_radius: Number(values.get("blast")),
        recent_incident_rate: Number(values.get("rate")),
        changed_components: Number(values.get("components")),
        rollback_ready: values.get("rollback") === "on",
      }),
    );
  }

  async function submitCapacity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const samples = String(values.get("samples")).split(",").map(Number);
    const now = Date.now();
    const points = samples.map((value, index) => ({
      occurred_at: new Date(now - (samples.length - index - 1) * 3_600_000).toISOString(),
      value,
    }));
    setCapacity(await forecastCapacity({ points, threshold: Number(values.get("threshold")) }));
  }

  return (
    <>
      <PageHeader
        description="使用可解释公式计算错误预算、燃烧速率和发布风险；容量预测接口保留给真实时序接入。"
        eyebrow="SRE ENGINEERING"
        title="SLO、错误预算与变更风险"
      />
      <section className="two-column-grid form-grid">
        <form className="console-card" onSubmit={(event) => void submitSlo(event)}>
          <span className="eyebrow">ERROR BUDGET</span>
          <h2>SLO 评估</h2>
          <label>
            目标名称
            <input defaultValue="API 可用性" name="name" />
          </label>
          <label>
            目标比例
            <input
              defaultValue="0.999"
              max="0.99999"
              min="0.01"
              name="objective"
              step="0.0001"
              type="number"
            />
          </label>
          <label>
            好事件数
            <input defaultValue="9985" min="0" name="good" type="number" />
          </label>
          <label>
            总事件数
            <input defaultValue="10000" min="1" name="total" type="number" />
          </label>
          <button type="submit">计算错误预算</button>
          {slo && <pre>{JSON.stringify(slo, null, 2)}</pre>}
        </form>
        <form className="console-card" onSubmit={(event) => void submitRisk(event)}>
          <span className="eyebrow">CHANGE RISK</span>
          <h2>变更风险评估</h2>
          <label>
            影响半径 0..1
            <input defaultValue="0.4" max="1" min="0" name="blast" step="0.1" type="number" />
          </label>
          <label>
            近期事件率 0..1
            <input defaultValue="0.2" max="1" min="0" name="rate" step="0.1" type="number" />
          </label>
          <label>
            变更组件数
            <input defaultValue="2" min="1" name="components" type="number" />
          </label>
          <label className="checkbox-label">
            <input defaultChecked name="rollback" type="checkbox" /> 已准备回滚
          </label>
          <button type="submit">评估发布风险</button>
          {risk && (
            <div className="risk-result">
              <strong>
                {risk.level} · {Math.round(risk.score * 100)}%
              </strong>
              {risk.reasons.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          )}
        </form>
        <form
          className="console-card capacity-form"
          onSubmit={(event) => void submitCapacity(event)}
        >
          <span className="eyebrow">CAPACITY FORECAST</span>
          <h2>容量趋势预测</h2>
          <label>
            最近每小时利用率（逗号分隔）
            <input defaultValue="62,65,68,72" name="samples" />
          </label>
          <label>
            容量阈值
            <input defaultValue="85" name="threshold" type="number" />
          </label>
          <button type="submit">预测阈值时间</button>
          {capacity && <pre>{JSON.stringify(capacity, null, 2)}</pre>}
        </form>
      </section>
    </>
  );
}
