import { apiGet, apiPost, apiPostBlob } from "@/lib/shared/api";

export type OutputRunResponseDto = {
  ok: boolean;
  message?: string;
};

export function getOrgProductOutputSnapshot(
  entityCode: string,
  year: string | number,
  extraParams?: Record<string, string | number>,
): Promise<unknown> {
  let path = `/api/org-product-output/db-snapshot?entity_code=${encodeURIComponent(entityCode)}&year=${encodeURIComponent(String(year))}`;
  if (extraParams) {
    for (const [key, value] of Object.entries(extraParams)) {
      path += `&${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`;
    }
  }
  return apiGet(path);
}

export function getOutputVersions(
  entityCode: string,
  year: string | number,
  extraParams?: Record<string, string | number>,
): Promise<unknown> {
  let path = `/api/org-product-output/versions?entity_code=${encodeURIComponent(entityCode)}&year=${encodeURIComponent(String(year))}`;
  if (extraParams) {
    for (const [key, value] of Object.entries(extraParams)) {
      path += `&${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`;
    }
  }
  return apiGet(path);
}

export function runOrgProductOutput(payload: unknown): Promise<OutputRunResponseDto> {
  return apiPost<OutputRunResponseDto>("/api/org-product-output/run", payload);
}

export function exportOrgProductOutput(payload: unknown): Promise<{ blob: Blob; filename: string | null }> {
  return apiPostBlob("/api/org-product-output/export", payload);
}

export function commitOrgProductOutput(payload: unknown): Promise<unknown> {
  return apiPost("/api/org-product-output/commit", payload);
}
