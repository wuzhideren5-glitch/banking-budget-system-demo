import { apiDelete, apiGet, apiGetBlob, apiPost, apiPostBlob, apiPostForm, apiPut } from "@/lib/shared/api";

export type ExpenseForecastScopeOptionDto = {
  value: string;
  label: string;
};

export type ExpenseForecastOwnerGroupOptionDto = {
  group_value: string;
  group_label: string;
  owner_options: ExpenseForecastScopeOptionDto[];
};

export type ExpenseForecastLeafSubjectOptionDto = {
  id: number;
  label: string;
};

export type ExpenseForecastMetaResponseDto = {
  default_year: number;
  default_version: string;
  version_suggestions: string[];
  entity_options: ExpenseForecastScopeOptionDto[];
  group_options: ExpenseForecastScopeOptionDto[];
  owner_options: ExpenseForecastScopeOptionDto[];
  owner_group_options: ExpenseForecastOwnerGroupOptionDto[];
  leaf_subject_options: ExpenseForecastLeafSubjectOptionDto[];
};

export type ExpenseForecastMonthCellDto = {
  month: number;
  value: number;
  source: "actual" | "forecast";
  editable: boolean;
  rule_configured?: boolean;
  rule_scheme?: "MANUAL" | "RESIDUAL_ALLOC" | "METRIC_EXPR" | null;
  value_source?: "actual" | "manual" | "auto" | "override" | "unconfigured" | "aggregate";
  has_override?: boolean;
  system_value?: number | null;
  override_value?: number | null;
  override_reason?: string | null;
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
  annual_budget: number;
  forecast_budget_gap: number;
  budget_execution_rate: number | null;
  business_submission: number;
  capital_advice: number;
  capital_advice_gap: number;
  business_submission_editable: boolean;
  capital_advice_editable: boolean;
  rule_configured?: boolean;
  rule_scheme?: "MANUAL" | "RESIDUAL_ALLOC" | "METRIC_EXPR" | null;
  allow_manual_override?: boolean;
  rule_id?: number | null;
};

export type ExpenseForecastViewResponseDto = {
  year: number;
  forecast_version: string;
  scope_type: "entity" | "group" | "owner";
  scope_value: string;
  actual_cutoff_month: number;
  rows: ExpenseForecastRowDto[];
};

export type ExpenseForecastGroupOwnerViewDto = {
  owner_name: string;
  rows: ExpenseForecastRowDto[];
};

export type ExpenseForecastGroupViewResponseDto = {
  year: number;
  forecast_version: string;
  group_name: string;
  actual_cutoff_month: number;
  owner_views: ExpenseForecastGroupOwnerViewDto[];
};

export type ExpenseForecastSubjectOwnerRowDto = {
  owner_name: string;
  subject_id: number;
  subject_name: string;
  months: ExpenseForecastMonthCellDto[];
  total_value: number;
  annual_budget: number;
  forecast_budget_gap: number;
  budget_execution_rate: number | null;
  business_submission: number;
  capital_advice: number;
  capital_advice_gap: number;
  business_submission_editable: boolean;
  capital_advice_editable: boolean;
  rule_configured?: boolean;
  rule_scheme?: "MANUAL" | "RESIDUAL_ALLOC" | "METRIC_EXPR" | null;
  allow_manual_override?: boolean;
  rule_id?: number | null;
};

export type ExpenseForecastSubjectViewResponseDto = {
  year: number;
  forecast_version: string;
  scope_type: "entity" | "group" | "owner";
  scope_value: string;
  actual_cutoff_month: number;
  subject_id: number;
  subject_name: string;
  rows: ExpenseForecastSubjectOwnerRowDto[];
};

export type ExpenseForecastCellUpsertRequestDto = {
  year: number;
  forecast_version: string;
  scope_type: "entity" | "group" | "owner";
  scope_value: string;
  subject_id: number;
  field_name?: "month_forecast" | "business_submission" | "capital_advice";
  month?: number | null;
  value: number;
  override_reason?: string;
};

export type ExpenseForecastCellUpsertResponseDto = {
  updated: boolean;
  actual_cutoff_month: number;
  mode?: string;
};

