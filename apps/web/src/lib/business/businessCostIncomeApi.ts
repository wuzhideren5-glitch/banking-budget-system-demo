import { apiDelete, apiGet, apiPost, apiPostForm, apiPut, downloadFile } from "@/lib/shared/api";

const BASE_PATH = "/api/business-cost-income-ratio";

export type BusinessCostIncomeSection = "indicator" | "input" | "output";
export type BusinessCostIncomeItemSection = "input" | "output";
export type BusinessCostIncomeValueField = "actual" | "budget" | "forecast";
export type BusinessCostIncomeIndicatorFormat = "ratio" | "percent" | "number";
export type BusinessCostIncomeValueMode = "tree" | "self" | "self_and_tree";
export type BusinessCostIncomeEntryMode =
  | "manual"
  | "manual_preferred"
  | "computed"
  | "rollup"
  | "binding"
  | "indicator";
export type BusinessCostIncomeManualEntryMode = "disabled" | "manual" | "manual_preferred";

export type BusinessCostIncomeMetricsDto = {
  current_actual: number;
  annual_budget: number;
  budget_progress: number | null;
  annual_forecast: number;
  forecast_budget_gap: number;
  gap_rate: number | null;
  yoy_change: number;
  yoy_rate: number | null;
  last_year_actual: number;
};

export type BusinessCostIncomeMonthlyEntryDto = {
  month_actual: number;
  month_budget: number;
  month_forecast: number;
};

export type BusinessCostIncomeRowDto = {
  section: BusinessCostIncomeSection;
  id: number;
  name: string;
  parent_id: number | null;
  is_leaf: boolean;
  entry_mode: BusinessCostIncomeEntryMode;
  topic_metric_node_code?: string | null;
  data_acct_code?: string;
  org_product_ref?: string;
  org_product_entity_code?: string;
  org_product_table_name?: string;
  org_product_metric_code?: string;
  org_product_metric_name?: string;
  metric_code?: string;
  metric_name?: string;
  sort_order: number;
  enabled: boolean;
  metrics: BusinessCostIncomeMetricsDto;
  monthly_entry: BusinessCostIncomeMonthlyEntryDto;
};

export type BusinessCostIncomeReportResponse = {
  report_month: string;
  entity_name: string;
  group_name: string | null;
  product_code: string | null;
  amount_unit: string;
  amount_unit_label: string;
  rows: BusinessCostIncomeRowDto[];
  note: string;
};

export type BusinessCostIncomeMetaResponse = {
  entity_options: string[];
  product_options: Array<{ product_code: string; product_name: string }>;
  group_options: string[];
  amount_unit_options: Array<{ value: string; label: string }>;
};

export type BusinessCostIncomeCellUpsertRequest = {
  year_month: string;
  entity_name: string;
  group_name: string | null;
  product_code: string | null;
  amount_unit: string;
  item_section: BusinessCostIncomeItemSection;
  item_id: number;
  field: BusinessCostIncomeValueField;
  value: number;
};

export type BusinessCostIncomeItemDto = {
  id: number;
  product_code: string;
  section: BusinessCostIncomeItemSection;
  name: string;
  parent_id: number | null;
  display_group: boolean;
  data_acct_code: string;
  org_product_ref: string;
  org_product_entity_code: string;
  org_product_table_name: string;
  org_product_metric_code: string;
  org_product_metric_name: string;
  metric_code?: string;
  metric_name?: string;
  manual_entry_mode: BusinessCostIncomeManualEntryMode;
  value_mode: BusinessCostIncomeValueMode;
  entry_mode?: BusinessCostIncomeEntryMode;
  sort_order: number;
  enabled: boolean;
};

export type BusinessCostIncomeItemCreateRequest = {
  product_code?: string | null;
  section: BusinessCostIncomeItemSection;
  name: string;
  parent_id: number | null;
  display_group?: boolean;
  data_acct_code?: string | null;
  org_product_ref?: string | null;
  org_product_entity_code?: string | null;
  org_product_table_name?: string | null;
  org_product_metric_code?: string | null;
  org_product_metric_name?: string | null;
  manual_entry_mode?: BusinessCostIncomeManualEntryMode;
  value_mode?: BusinessCostIncomeValueMode;
  sort_order: number;
  enabled: boolean;
};

