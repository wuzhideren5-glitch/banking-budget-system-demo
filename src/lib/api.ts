/** 默认空字符串：开发态走 Vite proxy（`/api` →8003）；生产若前后端不同源请设 `VITE_API_BASE` */
const base = import.meta.env.VITE_API_BASE?.replace(/\/$/, "") ?? "";

export function buildApiUrl(path: string): string {
  return `${base}${path}`;
}

async function readErrorMessage(r: Response): Promise<string> {
  const fallback = r.statusText || `HTTP ${r.status}`;
  const text = await r.text();
  if (!text) return fallback;
  try {
    const json = JSON.parse(text) as { detail?: unknown };
    if (typeof json.detail === "string") return json.detail;
    if (json.detail !== undefined) return JSON.stringify(json.detail);
  } catch {
    // non-JSON error payload, keep raw text
  }
  return text;
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(buildApiUrl(path), { credentials: "include" });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiPostBlob(path: string, body: unknown): Promise<{ blob: Blob; filename: string | null }> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  const disposition = r.headers.get("Content-Disposition") || "";
  const match = /filename=\"?([^\";]+)\"?/i.exec(disposition);
  return { blob: await r.blob(), filename: match?.[1] ?? null };
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  return r.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const r = await fetch(buildApiUrl(path), { method: "DELETE", credentials: "include" });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
}

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const r = await fetch(buildApiUrl(path), { credentials: "include" });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  const disposition = r.headers.get("Content-Disposition") || "";
  const encodedMatch = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  const quotedMatch = /filename=\"?([^\";]+)\"?/i.exec(disposition);
  const filename = encodedMatch?.[1]
    ? decodeURIComponent(encodedMatch[1])
    : quotedMatch?.[1] ?? fallbackName;
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export type SessionInfo = {
  user_id: number;
  software_version: string;
  budget_year: number;
  version_id: number;
  version_name: string;
  version_date_time: string;
  user_display_name: string;
  user_role: string;
  permission_type: number;
  first_login_required: boolean;
  db_connected: boolean;
  last_global_calc_refresh_time: string | null;
};

export type GlobalRefreshAnnualStatusDto = {
  data_file_name: string;
  year: number;
  refresh_time_a: string | null;
};

export type GlobalRefreshStatusDto = {
  annual_items: GlobalRefreshAnnualStatusDto[];
  compare_refresh_time_b: string | null;
  next_planned_refresh_time_c: string | null;
};

export type VersionSnapshotItemDto = {
  label: string;
  budget_year: number;
  version_id: number;
  version_name: string;
  /** 该版本在库中的 current_month（1–13），与编辑/展示配置中的版本对应 */
  current_month?: number;
};

export type VersionSnapshotResponseDto = {
  items: VersionSnapshotItemDto[];
};

export type ChartReportTreeNodeDto = {
  report_acct_code: string;
  report_acct_name: string;
  is_summary: boolean;
  children: ChartReportTreeNodeDto[];
};

export type ChartVersionItemDto = {
  data_file_id: number;
  data_file_name: string;
  year: number;
  version_id: number;
  version_name: string;
  current_month: number;
};

export type ChartVersionOptionsResponseDto = {
  options: ChartVersionItemDto[];
};

export type ChartVersionSelectionDto = {
  data_file_id: number;
  version_id: number;
};

export type ChartStackedRequestDto = {
  report_acct_code: string;
  use_all_versions: boolean;
  selected_versions: ChartVersionSelectionDto[];
  single_version_granularity: "month" | "quarter";
  stack_mode: "absolute" | "percent";
};

export type ChartBarRequestDto = {
  report_acct_code: string;
  bar_compare_scope: "self" | "children";
  use_all_versions: boolean;
  selected_versions: ChartVersionSelectionDto[];
  single_version_granularity: "month" | "quarter";
};

export type ChartStackedSeriesDto = {
  key: string;
  label: string;
  values: number[];
  value_type?: string | null;
};

export type ChartStackedMatrixRowDto = {
  row_label: string;
  values: number[];
  value_type?: string | null;
};

export type ChartStackedResolvedVersionDto = {
  data_file_id: number;
  year: number;
  version_id: number;
  version_name: string;
};

