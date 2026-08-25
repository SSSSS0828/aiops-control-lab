// 故障实验室类型直接对应控制面公开的真值目录。
export interface FaultScenario {
  id: string;
  title: string;
  asset_id: string;
  metric_name: string;
  current_value: number;
  baseline: number[];
  root_cause_asset: string;
  root_cause: string;
  injection_kind: "container_stop" | "application_control" | string;
  expected_remediation: string;
}
