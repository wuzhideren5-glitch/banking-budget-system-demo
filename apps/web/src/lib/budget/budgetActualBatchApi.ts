import { apiGet, apiPost } from "@/lib/shared/api";

export type BudgetActualBatchVersionOptionDto = {
  version_id: number;
  version_name: string;
  version_date_time: string | null;
  current_month: number;
};

export type BudgetActualBatchRequestDto = {
  product_code: string;
  version_id: number | null;
  budget_actuals: number[];
  run_formula: boolean;
  rebuild_summary: boolean;
  sync_compare: boolean;
  rebuild_aggregate: boolean;
};

export type MetricRollupAuditItemDto = {
  node_code: string;
  target_data_acct_code: string;
  target_metric_code?: string;
  scope_code: string;
  method: "SUM" | "FORMULA" | string;
  budget_actual: number;
  period_count: number;
  cell_count: number;
  source_count: number;
  source_codes: string[];
  source_metric_codes?: string[];
  formula: string | null;
};

export type BudgetActualBatchResponseDto = {
  mode: "preview" | "run";
  budget_year: number;
  version_id: number;
  product_code: string;
  product_count: number;
  data_account_count: number;
  metric_count?: number;
  formula_task_count: number;
  formula_cell_count: number;
  manual_override_cell_count: number;
  metric_rollup_task_count: number;
  metric_rollup_cell_count: number;
  metric_rollup_cells_written: number;
  metric_rollup_audit_items: MetricRollupAuditItemDto[];
  metric_rollup_audit_truncated: boolean;
  formula_rows_recalculated: number;
  summary_rows_rebuilt: number;
  budget_aggregate_rows_rebuilt: number;
  compare_rows_inserted: number;
  compare_aggregate_rows_rebuilt: number;
  selected_compare_versions: number;
  warnings: string[];
  message: string;
};

export type BudgetActualBatchHistoryItemDto = {
  log_id: number;
  create_time: string;
  user_id: string | null;
  version_id: number | null;
  budget_year: number | null;
  product_code: string;
  product_count: number;
  budget_actuals: number[];
  run_formula: boolean;
  rebuild_summary: boolean;
  sync_compare: boolean;
  rebuild_aggregate: boolean;
  data_account_count: number;
  metric_count?: number;
  formula_task_count: number;
  formula_cell_count: number;
  manual_override_cell_count: number;
  metric_rollup_task_count: number;
  metric_rollup_cell_count: number;
  metric_rollup_cells_written: number;
  formula_rows_recalculated: number;
  summary_rows_rebuilt: number;
  budget_aggregate_rows_rebuilt: number;
  compare_rows_inserted: number;
  compare_aggregate_rows_rebuilt: number;
  selected_compare_versions: number;
  affected_rows: number;
};

export async function fetchBudgetActualBatchVersions(): Promise<BudgetActualBatchVersionOptionDto[]> {
  return apiGet<BudgetActualBatchVersionOptionDto[]>("/api/budget-actual-batch/versions");
}

export async function fetchBudgetActualBatchHistory(limit = 30): Promise<BudgetActualBatchHistoryItemDto[]> {
  return apiGet<BudgetActualBatchHistoryItemDto[]>(`/api/budget-actual-batch/history?limit=${limit}`);
}

export async function previewBudgetActualBatch(
  payload: BudgetActualBatchRequestDto,
): Promise<BudgetActualBatchResponseDto> {
  return apiPost<BudgetActualBatchResponseDto>("/api/budget-actual-batch/preview", payload);
}

export async function runBudgetActualBatch(payload: BudgetActualBatchRequestDto): Promise<BudgetActualBatchResponseDto> {
  return apiPost<BudgetActualBatchResponseDto>("/api/budget-actual-batch/run", payload);
}
