import type {
  ExpenseBudgetExecutionAmountUnit,
  ExpenseBudgetExecutionExportRequest,
  ExpenseBudgetExecutionMode,
  ExpenseBudgetExecutionPerspective,
  ExpenseBudgetExecutionReportRequest,
  ExpenseBudgetExecutionResponseDto,
  ExpenseBudgetExecutionSubjectScopeNodeDto,
} from "@/lib/expense/expenseBudgetExecutionApi";

type AmountUnitOption = {
  value: ExpenseBudgetExecutionAmountUnit;
  label: string;
  divisor: number;
};

export const expenseBudgetExecutionAmountUnitOptions: AmountUnitOption[] = [
  { value: "yuan", label: "元", divisor: 1 },
  { value: "thousand", label: "千元", divisor: 1_000 },
  { value: "ten_thousand", label: "万元", divisor: 10_000 },
  { value: "million", label: "百万元", divisor: 1_000_000 },
  { value: "hundred_million", label: "亿元", divisor: 100_000_000 },
];

export const expenseBudgetExecutionStorageKeys = {
  reportMode: "expense-budget-execution-report-mode",
  queryReportMonth: "expense-budget-execution-query-report-month",
  templateReportMonth: "expense-budget-execution-template-report-month",
  templateEntity: "expense-budget-execution-template-entity",
  templateGroup: "expense-budget-execution-template-group",
  templateOwner: "expense-budget-execution-template-owner",
  subjectReportMonth: "expense-budget-execution-subject-report-month",
  subjectSelectedId: "expense-budget-execution-subject-selected-id",
  amountUnit: "expense-budget-execution-amount-unit",
} as const;

export function formatExpenseBudgetExecutionNumber(
  value: number | null | undefined,
  divisor = 1,
): string {
  if (value == null || Number.isNaN(value)) return "-";
  const fractionDigits = divisor === 100_000_000 ? 1 : 0;
  return (value / divisor).toLocaleString("zh-CN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export function formatExpenseBudgetExecutionPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(0)}%`;
}

export function normalizeExpenseBudgetExecutionReportMonth(value: string | number | null | undefined): string {
  if (value == null || value === "") return "";
  const month = Number(value);
  if (!Number.isInteger(month) || month < 1 || month > 12) return "";
  return String(month);
}

export function normalizeExpenseBudgetExecutionReportMode(
  value: string | null | undefined,
): ExpenseBudgetExecutionMode | null {
  if (value === "query" || value === "template" || value === "subject") return value;
  return null;
}

export function normalizeExpenseBudgetExecutionAmountUnit(
  value: string | null | undefined,
): ExpenseBudgetExecutionAmountUnit | null {
  const option = expenseBudgetExecutionAmountUnitOptions.find((item) => item.value === value);
  return option?.value ?? null;
}

export function getExpenseBudgetExecutionAmountDivisor(value: string | null | undefined): number {
  const option = expenseBudgetExecutionAmountUnitOptions.find((item) => item.value === value);
  return option?.divisor ?? 1;
}

export function normalizeExpenseBudgetExecutionSubjectId(value: string | number | null | undefined): string {
  if (value == null || value === "") return "";
  const subjectId = Number(value);
  if (!Number.isInteger(subjectId) || subjectId <= 0) return "";
  return String(subjectId);
}

export function findExpenseBudgetExecutionSubjectScopeNodeById(
  nodes: ExpenseBudgetExecutionSubjectScopeNodeDto[],
  id: number,
): ExpenseBudgetExecutionSubjectScopeNodeDto | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = findExpenseBudgetExecutionSubjectScopeNodeById(node.children, id);
    if (child) return child;
  }
  return null;
}

type ScopeOption = NonNullable<ExpenseBudgetExecutionResponseDto["template_scope_options"]>[number];

export function getExpenseBudgetExecutionGroupOptions(
  scopeOptions: ScopeOption[],
  entityName: string,
): string[] {
  return Array.from(
    new Set(
      scopeOptions
        .filter((item) => !entityName || item.entity_name === entityName)
        .map((item) => item.group_name),
    ),
  );
}

