import { apiDelete, apiGet, apiPostForm, downloadFile } from "@/lib/shared/api";

export type ExpenseActualImportKind = "current_year_actual" | "prior_year_actual";

export type ExpenseActualImportPreviewRowDto = {
  data_date: string;
  period_ym: string;
  org_code: string;
  org_name: string;
  dep_code: string;
  dep_name: string;
  subject_code: string;
  subject_name: string;
  journal_name: string;
  serial_no: string;
  line_desc: string;
  fee_type_code: string;
  fee_type_name: string;
  bi_ai_source_code: string;
  bi_ai_source_name: string;
  manage_department_code: string;
  owner_name_raw: string;
  monthly_caliber: string;
  owner_name_mapped: string | null;
  budget_subject_raw: string;
  budget_subject_mapped: string | null;
  fee_major_mapped: string;
  fee_category_mapped: string;
  budget_release_caliber_mapped: string;
  manage_department2: string;
  special_control_tag: string;
  amount: number;
  match_status: string;
  match_note: string | null;
};

export type ExpenseActualImportManageDepartmentWarningDto = {
  period_ym: string;
  owner_name_raw: string;
  budget_subject_mapped: string;
  budget_release_caliber_mapped: string;
  import_manage_department: string;
  mapping_manage_department: string;
  message: string;
};

export type ExpenseActualImportPreviewResponseDto = {
  file_name: string;
  row_count: number;
  periods: string[];
  matched_owner_rows: number;
  matched_subject_rows: number;
  unmatched_rows: number;
  preview_rows: ExpenseActualImportPreviewRowDto[];
  unmatched_preview_rows: ExpenseActualImportPreviewRowDto[];
  manage_department_warnings: ExpenseActualImportManageDepartmentWarningDto[];
};

export type ExpenseActualImportApplyResponseDto = {
  batch_id: number;
  import_kind: ExpenseActualImportKind;
  file_name: string;
  import_mode: string;
  row_count: number;
  periods: string[];
  matched_owner_rows: number;
  matched_subject_rows: number;
  unmatched_rows: number;
  note: string | null;
  manage_department_warnings: ExpenseActualImportManageDepartmentWarningDto[];
};

export type ExpenseActualImportBatchRowDto = {
  id: number;
  import_kind: ExpenseActualImportKind;
  file_name: string;
  import_mode: string;
  periods: string[];
  total_rows: number;
  matched_owner_rows: number;
  matched_subject_rows: number;
  unmatched_rows: number;
  created_at: string;
  note: string | null;
};

export function listExpenseActualImportBatches(
  importKind: ExpenseActualImportKind = "current_year_actual",
): Promise<ExpenseActualImportBatchRowDto[]> {
  return apiGet<ExpenseActualImportBatchRowDto[]>(`/api/expense-actual-import/batches?import_kind=${importKind}`);
}

export function previewExpenseActualImport(
  file: File,
  importKind: ExpenseActualImportKind = "current_year_actual",
): Promise<ExpenseActualImportPreviewResponseDto> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ExpenseActualImportPreviewResponseDto>(
    `/api/expense-actual-import/import-preview?import_kind=${importKind}`,
    form,
  );
}

export function applyExpenseActualImport(
  file: File,
  mode: "append" | "overwrite",
  importKind: ExpenseActualImportKind = "current_year_actual",
): Promise<ExpenseActualImportApplyResponseDto> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ExpenseActualImportApplyResponseDto>(
    `/api/expense-actual-import/import-apply?mode=${mode}&import_kind=${importKind}`,
    form,
  );
}

export async function exportExpenseActualImportBatch(batchId: number): Promise<void> {
  return downloadFile(`/api/expense-actual-import/export?batch_id=${batchId}`, "费用执行明细匹配结果.xlsx");
}

export function deleteExpenseActualImportBatch(batchId: number): Promise<void> {
  return apiDelete(`/api/expense-actual-import/batches/${batchId}`);
}
