import { apiGet, apiPost, apiPostBlob } from "@/lib/shared/api";

export type ChartMetricTreeNodeDto = {
  metric_node_code: string;
  metric_node_name: string;
  is_summary: boolean;
  children: ChartMetricTreeNodeDto[];
};

export type ChartVersionItemDto = {
  show_level: number;
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
  show_level: number;
  data_file_id: number;
  version_id: number;
};

export type ChartStackedRequestDto = {
  metric_node_code: string;
  use_all_versions: boolean;
  selected_versions: ChartVersionSelectionDto[];
  single_version_granularity: "month" | "quarter";
  stack_mode: "absolute" | "percent";
};

export type ChartBarRequestDto = {
  metric_node_code: string;
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

export async function fetchChartMetricTree(): Promise<ChartMetricTreeNodeDto[]> {
  return apiGet<ChartMetricTreeNodeDto[]>("/api/chart/metric-tree");
}

export async function fetchChartVersionOptions(): Promise<ChartVersionOptionsResponseDto> {
  return apiGet<ChartVersionOptionsResponseDto>("/api/chart/version-options");
}

export async function fetchStackedChartData(payload: ChartStackedRequestDto): Promise<ChartStackedResponseDto> {
  return apiPost<ChartStackedResponseDto>("/api/chart/stacked", payload);
}

export async function fetchBarChartData(payload: ChartBarRequestDto): Promise<ChartStackedResponseDto> {
  return apiPost<ChartStackedResponseDto>("/api/chart/bar", payload);
}

export async function exportChartPpt(
  payload: ChartPptExportRequestDto,
): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob("/api/chart/export-ppt", payload);
}