export function getExpenseBudgetExecutionOwnerOptions(
  scopeOptions: ScopeOption[],
  entityName: string,
  groupName: string,
): string[] {
  return Array.from(
    new Set(
      scopeOptions
        .filter((item) => !entityName || item.entity_name === entityName)
        .filter((item) => !groupName || item.group_name === groupName)
        .map((item) => item.owner_dept),
    ),
  );
}

type ExpenseBudgetExecutionFilterState = {
  reportMode: ExpenseBudgetExecutionMode;
  perspective: ExpenseBudgetExecutionPerspective;
  amountUnit: ExpenseBudgetExecutionAmountUnit;
  activeKeyword: string;
  includeZeroRows: boolean;
  queryEntityName: string;
  queryGroupName: string;
  queryOwnerDept: string;
  queryReportMonth: string;
  subjectEntityName: string;
  subjectReportMonth: string;
  subjectSelectedId: string;
  templateEntityName: string;
  templateGroupName: string;
  templateOwnerDept: string;
  templateReportMonth: string;
};

type ExpenseBudgetExecutionModeViewState = {
  reportMode: ExpenseBudgetExecutionMode;
  templateKeyword: string;
  subjectKeyword: string;
};

type ExpenseBudgetExecutionKeywordMode = "template" | "subject" | null;

export function getExpenseBudgetExecutionModeView(
  state: ExpenseBudgetExecutionModeViewState,
): {
  isTreeReportMode: boolean;
  hasTreeSection: boolean;
  activeKeyword: string;
  keywordMode: ExpenseBudgetExecutionKeywordMode;
} {
  const isTreeReportMode = state.reportMode === "template" || state.reportMode === "subject";
  if (state.reportMode === "template") {
    return {
      isTreeReportMode,
      hasTreeSection: true,
      activeKeyword: state.templateKeyword,
      keywordMode: "template",
    };
  }
  if (state.reportMode === "subject") {
    return {
      isTreeReportMode,
      hasTreeSection: true,
      activeKeyword: state.subjectKeyword,
      keywordMode: "subject",
    };
  }
  return {
    isTreeReportMode,
    hasTreeSection: true,
    activeKeyword: "",
    keywordMode: null,
  };
}

function scopedGroupName(state: ExpenseBudgetExecutionFilterState): string {
  if (state.reportMode === "template") {
    return state.templateEntityName ? state.templateGroupName : "";
  }
  if (state.reportMode === "query") {
    return state.queryEntityName ? state.queryGroupName : "";
  }
  return "";
}

function scopedOwnerDept(state: ExpenseBudgetExecutionFilterState): string {
  if (state.reportMode === "template") {
    return state.templateEntityName && state.templateGroupName ? state.templateOwnerDept : "";
  }
  if (state.reportMode === "query") {
    return state.queryEntityName && state.queryGroupName ? state.queryOwnerDept : "";
  }
  return "";
}

function scopedEntityName(state: ExpenseBudgetExecutionFilterState): string {
  if (state.reportMode === "template") return state.templateEntityName;
  if (state.reportMode === "subject") return state.subjectEntityName;
  return state.queryEntityName;
}

function scopedReportMonth(state: ExpenseBudgetExecutionFilterState): string {
  if (state.reportMode === "template") return state.templateReportMonth;
  if (state.reportMode === "subject") return state.subjectReportMonth;
  return state.queryReportMonth;
}

export function buildExpenseBudgetExecutionReportRequest(
  state: ExpenseBudgetExecutionFilterState,
): ExpenseBudgetExecutionReportRequest {
  const subjectId = normalizeExpenseBudgetExecutionSubjectId(state.subjectSelectedId);
  const reportMonth = normalizeExpenseBudgetExecutionReportMonth(scopedReportMonth(state));
  return {
    mode: state.reportMode,
    perspective: state.perspective,
    keyword: state.activeKeyword,
    includeZeroRows: state.includeZeroRows,
    entityName: scopedEntityName(state),
    groupName: scopedGroupName(state),
    ownerDept: scopedOwnerDept(state),
    subjectId: state.reportMode === "subject" ? subjectId : "",
    reportMonth,
  };
}