export type ChartStackedResponseDto = {
  categories: string[];
  series: ChartStackedSeriesDto[];
  matrix_headers: string[];
  matrix_rows: ChartStackedMatrixRowDto[];
  resolved_versions: ChartStackedResolvedVersionDto[];
  note: string | null;
};

export type ChartPptSeriesDto = {
  name: string;
  values: number[];
};

export type ChartPptMatrixRowDto = {
  label: string;
  values: string[];
};

export type ChartPptExportRequestDto = {
  chart_type: "bar" | "stacked" | "line" | "pie" | "doughnut";
  title: string;
  subtitle?: string | null;
  categories: string[];
  series: ChartPptSeriesDto[];
  matrix_headers?: string[];
  matrix_rows?: ChartPptMatrixRowDto[];
};

export type LoginRequestDto = {
  user_name: string;
  password: string;
};

export type LoginResponseDto = {
  ok: boolean;
  need_change_password: boolean;
  user_name: string;
  permission_type: number;
};

export type AssumptionParameterDto = {
  parameter_code: string;
  parameter_name: string;
  category: string;
  value_type: string;
  scope_type: string;
  time_granularity: string;
  apply_products?: string | null;
  input_mode: string;
  value_formula?: string | null;
  source_data_code?: string | null;
  default_unit?: string | null;
  is_enabled: boolean;
  remark?: string | null;
  create_time: string;
  update_time: string;
};

export type AssumptionValueDto = {
  parameter_code: string;
  budget_year: number;
  version_id: number;
  scenario_code: string;
  product_scope_key: string;
  product_code?: string | null;
  month_index: number;
  value: number;
  update_time: string;
};

export type AssumptionValueUpsertItemDto = {
  parameter_code: string;
  month_index: number;
  value: number;
  product_scope_key?: string;
  product_code?: string | null;
  scenario_code?: string;
};

export type AssumptionRuleTemplateDto = {
  rule_code: string;
  rule_name: string;
  rule_type: string;
  config_json: string;
  is_enabled: boolean;
  remark?: string | null;
  create_time: string;
  update_time: string;
};

export type AssumptionImpactItemDto = {
  rule_code?: string | null;
  rule_name?: string | null;
  data_acct_code?: string | null;
  data_acct_name?: string | null;
  match_source: string;
};

export type AssumptionImpactResponseDto = {
  parameter_code: string;
  parameter_name?: string | null;
  items: AssumptionImpactItemDto[];
};

export type ForecastWorkbenchSummaryDto = {
  layout_count: number;
  binding_count: number;
  bound_line_count: number;
  unbound_line_count: number;
  data_account_count: number;
  parameter_count: number;
  template_count: number;
};

export type ForecastWorkbenchBindingRowDto = {
  id: number;
  line_code: string;
  binding_type: string;
  binding_code: string;
  binding_name?: string | null;
  binding_role: string;
  sort_order: number;
  remark?: string | null;
};

export type ForecastWorkbenchLineRowDto = {
  line_code: string;
  line_name: string;
  line_group: string;
  line_category: string;
  display_mode: string;
  sort_order: number;
  is_enabled: boolean;
  binding_hint?: string | null;
  remark?: string | null;
  binding_count: number;
  bindings: ForecastWorkbenchBindingRowDto[];
};

export type ForecastWorkbenchOverviewDto = {
  budget_year: number;
  version_id: number;
  version_name: string;
  current_month: number;
  summary: ForecastWorkbenchSummaryDto;
  lines: ForecastWorkbenchLineRowDto[];
};

export type SmartReportVariableTypeDto = "metric" | "formula" | "calc" | "parameter" | "text" | "table" | "chart" | "analysis";

export type SmartReportTemplateDto = {
  template_id: number;
  template_code: string;
  template_name: string;
  template_type: string;
  status: string;
  version_no: number;
  remark?: string | null;
  created_at: string;
  updated_at: string;
  variable_count: number;
};

export type SmartReportTemplateCreateResponseDto = {
  template: SmartReportTemplateDto;
  placeholders: string[];
};

