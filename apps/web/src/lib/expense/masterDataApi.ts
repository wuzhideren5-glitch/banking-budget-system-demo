import { apiDelete, apiGet, apiPatch, apiPost, downloadFile } from "@/lib/shared/api";
import { createExcelImportWorkflow } from "@/lib/org-product/excelImportApi";

export type OrgProductRuntimeProductDto = {
  product_code: string;
  product_name: string;
  remark: string | null;
  parent_code: string | null;
  level: number;
};

export type DeptAccountDto = {
  dept_code: string;
  dept_name: string;
  entity_name: string;
  parent_code: string | null;
  level: number;
  is_leaf: boolean;
};

export type DeptAccountWriteDto = {
  dept_code?: string;
  dept_name: string;
  entity_name?: string;
  parent_code?: string | null;
  level?: number;
  is_leaf?: boolean;
};

export type BudgetSubjectCatalogDto = {
  id: number;
  parent_id: number | null;
  level_number: number;
  level_label: string;
  subject_name: string;
  manage_department: string | null;
  formula_text: string | null;
  sort_order: number;
  is_leaf: boolean;
};

export type BudgetSubjectCatalogWriteDto = {
  parent_id?: number | null;
  subject_name: string;
  manage_department?: string | null;
  formula_text?: string | null;
};

export const deptAccountImportWorkflow = createExcelImportWorkflow({
  templateName: "dept_acct_temp",
  previewPath: "/api/dept-accounts/import-preview",
  applyPath: "/api/dept-accounts/import-apply",
});

export function listOrgProductRuntimeProducts(): Promise<OrgProductRuntimeProductDto[]> {
  return apiGet<OrgProductRuntimeProductDto[]>("/api/org-product-runtime-products");
}

export function listDeptAccounts(): Promise<DeptAccountDto[]> {
  return apiGet<DeptAccountDto[]>("/api/dept-accounts");
}

export function createDeptAccount(body: DeptAccountWriteDto): Promise<DeptAccountDto> {
  return apiPost<DeptAccountDto>("/api/dept-accounts", body);
}

export function updateDeptAccount(code: string, body: DeptAccountWriteDto): Promise<DeptAccountDto> {
  return apiPatch<DeptAccountDto>(`/api/dept-accounts/${encodeURIComponent(code)}`, body);
}

export function deleteDeptAccount(code: string): Promise<void> {
  return apiDelete(`/api/dept-accounts/${encodeURIComponent(code)}`);
}

export function exportDeptTree(): Promise<void> {
  return downloadFile("/api/dept-tree/export", "dept_tree_export.xlsx");
}

export function listBudgetSubjectCatalog(): Promise<BudgetSubjectCatalogDto[]> {
  return apiGet<BudgetSubjectCatalogDto[]>("/api/budget-subject-catalog");
}

export function createBudgetSubjectCatalog(
  body: BudgetSubjectCatalogWriteDto,
): Promise<BudgetSubjectCatalogDto> {
  return apiPost<BudgetSubjectCatalogDto>("/api/budget-subject-catalog", body);
}

export function updateBudgetSubjectCatalog(
  id: number,
  body: BudgetSubjectCatalogWriteDto,
): Promise<BudgetSubjectCatalogDto> {
  return apiPatch<BudgetSubjectCatalogDto>(`/api/budget-subject-catalog/${id}`, body);
}

export function deleteBudgetSubjectCatalog(id: number): Promise<void> {
  return apiDelete(`/api/budget-subject-catalog/${id}`);
}

export function exportBudgetSubjectCatalog(): Promise<void> {
  return downloadFile("/api/budget-subject-catalog/export", "budget_subject_catalog.xlsx");
}
