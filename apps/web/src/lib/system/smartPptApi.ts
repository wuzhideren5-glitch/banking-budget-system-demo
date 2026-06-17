import { apiGet, apiPost, apiPut, downloadFile } from "@/lib/shared/api";
import {
  generateSmartReport,
  listSmartReportTemplateVariables,
  listSmartReportTemplates,
  type SmartReportGenerateRequestDto,
  type SmartReportGenerateResponseDto,
  type SmartReportTemplateDto,
  type SmartReportTemplateVariableDto,
} from "@/lib/system/smartReportApi";

const BASE_PATH = "/api/smart-ppt";

export type SmartPptReportTemplateDto = SmartReportTemplateDto;
export type SmartPptReportTemplateVariableDto = SmartReportTemplateVariableDto;
export type SmartPptReportTemplateGenerateRequestDto = SmartReportGenerateRequestDto;
export type SmartPptReportTemplateGenerateResponseDto = SmartReportGenerateResponseDto;

export type SmartPptSceneDto = {
  scene_id: number;
  scene_code: string;
  scene_name: string;
  scene_type: string;
  description?: string | null;
  slide_template_json: Record<string, unknown>;
  default_params_json: Record<string, unknown>;
  sort_order: number;
  status: string;
  created_at: string;
  updated_at: string;
};

export type SmartPptSlidePreviewDto = {
  slide_index: number;
  slide_type: string;
  title: string;
  subtitle?: string | null;
  chart_type?: string | null;
  chart_title?: string | null;
  narrative?: string | null;
  metric_cards: Array<Record<string, unknown>>;
  table_headers: string[];
  table_rows: string[][];
};

export type SmartPptSceneDetailResponseDto = {
  scene: SmartPptSceneDto;
  slide_previews: SmartPptSlidePreviewDto[];
};

export type SmartPptPreviewRequestDto = {
  scene_id: number;
  params: Record<string, unknown>;
  slide_index?: number | null;
};

export type SmartPptPreviewResponseDto = {
  scene: SmartPptSceneDto;
  slide_previews: SmartPptSlidePreviewDto[];
};

export type SmartPptGenerateRequestDto = {
  scene_id: number;
  instance_name?: string | null;
  params: Record<string, unknown>;
};

export type SmartPptGenerateResponseDto = {
  instance_id: number;
  output_filename: string;
  download_url: string;
  generated_at: string;
  slide_previews: SmartPptSlidePreviewDto[];
  warnings: string[];
};

