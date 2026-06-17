import type {
  ExpenseForecastMetaResponseDto,
  ExpenseForecastMonthCellDto,
  ExpenseForecastRowDto,
  ExpenseForecastSubjectOwnerRowDto,
  ExpenseForecastSubjectViewResponseDto,
} from "@/lib/expense/expenseForecastApi";
import type { BudgetSubjectTreeNode } from "@/lib/budget/budgetSubjectCatalogViewModel";
import type { DeptTreeNode } from "@/lib/business/deptCatalogViewModel";
import type { BudgetSubjectCatalogDto } from "@/lib/expense/masterDataApi";

export { buildBudgetSubjectTree } from "@/lib/budget/budgetSubjectCatalogViewModel";
export { buildDeptTree } from "@/lib/business/deptCatalogViewModel";
export type { BudgetSubjectTreeNode };
export type { DeptTreeNode };

export type ScopeType = "entity" | "group" | "owner";
export type ImportMode = "append" | "overwrite";
export type AmountUnit = "yuan" | "thousand" | "ten_thousand" | "million" | "hundred_million";
export type CompileMode = "scope" | "subject";

export type SubjectOwnerTreeNode = {
  key: string;
  name: string;
  level: number;
  isLeaf: boolean;
  row: ExpenseForecastSubjectOwnerRowDto;
  children: SubjectOwnerTreeNode[];
};

export type BudgetSubjectSearchMatch = {
  row: BudgetSubjectCatalogDto;
  path: string;
};

export const EXPORT_FIELDS = [
  { key: "jan", label: "1月", group: "月度" },
  { key: "feb", label: "2月", group: "月度" },
  { key: "mar", label: "3月", group: "月度" },
  { key: "apr", label: "4月", group: "月度" },
  { key: "may", label: "5月", group: "月度" },
  { key: "jun", label: "6月", group: "月度" },
  { key: "jul", label: "7月", group: "月度" },
  { key: "aug", label: "8月", group: "月度" },
  { key: "sep", label: "9月", group: "月度" },
  { key: "oct", label: "10月", group: "月度" },
  { key: "nov", label: "11月", group: "月度" },
  { key: "dec", label: "12月", group: "月度" },
  { key: "total", label: "全年预测", group: "汇总" },
  { key: "annual_budget", label: "年度预算", group: "汇总" },
  { key: "gap", label: "全年预测-年度预算", group: "汇总" },
  { key: "rate", label: "预算执行率", group: "汇总" },
  { key: "biz", label: "业务报送", group: "报送" },
  { key: "capital", label: "资划建议", group: "报送" },
  { key: "capital_gap", label: "资划建议-业务报送", group: "报送" },
];

export const ALL_FIELD_KEYS = EXPORT_FIELDS.map((field) => field.key);
export const AMOUNT_UNIT_STORAGE_KEY = "expense-forecast-amount-unit";
export const ALL_OWNER_DEPARTMENTS_VALUE = "__ALL_OWNER_DEPARTMENTS__";

export const amountUnitOptions: Array<{ value: AmountUnit; label: string; divisor: number }> = [
  { value: "yuan", label: "元", divisor: 1 },
  { value: "thousand", label: "千元", divisor: 1_000 },
  { value: "ten_thousand", label: "万元", divisor: 10_000 },
  { value: "million", label: "百万元", divisor: 1_000_000 },
  { value: "hundred_million", label: "亿元", divisor: 100_000_000 },
];

