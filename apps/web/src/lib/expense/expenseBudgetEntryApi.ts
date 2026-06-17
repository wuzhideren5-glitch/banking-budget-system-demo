import { apiDelete, apiGet, apiPatch, buildApiUrl, readErrorMessage } from "@/lib/shared/api";
import type { ExpenseBudgetAmountUnit } from "@/lib/expense/expenseBudgetEntryUnits";

export type ExpenseBudgetEntryPreviewRowDto = {
  owner_name_raw: string;
  owner_name_mapped: string | null;
  budget_subject_raw: string;
  budget_subject_mapped: string | null;
  amount: number;
  match_status: string;
  match_note: string | null;
};

export type ExpenseBudgetEntryPreviewResponseDto = {
  file_name: string;
  budget_year: number;
  amount_unit: string;
  row_count: number;
  matched_rows: number;
  unmatched_rows: number;
  preview_rows: ExpenseBudgetEntryPreviewRowDto[];
  unmatched_preview_rows: ExpenseBudgetEntryPreviewRowDto[];
};

export type ExpenseBudgetEntryApplyResponseDto = {
  batch_id: number;
  budget_year: number;
  file_name: string;
  import_mode: string;
  amount_unit: string;
  row_count: number;
  matched_rows: number;
  unmatched_rows: number;
  note: string | null;
};

export type ExpenseBudgetEntryBatchRowDto = {
  id: number;
  budget_year: number;
  file_name: string;
  import_mode: string;
  total_rows: number;
  matched_rows: number;
  unmatched_rows: number;
  created_at: string;
  note: string | null;
};

export type ExpenseBudgetEntryRowDto = {
  id: number;
  batch_id: number;
  budget_year: number;
  owner_name_raw: string;
  owner_name_mapped: string | null;
  budget_subject_raw: string;
  budget_subject_mapped: string | null;
  amount: number;
  adjustment_amount: number;
  adjusted_amount: number;
  match_status: string;
  match_note: string | null;
};

export type ExpenseBudgetEntryUpdatePayload = {
  amount?: number;
  adjustment_amount?: number;
};

function normalizeExpenseBudgetEntryRow(row: ExpenseBudgetEntryRowDto): ExpenseBudgetEntryRowDto {
  const amount = Number(row.amount ?? 0);
  const adjustmentAmount = Number(row.adjustment_amount ?? 0);
  const adjustedAmount = Number.isFinite(row.adjusted_amount)
    ? Number(row.adjusted_amount)
    : amount + adjustmentAmount;
  return {
    ...row,
    amount,
    adjustment_amount: adjustmentAmount,
    adjusted_amount: Math.round(adjustedAmount * 100) / 100,
  };
}

async function postFormJson<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!response.ok) throw new Error(await readErrorMessage(response));
  return response.json() as Promise<T>;
}

export async function downloadExpenseBudgetEntryTemplate(): Promise<void> {
  const response = await fetch(buildApiUrl("/api/expense-budget-entry/template"), {
    credentials: "include",
  });
  if (!response.ok) throw new Error(await readErrorMessage(response));
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const utf8Name = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const asciiName = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const filename = utf8Name ? decodeURIComponent(utf8Name) : asciiName || "预算录入模板.xlsx";
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function listExpenseBudgetEntryBatches(
  budgetYear: number,
): Promise<ExpenseBudgetEntryBatchRowDto[]> {
  return apiGet<ExpenseBudgetEntryBatchRowDto[]>(`/api/expense-budget-entry/batches?budget_year=${budgetYear}`);
}

export function listExpenseBudgetEntryRows(
  budgetYear: number,
  batchId?: number,
): Promise<ExpenseBudgetEntryRowDto[]> {
  const suffix = batchId ? `&batch_id=${batchId}` : "";
  return apiGet<ExpenseBudgetEntryRowDto[]>(`/api/expense-budget-entry/rows?budget_year=${budgetYear}${suffix}`).then(
    (rows) => rows.map(normalizeExpenseBudgetEntryRow),
  );
}

export function previewExpenseBudgetEntry(
  file: File,
  budgetYear: number,
  amountUnit: ExpenseBudgetAmountUnit,
): Promise<ExpenseBudgetEntryPreviewResponseDto> {
  const form = new FormData();
  form.append("file", file);
  form.append("amount_unit", amountUnit);
  return postFormJson<ExpenseBudgetEntryPreviewResponseDto>(
    `/api/expense-budget-entry/import-preview?budget_year=${encodeURIComponent(String(budgetYear))}&amount_unit=${encodeURIComponent(amountUnit)}`,
    form,
  );
}

export function applyExpenseBudgetEntry(
  file: File,
  budgetYear: number,
  mode: "append" | "overwrite",
  amountUnit: ExpenseBudgetAmountUnit,
): Promise<ExpenseBudgetEntryApplyResponseDto> {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", mode);
  form.append("amount_unit", amountUnit);
  return postFormJson<ExpenseBudgetEntryApplyResponseDto>(
    `/api/expense-budget-entry/import-apply?budget_year=${encodeURIComponent(String(budgetYear))}&mode=${encodeURIComponent(mode)}&amount_unit=${encodeURIComponent(amountUnit)}`,
    form,
  );
}

export async function exportExpenseBudgetEntryPreview(
  file: File,
  budgetYear: number,
  amountUnit: ExpenseBudgetAmountUnit,
): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  form.append("amount_unit", amountUnit);
  const response = await fetch(
    buildApiUrl(
      `/api/expense-budget-entry/import-export?budget_year=${encodeURIComponent(String(budgetYear))}&amount_unit=${encodeURIComponent(amountUnit)}`,
    ),
    {
      method: "POST",
      credentials: "include",
      body: form,
    },
  );
  if (!response.ok) throw new Error(await readErrorMessage(response));
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const utf8Name = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const asciiName = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const filename = utf8Name ? decodeURIComponent(utf8Name) : asciiName || "预算录入_匹配结果.xlsx";
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function deleteExpenseBudgetEntryBatch(batchId: number): Promise<void> {
  return apiDelete(`/api/expense-budget-entry/batches/${batchId}`);
}

export function updateExpenseBudgetEntryRow(
  rowId: number,
  payload: ExpenseBudgetEntryUpdatePayload,
): Promise<ExpenseBudgetEntryRowDto> {
  return apiPatch<ExpenseBudgetEntryRowDto>(`/api/expense-budget-entry/rows/${rowId}`, payload).then(
    normalizeExpenseBudgetEntryRow,
  );
}
