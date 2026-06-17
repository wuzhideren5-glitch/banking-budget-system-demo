import { apiDelete, apiGet, apiPatch, apiPost, apiPostForm, downloadFile } from "@/lib/shared/api";

export type BudgetOutputVersionDto = {
  key: string;
  label: string;
  source: "editable" | "show" | "budget" | "forecast";
  show_level: number | null;
  year: number;
  version_id: number;
  version_name: string;
  current_month: number;
  selected_by_default: boolean;
};

export type BudgetOutputProductNodeDto = {
  product_code: string;
  product_name: string;
  parent_code: string | null;
  level: number;
  children: BudgetOutputProductNodeDto[];
};

export type BudgetOutputReportNodeDto = {
  row_key: string;
  display_name: string;
  parent_row_key: string | null;
  level: number;
  is_summary: boolean;
  is_minus: boolean;
  children: BudgetOutputReportNodeDto[];
};

export type BudgetOutputVersionMetricDto = {
  annual_value: number;
  budget_value: number;
  variance_to_budget: number;
  monthly_values: number[];
  monthly_budget_values: number[];
  monthly_actual_values: number[];
};

export type BudgetOutputReportRowDto = {
  row_key: string;
  display_name: string;
  data_acct_code?: string | null;
  data_acct_name?: string | null;
  org_product_ref?: string | null;
  org_product_entity_code?: string | null;
  org_product_table_name?: string | null;
  org_product_metric_code?: string | null;
  org_product_metric_name?: string | null;
  metric_code?: string | null;
  metric_name?: string | null;
  metric_node_code?: string | null;
  metric_node_name?: string | null;
  source_scope_type?: string | null;
  source_scope_code?: string | null;
  source_scope_name?: string | null;
  budget_formula?: string | null;
  actual_formula?: string | null;
  formula_calc_mode?: number;
  allow_manual_entry?: number;
  value_type: string | null;
  row_type: string;
  level: number;
  parent_row_key: string | null;
  is_summary: boolean;
  is_minus: boolean;
  values_by_version: Record<string, BudgetOutputVersionMetricDto>;
};

export type BudgetOutputProductBlockDto = {
  product_code: string;
  product_name: string;
  descendant_product_codes: string[];
  rows: BudgetOutputReportRowDto[];
};

export type BudgetOutputDisplayReportResponseDto = {
  title: string;
  unit_label: string;
  available_years: number[];
  selected_year: number;
  budget_version_id: number | null;
  forecast_version_ids: number[];
  versions: BudgetOutputVersionDto[];
  selected_show_levels: number[];
  product_tree: BudgetOutputProductNodeDto[];
  report_tree: BudgetOutputReportNodeDto[];
  product_overview_tree: BudgetOutputReportNodeDto[];
  product_detail_tree: BudgetOutputReportNodeDto[];
  selected_products: BudgetOutputProductNodeDto[];
  total_rows: BudgetOutputReportRowDto[];
  product_blocks: BudgetOutputProductBlockDto[];
  product_overview_blocks: BudgetOutputProductBlockDto[];
  product_detail_blocks: BudgetOutputProductBlockDto[];
  note: string;
};

export type BudgetOutputDisplayCandidateDto = {
  candidate_key?: string | null;
  data_acct_code: string;
  data_acct_name: string;
  metric_node_code: string;
  metric_node_name: string;
  scope_type: string;
  scope_code: string;
  scope_name: string | null;
  value_type: string;
  source_type?: string;
  source_label?: string;
  source_ref?: string | null;
  org_product_ref?: string | null;
  org_product_entity_code?: string | null;
  org_product_table_name?: string | null;
  org_product_metric_code?: string | null;
  org_product_metric_name?: string | null;
  metric_code?: string | null;
  metric_name?: string | null;
  selected: boolean;
};