export function buildExpenseBudgetExecutionExportRequest(
  state: ExpenseBudgetExecutionFilterState & {
    includeMonthlyActuals: boolean;
    includeLastYearMonthlyActuals: boolean;
  },
): ExpenseBudgetExecutionExportRequest {
  const reportMonth = normalizeExpenseBudgetExecutionReportMonth(scopedReportMonth(state));
  const subjectId = normalizeExpenseBudgetExecutionSubjectId(state.subjectSelectedId);
  return {
    ...buildExpenseBudgetExecutionReportRequest(state),
    amountUnit: state.amountUnit,
    subjectId: state.reportMode === "subject" && subjectId ? Number(subjectId) : undefined,
    reportMonth: reportMonth ? Number(reportMonth) : undefined,
    includeMonthlyActuals: state.includeMonthlyActuals,
    includeLastYearMonthlyActuals: state.includeLastYearMonthlyActuals,
  };
}

export function describeExpenseBudgetExecutionSummary(
  report: ExpenseBudgetExecutionResponseDto | null,
  reportMode: ExpenseBudgetExecutionMode,
  selectedSubjectNode: ExpenseBudgetExecutionSubjectScopeNodeDto | null,
): string {
  if (!report) return "";
  if (reportMode === "query") {
    const entityText = report.selected_entity_name ? ` / 主体 ${report.selected_entity_name}` : " / 全部主体";
    const groupText = report.selected_group_name ? ` / 事业群 ${report.selected_group_name}` : "";
    const ownerText = report.selected_owner_dept ? ` / 费用归属部门 ${report.selected_owner_dept}` : "";
    return `${report.template_title || `${report.budget_year}年${report.current_month}月费用统计表`}${entityText}${groupText}${ownerText} / 月报格式`;
  }
  if (reportMode === "template") {
    const entityText = report.selected_entity_name ? ` / 主体 ${report.selected_entity_name}` : " / 全部主体";
    const groupText = report.selected_group_name ? ` / 事业群 ${report.selected_group_name}` : "";
    const ownerText = report.selected_owner_dept ? ` / 费用归属部门 ${report.selected_owner_dept}` : "";
    return `${report.template_title || `${report.budget_year}年${report.current_month}月费用统计表`}${entityText} / 费用类型共 ${
      report.subject_tree?.length ?? 0
    } 个一级节点${groupText}${ownerText}`;
  }
  const entityText = report.selected_entity_name ? ` / 主体 ${report.selected_entity_name}` : " / 全部主体";
  const subjectText = selectedSubjectNode ? ` / 当前科目 ${selectedSubjectNode.subject_name}` : " / 全部科目";
  return `${report.subject_title || `${report.budget_year}年${report.current_month}月预算科目报表`} / 部门树共 ${
    report.subject_tree?.length ?? 0
  } 个主体节点${entityText}${subjectText}`;
}

export function getExpenseBudgetExecutionTreeMeta(
  report: ExpenseBudgetExecutionResponseDto | null,
  reportMode: ExpenseBudgetExecutionMode,
): { nodeLabel: string; title: string; loadingText: string } {
  if (reportMode === "query") {
    return {
      nodeLabel: "费用类型",
      title: report?.template_title || "月报格式",
      loadingText: "正在加载月报格式...",
    };
  }
  if (reportMode === "subject") {
    return {
      nodeLabel: "部门",
      title: report?.subject_title || "科目模式",
      loadingText: "正在加载科目模式报表...",
    };
  }
  return {
    nodeLabel: "费用类型",
    title: report?.template_title || "部门模式",
    loadingText: "正在加载部门模式报表...",
  };
}

export function buildExpenseBudgetExecutionMonthlyLabels(currentMonth: number | null | undefined): string[] {
  return Array.from({ length: currentMonth ?? 0 }, (_, idx) => `${idx + 1}月实际`);
}

export function buildExpenseBudgetExecutionLastYearMonthlyLabels(
  budgetYear: number | null | undefined,
): string[] {
  const previousYearShort = String((budgetYear ?? new Date().getFullYear()) - 1).slice(-2);
  return Array.from({ length: 12 }, (_, idx) => `${previousYearShort}年${idx + 1}月实际`);
}
