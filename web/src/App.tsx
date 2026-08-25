// App 只解析当前页面并交给共享壳层，不在根组件中维护业务状态。
import { AppShell } from "./app/AppShell";
import { resolvePageId } from "./app/navigation";
import { useHashRoute } from "./app/useHashRoute";
import { AlgorithmsPage } from "./pages/AlgorithmsPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AssetsPage } from "./pages/AssetsPage";
import { AuditPage } from "./pages/AuditPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";
import { DemoPage } from "./pages/DemoPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { LabPage } from "./pages/LabPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PluginsPage } from "./pages/PluginsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SrePage } from "./pages/SrePage";
import { TelemetryPage } from "./pages/TelemetryPage";
import { TopologyPage } from "./pages/TopologyPage";

const pages = {
  demo: <DemoPage />,
  overview: <OverviewPage />,
  assets: <AssetsPage />,
  topology: <TopologyPage />,
  telemetry: <TelemetryPage />,
  incidents: <IncidentsPage />,
  diagnostics: <DiagnosticsPage />,
  approvals: <ApprovalsPage />,
  audit: <AuditPage />,
  plugins: <PluginsPage />,
  sre: <SrePage />,
  lab: <LabPage />,
  algorithms: <AlgorithmsPage />,
  settings: <SettingsPage />,
};

export function App() {
  const path = useHashRoute();
  return <AppShell path={path}>{pages[resolvePageId(path)]}</AppShell>;
}
