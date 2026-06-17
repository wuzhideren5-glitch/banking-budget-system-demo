import type { BudgetSummaryRowDto, CompareSummaryRowDto } from "@/lib/org-product/pivotSummaryApi";

export interface PivotField {
  id: string;
  name: string;
  type: "dimension" | "measure";
}

export type DropZone = "pool" | "row" | "column" | "page" | "value";
export type PivotDataSource = "budget" | "compare";
export type PivotSummaryRow = BudgetSummaryRowDto | CompareSummaryRowDto;
export type PivotValueDisplayKind = "amount" | "percent";
export type PivotValueFormatStats = { amount: number; percent: number };

export type PivotResult = {
  rowFieldDefs: PivotField[];
  colFieldDefs: PivotField[];
  colHeaderRows: Array<Array<{ key: string; label: string; span: number }>>;
  colKeys: string[];
  rowNodes: Array<{
    key: string;
    level: number;
    path: string[];
    label: string;
    colMap: Map<string, number>;
    colFmtMap: Map<string, PivotValueFormatStats>;
    total: number;
    totalFmt: PivotValueFormatStats;
    isLeaf: boolean;
  }>;
  colTotals: Map<string, number>;
  colTotalFmt: Map<string, PivotValueFormatStats>;
  grandTotal: number;
  grandTotalFmt: PivotValueFormatStats;
};

const BASE_DIMENSION_FIELDS: PivotField[] = [
  { id: "metric_level1", name: "指标1级", type: "dimension" },
  { id: "metric_level2", name: "指标2级", type: "dimension" },
  { id: "metric_level3", name: "指标3级", type: "dimension" },
  { id: "metric_level4", name: "指标4级", type: "dimension" },
  { id: "metric_level5", name: "指标5级", type: "dimension" },
  { id: "dept_level1", name: "部门科目1级", type: "dimension" },
  { id: "dept_level2", name: "部门科目2级", type: "dimension" },
  { id: "dept_level3", name: "部门科目3级", type: "dimension" },
  { id: "data_code_name", name: "机构及产品指标编码", type: "dimension" },
  { id: "product_code_name", name: "机构及产品", type: "dimension" },
  { id: "year", name: "年度", type: "dimension" },
  { id: "month", name: "月份", type: "dimension" },
  { id: "quarter", name: "季度", type: "dimension" },
  { id: "budget_actual", name: "预算/实际", type: "dimension" },
  { id: "value_source", name: "取值来源", type: "dimension" },
  { id: "value_type", name: "数值类型", type: "dimension" },
];

const VERSION_FIELD: PivotField = { id: "version_display", name: "版本号及名称", type: "dimension" };
const VALUE_FIELD: PivotField = { id: "value", name: "预算数值", type: "measure" };

export function getPivotFields(dataSource: PivotDataSource): PivotField[] {
  if (dataSource === "compare") {
    return [VERSION_FIELD, ...BASE_DIMENSION_FIELDS, VALUE_FIELD];
  }
  const beforeValueType = BASE_DIMENSION_FIELDS.filter((f) => f.id !== "value_type");
  return [...beforeValueType, VERSION_FIELD, BASE_DIMENSION_FIELDS[BASE_DIMENSION_FIELDS.length - 1], VALUE_FIELD];
}

