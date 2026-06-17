import { apiGet, downloadFile } from "@/lib/shared/api";

const BASE_PATH = "/api/input-output-topic-overview";

export type InputOutputTopicSectionType = "indicator" | "input" | "output";
export type InputOutputTopicViewMode = "total" | "detail";
export type InputOutputTopicIndicatorFormat = "ratio" | "percent" | "number";

export type InputOutputTopicMetricsDto = {
  current_actual: number;
  annual_budget: number;
  budget_progress: number | null;
  annual_forecast: number;
  forecast_budget_gap: number;
  gap_rate: number | null;
  yoy_change: number;
  yoy_rate: number | null;
  month_over_month: number | null;
  month_over_month_rate: number | null;
  last_year_actual: number;
};

export type InputOutputTopicMonthlyEntryDto = {
  month_actual: number;
  month_budget: number;
  month_forecast: number;
};

export type InputOutputTopicMonthlySeriesDto = {
  actual: number[];
  last_year_actual: number[];
};

export type InputOutputTopicRowDto = {
  section: InputOutputTopicSectionType;
  id: number;
  name: string;
  parent_id: number | null;
  is_leaf: boolean;
  display_group?: boolean;
  display_format?: InputOutputTopicIndicatorFormat | null;
  topic_metric_node_code?: string | null;
  data_acct_code?: string | null;
  metric_code?: string | null;
  metric_name?: string | null;
  org_product_refs?: string[];
  sort_order: number;
  enabled: boolean;
  metrics: InputOutputTopicMetricsDto;
  monthly_entry: InputOutputTopicMonthlyEntryDto;
  monthly_series: InputOutputTopicMonthlySeriesDto;
};

export type InputOutputTopicProductBlockDto = {
  product_code: string;
  product_name: string;
  rows: InputOutputTopicRowDto[];
};

export type InputOutputTopicMetaResponseDto = {
  entity_options: string[];
  product_options: Array<{
    product_code: string;
    product_name: string;
    group_code?: string;
    group_name?: string;
  }>;
  group_options: string[];
  amount_unit_options: Array<{ value: string; label: string }>;
  available_years: number[];
};

export type InputOutputTopicReportResponseDto = {
  report_month: string;
  selected_year: number;
  entity_name: string;
  group_name: string | null;
  amount_unit: string;
  amount_unit_label: string;
  selected_product_codes: string[];
  total_rows: InputOutputTopicRowDto[];
  product_blocks: InputOutputTopicProductBlockDto[];
  note: string;
};

export type InputOutputTopicReportRequest = {
  reportMonth: string;
  groupName: string;
  amountUnit: string;
  productCodes: string[];
  entityName?: string;
};

export type InputOutputTopicExportRequest = InputOutputTopicReportRequest & {
  viewMode: InputOutputTopicViewMode;
};

function appendTopicParams(params: URLSearchParams, request: InputOutputTopicReportRequest): void {
  params.set("report_month", request.reportMonth);
  params.set("amount_unit", request.amountUnit);
  if (request.entityName) params.set("entity_name", request.entityName);
  if (request.groupName) params.set("group_name", request.groupName);
  request.productCodes.forEach((code) => params.append("product_codes", code));
}

export function getInputOutputTopicMeta(): Promise<InputOutputTopicMetaResponseDto> {
  return apiGet<InputOutputTopicMetaResponseDto>(`${BASE_PATH}/meta`);
}

export function getInputOutputTopicReport(
  request: InputOutputTopicReportRequest,
): Promise<InputOutputTopicReportResponseDto> {
  const params = new URLSearchParams();
  appendTopicParams(params, request);
  return apiGet<InputOutputTopicReportResponseDto>(`${BASE_PATH}/report?${params.toString()}`);
}

export function exportInputOutputTopicReport(request: InputOutputTopicExportRequest): Promise<void> {
  const params = new URLSearchParams();
  appendTopicParams(params, request);
  params.set("view_mode", request.viewMode);
  return downloadFile(
    `${BASE_PATH}/export?${params.toString()}`,
    `投入产出专题概览_${request.viewMode === "total" ? "全行总表" : "分产品明细"}_${request.reportMonth}.xlsx`,
  );
}
