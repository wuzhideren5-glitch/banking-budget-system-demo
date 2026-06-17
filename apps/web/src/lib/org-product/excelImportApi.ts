import { buildApiUrl, downloadBlob, readDownloadFilename, readErrorMessage } from "@/lib/shared/api";

export type ExcelImportMode = "upsert" | "replace";

export type ExcelImportPreviewResponseDto = {
  columns: string[];
  preview_rows: Record<string, string>[];
  row_count: number;
};

export type ExcelImportApplyRequest = {
  file: File;
  mode: ExcelImportMode;
  mappings: Record<string, string>;
};

export type ExcelImportApplyResult =
  | {
      kind: "json_summary";
      total: number;
      inserted: number;
      updated: number;
      summary: string;
    }
  | {
      kind: "excel_result";
      total: number;
      success: number;
      overwrite: number;
      failed: number;
      fileName: string;
      summary: string;
    };

export type ExcelImportWorkflow = {
  downloadTemplate: () => Promise<void>;
  preview: (file: File) => Promise<ExcelImportPreviewResponseDto>;
  apply: (request: ExcelImportApplyRequest) => Promise<ExcelImportApplyResult>;
};

type ExcelImportWorkflowConfig = {
  templateName: string;
  previewPath: string;
  applyPath: string;
};

type JsonImportResultDto = {
  ok?: boolean;
  inserted?: number;
  updated?: number;
  total?: number;
  detail?: string;
};

function buildFormData(file: File, request?: Pick<ExcelImportApplyRequest, "mode" | "mappings">): FormData {
  const form = new FormData();
  form.append("file", file);
  if (request) {
    form.append("mode", request.mode);
    form.append("mappings_json", JSON.stringify(request.mappings));
  }
  return form;
}

function readHeaderInt(response: Response, name: string): number {
  return parseInt(response.headers.get(name) || "", 10) || 0;
}

async function downloadTemplate(templateName: string): Promise<void> {
  const response = await fetch(buildApiUrl(`/api/templates/${encodeURIComponent(templateName)}`), {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  const fileName = readDownloadFilename(response, `${templateName}.xlsx`);
  downloadBlob(await response.blob(), fileName);
}

async function previewExcelImport(path: string, file: File): Promise<ExcelImportPreviewResponseDto> {
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    body: buildFormData(file),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return response.json() as Promise<ExcelImportPreviewResponseDto>;
}

async function applyExcelImport(path: string, request: ExcelImportApplyRequest): Promise<ExcelImportApplyResult> {
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    body: buildFormData(request.file, request),
  });

  const totalHeader = response.headers.get("X-Import-Total");
  if (totalHeader) {
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    const total = readHeaderInt(response, "X-Import-Total");
    const success = readHeaderInt(response, "X-Import-Success");
    const overwrite = readHeaderInt(response, "X-Import-Overwrite");
    const failed = readHeaderInt(response, "X-Import-Failed");
    const fileName = readDownloadFilename(response, "import_result.xlsx");
    downloadBlob(await response.blob(), fileName);
    return {
      kind: "excel_result",
      total,
      success,
      overwrite,
      failed,
      fileName,
      summary: `导入完成：共 ${total} 条，成功 ${success} 条，覆盖 ${overwrite} 条，失败 ${failed} 条。结果文件已下载：${fileName}`,
    };
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  const result = (await response.json()) as JsonImportResultDto;
  if (!result.ok) {
    throw new Error(result.detail || "导入失败");
  }
  const inserted = result.inserted ?? 0;
  const updated = result.updated ?? 0;
  const total = result.total ?? 0;
  return {
    kind: "json_summary",
    total,
    inserted,
    updated,
    summary: `导入完成：共 ${total} 条，新增 ${inserted} 条，更新 ${updated} 条。`,
  };
}

export function createExcelImportWorkflow(config: ExcelImportWorkflowConfig): ExcelImportWorkflow {
  return {
    downloadTemplate: () => downloadTemplate(config.templateName),
    preview: (file) => previewExcelImport(config.previewPath, file),
    apply: (request) => applyExcelImport(config.applyPath, request),
  };
}
