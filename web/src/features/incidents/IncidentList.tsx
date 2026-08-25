// IncidentList 只负责事件选择和摘要展示，不发起网络请求。
import type { Incident } from "./types";

interface IncidentListProps {
  incidents: Incident[];
  selectedId?: string;
  onSelect: (incident: Incident) => void;
}

const statusLabel: Record<string, string> = {
  waiting_approval: "等待审批",
  remediating: "修复中",
  resolved: "已恢复",
  failed: "修复失败",
};

export function IncidentList({ incidents, selectedId, onSelect }: IncidentListProps) {
  if (incidents.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-icon">◇</span>
        <strong>当前没有活跃事件</strong>
        <p>从右侧故障实验室注入一个场景，观察完整 AIOps 数据流。</p>
      </div>
    );
  }

  return (
    <div className="incident-list">
      {incidents.map((incident) => (
        <button
          className={`incident-row ${selectedId === incident.id ? "selected" : ""}`}
          key={incident.id}
          onClick={() => onSelect(incident)}
          type="button"
        >
          <span className={`severity-dot ${incident.severity}`} aria-hidden="true" />
          <span className="incident-copy">
            <strong>{incident.title}</strong>
            <small>
              {incident.asset_id} · {new Date(incident.created_at).toLocaleTimeString()}
            </small>
          </span>
          <span className={`status-pill ${incident.status}`}>
            {statusLabel[incident.status] ?? incident.status}
          </span>
        </button>
      ))}
    </div>
  );
}