export type BusinessCostIncomeItemUpdateRequest = {
  product_code?: string | null;
  name: string;
  parent_id: number | null;
  display_group?: boolean;
  data_acct_code?: string | null;
  org_product_ref?: string | null;
  org_product_entity_code?: string | null;
  org_product_table_name?: string | null;
  org_product_metric_code?: string | null;
  org_product_metric_name?: string | null;
  manual_entry_mode?: BusinessCostIncomeManualEntryMode;
  value_mode?: BusinessCostIncomeValueMode;
  sort_order: number;
  enabled: boolean;
};

export type BusinessCostIncomeIndicatorDto = {
  id: number;
  product_code: string;
  name: string;
  parent_id: number | null;
  display_group: boolean;
  topic_metric_node_code: string | null;
  numerator_section: BusinessCostIncomeItemSection;
  numerator_item_id: number;
  numerator_value_mode: BusinessCostIncomeValueMode;
  denominator_section: BusinessCostIncomeItemSection;
  denominator_item_id: number;
  denominator_value_mode: BusinessCostIncomeValueMode;
  format: BusinessCostIncomeIndicatorFormat;
  annualize: boolean;
  sort_order: number;
  enabled: boolean;
};

export type BusinessCostIncomeIndicatorCreateRequest = {
  product_code?: string | null;
  name: string;
  parent_id?: number | null;
  display_group?: boolean;
  topic_metric_node_code?: string | null;
  numerator_section: BusinessCostIncomeItemSection;
  numerator_item_id: number;
  numerator_value_mode?: BusinessCostIncomeValueMode;
  denominator_section: BusinessCostIncomeItemSection;
  denominator_item_id: number;
  denominator_value_mode?: BusinessCostIncomeValueMode;
  format: BusinessCostIncomeIndicatorFormat;
  annualize?: boolean;
  sort_order: number;
  enabled: boolean;
};

export type BusinessCostIncomeIndicatorUpdateRequest = BusinessCostIncomeIndicatorCreateRequest;

export type BusinessCostIncomeActualImportPreviewItemDto = {
  row_number: number;
  sheet_name: string;
  field: BusinessCostIncomeValueField | string;
  field_label: string;
  entity_name: string;
  group_name: string;
  product_code: string;
  section: string;
  item_id: number | null;
  item_name: string;
  month: number | null;
  value_text: string;
  action: "ready" | "error" | string;
  message: string | null;
};

export type BusinessCostIncomeActualImportPreviewResponse = {
  file_name: string;
  year: number;
  preview_count: number;
  insertable_cells: number;
  updatable_cells: number;
  skipped_cells: number;
  error_cells: number;
  items: BusinessCostIncomeActualImportPreviewItemDto[];
};

export type BusinessCostIncomeActualImportApplyResponse = {
  file_name: string;
  year: number;
  saved_cells: number;
  skipped_cells: number;
  error_cells: number;
};

