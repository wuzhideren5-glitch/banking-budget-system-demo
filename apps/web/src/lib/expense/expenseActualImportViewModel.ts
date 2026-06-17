import type { ExpenseActualImportKind, ExpenseActualImportPreviewRowDto } from "@/lib/expense/expenseActualImportApi";

export const expenseActualImportKindOptions: { key: ExpenseActualImportKind; label: string; description: string }[] = [
  { key: "current_year_actual", label: "本年实际导入", description: "导入预算系统中的部门费用执行实际明细，供费用预算执行报表和费用统计表取数。" },
  { key: "prior_year_actual", label: "上年实际导入", description: "按相同格式导入上年实际明细，供去年同期口径使用。" },
];

export function expenseActualImportKindLabel(key: string): string {
  return expenseActualImportKindOptions.find((option) => option.key === key)?.label ?? "本年实际导入";
}

type PreviewColumnKey =
  | keyof ExpenseActualImportPreviewRowDto
  | "amount_display";

type ExpenseActualImportPreviewColumn = {
  key: PreviewColumnKey;
  header: string;
  numeric?: boolean;
};

export const expenseActualPreviewColumns: ExpenseActualImportPreviewColumn[] = [
  { key: "data_date", header: "数据日期" },
  { key: "org_code", header: "费用归属部门编码" },
  { key: "org_name", header: "费用部门" },
  { key: "dep_code", header: "责任中心编码" },
  { key: "dep_name", header: "责任中心" },
  { key: "subject_code", header: "科目编码" },
  { key: "subject_name", header: "科目描述" },
  { key: "period_ym", header: "期间" },
  { key: "journal_name", header: "日记帐名" },
  { key: "serial_no", header: "流水号" },
  { key: "line_desc", header: "行说明" },
  { key: "amount_display", header: "金额", numeric: true },
  { key: "fee_type_code", header: "费用类别编码" },
  { key: "fee_type_name", header: "费用类别" },
  { key: "bi_ai_source_code", header: "BI-AI源编码" },
  { key: "bi_ai_source_name", header: "BI-AI源名称" },
  { key: "manage_department_code", header: "归口管理部门编码" },
  { key: "owner_name_raw", header: "归口管理部门" },
  { key: "fee_major_mapped", header: "费用大类" },
  { key: "fee_category_mapped", header: "费用类别（一级）" },
  { key: "budget_release_caliber_mapped", header: "预算发布口径（二级）" },
  { key: "manage_department2", header: "归口管理部门2" },
  { key: "special_control_tag", header: "专项管控打标" },
  { key: "match_status", header: "匹配状态" },
  { key: "match_note", header: "说明" },
];

export const expenseActualUnmatchedPreviewColumns: ExpenseActualImportPreviewColumn[] = [
  { key: "data_date", header: "数据日期" },
  { key: "org_name", header: "费用部门" },
  { key: "dep_name", header: "责任中心" },
  { key: "subject_name", header: "科目描述" },
  { key: "bi_ai_source_name", header: "BI-AI源名称" },
  { key: "owner_name_raw", header: "归口管理部门" },
  { key: "amount_display", header: "金额", numeric: true },
  { key: "match_note", header: "说明" },
];

export function formatExpenseActualPreviewCell(
  row: ExpenseActualImportPreviewRowDto,
  column: ExpenseActualImportPreviewColumn,
): string {
  if (column.key === "amount_display") {
    return row.amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }
  const value = row[column.key];
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}