export type ExpenseForecastImportPreviewItemDto = {
  row_number: number;
  owner_name?: string | null;
  budget_subject: string;
  field_name: "month_forecast" | "business_submission" | "capital_advice";
  field_label: string;
  month: number | null;
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

export type ExpenseForecastRuleParamItemDto = {
  param_group: string;
  param_key: string;
  param_value?: string | null;
  value_type: string;
};

export type ExpenseForecastRuleVariableItemDto = {
  variable_code: string;
  variable_name?: string | null;
  source_type: "metric_tree" | "org_product_metric" | "forecast_inline" | "actual" | "annual_field" | "constant";
  source_key?: string | null;
  source_subkey?: string | null;
  org_product_ref?: string | null;
  org_product_metric_code?: string | null;
  org_product_entity_code?: string | null;
  org_product_table_name?: string | null;
  default_value?: number | null;
  sort_order: number;
  org_product_refs?: string[];
};

export type ExpenseForecastRuleRowDto = {
  id: number;
  forecast_year: number;
  forecast_version: string;
  owner_name: string;
  subject_id: number;
  subject_name: string;
  scheme_code: "MANUAL" | "RESIDUAL_ALLOC" | "METRIC_EXPR";
  enabled: boolean;
  allow_manual_override: boolean;
  auto_refresh_enabled: boolean;
  manual_recalc_enabled: boolean;
  metric_source_priority: "metric_first" | "inline_first";
  effective_from_month: number;
  effective_to_month: number;
  priority: number;
  remark?: string | null;
  created_at: string;
  updated_at: string;
  params: ExpenseForecastRuleParamItemDto[];
  variables: ExpenseForecastRuleVariableItemDto[];
};

export type ExpenseForecastRuleListResponseDto = {
  items: ExpenseForecastRuleRowDto[];
};

export type ExpenseForecastRuleSaveRequestDto = {
  forecast_year: number;
  forecast_version: string;
  owner_name: string;
  subject_id: number;
  scheme_code: "MANUAL" | "RESIDUAL_ALLOC" | "METRIC_EXPR";
  enabled: boolean;
  allow_manual_override: boolean;
  auto_refresh_enabled: boolean;
  manual_recalc_enabled: boolean;
  metric_source_priority: "metric_first" | "inline_first";
  effective_from_month: number;
  effective_to_month: number;
  priority: number;
  remark?: string | null;
  params: ExpenseForecastRuleParamItemDto[];
  variables: ExpenseForecastRuleVariableItemDto[];
};

export type ExpenseForecastRuleCopyRequestDto = {
  forecast_year: number;
  source_version: string;
  target_version: string;
};

export type ExpenseForecastRuleCopyResponseDto = {
  copied_rules: number;
};

export type ExpenseForecastRuleImportPreviewItemDto = {
  row_number: number;
  owner_name: string;
  subject_name: string;
  scheme_code: string;
  action: string;
  message?: string | null;
};

export type ExpenseForecastRuleImportPreviewResponseDto = {
  file_name: string;
  preview_count: number;
  insertable_rules: number;
  updatable_rules: number;
  skipped_rules: number;
  error_rules: number;
  items: ExpenseForecastRuleImportPreviewItemDto[];
};

export type ExpenseForecastRuleImportApplyResponseDto = {
  file_name: string;
  inserted_rules: number;
  updated_rules: number;
  skipped_rules: number;
  error_rules: number;
};

export type ExpenseForecastRecalculateRequestDto = {
  forecast_year: number;
  forecast_version: string;
  owner_name?: string | null;
  subject_id?: number | null;
};

export type ExpenseForecastRecalculateResponseDto = {
  recalculated_rules: number;
  updated_cells: number;
};

export type ExpenseForecastOverrideRequestDto = {
  forecast_year: number;
  forecast_version: string;
  owner_name: string;
  subject_id: number;
  month: number;
  override_value: number;
  override_reason?: string | null;
};

export type ExpenseForecastTraceMonthItemDto = {
  month: number;
  final_value: number;
  system_value?: number | null;
  override_value?: number | null;
  value_source: "actual" | "manual" | "auto" | "override" | "unconfigured" | "aggregate";
  calc_basis_json?: string | null;
};

export type ExpenseForecastTraceResponseDto = {
  forecast_year: number;
  forecast_version: string;
  owner_name: string;
  subject_id: number;
  rule_id?: number | null;
  rule_scheme?: "MANUAL" | "RESIDUAL_ALLOC" | "METRIC_EXPR" | null;
  items: ExpenseForecastTraceMonthItemDto[];
};

type ExpenseForecastScopeType = "entity" | "group" | "owner";

type ForecastViewParams = {
  year: number | string;
  forecastVersion: string;
  scopeType: ExpenseForecastScopeType;
  scopeValue: string;
};

type ForecastSubjectViewParams = ForecastViewParams & {
  subjectId: number | string;
};

type ForecastImportParams = ForecastViewParams & {
  compileMode: "scope" | "subject";
  mode: "append" | "overwrite";
  subjectId?: number | string | null;
  groupName?: string | null;
};

type ForecastExportParams = ForecastViewParams & {
  compileMode: "scope" | "subject";
  subjectId?: number | string | null;
  amountUnit: string;
  excludeFields: string[];
};

type ForecastGroupExportParams = {
  year: number | string;
  forecastVersion: string;
  groupName: string;
  amountUnit: string;
  excludeFields: string[];
};

type RuleListParams = {
  year: number | string;
  forecastVersion: string;
  ownerName?: string;
  subjectId?: number | null;
};

async function postJsonBlob(
  path: string,
  body: unknown,
  fallbackName: string,
): Promise<{ blob: Blob; filename: string }> {
  const { blob, filename } = await apiPostBlob(path, body);
  return { blob, filename: filename ?? fallbackName };
}

export function fetchExpenseForecastMeta(year: number | string): Promise<ExpenseForecastMetaResponseDto> {
  return apiGet<ExpenseForecastMetaResponseDto>(`/api/expense-forecast/meta?year=${year}`);
}

export function fetchExpenseForecastView(params: ForecastViewParams): Promise<ExpenseForecastViewResponseDto> {
  const query = new URLSearchParams({
    year: String(params.year),
    forecast_version: params.forecastVersion,
    scope_type: params.scopeType,
    scope_value: params.scopeValue,
  });
  return apiGet<ExpenseForecastViewResponseDto>(`/api/expense-forecast/view?${query.toString()}`);
}

export function fetchExpenseForecastGroupView(params: {
  year: number | string;
  forecastVersion: string;
  groupName: string;
}): Promise<ExpenseForecastGroupViewResponseDto> {
  const query = new URLSearchParams({
    year: String(params.year),
    forecast_version: params.forecastVersion,
    group_name: params.groupName,
  });
  return apiGet<ExpenseForecastGroupViewResponseDto>(`/api/expense-forecast/group-view?${query.toString()}`);
}

export function fetchExpenseForecastSubjectView(
  params: ForecastSubjectViewParams,
): Promise<ExpenseForecastSubjectViewResponseDto> {
  const query = new URLSearchParams({
    year: String(params.year),
    forecast_version: params.forecastVersion,
    scope_type: params.scopeType,
    scope_value: params.scopeValue,
    subject_id: String(params.subjectId),
  });
  return apiGet<ExpenseForecastSubjectViewResponseDto>(`/api/expense-forecast/subject-view?${query.toString()}`);
}

export function saveExpenseForecastCell(
  body: ExpenseForecastCellUpsertRequestDto,
): Promise<ExpenseForecastCellUpsertResponseDto> {
  return apiPost<ExpenseForecastCellUpsertResponseDto>("/api/expense-forecast/cell", body);
}

export function exportExpenseForecastWorkbook(
  params: ForecastExportParams,
): Promise<{ blob: Blob; filename: string }> {
  return postJsonBlob(
    "/api/expense-forecast/export",
    {
      year: params.year,
      forecast_version: params.forecastVersion,
      scope_type: params.scopeType,
      scope_value: params.scopeValue,
      compile_mode: params.compileMode,
      subject_id: params.subjectId ? Number(params.subjectId) : null,
      amount_unit: params.amountUnit,
      exclude_fields: params.excludeFields,
    },
    `费用预测表_${params.year}_${params.forecastVersion}.xlsx`,
  );
}

export function exportExpenseForecastGroupWorkbook(
  params: ForecastGroupExportParams,
): Promise<{ blob: Blob; filename: string }> {
  return postJsonBlob(
    "/api/expense-forecast/export-by-group",
    {
      year: String(params.year),
      forecast_version: params.forecastVersion,
      group_name: params.groupName,
      amount_unit: params.amountUnit,
      exclude_fields: params.excludeFields,
    },
    `费用预测表_${params.year}_${params.forecastVersion}_${params.groupName}.xlsx`,
  );
}

function buildForecastImportPath(action: "import-preview" | "import-apply", params: ForecastImportParams): string {
  const query = new URLSearchParams({
    year: String(params.year),
    forecast_version: params.forecastVersion,
    scope_type: params.scopeType,
    scope_value: params.scopeValue,
    compile_mode: params.compileMode,
    mode: params.mode,
  });
  if (params.subjectId) query.set("subject_id", String(params.subjectId));
  if (params.groupName) query.set("group_name", params.groupName);
  return `/api/expense-forecast/${action}?${query.toString()}`;
}

export function previewExpenseForecastImport(
  params: ForecastImportParams,
  file: File,
): Promise<ExpenseForecastImportPreviewResponseDto> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ExpenseForecastImportPreviewResponseDto>(buildForecastImportPath("import-preview", params), form);
}