export type SmartReportTextTemplateCreateDto = {
  template_code: string;
  template_name: string;
  content: string;
  template_type?: string;
  remark?: string | null;
};

export type SmartReportCalcMetricComponentDto = {
  alias: string;
  data_acct_code: string;
  data_acct_name?: string | null;
};

export type SmartReportCalcMetricDto = {
  metric_code: string;
  metric_name: string;
  expression: string;
  components: SmartReportCalcMetricComponentDto[];
  value_type: string;
  format_type: string;
  remark?: string | null;
  created_at: string;
  updated_at: string;
};

export type SmartReportCalcMetricUpsertDto = {
  metric_code: string;
  metric_name: string;
  expression: string;
  components: SmartReportCalcMetricComponentDto[];
  value_type?: string;
  format_type?: string;
  remark?: string | null;
};

export type SmartReportTemplateVariableDto = {
  variable_id: number;
  template_id: number;
  variable_key: string;
  variable_name: string;
  variable_type: SmartReportVariableTypeDto;
  binding_config: Record<string, unknown>;
  display_order: number;
  created_at: string;
  updated_at: string;
};

export type SmartReportTemplateVariableUpsertDto = {
  variable_key: string;
  variable_name?: string | null;
  variable_type?: SmartReportVariableTypeDto | null;
  binding_config?: Record<string, unknown>;
  display_order?: number;
};

export type SmartReportGenerateRequestDto = {
  template_id: number;
  instance_name?: string | null;
  report_id?: number | null;
  parameters: Record<string, unknown>;
  text_values: Record<string, unknown>;
};

export type SmartReportPreviewRequestDto = {
  template_id: number;
  parameters: Record<string, unknown>;
  text_values: Record<string, unknown>;
};

export type SmartReportPreviewResponseDto = {
  preview_text: string;
  resolved_values: Record<string, string>;
  warnings: string[];
};

export type SmartReportGenerateResponseDto = {
  instance_id: number;
  job_id: number;
  output_filename: string;
  download_url: string;
  generated_at: string;
  resolved_values: Record<string, string>;
  warnings: string[];
};

