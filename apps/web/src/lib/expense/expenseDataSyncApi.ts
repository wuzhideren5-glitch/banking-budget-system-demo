import { apiGet, apiPostForm } from "@/lib/shared/api";

const EXPENSE_EXECUTION_BASE_PATH = "/api/expense-budget-execution";

export type ExpenseBudgetExecutionStatusDto = {
  framework_import?: ExpenseSyncMetaDto | null;
  master_apply?: ExpenseSyncMetaDto | null;
  counts: Record<string, number>;
};

export type ExpenseSyncMetaDto = {
  source_file: string;
  source_mtime: string | null;
  synced_at: string;
  row_count: number;
  note: string | null;
};

export type ExpenseFrameworkPreviewDto = {
  source_file: string;
  framework: {
    group_count: number;
    owner_count: number;
    budget_department_count: number;
    product_department_count: number;
    subject_count: number;
  };
  master_preview: {
    dept_rows: number;
    matched_subjects: number;
    new_subjects: number;
    unmatched_existing_subjects: number;
    sample_new_subjects: string[];
    sample_unmatched_existing_subjects: string[];
  };
};

export type ExpenseFrameworkSyncResultDto = {
  source_file: string;
  framework_rows: {
    budget_departments: number;
    product_departments: number;
    subjects: number;
  };
  master_applied: boolean;
  master_apply?: {
    backup_file: string;
    dept_rows: number;
    matched_metric_subjects: number;
    matched_subjects: number;
    new_subjects: number;
    unmatched_existing_subjects: number;
    sample_new_subjects: string[];
    sample_unmatched_existing_subjects: string[];
  };
};

function formDataWithFile(file: File): FormData {
  const formData = new FormData();
  formData.append("file", file);
  return formData;
}

export function getExpenseBudgetExecutionStatus(): Promise<ExpenseBudgetExecutionStatusDto> {
  return apiGet<ExpenseBudgetExecutionStatusDto>(`${EXPENSE_EXECUTION_BASE_PATH}/status`);
}

export function previewExpenseFramework(file: File): Promise<ExpenseFrameworkPreviewDto> {
  return apiPostForm<ExpenseFrameworkPreviewDto>(
    `${EXPENSE_EXECUTION_BASE_PATH}/admin/framework-preview`,
    formDataWithFile(file),
  );
}

export function syncExpenseFramework(
  file: File,
  applyToMasterData = true,
): Promise<ExpenseFrameworkSyncResultDto> {
  const formData = formDataWithFile(file);
  formData.append("apply_to_master_data", String(applyToMasterData));
  return apiPostForm<ExpenseFrameworkSyncResultDto>(
    `${EXPENSE_EXECUTION_BASE_PATH}/admin/framework-sync`,
    formData,
  );
}
