import { apiGet, apiPost, apiPostBlob, apiPostForm } from "@/lib/shared/api";

export type DataEntrySnapshotDto = {
  status: string;
  metrics: unknown[];
};

export type DataEntrySaveRefreshResponseDto = {
  ok: boolean;
  updated_at: string;
};

export type BudgetSyncPreviewResponseDto = {
  preview_rows: unknown[];
  message?: string;
};

export type BudgetSyncApplyResponseDto = {
  applied: number;
  message: string;
};

export function getOrgProductDataEntrySnapshot(
  entityCode: string,
  year: string | number,
  versionId?: string | number,
  tableName?: string,
): Promise<unknown> {
  let path = `/api/org-product-data-entry/db-snapshot?entity_code=${encodeURIComponent(entityCode)}&year=${encodeURIComponent(String(year))}`;
  if (versionId !== undefined) path += `&version_id=${encodeURIComponent(String(versionId))}`;
  if (tableName) path += `&table_name=${encodeURIComponent(tableName)}`;
  return apiGet(path);
}

export function saveRefreshOrgProductDataEntry(payload: unknown): Promise<DataEntrySaveRefreshResponseDto> {
  return apiPost<DataEntrySaveRefreshResponseDto>("/api/org-product-data-entry/save-refresh", payload);
}

export function exportOrgProductDataEntry(payload: unknown): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob("/api/org-product-data-entry/export", payload);
}

export type DataEntryBatchExportItem = {
  entity_code: string;
  entity_name?: string;
  table_name: string;
};

export type DataEntryBatchExportRequest = {
  year: number;
  month_index: number;
  items: DataEntryBatchExportItem[];
  include_saved_values?: boolean;
  version_id?: number;
  version_name?: string;
};

export function exportOrgProductDataEntryBatch(
  payload: DataEntryBatchExportRequest,
): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob("/api/org-product-data-entry/export-batch", payload);
}

export type DataEntryImportWorkbookApplyResponse = {
  saved: Array<{
    sheet_name: string;
    entity_code: string;
    entity_name: string;
    table_name: string;
    row_count: number;
    updated_at: string;
  }>;
  unmatched: Array<{
    sheet_name: string;
    entity_code?: string;
    table_name?: string;
    row_count?: number;
    reason?: string;
  }>;
  saved_count: number;
  unmatched_count: number;
  sheet_count: number;
};

export function applyDataEntryWorkbookImport(
  year: string | number,
  month: string | number,
  formData: FormData,
  extraParams?: Record<string, string | number>,
): Promise<DataEntryImportWorkbookApplyResponse> {
  let url = `/api/org-product-data-entry/import-workbook-apply?year=${encodeURIComponent(String(year))}&month=${encodeURIComponent(String(month))}`;
  if (extraParams) {
    for (const [key, value] of Object.entries(extraParams)) {
      url += `&${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`;
    }
  }
  return apiPostForm(url, formData);
}

export function previewDataEntryBudgetSync(payload: unknown): Promise<BudgetSyncPreviewResponseDto> {
  return apiPost<BudgetSyncPreviewResponseDto>("/api/org-product-data-entry/budget-sync/preview", payload);
}

export function applyDataEntryBudgetSync(payload: unknown): Promise<BudgetSyncApplyResponseDto> {
  return apiPost<BudgetSyncApplyResponseDto>("/api/org-product-data-entry/budget-sync/apply", payload);
}

export function getDataEntryVersions(
  entityCode: string,
  year: string | number,
  extraParams?: Record<string, string | number>,
): Promise<unknown> {
  let path = `/api/org-product-data-entry/versions?entity_code=${encodeURIComponent(entityCode)}&year=${encodeURIComponent(String(year))}`;
  if (extraParams) {
    for (const [key, value] of Object.entries(extraParams)) {
      path += `&${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`;
    }
  }
  return apiGet(path);
}

export function importDataEntryWorkbook(
  year: string | number,
  month: string | number,
  formData: FormData,
): Promise<unknown> {
  const url = `/api/org-product-data-entry/import-workbook?year=${encodeURIComponent(String(year))}&month=${encodeURIComponent(String(month))}`;
  return apiPostForm(url, formData);
}