export type BudgetOutputDisplayConfigItemDto = {
  row_key: string;
  display_view: string;
  parent_row_key: string | null;
  data_acct_code: string | null;
  data_acct_name: string | null;
  org_product_ref?: string | null;
  org_product_entity_code?: string | null;
  org_product_table_name?: string | null;
  org_product_metric_code?: string | null;
  org_product_metric_name?: string | null;
  metric_code?: string | null;
  metric_name?: string | null;
  row_type: string;
  display_name: string;
  metric_node_code: string | null;
  metric_node_name: string | null;
  source_scope_type: string | null;
  source_scope_code: string | null;
  scope_name: string | null;
  value_type: string | null;
  level: number;
  sort_order: number;
  is_active: number;
};

export type BudgetOutputDisplayConfigResponseDto = {
  items: BudgetOutputDisplayConfigItemDto[];
  candidates: BudgetOutputDisplayCandidateDto[];
};

export type BudgetOutputDisplayReportParams = {
  year?: number | null;
  budgetVersionId?: number | null;
  forecastVersionIds?: number[] | null;
  productCodes?: string[] | null;
};

export type BudgetOutputDisplayConfigCreateDto = {
  data_acct_code: string;
  display_name: string;
  parent_row_key?: string | null;
  insert_after_row_key?: string | null;
  org_product_ref?: string | null;
  org_product_entity_code?: string | null;
  org_product_table_name?: string | null;
  org_product_metric_code?: string | null;
  org_product_metric_name?: string | null;
};

export type BudgetOutputDisplayConfigUpdateDto = Partial<
  Pick<BudgetOutputDisplayConfigItemDto, "display_name" | "sort_order" | "is_active">
>;

export type BudgetOutputDisplayConfigImportResponseDto = {
  saved_rows: number;
  metric_rows: number;
  group_rows: number;
};

function displayReportQuery(params: BudgetOutputDisplayReportParams): URLSearchParams {
  const query = new URLSearchParams();
  if (params.year != null) query.set("year", String(params.year));
  if (params.budgetVersionId != null) query.set("budget_version_id", String(params.budgetVersionId));
  params.forecastVersionIds?.forEach((versionId) => query.append("forecast_version_ids", String(versionId)));
  params.productCodes?.forEach((code) => query.append("product_codes", code));
  return query;
}

export async function fetchBudgetOutputDisplayReport(
  params: BudgetOutputDisplayReportParams,
): Promise<BudgetOutputDisplayReportResponseDto> {
  const query = displayReportQuery(params);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<BudgetOutputDisplayReportResponseDto>(`/api/budget-output/display-report${suffix}`);
}

export async function fetchBudgetOutputDisplayConfig(): Promise<BudgetOutputDisplayConfigResponseDto> {
  return apiGet<BudgetOutputDisplayConfigResponseDto>("/api/budget-output/display-config");
}

export async function createBudgetOutputDisplayConfigItem(
  payload: BudgetOutputDisplayConfigCreateDto,
): Promise<BudgetOutputDisplayConfigItemDto> {
  return apiPost<BudgetOutputDisplayConfigItemDto>("/api/budget-output/display-config/items", payload);
}

export async function updateBudgetOutputDisplayConfigItem(
  rowKey: string,
  payload: BudgetOutputDisplayConfigUpdateDto,
): Promise<BudgetOutputDisplayConfigItemDto> {
  return apiPatch<BudgetOutputDisplayConfigItemDto>(
    `/api/budget-output/display-config/items/${encodeURIComponent(rowKey)}`,
    payload,
  );
}

export async function deleteBudgetOutputDisplayConfigItem(rowKey: string): Promise<void> {
  return apiDelete(`/api/budget-output/display-config/items/${encodeURIComponent(rowKey)}`);
}

export async function exportBudgetOutputDisplayReport(params: BudgetOutputDisplayReportParams): Promise<void> {
  const query = displayReportQuery(params);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return downloadFile(`/api/budget-output/display-report/export-full${suffix}`, "预算展示全套报表.xlsx");
}

export async function exportBudgetOutputDisplayConfig(): Promise<void> {
  return downloadFile("/api/budget-output/display-config/export", "预算展示配置导入模板.xlsx");
}

export async function importBudgetOutputDisplayConfig(file: File): Promise<BudgetOutputDisplayConfigImportResponseDto> {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", "replace");
  return apiPostForm<BudgetOutputDisplayConfigImportResponseDto>("/api/budget-output/display-config/import", form);
}