export type SmartReportInstanceDto = {
  instance_id: number;
  report_id?: number | null;
  template_id: number;
  template_name?: string | null;
  instance_name: string;
  generation_status: string;
  output_file_path?: string | null;
  error_message?: string | null;
  last_generated_at?: string | null;
  last_refresh_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductScopeMigrationFileItemDto = {
  file_name: string;
  file_year?: number | null;
  rows_to_insert: number;
  rows_to_delete: number;
};

export type ProductScopeMigrationPreviewDto = {
  data_acct_code: string;
  affects_all_budget_files?: boolean;
  files: ProductScopeMigrationFileItemDto[];
  total_rows_to_insert: number;
  total_rows_to_delete: number;
  message: string;
};

export type DataAccountDto = {
  data_acct_code: string;
  data_acct_name: string;
  metric_group_code: string | null;
  metric_group_name: string | null;
  product_code: string | null;
  budget_formula: string | null;
  actual_formula: string | null;
  budget_rule_code?: string | null;
  budget_rule_config_json?: string | null;
  value_type: string;
  remark: string | null;
  product_name: string | null;
  product_display: string;
  product_codes: string | null;
  has_budget_data_records?: boolean;
  budget_data_ref_count?: number;
  report_mapping_ref_count?: number;
  migration_inserted_total?: number | null;
  migration_deleted_total?: number | null;
  migration_files?: ProductScopeMigrationFileItemDto[] | null;
};

export type DataAccountMetricNodeDto = {
  node_code: string;
  node_name: string;
  parent_code: string | null;
  level: number;
  node_type: string;
  sort_order: number;
  is_active: number;
  remark: string | null;
};

export type DataAccountMetricBindingDto = {
  binding_code: string;
  metric_node_code: string;
  metric_node_name: string | null;
  scope_type: string;
  scope_code: string;
  product_code: string | null;
  product_name: string | null;
  data_acct_code: string;
  data_acct_name: string | null;
  sort_order: number;
  is_active: number;
  remark: string | null;
};

export type DataAccountMetricTreeDto = {
  nodes: DataAccountMetricNodeDto[];
  bindings: DataAccountMetricBindingDto[];
};

export type ProductTypeDto = {
  product_code: string;
  product_name: string;
  remark: string | null;
  parent_code: string | null;
  level: number;
};

export type ReportAccountDto = {
  report_acct_code: string;
  report_acct_name: string;
  parent_code: string | null;
  is_summary: boolean;
  is_minus: boolean;
  level: number;
  is_leaf: boolean;
  remark: string | null;
};

export type ReportDataMappingDto = {
  report_acct_code: string;
  data_acct_code: string;
};

export type DeptAccountDto = {
  dept_code: string;
  dept_name: string;
  parent_code: string | null;
  level: number;
  is_leaf: boolean;
};

export type DeptProductMappingDto = {
  dept_code: string;
  product_code: string;
};

export type BudgetSubjectCatalogDto = {
  id: number;
  parent_id: number | null;
  level_number: number;
  level_label: string;
  subject_name: string;
  formula_text: string | null;
  sort_order: number;
  is_leaf: boolean;
};

export type ExpenseForecastScopeOptionDto = {
  value: string;
  label: string;
};

export type ExpenseForecastOwnerGroupOptionDto = {
  group_value: string;
  group_label: string;
  owner_options: ExpenseForecastScopeOptionDto[];
};

export type ExpenseForecastMetaResponseDto = {
  default_year: number;
  default_version: string;
  version_suggestions: string[];
  entity_options: ExpenseForecastScopeOptionDto[];
  group_options: ExpenseForecastScopeOptionDto[];
  owner_options: ExpenseForecastScopeOptionDto[];
  owner_group_options: ExpenseForecastOwnerGroupOptionDto[];
};

export type ExpenseForecastMonthCellDto = {
  month: number;
  value: number;
  source: "actual" | "forecast";
  editable: boolean;
};

export type ExpenseForecastRowDto = {
  id: number;
  parent_id: number | null;
  level_number: number;
  subject_name: string;
  formula_text: string | null;
  sort_order: number;
  is_leaf: boolean;
  months: ExpenseForecastMonthCellDto[];
  total_value: number;
};

export type ExpenseForecastViewResponseDto = {
  year: number;
  forecast_version: string;
  scope_type: "entity" | "group" | "owner";
  scope_value: string;
  actual_cutoff_month: number;
  rows: ExpenseForecastRowDto[];
};

export type ExpenseForecastCellUpsertRequestDto = {
  year: number;
  forecast_version: string;
  scope_type: "entity" | "group" | "owner";
  scope_value: string;
  subject_id: number;
  month: number;
  value: number;
};

export type ExpenseForecastCellUpsertResponseDto = {
  updated: boolean;
  actual_cutoff_month: number;
};

export type ExpenseForecastImportPreviewItemDto = {
  row_number: number;
  budget_subject: string;
  month: number;
  value: number;
  action: string;
  message: string | null;
};

export type ExpenseForecastImportPreviewResponseDto = {
  file_name: string;
  import_mode: "append" | "overwrite";
  actual_cutoff_month: number;
  preview_count: number;
  insertable_cells: number;
  updatable_cells: number;
  skipped_cells: number;
  error_cells: number;
  items: ExpenseForecastImportPreviewItemDto[];
};

export type ExpenseForecastImportApplyResponseDto = {
  file_name: string;
  import_mode: "append" | "overwrite";
  actual_cutoff_month: number;
  inserted_cells: number;
  updated_cells: number;
  skipped_cells: number;
  error_cells: number;
};

export type ExpenseActualImportPreviewRowDto = {
  period_ym: string;
  owner_name_raw: string;
  owner_name_mapped: string | null;
  budget_subject_raw: string;
  budget_subject_mapped: string | null;
  amount: number;
  match_status: string;
  match_note: string | null;
};

export type ExpenseActualImportPreviewResponseDto = {
  file_name: string;
  row_count: number;
  periods: string[];
  matched_owner_rows: number;
  matched_subject_rows: number;
  unmatched_rows: number;
  preview_rows: ExpenseActualImportPreviewRowDto[];
  unmatched_preview_rows: ExpenseActualImportPreviewRowDto[];
};

export type ExpenseActualImportApplyResponseDto = {
  batch_id: number;
  file_name: string;
  import_mode: string;
  row_count: number;
  periods: string[];
  matched_owner_rows: number;
  matched_subject_rows: number;
  unmatched_rows: number;
  note: string | null;
};

export type ExpenseActualImportBatchRowDto = {
  id: number;
  file_name: string;
  import_mode: string;
  periods: string[];
  total_rows: number;
  matched_owner_rows: number;
  matched_subject_rows: number;
  unmatched_rows: number;
  created_at: string;
  note: string | null;
};

export type BudgetInputPeriodDto = {
  period_id: number;
  month_label: string;
  month_index: number;
  editable: boolean;
};

export type BudgetInputRowDto = {
  report_path: string[];
  report_code: string | null;
  data_acct_code: string;
  data_acct_name: string;
  value_type: string;
  calc_formula: string | null;
  formula_locked: boolean;
  formula_errors?: (string | null)[];
  values: number[];
  total: number;
};

export type BudgetInputLoadResponseDto = {
  budget_year: number;
  version_id: number;
  current_month: number;
  budget_actual: number;
  product_code: string;
  periods: BudgetInputPeriodDto[];
  rows: BudgetInputRowDto[];
};

export type BudgetInputCellUpsertDto = {
  data_acct_code: string;
  product_code: string;
  period_id: number;
  version_id: number;
  budget_actual: number;
  value: number;
};

export type BudgetInputWriteResultDto = {
  saved: number;
};

export type BudgetInputImportCellStatus =
  | "empty"
  | "inserted"
  | "updated"
  | "skipped"
  | "error";

export type BudgetInputImportMonthResultDto = {
  month: number;
  value_text: string;
  status: BudgetInputImportCellStatus;
  reason?: string | null;
};

export type BudgetInputImportResultRowDto = {
  sheet_name: string;
  excel_row: number;
  data_acct_code: string;
  product_code: string;
  months: BudgetInputImportMonthResultDto[];
  note: string;
};

export type BudgetInputImportResponseDto = {
  budget_year: number;
  version_id: number;
  current_month: number;
  rows: BudgetInputImportResultRowDto[];
  saved_cells: number;
};

/** 下载预算基础数据上传模版（与 download_template/budget_data_temp.xlsx 一致） */
export async function downloadBudgetInputTemplate(): Promise<void> {
  const r = await fetch(buildApiUrl("/api/budget-input/template"), { credentials: "include" });
  if (!r.ok) {
    throw new Error(await readErrorMessage(r));
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "budget_data_temp.xlsx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function importBudgetInputExcel(
  file: File,
  versionId: number,
): Promise<BudgetInputImportResponseDto> {
  const fd = new FormData();
  fd.append("file", file);
  return apiPostForm<BudgetInputImportResponseDto>(
    `/api/budget-input/import?version_id=${encodeURIComponent(String(versionId))}`,
    fd,
  );
}

export type BudgetSummaryRebuildResultDto = {
  version_id: number;
  current_month: number;
  rebuilt_rows: number;
  rule_message: string;
};

export type BudgetSummaryRowDto = {
  report_level1: string | null;
  report_level2: string | null;
  report_level3: string | null;
  report_level4: string | null;
  report_level5: string | null;
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

export type CompareSyncLatestStatusDto = {
  job_id: number | null;
  start_time: string | null;
  end_time: string | null;
  trigger_source: string | null;
  status: string | null;
  message: string | null;
};

export type CompareSummaryRowDto = {
  show_level: number;
  data_file_id: number;
  source_year: number;
  source_version_id: number;
  source_version_name: string | null;
  report_level1: string | null;
  report_level2: string | null;
  report_level3: string | null;
  report_level4: string | null;
  report_level5: string | null;
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
  sync_time: string;
};

export type SystemDatabaseRowDto = {
  id: number;
  data_file_name: string;
  year: number;
  create_time: string;
  file_path: string;
};

export type SystemVersionRowDto = {
  version_id: number;
  version_name: string;
  version_date_time: string;
  current_month: number;
};

export type EditVersionSelectionDto = {
  data_file_id: number;
  version_id: number;
};

export type EditShowVersionSelectionDto = {
  level: number;
  data_file_id: number;
  version_id: number;
};

export type EditShowVersionStateDto = {
  edit: EditVersionSelectionDto | null;
  shows: EditShowVersionSelectionDto[];
};

export type SystemUserRowDto = {
  id: number;
  user_name: string;
  permission_type: number;
  first_login_flag: number;
  create_time: string;
  update_time: string | null;
};

export type AgentChatMessageDto = {
  role: string;
  content: string;
  dialogue_id?: number;
};

export type AgentChatRequestDto = {
  message: string;
  history?: AgentChatMessageDto[];
  top_k?: number;
  last_dialogue_id?: number;
  pending_query_spec?: Record<string, unknown>;
};

export type AgentReplyOptionDto = {
  id: string;
  label: string;
};

export type AgentPivotSuggestionDto = {
  row_field_ids: string[];
  column_field_ids: string[];
  page_field_ids: string[];
  value_field_ids: string[];
  page_selections: Record<string, string>;
  /** 仅报告/数据科目 code，空格分隔，透视内 OR 搜索 */
  pivot_search_text?: string;
  explanation: string;
  confidence: number;
};

export type AgentChatResponseDto = {
  reply: string;
  intent_type: string;
  next_action: string;
  need_clarification: boolean;
  missing_slots: string[];
  clarification_options: Record<string, string[]>;
  assumptions: string[];
  suggested_sql: string | null;
  kb_context: Record<string, unknown>;
  executed: boolean;
  result_row_count: number;
  result_preview: Record<string, unknown>[];
  memory_id: string | null;
  reply_options?: AgentReplyOptionDto[];
  open_pivot_table?: boolean;
  pivot_suggestion?: AgentPivotSuggestionDto | null;
  dialogue_id?: number;
  pending_query_spec?: Record<string, unknown> | null;
};

export async function agentChat(body: AgentChatRequestDto): Promise<AgentChatResponseDto> {
  return apiPost<AgentChatResponseDto>("/api/agent/chat", body);
}

export type AgentDebugEventDto = {
  event_id: string;
  ts: string;
  kind: string;
  session_id: string;
  dialogue_id: number;
  turn_id: string;
  channel: string;
  user_query: string;
  purpose: string;
  model: string;
  input_full: Record<string, unknown> | null;
  output_full: string | null;
  error: string | null;
};

export type AgentDebugEventsResponseDto = {
  items: AgentDebugEventDto[];
};

export async function getAgentDebugEvents(limit = 200): Promise<AgentDebugEventsResponseDto> {
  return apiGet<AgentDebugEventsResponseDto>(`/api/system/agent-debug/events?limit=${encodeURIComponent(String(limit))}`);
}

export async function clearAgentDebugEvents(): Promise<void> {
  return apiDelete("/api/system/agent-debug/events");
}

export type AgentFeedbackRequestDto = {
  memory_id: string;
  satisfied: boolean;
  comment?: string;
};

export type AgentFeedbackResponseDto = {
  updated: boolean;
  memory_id: string;
};

export async function submitAgentFeedback(
  body: AgentFeedbackRequestDto,
): Promise<AgentFeedbackResponseDto> {
  return apiPost<AgentFeedbackResponseDto>("/api/agent/feedback", body);
}

export type AgentFileParseResponseDto = {
  filename: string;
  file_type: string;
  char_count: number;
  summary: string;
  key_points: string[];
  suggested_actions: string[];
  warnings: string[];
};

export async function parseAgentFile(file: File): Promise<AgentFileParseResponseDto> {
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<AgentFileParseResponseDto>("/api/agent/file/parse", formData);
}

// ── 预算预测驱动模块 DTOs ──

export type DriverProductDto = {
  id: number;
  indicator_code: string;
  product_code: string;
  product_name: string | null;
  sort_order: number;
  data_accounts: DriverMappedDataAccountDto[];
};

export type DriverMappedDataAccountDto = {
  data_acct_code: string;
  data_acct_name: string;
  value_type: string;
  report_code: string | null;
  report_path: string[];
  actual_values: number[];
  sort_order: number;
};

export type DriverDataAccountOptionDto = {
  data_acct_code: string;
  data_acct_name: string;
  value_type: string;
  product_codes: string | null;
  report_code: string | null;
  report_path: string[];
};

export type DriverAccountMappingUpsertDto = {
  indicator_code: string;
  category_code?: string | null;
  product_code: string;
  data_acct_code: string;
  sort_order?: number;
};

export type DriverIndicatorDto = {
  indicator_code: string;
  indicator_name: string;
  value_type: string;
  data_acct_code: string | null;
  has_product_detail: number;
  has_monthly_detail: number;
  sort_order: number;
  products: DriverProductDto[];
};

export type DriverCategoryDto = {
  category_code: string;
  category_name: string;
  current_month: number;
  sort_order: number;
  indicators: DriverIndicatorDto[];
};

export type DriverImportMonthlyItem = {
  month: string;
  value: number;
};

export type DriverImportRequestDto = {
  indicator_code: string;
  product_code: string | null;
  data_acct_code?: string | null;
  monthly_values: DriverImportMonthlyItem[];
};

export type DriverImportResponseDto = {
  version_id: number;
  budget_year: number;
  saved_cells: number;
  summary: Record<string, unknown>;
  monthly: Record<string, unknown>[];
  errors: string[];
  warnings: string[];
};

export type DriverImportPreviewRowDto = {
  sheet_name: string;
  excel_row: number;
  indicator_text: string;
  product_text: string;
  requested_data_acct_code: string | null;
  matched_indicator_code: string | null;
  matched_indicator_name: string | null;
  matched_product_code: string | null;
  resolved_data_acct_codes: string[];
  recognized_value_cells: number;
  status: string;
  message: string | null;
};

export type DriverImportPreviewResponseDto = {
  row_count: number;
  ready_rows: number;
  error_rows: number;
  preview_rows: DriverImportPreviewRowDto[];
  errors: string[];
  warnings: string[];
};

// ── 预算预测驱动模块 API ──

export async function fetchDriverCategories(): Promise<DriverCategoryDto[]> {
  return apiGet<DriverCategoryDto[]>("/api/driver/categories");
}

export async function fetchDriverDataAccountOptions(q = ""): Promise<DriverDataAccountOptionDto[]> {
  const suffix = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  return apiGet<DriverDataAccountOptionDto[]>(`/api/driver/data-account-options${suffix}`);
}

export async function saveDriverAccountMapping(
  body: DriverAccountMappingUpsertDto
): Promise<DriverMappedDataAccountDto> {
  return apiPost<DriverMappedDataAccountDto>("/api/driver/account-mappings", body);
}

export async function deleteDriverAccountMapping(
  indicatorCode: string,
  productCode: string,
  dataAcctCode: string
): Promise<{ deleted: number }> {
  const qs = new URLSearchParams({
    indicator_code: indicatorCode,
    product_code: productCode,
    data_acct_code: dataAcctCode,
  });
  return apiDelete(`/api/driver/account-mappings?${qs.toString()}`).then(() => ({ deleted: 1 }));
}

export async function downloadDriverTemplate(): Promise<void> {
  const r = await fetch(buildApiUrl("/api/driver/template"), { credentials: "include" });
  if (!r.ok) throw new Error(await readErrorMessage(r));
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "driver_template.xlsx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function importDriverExcel(file: File): Promise<DriverImportResponseDto> {
  const fd = new FormData();
  fd.append("file", file);
  return apiPostForm<DriverImportResponseDto>("/api/driver/import", fd);
}

export async function previewDriverExcel(file: File): Promise<DriverImportPreviewResponseDto> {
  const fd = new FormData();
  fd.append("file", file);
  return apiPostForm<DriverImportPreviewResponseDto>("/api/driver/preview", fd);
}

export async function importDriverJson(
  items: DriverImportRequestDto[],
  options?: { recalculate?: boolean }
): Promise<DriverImportResponseDto> {
  const recalculate = options?.recalculate ?? true;
  return apiPost<DriverImportResponseDto>(`/api/driver/import-json?recalculate=${recalculate ? "true" : "false"}`, items);
}
