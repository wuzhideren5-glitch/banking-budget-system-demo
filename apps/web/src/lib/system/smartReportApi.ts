import { apiGet, apiPost, apiPostForm, apiPut, downloadFile } from "@/lib/shared/api";

const BASE_PATH = "/api/smart-reports";

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

export type SmartReportAIBlockDto = {
  block_id: string;
  block_type: string;
  text: string;
  metrics: Record<string, unknown>[];
  analysis_rule_nl?: string | null;
  structured_plan: Record<string, unknown>;
  confidence: number;
};

export type SmartReportAIInspectionIssueDto = {
  issue_type: string;
  text: string;
  suggested_action: string;
  candidates: Record<string, unknown>[];
  rule_preview?: string | null;
};

export type SmartReportAIInspectionResponseDto = {
  filename: string;
  model: string;
  summary: string;
  blocks: SmartReportAIBlockDto[];
  issues: SmartReportAIInspectionIssueDto[];
  assumptions: string[];
  raw_text_excerpt: string;
  warnings: string[];
};

export type SmartReportBlueprintDto = {
  blueprint_id: number;
  blueprint_name: string;
  source_filename: string;
  status: string;
  issue_count: number;
  block_count: number;
  output_file_path?: string | null;
  last_generated_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type SmartReportBlueprintDetailDto = SmartReportBlueprintDto & {
  inspection: SmartReportAIInspectionResponseDto;
};

export type SmartReportBlueprintSaveRequestDto = {
  blueprint_name: string;
  inspection: SmartReportAIInspectionResponseDto;
};

export type SmartReportBlueprintPreviewResponseDto = {
  blueprint_id: number;
  preview_text: string;
  issue_count: number;
  warnings: string[];
};

export type SmartReportBlueprintGenerateResponseDto = {
  blueprint_id: number;
  output_filename: string;
  download_url: string;
  generated_at: string;
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
  metric_code?: string | null;
  metric_name?: string | null;
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

export type SmartReportTemplateUploadInputDto = {
  file: File;
  template_code: string;
  template_name: string;
  template_type: string;
};

export function listSmartReportTemplates(): Promise<SmartReportTemplateDto[]> {
  return apiGet<SmartReportTemplateDto[]>(`${BASE_PATH}/templates`);
}

export function listSmartReportInstances(): Promise<SmartReportInstanceDto[]> {
  return apiGet<SmartReportInstanceDto[]>(`${BASE_PATH}/instances`);
}

export function listSmartReportCalcMetrics(): Promise<SmartReportCalcMetricDto[]> {
  return apiGet<SmartReportCalcMetricDto[]>(`${BASE_PATH}/calc-metrics`);
}

export function listSmartReportTemplateVariables(templateId: number): Promise<SmartReportTemplateVariableDto[]> {
  return apiGet<SmartReportTemplateVariableDto[]>(`${BASE_PATH}/templates/${templateId}/variables`);
}

export function uploadSmartReportTemplate(
  input: SmartReportTemplateUploadInputDto,
): Promise<SmartReportTemplateCreateResponseDto> {
  const form = new FormData();
  form.append("file", input.file);
  form.append("template_code", input.template_code);
  form.append("template_name", input.template_name);
  form.append("template_type", input.template_type);
  return apiPostForm<SmartReportTemplateCreateResponseDto>(`${BASE_PATH}/templates`, form);
}

export function inspectSmartReportWithAI(file: File): Promise<SmartReportAIInspectionResponseDto> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<SmartReportAIInspectionResponseDto>(`${BASE_PATH}/ai/inspect`, form);
}

export function saveSmartReportBlueprint(
  payload: SmartReportBlueprintSaveRequestDto,
): Promise<SmartReportBlueprintDetailDto> {
  return apiPost<SmartReportBlueprintDetailDto>(`${BASE_PATH}/blueprints`, payload);
}

export function previewSmartReportBlueprint(blueprintId: number): Promise<SmartReportBlueprintPreviewResponseDto> {
  return apiPost<SmartReportBlueprintPreviewResponseDto>(`${BASE_PATH}/blueprints/${blueprintId}/preview`, {});
}

export function generateSmartReportBlueprint(blueprintId: number): Promise<SmartReportBlueprintGenerateResponseDto> {
  return apiPost<SmartReportBlueprintGenerateResponseDto>(`${BASE_PATH}/blueprints/${blueprintId}/generate`, {});
}

export function createSmartReportTextTemplate(
  payload: SmartReportTextTemplateCreateDto,
): Promise<SmartReportTemplateCreateResponseDto> {
  return apiPost<SmartReportTemplateCreateResponseDto>(`${BASE_PATH}/templates/text`, payload);
}

export function upsertSmartReportCalcMetric(
  metricCode: string,
  payload: SmartReportCalcMetricUpsertDto,
): Promise<SmartReportCalcMetricDto> {
  return apiPut<SmartReportCalcMetricDto>(`${BASE_PATH}/calc-metrics/${encodeURIComponent(metricCode)}`, payload);
}

export function previewSmartReport(payload: SmartReportPreviewRequestDto): Promise<SmartReportPreviewResponseDto> {
  return apiPost<SmartReportPreviewResponseDto>(`${BASE_PATH}/preview`, payload);
}

export function generateSmartReport(payload: SmartReportGenerateRequestDto): Promise<SmartReportGenerateResponseDto> {
  return apiPost<SmartReportGenerateResponseDto>(`${BASE_PATH}/generate`, payload);
}

export function refreshSmartReportInstance(instanceId: number): Promise<SmartReportGenerateResponseDto> {
  return apiPost<SmartReportGenerateResponseDto>(`${BASE_PATH}/instances/${instanceId}/refresh`, {});
}

export function downloadSmartReportGeneratedFile(downloadUrl: string, fallbackName: string): Promise<void> {
  return downloadFile(downloadUrl, fallbackName);
}

export function downloadSmartReportInstance(instance: SmartReportInstanceDto): Promise<void> {
  return downloadFile(`${BASE_PATH}/instances/${instance.instance_id}/download`, `${instance.instance_name}.docx`);
}