export function formatNumber(value: number | null | undefined, divisor = 1): string {
  const normalized = Number.isFinite(value) ? Number(value) : 0;
  return (normalized / divisor).toLocaleString("zh-CN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "-";
  if (!Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

export function parseNumberInput(raw: string): number {
  const parsed = Number.parseFloat(raw.replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

export function monthCellStatusTitle(cell: ExpenseForecastMonthCellDto): string {
  const source = cell.value_source ?? (cell.source === "actual" ? "actual" : "manual");
  if (source === "actual") return "来源：实际，只读";
  if (source === "manual") return "来源：手工/导入预测";
  if (source === "auto") return "来源：自动测算";
  if (source === "override") return `来源：人工覆盖${cell.override_reason ? `，原因：${cell.override_reason}` : ""}`;
  if (source === "unconfigured") return "未配置预测逻辑";
  return "汇总单元格";
}

export function monthCellButtonClass(cell: ExpenseForecastMonthCellDto): string {
  const source = cell.value_source ?? (cell.source === "actual" ? "actual" : "manual");
  if (source === "override") return "text-amber-700";
  if (source === "auto") return "text-violet-700";
  if (source === "unconfigured") return "text-red-600";
  return "";
}

export function scopeLabel(scopeType: ScopeType): string {
  if (scopeType === "entity") return "主体";
  if (scopeType === "group") return "事业群";
  return "费用归属部门";
}

export function suggestedScopeType(meta: ExpenseForecastMetaResponseDto | null): ScopeType {
  if (!meta) return "group";
  if (meta.group_options.length > 0) return "group";
  if (meta.entity_options.length > 0) return "entity";
  return "owner";
}


export function buildBudgetSubjectRowMap(rows: BudgetSubjectCatalogDto[]): Map<number, BudgetSubjectCatalogDto> {
  const map = new Map<number, BudgetSubjectCatalogDto>();
  rows.forEach((row) => map.set(row.id, row));
  return map;
}

export function buildBudgetSubjectPathMap(tree: BudgetSubjectTreeNode[]): Map<number, string> {
  const result = new Map<number, string>();
  const walk = (node: BudgetSubjectTreeNode, parentPath: string[]) => {
    const nextPath = [...parentPath, node.subject_name];
    if (node.is_leaf) {
      result.set(node.id, nextPath.join(" / "));
    }
    node.children.forEach((child) => walk(child, nextPath));
  };
  tree.forEach((node) => walk(node, []));
  return result;
}

export function searchBudgetSubjects(
  rows: BudgetSubjectCatalogDto[],
  pathMap: Map<number, string>,
  keyword: string,
): BudgetSubjectSearchMatch[] {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return [];
  return rows
    .filter((row) => row.is_leaf)
    .map((row) => ({
      row,
      path: pathMap.get(row.id) ?? row.subject_name,
    }))
    .filter(
      ({ row, path }) =>
        row.subject_name.toLowerCase().includes(normalizedKeyword) ||
        path.toLowerCase().includes(normalizedKeyword),
    )
    .sort((a, b) => a.path.localeCompare(b.path, "zh-CN"));
}

export function buildExpenseForecastRowMap(rows: ExpenseForecastRowDto[]): Map<number, ExpenseForecastRowDto> {
  const map = new Map<number, ExpenseForecastRowDto>();
  rows.forEach((row) => map.set(row.id, row));
  return map;
}

export function groupExpenseForecastRowsByParent(rows: ExpenseForecastRowDto[]): Map<number | null, ExpenseForecastRowDto[]> {
  const map = new Map<number | null, ExpenseForecastRowDto[]>();
  rows.forEach((row) => {
    const parentId = row.parent_id ?? null;
    const list = map.get(parentId) ?? [];
    list.push(row);
    map.set(parentId, list);
  });
  return map;
}

export function findMatchedExpenseForecastRowIds(
  rows: ExpenseForecastRowDto[],
  rowMap: Map<number, ExpenseForecastRowDto>,
  keyword: string,
): Set<number> | null {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return null;
  const matched = new Set<number>();
  rows.forEach((row) => {
    if (!row.subject_name.toLowerCase().includes(normalizedKeyword)) return;
    matched.add(row.id);
    let parentId = row.parent_id;
    while (parentId != null) {
      matched.add(parentId);
      parentId = rowMap.get(parentId)?.parent_id ?? null;
    }
  });
  return matched;
}

export function buildVisibleExpenseForecastRows(
  rows: ExpenseForecastRowDto[],
  childrenByParent: Map<number | null, ExpenseForecastRowDto[]>,
  matchedRowIds: Set<number> | null,
  expandedIds: Set<number>,
): ExpenseForecastRowDto[] {
  const result: ExpenseForecastRowDto[] = [];
  const walk = (parentId: number | null) => {
    for (const row of childrenByParent.get(parentId) ?? []) {
      const matched = matchedRowIds ? matchedRowIds.has(row.id) : true;
      if (matched) result.push(row);
      const shouldWalk = matchedRowIds ? matchedRowIds.has(row.id) : expandedIds.has(row.id);
      if (shouldWalk) {
        walk(row.id);
      }
    }
  };
  walk(null);
  if (result.length > 0) return result;
  if (!rows.length) return result;
  if (!matchedRowIds) return rows;
  return rows.filter((row) => matchedRowIds.has(row.id));
}

export function buildExpenseForecastRowDepthMap(
  childrenByParent: Map<number | null, ExpenseForecastRowDto[]>,
): Map<number, number> {
  const map = new Map<number, number>();
  const walk = (parentId: number | null, depth: number) => {
    for (const row of childrenByParent.get(parentId) ?? []) {
      map.set(row.id, depth);
      walk(row.id, depth + 1);
    }
  };
  walk(null, 0);
  return map;
}

export function buildSubjectOwnerTree(params: {
  enabled: boolean;
  scopeType: ScopeType;
  scopeValue: string;
  deptTree: DeptTreeNode[];
  subjectView: ExpenseForecastSubjectViewResponseDto | null;
}): SubjectOwnerTreeNode[] {
  const { enabled, scopeType, scopeValue, deptTree, subjectView } = params;
  if (!enabled || scopeType !== "entity") return [];
  const rows = subjectView?.rows ?? [];
  const ownerRowMap = new Map(rows.map((row) => [row.owner_name, row] as const));
  const buildNodes = (nodes: DeptTreeNode[], parentKey = ""): SubjectOwnerTreeNode[] => {
    return nodes
      .filter((node) => node.level <= 2)
      .map((node) => {
        const key = parentKey ? `${parentKey}/${node.dept_code}` : node.dept_code;
        const directRow = ownerRowMap.get(node.dept_name);
        const children = buildNodes(node.children, key);
        const aggregatedRow: ExpenseForecastSubjectOwnerRowDto | null =
          directRow ??
          (children.length > 0
            ? {
                owner_name: node.dept_name,
                subject_id: subjectView?.subject_id ?? 0,
                subject_name: subjectView?.subject_name ?? "",
                months: Array.from({ length: 12 }, (_, idx) => ({
                  month: idx + 1,
                  value: children.reduce((sum, child) => sum + (child.row.months[idx]?.value ?? 0), 0),
                  source: idx + 1 <= (subjectView?.actual_cutoff_month ?? 0) ? "actual" : "forecast",
                  editable: false,
                })),
                total_value: children.reduce((sum, child) => sum + child.row.total_value, 0),
                annual_budget: children.reduce((sum, child) => sum + child.row.annual_budget, 0),
                forecast_budget_gap: children.reduce((sum, child) => sum + child.row.forecast_budget_gap, 0),
                budget_execution_rate: null,
                business_submission: children.reduce((sum, child) => sum + child.row.business_submission, 0),
                capital_advice: children.reduce((sum, child) => sum + child.row.capital_advice, 0),
                capital_advice_gap: children.reduce((sum, child) => sum + child.row.capital_advice_gap, 0),
                business_submission_editable: false,
                capital_advice_editable: false,
              }
            : null);
        if (!aggregatedRow) return null;
        const budget = aggregatedRow.annual_budget;
        const total = aggregatedRow.total_value;
        return {
          key,
          name: node.dept_name,
          level: node.level,
          isLeaf: children.length === 0,
          children,
          row: {
            ...aggregatedRow,
            budget_execution_rate: budget ? total / budget : null,
            forecast_budget_gap: total - budget,
            capital_advice_gap: aggregatedRow.capital_advice - aggregatedRow.business_submission,
          },
        };
      })
      .filter((node): node is SubjectOwnerTreeNode => Boolean(node));
  };
  return buildNodes(deptTree.filter((node) => node.entity_name === scopeValue));
}

export function filterSubjectOwnerTree(nodes: SubjectOwnerTreeNode[], keyword: string): SubjectOwnerTreeNode[] {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return nodes;
  return nodes
    .map((node) => {
      const children = filterSubjectOwnerTree(node.children, normalizedKeyword);
      const matched = node.name.toLowerCase().includes(normalizedKeyword);
      if (matched || children.length > 0) {
        return { ...node, children };
      }
      return null;
    })
    .filter((node): node is SubjectOwnerTreeNode => Boolean(node));
}

export function flattenVisibleSubjectOwnerNodes(
  nodes: SubjectOwnerTreeNode[],
  expandedKeys: Set<string>,
  keyword: string,
): SubjectOwnerTreeNode[] {
  const normalizedKeyword = keyword.trim();
  const result: SubjectOwnerTreeNode[] = [];
  const walk = (currentNodes: SubjectOwnerTreeNode[]) => {
    currentNodes.forEach((node) => {
      result.push(node);
      if (node.children.length > 0 && (normalizedKeyword || expandedKeys.has(node.key))) {
        walk(node.children);
      }
    });
  };
  walk(nodes);
  return result;
}

export function filterExpenseForecastRows(rows: ExpenseForecastRowDto[], keyword: string): ExpenseForecastRowDto[] {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return rows;
  const rowMap = new Map<number, ExpenseForecastRowDto>();
  rows.forEach((row) => rowMap.set(row.id, row));
  const matched = new Set<number>();
  rows.forEach((row) => {
    if (!row.subject_name.toLowerCase().includes(normalizedKeyword)) return;
    matched.add(row.id);
    let parentId = row.parent_id;
    while (parentId != null) {
      matched.add(parentId);
      parentId = rowMap.get(parentId)?.parent_id ?? null;
    }
  });
  return rows.filter((row) => matched.has(row.id));
}