export type SmartPptInstanceDto = {
  instance_id: number;
  scene_id: number;
  scene_name?: string | null;
  instance_name: string;
  parameter_values: Record<string, unknown>;
  generation_status: string;
  output_file_path?: string | null;
  error_message?: string | null;
  last_generated_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type SmartPptChartConfigDto = {
  config_id: number;
  config_code: string;
  chart_type: string;
  metric_config_json: Record<string, unknown>;
  visual_config_json: Record<string, unknown>;
  remark?: string | null;
  created_at: string;
  updated_at: string;
};

export type SmartPptTemplateObjectDto = {
  object_id: string;
  shape_id?: number | null;
  shape_name?: string | null;
  object_type: string;
  text_excerpt?: string | null;
  chart_type?: string | null;
  row_count?: number | null;
  column_count?: number | null;
  left?: number | null;
  top?: number | null;
  width?: number | null;
  height?: number | null;
};

export type SmartPptTemplateSlideReportDto = {
  slide_index: number;
  title?: string | null;
  object_count: number;
  text_count: number;
  table_count: number;
  chart_count: number;
  picture_count: number;
  group_count: number;
  other_count: number;
  objects: SmartPptTemplateObjectDto[];
};

export type SmartPptTemplateInspectResponseDto = {
  template_file_name: string;
  slide_count: number;
  slide_width: number;
  slide_height: number;
  object_count: number;
  text_count: number;
  table_count: number;
  chart_count: number;
  picture_count: number;
  group_count: number;
  other_count: number;
  slides: SmartPptTemplateSlideReportDto[];
  warnings: string[];
};

export type SmartPptTemplateBindingConfigDto = {
  object_id: string;
  slide_index: number;
  object_type: string;
  binding_type: string;
  target_key?: string | null;
  data_source?: string | null;
  chart_config_code?: string | null;
  metric_code?: string | null;
  org_product_metric_ref?: string | null;
  org_product_metric_name?: string | null;
  org_product_data_acct_code?: string | null;
  prompt?: string | null;
  enabled: boolean;
  notes?: string | null;
};

export type SmartPptTemplateBindingConfigResponseDto = {
  template_file_name: string;
  bindings: SmartPptTemplateBindingConfigDto[];
  updated_at?: string | null;
};

export type SmartPptTemplateChartBlockDto = {
  block_id: string;
  block_name: string;
  section?: string | null;
  slide_index: number;
  chart_object_id: string;
  chart_type?: string | null;
  nearby_title_object_id?: string | null;
  nearby_title?: string | null;
  default_chart_config_code?: string | null;
  binding: SmartPptTemplateBindingConfigDto;
};

export type SmartPptTemplateChartBlockResponseDto = {
  template_file_name: string;
  blocks: SmartPptTemplateChartBlockDto[];
};

export type SmartPptTemplateGenerateRequestDto = {
  template_file_name: string;
  bindings: SmartPptTemplateBindingConfigDto[];
  max_slides: number;
  params: Record<string, unknown>;
};

export type SmartPptTemplateGenerateResponseDto = {
  output_filename: string;
  download_url: string;
  generated_at: string;
  applied_count: number;
  slide_count: number;
  warnings: string[];
};

export type SmartPptTemplateStudioDataDto = {
  report: SmartPptTemplateInspectResponseDto;
  bindings: SmartPptTemplateBindingConfigDto[];
  chart_configs: SmartPptChartConfigDto[];
};

export async function listSmartPptReportTemplates(): Promise<SmartPptReportTemplateDto[]> {
  const rows = await listSmartReportTemplates();
  return rows.filter((item) => item.template_type === "ppt");
}

export function listSmartPptReportTemplateVariables(
  templateId: number,
): Promise<SmartPptReportTemplateVariableDto[]> {
  return listSmartReportTemplateVariables(templateId);
}

export function generateSmartPptFromReportTemplate(
  payload: SmartPptReportTemplateGenerateRequestDto,
): Promise<SmartPptReportTemplateGenerateResponseDto> {
  return generateSmartReport(payload);
}

export function listSmartPptScenes(): Promise<SmartPptSceneDto[]> {
  return apiGet<SmartPptSceneDto[]>(`${BASE_PATH}/scenes`);
}

export function previewSmartPptScene(payload: SmartPptPreviewRequestDto): Promise<SmartPptSceneDetailResponseDto> {
  return apiPost<SmartPptSceneDetailResponseDto>(`${BASE_PATH}/preview`, payload);
}

export function generateSmartPptScene(payload: SmartPptGenerateRequestDto): Promise<SmartPptGenerateResponseDto> {
  return apiPost<SmartPptGenerateResponseDto>(`${BASE_PATH}/generate`, payload);
}

export function listSmartPptInstances(): Promise<SmartPptInstanceDto[]> {
  return apiGet<SmartPptInstanceDto[]>(`${BASE_PATH}/instances`);
}

export function inspectSmartPptTemplate(templateFileName: string): Promise<SmartPptTemplateInspectResponseDto> {
  return apiGet<SmartPptTemplateInspectResponseDto>(
    `${BASE_PATH}/template-studio/inspect?template_file_name=${encodeURIComponent(templateFileName)}`,
  );
}

export function getSmartPptTemplateBindings(
  templateFileName: string,
): Promise<SmartPptTemplateBindingConfigResponseDto> {
  return apiGet<SmartPptTemplateBindingConfigResponseDto>(
    `${BASE_PATH}/template-studio/bindings?template_file_name=${encodeURIComponent(templateFileName)}`,
  );
}

export function listSmartPptChartConfigs(): Promise<SmartPptChartConfigDto[]> {
  return apiGet<SmartPptChartConfigDto[]>(`${BASE_PATH}/chart-configs`);
}

export async function loadSmartPptTemplateStudio(templateFileName: string): Promise<SmartPptTemplateStudioDataDto> {
  const [report, bindingResult, chartConfigs] = await Promise.all([
    inspectSmartPptTemplate(templateFileName),
    getSmartPptTemplateBindings(templateFileName),
    listSmartPptChartConfigs(),
  ]);
  return {
    report,
    bindings: bindingResult.bindings,
    chart_configs: chartConfigs,
  };
}

export function suggestSmartPptTemplateChartBlocks(
  templateFileName: string,
  maxSlides: number,
): Promise<SmartPptTemplateChartBlockResponseDto> {
  return apiGet<SmartPptTemplateChartBlockResponseDto>(
    `${BASE_PATH}/template-studio/chart-blocks?template_file_name=${encodeURIComponent(templateFileName)}&max_slides=${maxSlides}`,
  );
}

export function saveSmartPptTemplateBindings(
  templateFileName: string,
  bindings: SmartPptTemplateBindingConfigDto[],
): Promise<SmartPptTemplateBindingConfigResponseDto> {
  return apiPut<SmartPptTemplateBindingConfigResponseDto>(`${BASE_PATH}/template-studio/bindings`, {
    template_file_name: templateFileName,
    bindings,
  });
}

export function generateSmartPptTemplateDeck(
  payload: SmartPptTemplateGenerateRequestDto,
): Promise<SmartPptTemplateGenerateResponseDto> {
  return apiPost<SmartPptTemplateGenerateResponseDto>(`${BASE_PATH}/template-studio/generate`, payload);
}

export function downloadSmartPptGeneratedFile(downloadUrl: string, fallbackName: string): Promise<void> {
  return downloadFile(downloadUrl, fallbackName);
}
