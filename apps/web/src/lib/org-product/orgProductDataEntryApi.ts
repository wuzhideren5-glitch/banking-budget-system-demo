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
