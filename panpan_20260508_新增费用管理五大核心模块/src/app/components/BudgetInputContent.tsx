import { useEffect, useMemo, useRef, useState } from "react";
import {
  Building2,
  Database as DatabaseIcon,
  RefreshCw,
  Search,
  Upload,
  X,
} from "lucide-react";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableColumnWidths } from "@/lib/useTableColumnWidths";
import { useTableRowHeights } from "@/lib/useTableRowHeights";
import { ColumnResizeHandle } from "./ColumnResizeHandle";
import { BudgetInputExcelUploadDialog } from "./BudgetInputExcelUploadDialog";
import { TableRowResizeHandle } from "./TableRowResizeHandle";
import {
  apiGet,
  apiPost,
  type BudgetInputCellUpsertDto,
  type BudgetInputLoadResponseDto,
  type BudgetInputRowDto,
  type BudgetInputWriteResultDto,
  type DeptAccountDto,
  type DeptProductMappingDto,
  type ProductTypeDto,
  type SessionInfo,
} from "@/lib/api";

type ValueMetric = "budget" | "actual";

function buildBudgetInputRecalculateUrl(productCode: string, budgetActual: 0 | 1, versionId: number): string {
  return `/api/budget-input/recalculate?product_code=${encodeURIComponent(
    productCode
  )}&budget_actual=${budgetActual}&version_id=${versionId}`;
}

type EditingCell = {
  rowKey: string;
  periodId: number;
  metric: ValueMetric;
};
type ProductGroup = {
  deptCode: string;
  deptName: string;
  products: ProductTypeDto[];
};
type ReportLevel = {
  code: string;
  name: string;
};
type DualMetricRow = {
  rowKey: string;
  report_path: string[];
  report_code: string | null;
  data_acct_code: string;
  data_acct_name: string;
  value_type: string;
  budget_values: number[];
  actual_values: number[];
  budget_formula: string | null;
  actual_formula: string | null;
  budget_formula_locked: boolean;
  actual_formula_locked: boolean;
  budget_formula_errors: (string | null)[];
  actual_formula_errors: (string | null)[];
};
type PreparedBudgetRow = DualMetricRow & {
  reportLevels: ReportLevel[];
  visibleLevelFlags: boolean[];
};
type GridCell = {
  rowKey: string;
  periodId: number;
  metric: ValueMetric;
  editable: boolean;
};

