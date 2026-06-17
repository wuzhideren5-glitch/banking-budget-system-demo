import { apiGet, apiPost, apiPostBlob, apiPostForm } from "@/lib/shared/api";

export type OrgProductTreeSnapshotDto = {
  found: boolean;
  tree?: unknown;
};

export type OrgProductTreeImportResponseDto = {
  tree: unknown;
};

export type OrgProductTreeSaveRefreshResponseDto = {
  ok: boolean;
  updated_at: string;
};

export function getOrgProductTreeSnapshot(): Promise<OrgProductTreeSnapshotDto> {
  return apiGet<OrgProductTreeSnapshotDto>("/api/org-product-tree/db-snapshot");
}

export function importOrgProductTreeExcel(formData: FormData): Promise<OrgProductTreeImportResponseDto> {
  return apiPostForm<OrgProductTreeImportResponseDto>("/api/org-product-tree/import-excel", formData);
}

export function exportOrgProductTreeExcel(tree: unknown): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob("/api/org-product-tree/export-excel", { tree });
}

export function saveRefreshOrgProductTree(tree: unknown): Promise<OrgProductTreeSaveRefreshResponseDto> {
  return apiPost<OrgProductTreeSaveRefreshResponseDto>("/api/org-product-tree/save-refresh", { tree });
}