export function splitSearchKeywords(raw: string): string[] {
  return raw
    .toLowerCase()
    .split(/[\s,，;；/\\]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function resolveSelectionValueFromOptions(
  fieldId: string,
  desired: string,
  optionsMap: Record<string, string[]>,
  keepRawWhenUnknown = false,
): string {
  const options = optionsMap[fieldId] ?? ["全部"];
  const target = (desired ?? "").trim();
  if (!target) return options[0] || "全部";
  if (options.includes(target)) return target;
  const contains = options.find((opt) => opt.includes(target));
  if (contains) return contains;
  if (fieldId.startsWith("dept_level")) {
    const norm = (s: string) =>
      s
        .replace(/[|｜]/g, " ")
        .replace(/\s+/g, "")
        .replace(/(部门|事业部|业务条线|条线|部)$/g, "")
        .toLowerCase();
    const nt = norm(target);
    const fuzzy = options.find((opt) => norm(opt).includes(nt) || nt.includes(norm(opt)));
    if (fuzzy) return fuzzy;
  }
  if (keepRawWhenUnknown) return target;
  return options[0] || "全部";
}

export function detectValueDisplayKind(valueType: string): PivotValueDisplayKind {
  const t = String(valueType || "").trim();
  if (!t) return "amount";
  if (/(%|百分|占比|比率|比例|收益率|利率|费率|率)/.test(t)) return "percent";
  return "amount";
}

export function addFormatStats(target: PivotValueFormatStats, kind: PivotValueDisplayKind) {
  if (kind === "percent") {
    target.percent += 1;
  } else {
    target.amount += 1;
  }
}

export function resolveDisplayKindFromStats(stats: PivotValueFormatStats | undefined): PivotValueDisplayKind {
  if (!stats) return "amount";
  return stats.percent > 0 && stats.amount === 0 ? "percent" : "amount";
}

export function formatPivotValue(value: number, kind: PivotValueDisplayKind): string {
  if (kind === "percent") {
    const scaled = Math.abs(value) <= 1 ? value * 100 : value;
    return `${scaled.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  }
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function parseVersionIdFromDisplay(text: string): number | null {
  const m = String(text || "").match(/版本号[:：]\s*(\d{1,12})/);
  if (!m) return null;
  const v = Number(m[1]);
  return Number.isFinite(v) ? v : null;
}

export function pickLatestVersionOption(options: string[]): string | null {
  const realOptions = options.filter((o) => o && o !== "全部");
  let bestText: string | null = null;
  let bestId = -1;
  for (const opt of realOptions) {
    const vid = parseVersionIdFromDisplay(opt);
    if (vid == null) continue;
    if (vid > bestId) {
      bestId = vid;
      bestText = opt;
    }
  }
  if (bestText) return bestText;
  return realOptions[0] ?? null;
}

export function getFieldValue(row: PivotSummaryRow, fieldId: string): string {
  switch (fieldId) {
    case "show_level":
      return "show_level" in row ? String(row.show_level) : "未设置";
    case "data_file_id":
      return "data_file_id" in row ? String(row.data_file_id) : "未设置";
    case "source_year":
      return "source_year" in row ? String(row.source_year) : "未设置";
    case "metric_level1":
      return row.metric_level1 ?? "未设置";
    case "metric_level2":
      return row.metric_level2 ?? "未设置";
    case "metric_level3":
      return row.metric_level3 ?? "未设置";
    case "metric_level4":
      return row.metric_level4 ?? "未设置";
    case "metric_level5":
      return row.metric_level5 ?? "未设置";
    case "dept_level1":
      return row.dept_level1 ?? "未设置";
    case "dept_level2":
      return row.dept_level2 ?? "未设置";
    case "dept_level3":
      return row.dept_level3 ?? "未设置";
    case "data_code_name":
      return row.data_code_name;
    case "product_code_name":
      return row.product_code_name ?? "未设置";
    case "month":
      return row.month;
    case "year":
      return row.year;
    case "quarter":
      return row.quarter;
    case "budget_actual":
      return row.budget_actual === 0 ? "预算" : "实际";
    case "value_source":
      return row.value_source ?? "未设置";
    case "version_display": {
      const showLevelPrefix =
        "show_level" in row && row.show_level != null ? `展示版本第${String(row.show_level)}级 ` : "";
      const versionId =
        "version_id" in row
          ? row.version_id
          : ("source_version_id" in row ? row.source_version_id : null);
      const versionName =
        "version_name" in row
          ? (row.version_name ?? "")
          : ("source_version_name" in row ? (row.source_version_name ?? "") : "");
      const vidText = versionId != null ? String(versionId) : "未设置";
      const vnameText = versionName || "未设置";
      return `${showLevelPrefix}版本号：${vidText} 版本名称：${vnameText}`;
    }
    case "sync_time":
      return "sync_time" in row ? row.sync_time : "未设置";
    case "value_type":
      return row.value_type;
    default:
      return "未设置";
  }
}

export function buildFieldOptionsMap(fields: PivotField[], rows: PivotSummaryRow[]): Record<string, string[]> {
  const map: Record<string, string[]> = {};
  for (const field of fields) {
    if (field.type !== "dimension") continue;
    const values = new Set<string>();
    for (const row of rows) {
      values.add(getFieldValue(row, field.id));
    }
    map[field.id] = ["全部", ...Array.from(values).sort()];
  }
  return map;
}

export function filterPivotRows(args: {
  rows: PivotSummaryRow[];
  pageFields: PivotField[];
  pageFieldSelections: Record<string, string>;
  searchText: string;
  searchableFieldIds: string[];
  fieldOptionsMap: Record<string, string[]>;
}): PivotSummaryRow[] {
  const keywords = splitSearchKeywords(args.searchText);
  return args.rows.filter((row) => {
    const passPage = args.pageFields.every((f) => {
      const selected = args.pageFieldSelections[f.id];
      if (!selected || selected === "全部") return true;
      const options = args.fieldOptionsMap[f.id] ?? ["全部"];
      if (!options.includes(selected)) return true;
      return getFieldValue(row, f.id) === selected;
    });
    if (!passPage) return false;
    if (!keywords.length) return true;
    const searchableValues = args.searchableFieldIds.map((fieldId) => getFieldValue(row, fieldId).toLowerCase());
    return keywords.some((kw) => searchableValues.some((v) => v.includes(kw)));
  });
}

export function buildPivotResult(args: {
  rows: PivotSummaryRow[];
  rowFields: PivotField[];
  columnFields: PivotField[];
  valueFields: PivotField[];
}): PivotResult {
  const tupleKey = (parts: string[]) => parts.join("\u0001");
  const compareTuple = (a: string[], b: string[]) => {
    const n = Math.max(a.length, b.length);
    for (let i = 0; i < n; i += 1) {
      const av = a[i] ?? "";
      const bv = b[i] ?? "";
      const c = av.localeCompare(bv, "zh-Hans-CN");
      if (c !== 0) return c;
    }
    return 0;
  };

  type RowTreeNode = {
    label: string;
    level: number;
    path: string[];
    children: Map<string, RowTreeNode>;
    colMap: Map<string, number>;
    colFmtMap: Map<string, PivotValueFormatStats>;
    total: number;
    totalFmt: PivotValueFormatStats;
  };

  const rowFieldDefs = args.rowFields.length ? args.rowFields : [{ id: "__all__", name: "行", type: "dimension" as const }];
  const defaultValueHeader = args.valueFields[0]?.name || "预算数值";
  const colFieldDefs = args.columnFields.length
    ? args.columnFields
    : [{ id: "__col_all__", name: defaultValueHeader, type: "dimension" as const }];

  const colLeafTupleByKey = new Map<string, string[]>();
  const colTotals = new Map<string, number>();
  const colTotalFmt = new Map<string, PivotValueFormatStats>();
  const grandTotalFmt: PivotValueFormatStats = { amount: 0, percent: 0 };
  let grandTotal = 0;
  const root: RowTreeNode = {
    label: "__root__",
    level: 0,
    path: [],
    children: new Map(),
    colMap: new Map(),
    colFmtMap: new Map(),
    total: 0,
    totalFmt: { amount: 0, percent: 0 },
  };

  for (const row of args.rows) {
    const rowTuple = rowFieldDefs.map((f) => (f.id === "__all__" ? "全部" : getFieldValue(row, f.id)));
    const colTuple = colFieldDefs.map((f) => (f.id === "__col_all__" ? defaultValueHeader : getFieldValue(row, f.id)));
    const ck = tupleKey(colTuple);
    const value = row.value;
    const kind = detectValueDisplayKind(row.value_type);
    colLeafTupleByKey.set(ck, colTuple);

    root.colMap.set(ck, (root.colMap.get(ck) ?? 0) + value);
    const rootCellFmt = root.colFmtMap.get(ck) ?? { amount: 0, percent: 0 };
    addFormatStats(rootCellFmt, kind);
    root.colFmtMap.set(ck, rootCellFmt);
    root.total += value;
    addFormatStats(root.totalFmt, kind);
    let cursor = root;
    rowTuple.forEach((label, idx) => {
      let child = cursor.children.get(label);
      if (!child) {
        child = {
          label,
          level: idx + 1,
          path: [...cursor.path, label],
          children: new Map(),
          colMap: new Map(),
          colFmtMap: new Map(),
          total: 0,
          totalFmt: { amount: 0, percent: 0 },
        };
        cursor.children.set(label, child);
      }
      child.colMap.set(ck, (child.colMap.get(ck) ?? 0) + value);
      const childCellFmt = child.colFmtMap.get(ck) ?? { amount: 0, percent: 0 };
      addFormatStats(childCellFmt, kind);
      child.colFmtMap.set(ck, childCellFmt);
      child.total += value;
      addFormatStats(child.totalFmt, kind);
      cursor = child;
    });

    colTotals.set(ck, (colTotals.get(ck) ?? 0) + value);
    const colFmt = colTotalFmt.get(ck) ?? { amount: 0, percent: 0 };
    addFormatStats(colFmt, kind);
    colTotalFmt.set(ck, colFmt);
    grandTotal += value;
    addFormatStats(grandTotalFmt, kind);
  }

  const colLeafTuples = Array.from(colLeafTupleByKey.values()).sort(compareTuple);
  const normalizedColTuples = (colLeafTuples.length ? colLeafTuples : [[defaultValueHeader]]).map((t) => {
    if (t.length >= colFieldDefs.length) return t;
    return [...t, ...new Array(colFieldDefs.length - t.length).fill("")];
  });
  const colKeys = normalizedColTuples.map(tupleKey);

  const rowNodes: PivotResult["rowNodes"] = [];
  const walk = (node: RowTreeNode) => {
    const sortedChildren = Array.from(node.children.values()).sort((a, b) => a.label.localeCompare(b.label, "zh-Hans-CN"));
    for (const child of sortedChildren) {
      rowNodes.push({
        key: tupleKey(child.path),
        level: child.level,
        path: child.path,
        label: child.label,
        colMap: child.colMap,
        colFmtMap: child.colFmtMap,
        total: child.total,
        totalFmt: child.totalFmt,
        isLeaf: child.children.size === 0,
      });
      walk(child);
    }
  };
  walk(root);

  const colHeaderRows: PivotResult["colHeaderRows"] = [];
  const colDepth = Math.max(colFieldDefs.length, 1);
  for (let level = 0; level < colDepth; level += 1) {
    const rowCells: Array<{ key: string; label: string; span: number }> = [];
    let i = 0;
    while (i < normalizedColTuples.length) {
      const current = normalizedColTuples[i];
      const label = current[level] || "(空白)";
      let span = 1;
      while (i + span < normalizedColTuples.length) {
        const next = normalizedColTuples[i + span];
        let samePrefix = true;
        for (let p = 0; p <= level; p += 1) {
          if ((current[p] ?? "") !== (next[p] ?? "")) {
            samePrefix = false;
            break;
          }
        }
        if (!samePrefix) break;
        span += 1;
      }
      rowCells.push({ key: `${level}-${i}`, label, span });
      i += span;
    }
    colHeaderRows.push(rowCells);
  }

  return {
    rowFieldDefs,
    colFieldDefs,
    colHeaderRows,
    colKeys,
    rowNodes,
    colTotals,
    colTotalFmt,
    grandTotal,
    grandTotalFmt,
  };
}