function splitSearchKeywords(raw: string): string[] {
  return raw
    .toLowerCase()
    .split(/[\s,，;；/\\]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

const REPORT_COL_WIDTH = 300;
const DEPT_LEVEL1_COL_WIDTH = 180;
const DEPT_LEVEL2_COL_WIDTH = 220;
const DATA_COL_WIDTH = 220;
const VALUE_TYPE_COL_WIDTH = 90;

function parseNumberInput(raw: string): number {
  const parsed = Number.parseFloat(raw.replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function isPercentValueType(valueType: string): boolean {
  return valueType === "百分比";
}

function parseStoredValueInput(raw: string, valueType: string): number {
  const normalized = raw.replace(/[%％]/g, "");
  const parsed = parseNumberInput(normalized);
  if (isPercentValueType(valueType)) return parsed / 100;
  return parsed;
}

function formatNumber(value: number): string {
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function percentDisplayValue(value: number): number {
  // Backward compatible: historical data may have stored 5 for 5%.
  return Math.abs(value) > 1 ? value : value * 100;
}

function formatStoredValue(value: number, valueType: string): string {
  if (isPercentValueType(valueType)) {
    return `${formatNumber(percentDisplayValue(value))}%`;
  }
  return formatNumber(value);
}

function draftKey(rowKey: string, periodId: number, metric: ValueMetric): string {
  return `${rowKey}:${periodId}:${metric}`;
}

function parseReportLevel(token: string): ReportLevel {
  const trimmed = token.trim();
  if (!trimmed) return { code: "", name: "" };
  const m = trimmed.match(/^([A-Z]\d+)\s+(.+)$/);
  if (!m) return { code: "", name: trimmed };
  return { code: m[1], name: m[2] };
}

function buildDeptPath(deptCode: string, deptMap: Map<string, DeptAccountDto>): string[] {
  const path: string[] = [];
  const visited = new Set<string>();
  let currentCode: string | null = deptCode;
  while (currentCode && !visited.has(currentCode)) {
    visited.add(currentCode);
    const current = deptMap.get(currentCode);
    if (!current) {
      path.unshift(currentCode);
      break;
    }
    path.unshift(`${current.dept_code} ${current.dept_name}`);
    currentCode = current.parent_code;
  }
  return path;
}

export function BudgetInputContent() {
  const uPfx = useUserStorageKeyPrefix();
  const { rowStyle, beginResize } = useTableRowHeights(`${uPfx}::budget-input-main`, {
    minHeight: 24,
    maxHeight: 200,
  });
  const { colWidth, colStyle, beginColumnResize } = useTableColumnWidths(`${uPfx}::budget-input-cols`, {
    minWidth: 44,
    maxWidth: 520,
  });
  const [searchText, setSearchText] = useState("");
  const [sessionVersionId, setSessionVersionId] = useState<number | null>(null);
  const [sessionYear, setSessionYear] = useState<number | null>(null);
  const [sessionVersionName, setSessionVersionName] = useState<string>("");
  const initialRecalcDoneRef = useRef(false);
  const unmountSnapshotRef = useRef<{
    productCode: string;
    versionId: number;
  } | null>(null);
  const [products, setProducts] = useState<ProductTypeDto[]>([]);
  const [deptAccounts, setDeptAccounts] = useState<DeptAccountDto[]>([]);
  const [deptMappings, setDeptMappings] = useState<DeptProductMappingDto[]>([]);
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<ProductTypeDto | null>(null);
  const [showProductDialog, setShowProductDialog] = useState(false);
  const [productSearch, setProductSearch] = useState("");
  const [rows, setRows] = useState<DualMetricRow[]>([]);
  const [periods, setPeriods] = useState<BudgetInputLoadResponseDto["periods"]>([]);
  const [currentMonth, setCurrentMonth] = useState<number>(1);
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [showExcelDialog, setShowExcelDialog] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const skipNextBlurRef = useRef(false);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
        setShowProductDialog(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const loadSession = async () => {
    const s = await apiGet<SessionInfo>("/api/session");
    setSessionVersionId(s.version_id);
    setSessionYear(s.budget_year);
    setSessionVersionName(s.version_name?.trim() ?? "");
  };

  const loadProductContext = async () => {
    const [allProducts, deptAccounts, deptMappings] = await Promise.all([
      apiGet<ProductTypeDto[]>("/api/product-types"),
      apiGet<DeptAccountDto[]>("/api/dept-accounts"),
      apiGet<DeptProductMappingDto[]>("/api/dept-product-mappings"),
    ]);
    setProducts(allProducts);
    setDeptAccounts(deptAccounts);
    setDeptMappings(deptMappings);
    if (!selectedProduct && allProducts.length > 0) setSelectedProduct(allProducts[0]);

    const deptNameMap = new Map(deptAccounts.map((d) => [d.dept_code, d.dept_name]));
    const productMap = new Map(allProducts.map((p) => [p.product_code, p]));
    const groupedMap = new Map<string, ProductTypeDto[]>();
    const mappedProductCodes = new Set<string>();
    deptMappings.forEach((m) => {
      const p = productMap.get(m.product_code);
      if (!p) return;
      mappedProductCodes.add(p.product_code);
      const list = groupedMap.get(m.dept_code) ?? [];
      list.push(p);
      groupedMap.set(m.dept_code, list);
    });

    const groups: ProductGroup[] = Array.from(groupedMap.entries())
      .map(([deptCode, ps]) => ({
        deptCode,
        deptName: deptNameMap.get(deptCode) ?? "未命名部门",
        products: ps.sort((a, b) => a.product_code.localeCompare(b.product_code, "zh-CN")),
      }))
      .sort((a, b) => a.deptCode.localeCompare(b.deptCode, "zh-CN"));

    const unmapped = allProducts
      .filter((p) => !mappedProductCodes.has(p.product_code))
      .sort((a, b) => a.product_code.localeCompare(b.product_code, "zh-CN"));
    if (unmapped.length > 0) {
      groups.push({
        deptCode: "UNMAPPED",
        deptName: "未映射部门",
        products: unmapped,
      });
    }
    setProductGroups(groups);
  };

  const loadBudgetData = async () => {
    if (!selectedProduct || !sessionVersionId) return;
    setLoading(true);
    try {
      const budgetUrl = `/api/budget-input?product_code=${encodeURIComponent(
        selectedProduct.product_code
      )}&budget_actual=0&version_id=${sessionVersionId}`;
      const actualUrl = `/api/budget-input?product_code=${encodeURIComponent(
        selectedProduct.product_code
      )}&budget_actual=1&version_id=${sessionVersionId}`;
      const mergeRows = (
        budgetRows: BudgetInputRowDto[],
        actualRows: BudgetInputRowDto[]
      ): DualMetricRow[] => {
        const keyOf = (row: BudgetInputRowDto) =>
          `${row.report_code ?? "UNMAPPED"}|${row.data_acct_code}`;
        const budgetMap = new Map(budgetRows.map((r) => [keyOf(r), r]));
        const actualMap = new Map(actualRows.map((r) => [keyOf(r), r]));
        const orderedKeys = [
          ...budgetRows.map((r) => keyOf(r)),
          ...actualRows.map((r) => keyOf(r)).filter((k) => !budgetMap.has(k)),
        ];
        return orderedKeys.map((key) => {
          const budgetRow = budgetMap.get(key) ?? null;
          const actualRow = actualMap.get(key) ?? null;
          const base = budgetRow ?? actualRow!;
          const monthCount = Math.max(budgetRow?.values.length ?? 0, actualRow?.values.length ?? 0);
          const emptyErrors = Array.from({ length: monthCount }, () => null as string | null);
          return {
            rowKey: key,
            report_path: [...base.report_path],
            report_code: base.report_code,
            data_acct_code: base.data_acct_code,
            data_acct_name: base.data_acct_name,
            value_type: base.value_type,
            budget_values: budgetRow?.values ?? Array.from({ length: monthCount }, () => 0),
            actual_values: actualRow?.values ?? Array.from({ length: monthCount }, () => 0),
            budget_formula: budgetRow?.calc_formula ?? null,
            actual_formula: actualRow?.calc_formula ?? null,
            budget_formula_locked: Boolean(budgetRow?.formula_locked),
            actual_formula_locked: Boolean(actualRow?.formula_locked),
            budget_formula_errors: budgetRow?.formula_errors ?? emptyErrors,
            actual_formula_errors: actualRow?.formula_errors ?? emptyErrors,
          };
        });
      };
      let [budgetResp, actualResp] = await Promise.all([
        apiGet<BudgetInputLoadResponseDto>(budgetUrl),
        apiGet<BudgetInputLoadResponseDto>(actualUrl),
      ]);
      setRows(mergeRows(budgetResp.rows, actualResp.rows));
      setPeriods(budgetResp.periods);
      setCurrentMonth(budgetResp.current_month);
      setDraftValues({});
      setEditingCell(null);

      if (!initialRecalcDoneRef.current) {
        initialRecalcDoneRef.current = true;
        await Promise.all([
          apiPost<BudgetInputWriteResultDto>(
            buildBudgetInputRecalculateUrl(selectedProduct.product_code, 0, sessionVersionId),
            {}
          ),
          apiPost<BudgetInputWriteResultDto>(
            buildBudgetInputRecalculateUrl(selectedProduct.product_code, 1, sessionVersionId),
            {}
          ),
        ]);
        [budgetResp, actualResp] = await Promise.all([
          apiGet<BudgetInputLoadResponseDto>(budgetUrl),
          apiGet<BudgetInputLoadResponseDto>(actualUrl),
        ]);
        setRows(mergeRows(budgetResp.rows, actualResp.rows));
        setPeriods(budgetResp.periods);
        setCurrentMonth(budgetResp.current_month);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        await loadSession();
        await loadProductContext();
      } catch (e) {
        alert(e instanceof Error ? `初始化部门费用数据维护失败：${e.message}` : "初始化失败");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onSnapshotChanged = () => {
      void Promise.all([loadSession(), loadProductContext()]).catch(() => {
        /* 系统设定切换版本后刷新会话，失败时由后续加载提示 */
      });
    };
    window.addEventListener("budget-version-snapshot-changed", onSnapshotChanged);
    return () => {
      window.removeEventListener("budget-version-snapshot-changed", onSnapshotChanged);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadBudgetData().catch((e) =>
      alert(e instanceof Error ? `加载部门费用数据失败：${e.message}` : "加载失败")
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProduct?.product_code, sessionVersionId]);

  useEffect(() => {
    initialRecalcDoneRef.current = false;
  }, [selectedProduct?.product_code, sessionVersionId]);

  useEffect(() => {
    if (selectedProduct && sessionVersionId) {
      unmountSnapshotRef.current = {
        productCode: selectedProduct.product_code,
        versionId: sessionVersionId,
      };
    }
  }, [selectedProduct, sessionVersionId]);

  useEffect(() => {
    return () => {
      const snap = unmountSnapshotRef.current;
      if (!snap) return;
      void Promise.all([
        apiPost<BudgetInputWriteResultDto>(
          buildBudgetInputRecalculateUrl(snap.productCode, 0, snap.versionId),
          {}
        ),
        apiPost<BudgetInputWriteResultDto>(
          buildBudgetInputRecalculateUrl(snap.productCode, 1, snap.versionId),
          {}
        ),
      ]).catch(() => {
        /* 离开界面时静默尝试重算，失败不打扰 */
      });
    };
  }, []);

  const selectedDeptPath = useMemo(() => {
    if (!selectedProduct) return [];
    const deptCode = deptMappings.find((item) => item.product_code === selectedProduct.product_code)?.dept_code;
    if (!deptCode) return [];
    return buildDeptPath(
      deptCode,
      new Map(deptAccounts.map((item) => [item.dept_code, item]))
    );
  }, [deptAccounts, deptMappings, selectedProduct]);
  const selectedDeptLabel = selectedDeptPath.length > 0 ? selectedDeptPath.join(" > ") : "未映射部门";
  const selectedDeptLevel1 = selectedDeptPath[0] ?? "未映射部门";
  const selectedDeptLevel2 = selectedDeptPath[1] ?? "";

  const filteredRows = useMemo(() => {
    const keywords = splitSearchKeywords(searchText);
    if (!keywords.length) return rows;
    const deptText = selectedDeptLabel.toLowerCase();
    return rows.filter((row) => {
      const reportText = row.report_path.join(" > ").toLowerCase();
      const dataAcctCode = row.data_acct_code.toLowerCase();
      const dataAcctName = row.data_acct_name.toLowerCase();
      return keywords.some(
        (kw) =>
          reportText.includes(kw) ||
          deptText.includes(kw) ||
          dataAcctCode.includes(kw) ||
          dataAcctName.includes(kw)
      );
    });
  }, [rows, searchText, selectedDeptLabel]);

  const preparedRows = useMemo<PreparedBudgetRow[]>(() => {
    return filteredRows.map((row, idx) => {
      const reportLevels = row.report_path.map(parseReportLevel);
      const currentKeys = reportLevels.map((lvl) => (lvl.code ? `${lvl.code}|${lvl.name}` : lvl.name));
      const prev = filteredRows[idx - 1];
      if (!prev) {
        return {
          ...row,
          reportLevels,
          visibleLevelFlags: reportLevels.map(() => true),
        };
      }
      const prevLevels = prev.report_path.map(parseReportLevel);
      const prevKeys = prevLevels.map((lvl) => (lvl.code ? `${lvl.code}|${lvl.name}` : lvl.name));
      let changedAt = -1;
      const maxLen = Math.max(currentKeys.length, prevKeys.length);
      for (let i = 0; i < maxLen; i += 1) {
        if ((currentKeys[i] ?? "") !== (prevKeys[i] ?? "")) {
          changedAt = i;
          break;
        }
      }
      const visibleLevelFlags =
        changedAt === -1
          ? reportLevels.map(() => false)
          : reportLevels.map((_, i) => i >= changedAt);
      return {
        ...row,
        reportLevels,
        visibleLevelFlags,
      };
    });
  }, [filteredRows]);

  const valueTypeByDataCode = useMemo(() => {
    return new Map(rows.map((row) => [row.data_acct_code, row.value_type]));
  }, [rows]);
  const budgetRowByDataCode = useMemo(() => {
    return new Map(rows.map((row) => [row.data_acct_code, row]));
  }, [rows]);
  const actualRowByDataCode = useMemo(() => {
    return new Map(rows.map((row) => [row.data_acct_code, row]));
  }, [rows]);
  const periodIndexById = useMemo(() => {
    return new Map(periods.map((p, idx) => [p.period_id, idx]));
  }, [periods]);
  const gridRows = useMemo<GridCell[][]>(() => {
    return preparedRows.map((row) =>
      periods.map((p) => {
        const metric: ValueMetric = p.month_index < currentMonth ? "actual" : "budget";
        const formulaLocked = metric === "budget" ? row.budget_formula_locked : row.actual_formula_locked;
        return {
          rowKey: row.rowKey,
          periodId: p.period_id,
          metric,
          editable: !formulaLocked,
        };
      })
    );
  }, [preparedRows, periods, currentMonth]);
  const findCellPosition = (rowKey: string, periodId: number): { rowIndex: number; colIndex: number } | null => {
    for (let r = 0; r < gridRows.length; r += 1) {
      const c = gridRows[r].findIndex((cell) => cell.rowKey === rowKey && cell.periodId === periodId);
      if (c >= 0) return { rowIndex: r, colIndex: c };
    }
    return null;
  };
  const findNextHorizontalEditable = (
    rowIndex: number,
    colIndex: number,
    step: 1 | -1
  ): EditingCell | null => {
    if (!gridRows.length) return null;
    let r = rowIndex;
    let c = colIndex + step;
    while (r >= 0 && r < gridRows.length) {
      while (c >= 0 && c < periods.length) {
        const candidate = gridRows[r][c];
        if (candidate?.editable) {
          return { rowKey: candidate.rowKey, periodId: candidate.periodId, metric: candidate.metric };
        }
        c += step;
      }
      r += step;
      c = step > 0 ? 0 : periods.length - 1;
    }
    return null;
  };
  const findNextVerticalEditable = (
    rowIndex: number,
    colIndex: number,
    step: 1 | -1
  ): EditingCell | null => {
    let r = rowIndex + step;
    while (r >= 0 && r < gridRows.length) {
      const candidate = gridRows[r]?.[colIndex];
      if (candidate?.editable) {
        return { rowKey: candidate.rowKey, periodId: candidate.periodId, metric: candidate.metric };
      }
      r += step;
    }
    return null;
  };

  const visibleProductGroups = useMemo(() => {
    const keywords = splitSearchKeywords(productSearch);
    if (!keywords.length) return productGroups;
    return productGroups
      .map((g) => ({
        ...g,
        products: g.products.filter(
          (p) =>
            keywords.some(
              (kw) => p.product_code.toLowerCase().includes(kw) || p.product_name.toLowerCase().includes(kw)
            )
        ),
      }))
      .filter((g) => g.products.length > 0);
  }, [productGroups, productSearch]);

  const getDisplayNumber = (
    rowKey: string,
    periodId: number,
    metric: ValueMetric,
    valueType: string,
    fallback: number
  ): string => {
    const key = draftKey(rowKey, periodId, metric);
    if (draftValues[key] !== undefined) return draftValues[key];
    return formatStoredValue(fallback, valueType);
  };

  const saveCell = async (
    rowKey: string,
    dataCode: string,
    periodId: number,
    rawValue: string,
    valueType: string,
    metric: ValueMetric
  ) => {
    if (!sessionVersionId) return false;
    const value = parseStoredValueInput(rawValue, valueType);
    const payload: BudgetInputCellUpsertDto = {
      data_acct_code: dataCode,
      product_code: selectedProduct.product_code,
      period_id: periodId,
      version_id: sessionVersionId,
      budget_actual: metric === "budget" ? 0 : 1,
      value,
    };
    try {
      await apiPost<BudgetInputWriteResultDto>("/api/budget-input/cell", payload);
      const periodIdx = periodIndexById.get(periodId);
      if (periodIdx !== undefined && periodIdx >= 0) {
        setRows((prev) =>
          prev.map((row) => {
            if (row.rowKey !== rowKey) return row;
            if (metric === "budget") {
              const nextValues = [...row.budget_values];
              nextValues[periodIdx] = value;
              return { ...row, budget_values: nextValues };
            }
            const nextValues = [...row.actual_values];
            nextValues[periodIdx] = value;
            return { ...row, actual_values: nextValues };
          })
        );
      }
      setDraftValues((prev) => {
        const key = draftKey(rowKey, periodId, metric);
        if (prev[key] === undefined) return prev;
        const next = { ...prev };
        delete next[key];
        return next;
      });
      return true;
    } catch (e) {
      alert(e instanceof Error ? e.message : "单元格保存失败");
      setTimeout(() => {
        const id = `budget-input-${metric}-${rowKey.replace(/[^a-zA-Z0-9_-]/g, "_")}-${periodId}`;
        const el = document.getElementById(id) as HTMLInputElement | null;
        el?.focus();
        el?.select();
      }, 0);
      return false;
    }
  };
  const saveCellAndMove = async (
    rowKey: string,
    dataCode: string,
    periodId: number,
    rawValue: string,
    valueType: string,
    metric: ValueMetric,
    nextCell: EditingCell | null
  ) => {
    const ok = await saveCell(rowKey, dataCode, periodId, rawValue, valueType, metric);
    if (ok) setEditingCell(nextCell);
  };

  const recalculateAndRefresh = async () => {
    if (!selectedProduct || !sessionVersionId) return;
    try {
      await Promise.all([
        apiPost<BudgetInputWriteResultDto>(
          buildBudgetInputRecalculateUrl(selectedProduct.product_code, 0, sessionVersionId),
          {}
        ),
        apiPost<BudgetInputWriteResultDto>(
          buildBudgetInputRecalculateUrl(selectedProduct.product_code, 1, sessionVersionId),
          {}
        ),
      ]);
      await loadBudgetData();
    } catch (e) {
      alert(e instanceof Error ? `全局计算失败：${e.message}` : "全局计算失败");
    }
  };

  const rowFormulaHint = (row: DualMetricRow, periodId: number, metric: ValueMetric): string => {
    const formula = metric === "budget" ? row.budget_formula : row.actual_formula;
    const formulaLocked = metric === "budget" ? row.budget_formula_locked : row.actual_formula_locked;
    if (!formulaLocked || !formula) return "";
    const periodIdx = periodIndexById.get(periodId);
    const refMap = metric === "budget" ? budgetRowByDataCode : actualRowByDataCode;
    const valueFormula = formula.replace(/<([A-Z]\d+)\s+[^>]+>/g, (_m, code: string) => {
      const refRow = refMap.get(code);
      const rawValue =
        refRow && periodIdx !== undefined && periodIdx >= 0
          ? (metric === "budget" ? refRow.budget_values[periodIdx] : refRow.actual_values[periodIdx]) ?? 0
          : 0;
      const refValueType = refRow?.value_type ?? valueTypeByDataCode.get(code) ?? "金额";
      return formatStoredValue(rawValue, refValueType);
    });
    const finalValue =
      periodIdx !== undefined && periodIdx >= 0
        ? formatStoredValue(
            (metric === "budget" ? row.budget_values[periodIdx] : row.actual_values[periodIdx]) ?? 0,
            row.value_type
          )
        : formatStoredValue(0, row.value_type);
    const errors = metric === "budget" ? row.budget_formula_errors : row.actual_formula_errors;
    const formulaError = periodIdx !== undefined && periodIdx >= 0 ? errors?.[periodIdx] ?? null : null;
    if (formulaError) {
      return `公式：${formula}\n\n数值：${valueFormula}\n\n错误：${formulaError}`;
    }
    return `公式：${formula}\n\n数值：${valueFormula} = ${finalValue}`;
  };

  const monthWindowHint = (() => {
    const X = currentMonth;
    if (X === 13) return "当前月份窗口 13：全年按实际值口径录入";
    if (X <= 1) return "当前月份窗口 1：全年按预算值口径录入";
    return `当前月份窗口 ${X}：${X} 月前录入实际值，${X} 月及之后录入预算值`;
  })();

  const reportW = colWidth("report", REPORT_COL_WIDTH);
  const deptLevel1W = colWidth("dept-level1", DEPT_LEVEL1_COL_WIDTH);
  const deptLevel2W = colWidth("dept-level2", DEPT_LEVEL2_COL_WIDTH);
  const dataW = colWidth("data", DATA_COL_WIDTH);
  const valueTW = colWidth("valueType", VALUE_TYPE_COL_WIDTH);
  const totalW = colWidth("total", 112);
  const periodsWidthSum = periods.reduce((s, p) => s + colWidth(`period-${p.period_id}`, 96), 0);
  const tableMinWidth = reportW + deptLevel1W + deptLevel2W + dataW + valueTW + periodsWidthSum + totalW;

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">
          部门费用数据维护
          {sessionYear ? `（${sessionYear}）` : ""}
          {sessionVersionId != null && sessionVersionId > 0
            ? ` · 版本 ${sessionVersionId}${sessionVersionName ? ` ${sessionVersionName}` : ""}`
            : ""}
        </h3>
        <span className="text-[11px] text-gray-500">{monthWindowHint}</span>
        <div className="flex-1" />
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索科目或部门内容"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-52 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          {searchText && (
            <button
              type="button"
              onClick={() => setSearchText("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
              title="清除搜索"
            >
              <X className="w-3.5 h-3.5 text-gray-500" />
            </button>
          )}
        </div>
        <div className="relative">
          <button
            onClick={() => setShowProductDialog((v) => !v)}
            className="flex items-center gap-2 px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            <Building2 className="w-3 h-3" />
            {selectedProduct ? (
              <>
                <span className="font-mono">{selectedProduct.product_code}</span>
                <span>{selectedProduct.product_name}</span>
              </>
            ) : (
              <span>请选择产品科目</span>
            )}
          </button>
          {showProductDialog && (
            <div
              ref={dialogRef}
              className="absolute right-0 top-full mt-1 bg-white border border-gray-300 rounded shadow-lg z-50 w-96 max-h-96 overflow-auto"
            >
              <div className="px-3 py-2 bg-gray-100 border-b border-gray-300 sticky top-0 z-10">
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-medium text-gray-800">选择产品科目</h4>
                  <div className="flex-1" />
                  <div className="relative w-48">
                    <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                      value={productSearch}
                      onChange={(e) => setProductSearch(e.target.value)}
                      placeholder="搜索产品..."
                      className="pl-7 pr-7 py-1 text-xs border border-gray-300 rounded w-full"
                    />
                    {productSearch && (
                      <button
                        type="button"
                        onClick={() => setProductSearch("")}
                        className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
                      >
                        <X className="w-3 h-3 text-gray-500" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
              <div className="p-2">
                {visibleProductGroups.map((group) => (
                  <div key={group.deptCode} className="mb-2">
                    <div className="px-2 py-1 bg-blue-50 text-xs font-medium text-gray-700">
                      {group.deptCode === "UNMAPPED"
                        ? group.deptName
                        : `${group.deptCode} ${group.deptName}`}
                    </div>
                    {group.products.map((prod) => (
                      <div
                        key={prod.product_code}
                        onClick={() => {
                          setSelectedProduct(prod);
                          setShowProductDialog(false);
                        }}
                        className="px-4 py-1.5 hover:bg-gray-100 cursor-pointer flex items-center gap-2"
                      >
                        <DatabaseIcon className="w-3 h-3 text-green-600" />
                        <span className="font-mono text-xs text-gray-700">{prod.product_code}</span>
                        <span className="text-xs text-gray-700">{prod.product_name}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <button
          type="button"
          disabled={!sessionVersionId}
          onClick={() => setShowExcelDialog(true)}
          className="flex items-center gap-1 px-3 py-1 text-xs rounded bg-[#27ae60] text-white hover:bg-[#229954] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Upload className="w-3 h-3" />
          Excel上传数据
        </button>
        <button
          onClick={() => void recalculateAndRefresh()}
          className="flex items-center gap-1 px-3 py-1 text-xs rounded bg-[#3498db] text-white hover:bg-[#2980b9]"
        >
          <RefreshCw className="w-3 h-3" />
          全局计算并刷新
        </button>
      </div>

      <div className="flex-1 border border-gray-300 rounded overflow-auto" style={{ maxHeight: "calc(100vh - 200px)" }}>
        <table className="text-xs border-collapse" style={{ minWidth: `${Math.max(1200, tableMinWidth)}px` }}>
          <thead className="bg-gray-100 border-b border-gray-300 sticky top-0 z-20">
            <tr>
              <th
                className="relative px-2 py-1 pr-2.5 text-left align-bottom text-gray-700 font-medium border-r border-gray-200 sticky top-0 left-0 bg-gray-100 z-30"
                style={colStyle("report", REPORT_COL_WIDTH)}
              >
                报告科目
                <ColumnResizeHandle
                  onResizeStart={(e) => beginColumnResize("report", e, REPORT_COL_WIDTH)}
                />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-left align-bottom text-gray-700 font-medium border-r-2 border-gray-400 sticky top-0 bg-gray-100 z-30"
                style={{
                  left: `${reportW}px`,
                  ...colStyle("dept-level1", DEPT_LEVEL1_COL_WIDTH),
                }}
              >
                一级部门
                <ColumnResizeHandle
                  onResizeStart={(e) => beginColumnResize("dept-level1", e, DEPT_LEVEL1_COL_WIDTH)}
                />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-left align-bottom text-gray-700 font-medium border-r-2 border-gray-400 sticky top-0 bg-gray-100 z-30"
                style={{
                  left: `${reportW + deptLevel1W}px`,
                  ...colStyle("dept-level2", DEPT_LEVEL2_COL_WIDTH),
                }}
              >
                二级部门
                <ColumnResizeHandle
                  onResizeStart={(e) => beginColumnResize("dept-level2", e, DEPT_LEVEL2_COL_WIDTH)}
                />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-left align-bottom text-gray-700 font-medium border-r-2 border-gray-400 sticky top-0 bg-gray-100 z-30"
                style={{
                  left: `${reportW + deptLevel1W + deptLevel2W}px`,
                  ...colStyle("data", DATA_COL_WIDTH),
                }}
              >
                数据科目
                <ColumnResizeHandle
                  onResizeStart={(e) => beginColumnResize("data", e, DATA_COL_WIDTH)}
                />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-left align-bottom text-gray-700 font-medium border-r-2 border-gray-400 sticky top-0 bg-gray-100 z-30"
                style={{
                  left: `${reportW + deptLevel1W + deptLevel2W + dataW}px`,
                  ...colStyle("valueType", VALUE_TYPE_COL_WIDTH),
                }}
              >
                数值类型
                <ColumnResizeHandle
                  onResizeStart={(e) => beginColumnResize("valueType", e, VALUE_TYPE_COL_WIDTH)}
                />
              </th>
              {periods.map((p) => {
                const metric: ValueMetric = p.month_index < currentMonth ? "actual" : "budget";
                return (
                  <th
                    key={`period-${p.period_id}`}
                    className="relative px-2 py-1 pr-2.5 text-center text-gray-700 font-medium border-r border-gray-200 sticky top-0 bg-gray-100 z-20"
                    style={colStyle(`period-${p.period_id}`, 96)}
                  >
                    {metric === "actual" ? "实际" : "预算"}
                    {p.month_label}
                    <ColumnResizeHandle
                      onResizeStart={(e) => beginColumnResize(`period-${p.period_id}`, e, 96)}
                    />
                  </th>
                );
              })}
              <th
                className="relative px-2 py-1 pr-2.5 text-center text-gray-700 font-medium sticky top-0 right-0 bg-gray-100 z-30 border-l-2 border-gray-400"
                style={colStyle("total", 112)}
              >
                全年滚动合计
                <ColumnResizeHandle
                  onResizeStart={(e) => beginColumnResize("total", e, 112)}
                />
              </th>
            </tr>
          </thead>
          <tbody className="bg-white">
            {loading ? (
              <tr>
                <td colSpan={periods.length + 6} className="px-2 py-6 text-center text-gray-500">
                  正在从数据库加载部门费用数据...
                </td>
              </tr>
            ) : preparedRows.length === 0 ? (
              <tr>
                <td colSpan={periods.length + 6} className="px-2 py-6 text-center text-gray-500">
                  当前产品暂无可录入部门费用数据。
                </td>
              </tr>
            ) : (
              preparedRows.map((row) => {
                const rowKey = row.rowKey;
                const rollingTotal = periods.reduce((sum, p, idx) => {
                  const metric: ValueMetric = p.month_index < currentMonth ? "actual" : "budget";
                  const metricValues = metric === "budget" ? row.budget_values : row.actual_values;
                  const current = parseStoredValueInput(
                    getDisplayNumber(rowKey, p.period_id, metric, row.value_type, metricValues[idx] ?? 0),
                    row.value_type
                  );
                  return sum + current;
                }, 0);
                return (
                  <tr
                    key={rowKey}
                    style={rowStyle(rowKey)}
                    className="border-b border-gray-200 hover:bg-gray-50"
                  >
                    <td
                      className="relative px-2 py-0.5 pb-1.5 border-r border-gray-200 sticky left-0 bg-gray-50 z-20"
                      style={colStyle("report", REPORT_COL_WIDTH)}
                    >
                      <div className="text-xs text-gray-700">
                        {row.reportLevels.some((_, idx) => row.visibleLevelFlags[idx]) ? (
                          row.reportLevels.map((lvl, idx) =>
                            row.visibleLevelFlags[idx] ? (
                              <div key={`${rowKey}-report-${idx}`} className="py-0.5" style={{ paddingLeft: `${idx}rem` }}>
                                {lvl.code ? (
                                  <>
                                    <span className="font-mono text-[10px] text-gray-600">{lvl.code}</span>
                                    <span className={`ml-1 ${idx === 0 ? "font-medium" : ""}`}>{lvl.name}</span>
                                  </>
                                ) : (
                                  <span className={idx === 0 ? "font-medium" : ""}>{lvl.name}</span>
                                )}
                              </div>
                            ) : null
                          )
                        ) : (
                          <div className="py-0.5 text-transparent select-none">.</div>
                        )}
                      </div>
                      <TableRowResizeHandle
                        onResizeStart={(e) => beginResize(rowKey, e, () => (e.currentTarget as HTMLElement).closest("tr"))}
                      />
                    </td>
                    <td
                      className="px-2 py-0.5 border-r-2 border-gray-300 sticky bg-gray-50 z-20 align-bottom"
                      style={{
                        left: `${reportW}px`,
                        ...colStyle("dept-level1", DEPT_LEVEL1_COL_WIDTH),
                      }}
                      title={selectedDeptLabel}
                    >
                      <div className="truncate text-xs text-gray-700">{selectedDeptLevel1}</div>
                    </td>
                    <td
                      className="px-2 py-0.5 border-r-2 border-gray-300 sticky bg-gray-50 z-20 align-bottom"
                      style={{
                        left: `${reportW + deptLevel1W}px`,
                        ...colStyle("dept-level2", DEPT_LEVEL2_COL_WIDTH),
                      }}
                      title={selectedDeptLabel}
                    >
                      <div className="truncate text-xs text-gray-700">{selectedDeptLevel2}</div>
                    </td>
                    <td
                      className="px-2 py-0.5 border-r-2 border-gray-300 sticky bg-gray-50 z-20 align-bottom"
                      style={{
                        left: `${reportW + deptLevel1W + deptLevel2W}px`,
                        ...colStyle("data", DATA_COL_WIDTH),
                      }}
                    >
                      <div className="text-xs text-gray-700">
                        <span className="font-mono text-[10px] text-gray-600">{row.data_acct_code}</span>
                        <span className="ml-1 truncate">{row.data_acct_name}</span>
                      </div>
                    </td>
                    <td
                      className="px-2 py-0.5 border-r-2 border-gray-300 sticky bg-gray-50 z-20 align-bottom"
                      style={{
                        left: `${reportW + deptLevel1W + deptLevel2W + dataW}px`,
                        ...colStyle("valueType", VALUE_TYPE_COL_WIDTH),
                      }}
                    >
                      <span className="text-gray-700">{row.value_type}</span>
                    </td>
                    {periods.map((p, idx) => {
                      const metric: ValueMetric = p.month_index < currentMonth ? "actual" : "budget";
                      const formulaLocked =
                        metric === "budget" ? row.budget_formula_locked : row.actual_formula_locked;
                      const formulaErrors =
                        metric === "budget" ? row.budget_formula_errors : row.actual_formula_errors;
                      const metricValues = metric === "budget" ? row.budget_values : row.actual_values;
                      const formulaError = formulaErrors?.[idx] ?? null;
                      const currentValue = formulaError
                        ? formulaError
                        : getDisplayNumber(rowKey, p.period_id, metric, row.value_type, metricValues[idx] ?? 0);
                      const active =
                        editingCell?.rowKey === rowKey &&
                        editingCell.periodId === p.period_id &&
                        editingCell.metric === metric;
                      const cellWritable = !formulaLocked;
                      const inputId = `budget-input-${metric}-${rowKey.replace(/[^a-zA-Z0-9_-]/g, "_")}-${p.period_id}`;
                      return (
                        <td
                          key={`${rowKey}-${p.period_id}`}
                          className={`px-1 py-0.5 border-r border-gray-200 align-bottom ${
                            formulaLocked
                              ? formulaError
                                ? "bg-gray-100"
                                : "bg-gray-100 text-gray-500"
                              : ""
                          }`}
                          style={colStyle(`period-${p.period_id}`, 96)}
                          title={rowFormulaHint(row, p.period_id, metric)}
                        >
                          {active ? (
                            <input
                              id={inputId}
                              value={currentValue}
                              onChange={(e) =>
                                setDraftValues((prev) => ({
                                  ...prev,
                                  [draftKey(rowKey, p.period_id, metric)]: e.target.value,
                                }))
                              }
                              onBlur={(e) =>
                                void (async () => {
                                  if (skipNextBlurRef.current) {
                                    skipNextBlurRef.current = false;
                                    return;
                                  }
                                  const ok = await saveCell(
                                    rowKey,
                                    row.data_acct_code,
                                    p.period_id,
                                    e.target.value,
                                    row.value_type,
                                    metric
                                  );
                                  if (ok) setEditingCell(null);
                                })()
                              }
                              onKeyDown={(e) => {
                                const pos = findCellPosition(rowKey, p.period_id);
                                if (!pos) return;
                                const caretStart = e.currentTarget.selectionStart ?? 0;
                                const caretEnd = e.currentTarget.selectionEnd ?? 0;
                                const valueLength = e.currentTarget.value.length;
                                const hasSelection = caretStart !== caretEnd;
                                let nextCell: EditingCell | null = null;
                                if (e.key === "Enter") {
                                  nextCell =
                                    findNextVerticalEditable(pos.rowIndex, pos.colIndex, 1) ??
                                    findNextHorizontalEditable(pos.rowIndex, pos.colIndex, 1);
                                } else if (e.key === "Tab") {
                                  nextCell = findNextHorizontalEditable(
                                    pos.rowIndex,
                                    pos.colIndex,
                                    e.shiftKey ? -1 : 1
                                  );
                                } else if (e.key === "ArrowDown") {
                                  nextCell = findNextVerticalEditable(pos.rowIndex, pos.colIndex, 1);
                                } else if (e.key === "ArrowUp") {
                                  nextCell = findNextVerticalEditable(pos.rowIndex, pos.colIndex, -1);
                                } else if (
                                  e.key === "ArrowRight" &&
                                  !hasSelection &&
                                  caretEnd === valueLength
                                ) {
                                  nextCell = findNextHorizontalEditable(pos.rowIndex, pos.colIndex, 1);
                                } else if (e.key === "ArrowLeft" && !hasSelection && caretStart === 0) {
                                  nextCell = findNextHorizontalEditable(pos.rowIndex, pos.colIndex, -1);
                                }
                                if (!nextCell) return;
                                e.preventDefault();
                                skipNextBlurRef.current = true;
                                void saveCellAndMove(
                                  rowKey,
                                  row.data_acct_code,
                                  p.period_id,
                                  e.currentTarget.value,
                                  row.value_type,
                                  metric,
                                  nextCell
                                );
                              }}
                              onFocus={(e) => {
                                e.currentTarget.select();
                              }}
                              className="w-full px-1 py-0.5 text-right border border-blue-400 rounded"
                              autoFocus
                            />
                          ) : (
                            <div
                              role="button"
                              tabIndex={cellWritable ? 0 : -1}
                              onClick={() => {
                                if (!cellWritable) return;
                                setEditingCell({
                                  rowKey,
                                  periodId: p.period_id,
                                  metric,
                                });
                              }}
                              onFocus={() => {
                                if (!cellWritable) return;
                                setEditingCell({
                                  rowKey,
                                  periodId: p.period_id,
                                  metric,
                                });
                              }}
                              onKeyDown={(e) =>
                                e.key === "Enter" &&
                                cellWritable &&
                                setEditingCell({
                                  rowKey,
                                  periodId: p.period_id,
                                  metric,
                                })
                              }
                              className={`text-right rounded px-1 ${
                                !cellWritable
                                  ? formulaError
                                    ? "cursor-not-allowed text-red-600 font-semibold"
                                    : "cursor-not-allowed"
                                  : "cursor-text hover:bg-blue-50"
                              }`}
                            >
                              {currentValue}
                            </div>
                          )}
                        </td>
                      );
                    })}
                    <td
                      className="px-2 py-0.5 text-right font-medium sticky right-0 bg-gray-100 border-l-2 border-gray-300 align-bottom"
                      style={colStyle("total", 112)}
                    >
                      {formatStoredValue(rollingTotal, row.value_type)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <BudgetInputExcelUploadDialog
        isOpen={showExcelDialog}
        onClose={() => setShowExcelDialog(false)}
        versionId={sessionVersionId}
        onImportComplete={() => void loadBudgetData()}
      />
    </div>
  );
}