function withQuery(path: string, params: URLSearchParams): string {
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function getBusinessCostIncomeMeta(args: {
  entityName?: string;
  reportMonth?: string;
  productCode?: string;
}): Promise<BusinessCostIncomeMetaResponse> {
  const params = new URLSearchParams();
  if (args.entityName) params.set("entity_name", args.entityName);
  if (args.reportMonth) params.set("report_month", args.reportMonth);
  if (args.productCode) params.set("product_code", args.productCode);
  return apiGet<BusinessCostIncomeMetaResponse>(withQuery(`${BASE_PATH}/meta`, params));
}

export function getBusinessCostIncomeReport(args: {
  entityName: string;
  reportMonth: string;
  groupName?: string;
  productCode?: string;
  amountUnit: string;
}): Promise<BusinessCostIncomeReportResponse> {
  const params = new URLSearchParams();
  params.set("entity_name", args.entityName);
  params.set("report_month", args.reportMonth);
  params.set("amount_unit", args.amountUnit);
  if (args.groupName) params.set("group_name", args.groupName);
  if (args.productCode) params.set("product_code", args.productCode);
  return apiGet<BusinessCostIncomeReportResponse>(withQuery(`${BASE_PATH}/report`, params));
}

export function upsertBusinessCostIncomeCell(
  body: BusinessCostIncomeCellUpsertRequest
): Promise<{ updated: boolean }> {
  return apiPost<{ updated: boolean }>(`${BASE_PATH}/input/cell`, body);
}

export function listBusinessCostIncomeItems(productCode?: string): Promise<BusinessCostIncomeItemDto[]> {
  const params = new URLSearchParams();
  if (productCode) params.set("product_code", productCode);
  return apiGet<BusinessCostIncomeItemDto[]>(withQuery(`${BASE_PATH}/admin/items`, params));
}

export function createBusinessCostIncomeItem(
  body: BusinessCostIncomeItemCreateRequest
): Promise<BusinessCostIncomeItemDto> {
  return apiPost<BusinessCostIncomeItemDto>(`${BASE_PATH}/admin/items`, body);
}

export function updateBusinessCostIncomeItem(
  id: number,
  body: BusinessCostIncomeItemUpdateRequest
): Promise<BusinessCostIncomeItemDto> {
  return apiPut<BusinessCostIncomeItemDto>(`${BASE_PATH}/admin/items/${id}`, body);
}

export function deleteBusinessCostIncomeItem(id: number): Promise<void> {
  return apiDelete(`${BASE_PATH}/admin/items/${id}`);
}

export function reorderBusinessCostIncomeItems(itemIds: number[]): Promise<{ reordered: boolean; count: number }> {
  return apiPut<{ reordered: boolean; count: number }>(`${BASE_PATH}/admin/items-reorder`, {
    item_ids: itemIds,
  });
}

export function listBusinessCostIncomeIndicators(productCode?: string): Promise<BusinessCostIncomeIndicatorDto[]> {
  const params = new URLSearchParams();
  if (productCode) params.set("product_code", productCode);
  return apiGet<BusinessCostIncomeIndicatorDto[]>(withQuery(`${BASE_PATH}/admin/indicators`, params));
}

export function createBusinessCostIncomeIndicator(
  body: BusinessCostIncomeIndicatorCreateRequest
): Promise<BusinessCostIncomeIndicatorDto> {
  return apiPost<BusinessCostIncomeIndicatorDto>(`${BASE_PATH}/admin/indicators`, body);
}

export function updateBusinessCostIncomeIndicator(
  id: number,
  body: BusinessCostIncomeIndicatorUpdateRequest
): Promise<BusinessCostIncomeIndicatorDto> {
  return apiPut<BusinessCostIncomeIndicatorDto>(`${BASE_PATH}/admin/indicators/${id}`, body);
}

export function deleteBusinessCostIncomeIndicator(id: number): Promise<void> {
  return apiDelete(`${BASE_PATH}/admin/indicators/${id}`);
}

export function reorderBusinessCostIncomeIndicators(
  indicatorIds: number[]
): Promise<{ reordered: boolean; count: number }> {
  return apiPut<{ reordered: boolean; count: number }>(`${BASE_PATH}/admin/indicators-reorder`, {
    indicator_ids: indicatorIds,
  });
}

function importQuery(year: number, months: number[]): string {
  const params = new URLSearchParams();
  params.set("year", String(year));
  if (months.length > 0) params.set("months", months.join(","));
  return params.toString();
}

export function downloadBusinessCostIncomeImportTemplate(args: {
  year: number;
  productCodes: string[];
  months: number[];
}): Promise<void> {
  const params = new URLSearchParams();
  params.set("year", String(args.year));
  if (args.months.length > 0) params.set("months", args.months.join(","));
  args.productCodes.forEach((code) => params.append("product_codes", code));
  return downloadFile(`${BASE_PATH}/template?${params.toString()}`, `business_cost_income_import_template_${args.year}.xlsx`);
}

export function previewBusinessCostIncomeImport(
  file: File,
  year: number,
  months: number[]
): Promise<BusinessCostIncomeActualImportPreviewResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<BusinessCostIncomeActualImportPreviewResponse>(
    `${BASE_PATH}/import-preview?${importQuery(year, months)}`,
    form,
  );
}

export function applyBusinessCostIncomeImport(
  file: File,
  year: number,
  months: number[]
): Promise<BusinessCostIncomeActualImportApplyResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<BusinessCostIncomeActualImportApplyResponse>(
    `${BASE_PATH}/import-apply?${importQuery(year, months)}`,
    form,
  );
}
