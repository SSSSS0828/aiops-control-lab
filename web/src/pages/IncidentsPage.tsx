// Incident 工作台按上下文接口加载事件、最新计划和执行结果。
import { useCallback, useMemo, useState } from "react";

import { approvePlan } from "../features/incidents/api";
import { IncidentDetail } from "../features/incidents/IncidentDetail";
import { IncidentList } from "../features/incidents/IncidentList";
import type { ActionRun } from "../features/incidents/types";
import { listIncidentContexts } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function IncidentsPage() {
  const loader = useCallback(() => listIncidentContexts(), []);
  const { data = [], error, loading, refresh } = useApiResource(loader);
  const [selectedId, setSelectedId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [actionRun, setActionRun] = useState<ActionRun>();
  const selected = useMemo(
    () => data.find((item) => item.incident.id === selectedId) ?? data[0],
    [data, selectedId],
  );
  if (loading && !data.length) return <LoadingState />;
  if (error && !data.length) return <ErrorState message={error} />;

  async function handleApprove() {
    if (!selected?.plan) return;
    setBusy(true);
    try {
      setActionRun(await approvePlan(selected.plan));
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        actions={<button onClick={() => void refresh()}>刷新事件</button>}
        description="在一个上下文中检查检测证据、根因候选、修复步骤、回滚定义和最终执行结果。"
        eyebrow="INCIDENT WORKBENCH"
        title="Incident 工作台"
      />
      <section className="incident-workbench">
        <article className="console-card incident-list-card">
          <IncidentList
            incidents={data.map((item) => item.incident)}
            onSelect={(incident) => setSelectedId(incident.id)}
            selectedId={selected?.incident.id}
          />
        </article>
        <article className="console-card incident-detail-card">
          <IncidentDetail
            actionRun={actionRun ?? selected?.executions[0]}
            approving={busy}
            incident={selected?.incident}
            onApprove={() => void handleApprove()}
            plan={selected?.plan ?? undefined}
          />
        </article>
      </section>
    </>
  );
}