export function applyExpenseForecastImport(
  params: ForecastImportParams,
  file: File,
): Promise<ExpenseForecastImportApplyResponseDto> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ExpenseForecastImportApplyResponseDto>(buildForecastImportPath("import-apply", params), form);
}

export function listExpenseForecastRules(params: RuleListParams): Promise<ExpenseForecastRuleListResponseDto> {
  const query = new URLSearchParams({
    year: String(params.year),
    forecast_version: params.forecastVersion,
  });
  if (params.ownerName) query.set("owner_name", params.ownerName);
  if (params.subjectId != null) query.set("subject_id", String(params.subjectId));
  return apiGet<ExpenseForecastRuleListResponseDto>(`/api/expense-forecast/rules?${query.toString()}`);
}

export function createExpenseForecastRule(
  body: ExpenseForecastRuleSaveRequestDto,
): Promise<ExpenseForecastRuleRowDto> {
  return apiPost<ExpenseForecastRuleRowDto>("/api/expense-forecast/rules", body);
}

export function updateExpenseForecastRule(
  ruleId: number,
  body: ExpenseForecastRuleSaveRequestDto,
): Promise<ExpenseForecastRuleRowDto> {
  return apiPut<ExpenseForecastRuleRowDto>(`/api/expense-forecast/rules/${ruleId}`, body);
}

