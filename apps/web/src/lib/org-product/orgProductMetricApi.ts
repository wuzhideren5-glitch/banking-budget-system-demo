import { apiGet, apiPatch, apiPost, apiPostBlob, apiPostForm } from "@/lib/shared/api";

export type OrgProductMetricSnapshotDto = {
  entities: unknown[];
};

export type OrgProductMetricDbSnapshotDto = OrgProductMetricSnapshotDto;

export type MetricTableCatalogItem = {
  id: string;
  entity_scope: string;
  table_name: string;
  status: string;
};

export type MetricTableCatalogResponse = {
  items: MetricTableCatalogItem[];
};

export type BootstrapResponse = {
  entities: unknown[];
};

export type MetricSaveRefreshResponse = {
  ok: boolean;
  updated_at?: string;
};

export type MetricReportImportResponse = {
  ok: boolean;
  inserted?: number;
  updated?: number;
  detail?: string;
  imported_entities?: Array<{ entity_code: string; table_name: string; row_count: number; sheet_name?: string; has_formula_column?: boolean; metrics?: unknown[] }>;
  ignored_sheets?: string[];
  ignored_details?: Array<{ sheet_name: string; reason: string }>;
  formula_convert_errors?: Array<{ sheet_name: string; metric_code: string; error: string; row?: unknown; reason?: string }>;
};

export type MetricTableCatalogItemResponse = {
  id: string;
  entity_scope: string;
  table_name: string;
  status: string;
};

export function getOrgProductMetricSnapshot(): Promise<unknown> {
  return apiGet("/api/org-product-metrics/db-snapshot");
}

export function getOrgProductMetricDbSnapshot(): Promise<unknown> {
  return apiGet("/api/org-product-metrics/db-snapshot");
}

export function getOrgProductMetricBootstrap(): Promise<BootstrapResponse> {
  return apiGet<BootstrapResponse>("/api/org-product-metrics/bootstrap");
}

export function getMetricTableCatalog(): Promise<MetricTableCatalogResponse> {
  return apiGet<MetricTableCatalogResponse>("/api/org-product-metrics/table-catalog");
}

export function saveMetricTable(payload: unknown): Promise<unknown> {
  return apiPost("/api/org-product-metrics/save-table", payload);
}

export function saveRefreshOrgProductMetrics(entities: unknown): Promise<MetricSaveRefreshResponse> {
  return apiPost<MetricSaveRefreshResponse>("/api/org-product-metrics/save-refresh", { entities });
}

export function importMetricReport(formData: FormData): Promise<unknown> {
  return apiPostForm("/api/org-product-metrics/import-report", formData);
}

export function exportMetricReport(sheets: unknown): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob("/api/org-product-metrics/export-report", sheets);
}

export function saveMetricTableCatalog(payload: unknown): Promise<MetricTableCatalogItemResponse> {
  return apiPost<MetricTableCatalogItemResponse>("/api/org-product-metrics/table-catalog", payload);
}

export function deleteMetricTableCatalogItem(itemId: string): Promise<unknown> {
  return apiGet(`/api/org-product-metrics/table-catalog/${itemId}`);
}

export function patchMetricTableCatalogItem(itemId: string | number, payload: unknown): Promise<MetricTableCatalogItemResponse> {
  return apiPatch<MetricTableCatalogItemResponse>(`/api/org-product-metrics/table-catalog/${itemId}`, payload);
}
