import { apiGet, apiPostBlob } from "@/lib/shared/api";

const BASE_PATH = "/api/expense-budget-execution";

export type ExpenseBudgetExecutionMode = "query" | "template" | "subject";
export type ExpenseBudgetExecutionExportMode = ExpenseBudgetExecutionMode | "flat";
export type ExpenseBudgetExecutionPerspective = "entity" | "group" | "owner_dept";
export type ExpenseBudgetExecutionAmountUnit = "yuan" | "thousand" | "ten_thousand" | "million" | "hundred_million";

export type ExpenseBudgetExecutionRowDto = {
  perspective: ExpenseBudgetExecutionPerspective;
  dimension_value: string;
  entity_name: string;
  group_name: string;
  owner_dept: string;
  budget_subject: string;
  monthly_actuals: number[];
  cumulative_actual: number;
  annual_budget: number;
  execution_rate: number | null;
  month_over_month?: number | null;
  month_over_month_rate?: number | null;
};

export type ExpenseBudgetExecutionTemplateSubjectNodeDto = {
  id: number;
  parent_id: number | null;
  level_number: number;
  level_label: string;
  subject_name: string;
  formula_text: string | null;
  sort_order: number;
  is_leaf: boolean;
  monthly_actuals: number[];
  previous_year_monthly_actuals: number[];
  current_actual: number;
  annual_budget: number;
  budget_progress: number | null;
  yoy_change: number;
  yoy_rate: number | null;
  month_over_month: number | null;
  month_over_month_rate: number | null;
  last_year_actual: number;
  children: ExpenseBudgetExecutionTemplateSubjectNodeDto[];
};

export type ExpenseBudgetExecutionSubjectScopeNodeDto = {
  id: number;
  parent_id: number | null;
  level_number: number;
  level_label: string;
  subject_name: string;
  children: ExpenseBudgetExecutionSubjectScopeNodeDto[];
};

export type ExpenseBudgetExecutionMetricRowDto = {
  label: string;
  subject_name: string;
  level: number;
  current_actual: number;
  monthly_actuals?: number[];
  annual_budget: number;
  budget_progress: number | null;
  yoy_change: number;
  yoy_rate: number | null;
  month_over_month: number | null;
  month_over_month_rate: number | null;
  last_year_actual: number;
  previous_year_monthly_actuals?: number[];
};

export type ExpenseBudgetExecutionManagedBlockDto = {
  title: string;
  rows: ExpenseBudgetExecutionMetricRowDto[];
};

export type ExpenseBudgetExecutionMatrixRowDto = {
  label: string;
  level: number;
  actuals: Record<string, number>;
  monthly_actuals_by_subject?: Record<string, number[]>;
  monthly_actuals_total?: number[];
  budgets: Record<string, number>;
  progresses: Record<string, number | null>;
  actual_total: number;
  budget_total: number;
  budget_progress_total: number | null;
};

export type ExpenseBudgetExecutionConsistencyWarningDto = {
  metric_name: string;
  field: string;
  field_label: string;
  reports: string[];
  values: Array<{
    report: string;
    value: number | null;
  }>;
  difference: number;
  message: string;
};

export type ExpenseBudgetExecutionResponseDto = {
  mode?: ExpenseBudgetExecutionMode;
  perspective?: ExpenseBudgetExecutionPerspective;
  budget_year: number;
  version_id: number;
  version_name: string;
  current_month: number;
  framework_source_mode: "master";
  actual_source_mode: "internal" | "source";
  framework_source_file: string;
  actual_source_file: string;
  previous_actual_source_file?: string;
  available_entities?: string[];
  available_groups?: string[];
  available_owner_departments?: string[];
  template_scope_options?: Array<{
    entity_name: string;
    group_name: string;
    owner_dept: string;
  }>;
  selected_entity_name?: string;
  selected_group_name?: string;
  selected_owner_dept?: string;
  selected_subject_id?: number | null;
  template_title?: string;
  subject_title?: string;
  rows?: ExpenseBudgetExecutionRowDto[];
  subject_tree?: ExpenseBudgetExecutionTemplateSubjectNodeDto[];
  monthly_business_rows?: ExpenseBudgetExecutionMetricRowDto[];
  monthly_it_rows?: ExpenseBudgetExecutionMetricRowDto[];
  monthly_daily_managed_blocks?: ExpenseBudgetExecutionManagedBlockDto[];
  monthly_daily_other_columns?: string[];
  monthly_daily_other_rows?: ExpenseBudgetExecutionMatrixRowDto[];
  consistency_warnings?: ExpenseBudgetExecutionConsistencyWarningDto[];
  subject_scope_tree?: ExpenseBudgetExecutionSubjectScopeNodeDto[];
  note: string;
};

export type ExpenseBudgetExecutionReportRequest = {
  mode: ExpenseBudgetExecutionMode;
  perspective: ExpenseBudgetExecutionPerspective;
  keyword: string;
  includeZeroRows: boolean;
  entityName?: string;
  groupName?: string;
  ownerDept?: string;
  subjectId?: string;
  reportMonth?: string;
};

export type ExpenseBudgetExecutionExportRequest = Omit<ExpenseBudgetExecutionReportRequest, "mode" | "subjectId" | "reportMonth"> & {
  mode: ExpenseBudgetExecutionExportMode;
  amountUnit: ExpenseBudgetExecutionAmountUnit;
  subjectId?: number;
  reportMonth?: number;
  includeMonthlyActuals: boolean;
  includeLastYearMonthlyActuals: boolean;
};

export function buildExpenseBudgetExecutionExportPayload(request: ExpenseBudgetExecutionExportRequest) {
  return {
    mode: request.mode,
    perspective: request.perspective,
    amount_unit: request.amountUnit,
    keyword: request.keyword,
    include_zero_rows: request.includeZeroRows,
    entity_name: request.entityName ?? "",
    group_name: request.groupName ?? "",
    owner_dept: request.ownerDept ?? "",
    subject_id: request.subjectId,
    report_month: request.reportMonth,
    include_monthly_actuals: request.includeMonthlyActuals,
    include_last_year_monthly_actuals: request.includeLastYearMonthlyActuals,
  };
}

function appendReportParams(params: URLSearchParams, request: ExpenseBudgetExecutionReportRequest): void {
  params.set("mode", request.mode);
  params.set("perspective", request.perspective);
  params.set("keyword", request.keyword);
  params.set("include_zero_rows", String(request.includeZeroRows));
  if (request.entityName) params.set("entity_name", request.entityName);
  if (request.groupName) params.set("group_name", request.groupName);
  if (request.ownerDept) params.set("owner_dept", request.ownerDept);
  if (request.subjectId) params.set("subject_id", request.subjectId);
  if (request.reportMonth) params.set("report_month", request.reportMonth);
}

export function getExpenseBudgetExecutionReport(
  request: ExpenseBudgetExecutionReportRequest
): Promise<ExpenseBudgetExecutionResponseDto> {
  const params = new URLSearchParams();
  appendReportParams(params, request);
  return apiGet<ExpenseBudgetExecutionResponseDto>(`${BASE_PATH}?${params.toString()}`);
}

export function exportExpenseBudgetExecutionReport(
  request: ExpenseBudgetExecutionExportRequest
): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob(`${BASE_PATH}/export`, buildExpenseBudgetExecutionExportPayload(request));
}