export function deleteExpenseForecastRule(ruleId: number): Promise<void> {
  return apiDelete(`/api/expense-forecast/rules/${ruleId}`);
}

export function copyExpenseForecastRulesFromVersion(
  body: ExpenseForecastRuleCopyRequestDto,
): Promise<ExpenseForecastRuleCopyResponseDto> {
  return apiPost<ExpenseForecastRuleCopyResponseDto>("/api/expense-forecast/rules/copy-from-version", body);
}

export function recalculateExpenseForecast(
  body: ExpenseForecastRecalculateRequestDto,
): Promise<ExpenseForecastRecalculateResponseDto> {
  return apiPost<ExpenseForecastRecalculateResponseDto>("/api/expense-forecast/recalculate", body);
}

export function downloadExpenseForecastRuleTemplate(): Promise<{ blob: Blob; filename: string }> {
  return apiGetBlob("/api/expense-forecast/rules/template", "费用预测逻辑配置模板.xlsx");
}

export function previewExpenseForecastRuleImport(
  file: File,
): Promise<ExpenseForecastRuleImportPreviewResponseDto> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ExpenseForecastRuleImportPreviewResponseDto>(
    "/api/expense-forecast/rules/import-preview",
    form,
  );
}

export function applyExpenseForecastRuleImport(
  file: File,
): Promise<ExpenseForecastRuleImportApplyResponseDto> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ExpenseForecastRuleImportApplyResponseDto>(
    "/api/expense-forecast/rules/import-apply",
    form,
  );
}
