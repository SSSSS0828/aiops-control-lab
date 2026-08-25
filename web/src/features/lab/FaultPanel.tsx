// FaultPanel 展示服务端真值目录，并将用户选择上抛给页面编排层。
import type { FaultScenario } from "./types";

interface FaultPanelProps {
  injecting: boolean;
  onInject: (scenario: string) => void;
  scenarios: FaultScenario[];
}

export function FaultPanel({ injecting, onInject, scenarios }: FaultPanelProps) {
  return (
    <aside className="fault-panel">
      <span className="eyebrow">FAULT LAB / 安全沙箱</span>
      <h2>注入可解释故障</h2>
      <p>每个场景都携带真值，便于验证检测、根因和修复结果。</p>
      <div className="scenario-list">
        {scenarios.map((scenario) => (
          <button
            disabled={injecting}
            key={scenario.id}
            onClick={() => onInject(scenario.id)}
            type="button"
          >
            <span className="scenario-mark">+</span>
            <span>
              <strong>{scenario.title}</strong>
              <small>
                根因：{scenario.root_cause}；修复：{scenario.expected_remediation}
              </small>
            </span>
          </button>
        ))}
      </div>
      <div className="safety-note">
        <strong>安全边界</strong>
        <span>当前所有动作只能指向 lab-* 实验资源。</span>
      </div>
    </aside>
  );
}
