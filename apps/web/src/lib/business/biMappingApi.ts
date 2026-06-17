import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/shared/api";

export type ManageDeptOwnerMappingDto = {
  id: number;
  manage_department: string;
  owner_department: string;
};

export type ManageDeptOwnerReferenceDataDto = {
  manage_departments: string[];
  owner_departments: string[];
  owner_dept_groups: { group_name: string; departments: string[] }[];
};

export type ManageDeptOwnerMappingWriteDto = {
  manage_department: string;
  owner_department: string;
};

export type AutoGenerateResultDto = {
  generated: number;
  skipped: number;
};

export type BiAiSubjectMappingDto = {
  id: number;
  level5_code: string;
  level5_name: string;
  level6_code: string;
  level6_name: string;
  budget_release_caliber: string;
  fee_category: string;
  fee_major: string;
  manage_department: string;
  manage_departments: string[];
  manage_department_source: "override" | "auto" | "default_all";
  manage_department_override: string[] | null;
  manage_department_is_default_all: boolean;
  sort_order: number;
  source_file: string;
};

export type BiAiSubjectMappingCreateDto = {
  level5_code: string;
  level5_name: string;
  level6_code: string;
  level6_name: string;
  budget_release_caliber: string;
  fee_category: string;
  fee_major: string;
  manage_departments: string[] | null;
};

export type BiAiSubjectMappingReferenceDataDto = {
  expense_departments: string[];
};

export function listManageDeptOwnerMappings(): Promise<ManageDeptOwnerMappingDto[]> {
  return apiGet<ManageDeptOwnerMappingDto[]>("/api/manage-dept-owner-mapping/list");
}

export function createManageDeptOwnerMapping(
  body: ManageDeptOwnerMappingWriteDto,
): Promise<ManageDeptOwnerMappingDto> {
  return apiPost<ManageDeptOwnerMappingDto>("/api/manage-dept-owner-mapping/create", body);
}

export function updateManageDeptOwnerMapping(
  id: number,
  body: Pick<ManageDeptOwnerMappingWriteDto, "owner_department">,
): Promise<{ id: number; owner_department: string }> {
  return apiPut(`/api/manage-dept-owner-mapping/update/${id}`, body);
}

export function deleteManageDeptOwnerMapping(id: number): Promise<void> {
  return apiDelete(`/api/manage-dept-owner-mapping/delete/${id}`);
}

export function autoGenerateManageDeptOwnerMappings(): Promise<AutoGenerateResultDto> {
  return apiPost<AutoGenerateResultDto>("/api/manage-dept-owner-mapping/auto-generate", {});
}

export function getManageDeptOwnerReferenceData(): Promise<ManageDeptOwnerReferenceDataDto> {
  return apiGet<ManageDeptOwnerReferenceDataDto>("/api/manage-dept-owner-mapping/reference-data");
}

export function listBiAiSubjectMappings(): Promise<BiAiSubjectMappingDto[]> {
  return apiGet<BiAiSubjectMappingDto[]>("/api/bi-ai-subject-mapping/list");
}

export function getBiAiSubjectMappingReferenceData(): Promise<BiAiSubjectMappingReferenceDataDto> {
  return apiGet<BiAiSubjectMappingReferenceDataDto>("/api/bi-ai-subject-mapping/reference-data");
}

export function createBiAiSubjectMapping(body: BiAiSubjectMappingCreateDto): Promise<BiAiSubjectMappingDto> {
  return apiPost<BiAiSubjectMappingDto>("/api/bi-ai-subject-mapping/create", body);
}

export function updateBiAiSubjectMappingManageDepartments(
  id: number,
  manageDepartments: string[] | null,
): Promise<BiAiSubjectMappingDto> {
  return apiPut<BiAiSubjectMappingDto>(`/api/bi-ai-subject-mapping/update/${id}/manage-departments`, {
    manage_departments: manageDepartments,
  });
}

export function reloadBiAiSubjectMappings(): Promise<{ row_count: number; source_file: string }> {
  return apiPost<{ row_count: number; source_file: string }>("/api/bi-ai-subject-mapping/reload", {});
}
