import { apiPost, apiPostBlob, downloadBlob } from "@/lib/shared/api";

export type BudgetSummaryRowDto = {
  metric_level1: string | null;
  metric_level2: string | null;
  metric_level3: string | null;
  metric_level4: string | null;
  metric_level5: string | null;
  dept_level1: string | null;
  dept_level2: string | null;
  dept_level3: string | null;
  data_code_name: string;
  product_code_name: string | null;
  year: string;
  month: string;
  quarter: string;
  budget_actual: number;
  version_id: number;
  version_name: string | null;
  current_month: number;
  rule_message: string | null;
  value: number;
  value_type: string;
  value_source: string | null;
  update_time: string | null;
};

export type CompareSummarySyncResultDto = {
  inserted_rows: number;
  selected_versions: number;
  trigger_source: string;
  message: string;
  rule_message: string;
  level_rules: string[];
};

export type CompareSummaryRowDto = {
  show_level: number;
  data_file_id: number;
  source_year: number;
  source_version_id: number;
  source_version_name: string | null;
  metric_level1: string | null;
  metric_level2: string | null;
  metric_level3: string | null;
  metric_level4: string | null;
  metric_level5: string | null;
  dept_level1: string | null;
  dept_level2: string | null;
  dept_level3: string | null;
  data_code_name: string;
  product_code_name: string | null;
  year: string;
  month: string;
  quarter: string;
  budget_actual: number;
  value: number;
  value_type: string;
  value_source: string | null;
  sync_time: string;
};

export type PivotSummaryDataSource = "budget" | "compare";

export type PivotSummaryAggregateRequestDto = {
  row_field_ids: string[];
  column_field_ids: string[];
  page_field_ids: string[];
  page_selections: Record<string, string>;
  pivot_search_text: string;
};

export type PivotSummaryExportRequestDto = PivotSummaryAggregateRequestDto & {
  show_row_total: boolean;
  show_column_total: boolean;
};

export function fetchBudgetSummaryAggregate(
  payload: PivotSummaryAggregateRequestDto,
): Promise<BudgetSummaryRowDto[]> {
  return apiPost<BudgetSummaryRowDto[]>("/api/budget-summary/aggregate", payload);
}

export function fetchCompareSummaryAggregate(
  payload: PivotSummaryAggregateRequestDto,
): Promise<CompareSummaryRowDto[]> {
  return apiPost<CompareSummaryRowDto[]>("/api/compare-summary/aggregate", payload);
}

export async function downloadPivotSummaryExport(
  dataSource: PivotSummaryDataSource,
  payload: PivotSummaryExportRequestDto,
): Promise<void> {
  const endpoint =
    dataSource === "budget" ? "/api/budget-summary/export-aggregate-pivot" : "/api/compare-summary/export-aggregate-pivot";
  const fallbackName =
    dataSource === "budget" ? "budget_pivot_aggregate_export.xlsx" : "compare_pivot_aggregate_export.xlsx";
  const { blob, filename } = await apiPostBlob(endpoint, payload);
  downloadBlob(blob, filename || fallbackName);
}
