import { type DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { Download, GripVertical, RefreshCw, Search, X } from "lucide-react";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableColumnWidths } from "@/lib/useTableColumnWidths";
import { useTableRowHeights } from "@/lib/useTableRowHeights";
import { ColumnResizeHandle } from "./ColumnResizeHandle";
import { TableRowResizeHandle } from "./TableRowResizeHandle";
import {
  apiGet,
  apiPost,
  type AgentPivotSuggestionDto,
  type BudgetSummaryRebuildResultDto,
  type BudgetSummaryRowDto,
  type CompareSummarySyncResultDto,
  type CompareSummaryRowDto,
  type SessionInfo,
  buildApiUrl,
} from "../../lib/api";

interface PivotField {
  id: string;
  name: string;
  type: 'dimension' | 'measure';
}

type DropZone = 'pool' | 'row' | 'column' | 'page' | 'value';
const BUDGET_PIVOT_KEY_BASE = "budget_pivot_settings_v1";
const COMPARE_PIVOT_KEY_BASE = "budget_pivot_compare_settings_v1";
const PIVOT_APPLY_EVENT_BUDGET = "budget-agent-apply-pivot-suggestion";
const PIVOT_APPLY_EVENT_COMPARE = "budget-agent-apply-pivot-suggestion-compare";

function migratePivotKeyFromGlobalToUser(scopedKey: string, globalBase: string) {
  try {
    if (localStorage.getItem(scopedKey) != null) return;
    const g = localStorage.getItem(globalBase);
    if (g) {
      localStorage.setItem(scopedKey, g);
      localStorage.removeItem(globalBase);
    }
  } catch {
    // ignore
  }
}

type PersistedPivotSettings = {
  rowFieldIds?: string[];
  columnFieldIds?: string[];
  pageFieldIds?: string[];
  valueFieldIds?: string[];
  showRowTotal?: boolean;
  showColumnTotal?: boolean;
  pageFieldSelections?: Record<string, string>;
  /** 仅 code，多关键词 OR */
  pivotSearchText?: string;
};

type PivotDataSource = "budget" | "compare";
type PivotSummaryRow = BudgetSummaryRowDto | CompareSummaryRowDto;
type PivotValueDisplayKind = "amount" | "percent";
type PivotValueFormatStats = { amount: number; percent: number };

function splitSearchKeywords(raw: string): string[] {
  return raw
    .toLowerCase()
    .split(/[\s,，;；/\\]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function resolveSelectionValueFromOptions(
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

function detectValueDisplayKind(valueType: string): PivotValueDisplayKind {
  const t = String(valueType || "").trim();
  if (!t) return "amount";
  if (/(%|百分|占比|比率|比例|收益率|利率|费率|率)/.test(t)) return "percent";
  return "amount";
}

function addFormatStats(target: PivotValueFormatStats, kind: PivotValueDisplayKind) {
  if (kind === "percent") {
    target.percent += 1;
  } else {
    target.amount += 1;
  }
}

function resolveDisplayKindFromStats(stats: PivotValueFormatStats | undefined): PivotValueDisplayKind {
  if (!stats) return "amount";
  return stats.percent > 0 && stats.amount === 0 ? "percent" : "amount";
}

function formatPivotValue(value: number, kind: PivotValueDisplayKind): string {
  if (kind === "percent") {
    const scaled = Math.abs(value) <= 1 ? value * 100 : value;
    return `${scaled.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  }
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function parseVersionIdFromDisplay(text: string): number | null {
  const m = String(text || "").match(/版本号[:：]\s*(\d{1,12})/);
  if (!m) return null;
  const v = Number(m[1]);
  return Number.isFinite(v) ? v : null;
}

function pickLatestVersionOption(options: string[]): string | null {
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

export function PivotTableContent({ dataSource = "budget" }: { dataSource?: PivotDataSource }) {
  const storagePfx = useUserStorageKeyPrefix();
  const tableLayoutId = (suffix: string) => `${storagePfx}::${suffix}`;
  const settingsBaseKey = dataSource === "budget" ? BUDGET_PIVOT_KEY_BASE : COMPARE_PIVOT_KEY_BASE;
  const settingsStorageKey = `${settingsBaseKey}__${storagePfx}`;
  const { rowStyle, beginResize } = useTableRowHeights(tableLayoutId(`pivot-table-${dataSource}`), {
    minHeight: 22,
    maxHeight: 200,
  });
  const { colStyle, beginColumnResize } = useTableColumnWidths(tableLayoutId(`pivot-table-${dataSource}-cols`), {
    minWidth: 48,
    maxWidth: 480,
  });
  const allFields: PivotField[] = dataSource === "budget"
    ? [
    { id: "report_level1", name: "报告科目1级", type: "dimension" },
    { id: "report_level2", name: "报告科目2级", type: "dimension" },
    { id: "report_level3", name: "报告科目3级", type: "dimension" },
    { id: "report_level4", name: "报告科目4级", type: "dimension" },
    { id: "report_level5", name: "报告科目5级", type: "dimension" },
    { id: "dept_level1", name: "部门科目1级", type: "dimension" },
    { id: "dept_level2", name: "部门科目2级", type: "dimension" },
    { id: "dept_level3", name: "部门科目3级", type: "dimension" },
    { id: "data_code_name", name: "数据科目", type: "dimension" },
    { id: "product_code_name", name: "产品科目", type: "dimension" },
    { id: "year", name: "年度", type: "dimension" },
    { id: "month", name: "月份", type: "dimension" },
    { id: "quarter", name: "季度", type: "dimension" },
    { id: "budget_actual", name: "预算/实际", type: "dimension" },
    { id: "version_display", name: "版本号及名称", type: "dimension" },
    { id: "value_type", name: "数值类型", type: "dimension" },
    { id: "value", name: "预算数值", type: "measure" },
    ]
    : [
    { id: "version_display", name: "版本号及名称", type: "dimension" },
    { id: "report_level1", name: "报告科目1级", type: "dimension" },
    { id: "report_level2", name: "报告科目2级", type: "dimension" },
    { id: "report_level3", name: "报告科目3级", type: "dimension" },
    { id: "report_level4", name: "报告科目4级", type: "dimension" },
    { id: "report_level5", name: "报告科目5级", type: "dimension" },
    { id: "dept_level1", name: "部门科目1级", type: "dimension" },
    { id: "dept_level2", name: "部门科目2级", type: "dimension" },
    { id: "dept_level3", name: "部门科目3级", type: "dimension" },
    { id: "data_code_name", name: "数据科目", type: "dimension" },
    { id: "product_code_name", name: "产品科目", type: "dimension" },
    { id: "year", name: "年度", type: "dimension" },
    { id: "month", name: "月份", type: "dimension" },
    { id: "quarter", name: "季度", type: "dimension" },
    { id: "budget_actual", name: "预算/实际", type: "dimension" },
    { id: "value_type", name: "数值类型", type: "dimension" },
    { id: "value", name: "预算数值", type: "measure" },
    ];
  const [initialPivotState] = useState(() => {
    migratePivotKeyFromGlobalToUser(settingsStorageKey, settingsBaseKey);
    const byId = new Map(allFields.map((f) => [f.id, f]));
    const toFields = (ids: string[] | undefined, expected: PivotField["type"]) => {
      if (!ids?.length) return [] as PivotField[];
      const seen = new Set<string>();
      const out: PivotField[] = [];
      for (const id of ids) {
        if (!id || seen.has(id)) continue;
        const field = byId.get(id);
        if (!field || field.type !== expected) continue;
        seen.add(id);
        out.push(field);
      }
      return out;
    };

    try {
      const raw = localStorage.getItem(settingsStorageKey);
      if (!raw) throw new Error("empty");
      const saved = JSON.parse(raw) as PersistedPivotSettings;
      const row = toFields(saved.rowFieldIds, "dimension");
      const column = toFields(saved.columnFieldIds, "dimension");
      const page = toFields(saved.pageFieldIds, "dimension");
      const value = toFields(saved.valueFieldIds, "measure");
      const usedIds = new Set([...row, ...column, ...page, ...value].map((f) => f.id));
      const pool = allFields.filter((f) => !usedIds.has(f.id));
      const allowedPageIds = new Set(page.map((f) => f.id));
      const selections = Object.fromEntries(
        Object.entries(saved.pageFieldSelections ?? {}).filter(([k]) => allowedPageIds.has(k)),
      );
      return {
        rowFields: row,
        columnFields: column,
        pageFields: page,
        valueFields: value,
        fieldPool: pool,
        showRowTotal: saved.showRowTotal ?? true,
        showColumnTotal: saved.showColumnTotal ?? true,
        pageFieldSelections: selections,
        pivotSearchText: typeof saved.pivotSearchText === "string" ? saved.pivotSearchText : "",
      };
    } catch {
      return {
        rowFields: [] as PivotField[],
        columnFields: [] as PivotField[],
        pageFields: [] as PivotField[],
        valueFields: [] as PivotField[],
        fieldPool: allFields,
        showRowTotal: true,
        showColumnTotal: true,
        pageFieldSelections: {} as Record<string, string>,
        pivotSearchText: "",
      };
    }
  });

  const [rowFields, setRowFields] = useState<PivotField[]>(initialPivotState.rowFields);
  const [columnFields, setColumnFields] = useState<PivotField[]>(initialPivotState.columnFields);
  const [pageFields, setPageFields] = useState<PivotField[]>(initialPivotState.pageFields);
  const [valueFields, setValueFields] = useState<PivotField[]>(initialPivotState.valueFields);
  const [fieldPool, setFieldPool] = useState<PivotField[]>(initialPivotState.fieldPool);
  const [showRowTotal, setShowRowTotal] = useState(initialPivotState.showRowTotal);
  const [showColumnTotal, setShowColumnTotal] = useState(initialPivotState.showColumnTotal);
  const [searchText, setSearchText] = useState(() => {
    return typeof initialPivotState.pivotSearchText === "string" ? initialPivotState.pivotSearchText : "";
  });
  const [draggedField, setDraggedField] = useState<PivotField | null>(null);
  const [dragSource, setDragSource] = useState<DropZone | null>(null);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [pageFieldSelections, setPageFieldSelections] = useState<Record<string, string>>(initialPivotState.pageFieldSelections);
  const [summaryRows, setSummaryRows] = useState<PivotSummaryRow[]>([]);
  const [summaryRuleHint, setSummaryRuleHint] = useState<string | null>(null);
  const [budgetYear, setBudgetYear] = useState<number | null>(null);
  const [currentMonthWindow, setCurrentMonthWindow] = useState<number | null>(null);
  const [currentVersionId, setCurrentVersionId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportProgressOpen, setExportProgressOpen] = useState(false);
  const [exportProgressText, setExportProgressText] = useState("准备导出...");
  const [exportProgressDone, setExportProgressDone] = useState(0);
  const [exportProgressTotal, setExportProgressTotal] = useState(0);
  const [exportProgressPercent, setExportProgressPercent] = useState(0);
  const [exportProgressStatus, setExportProgressStatus] = useState<"queued" | "running" | "done" | "error">("queued");
  const exportProgressTimerRef = useRef<number | null>(null);
  const exportProgressStartAtRef = useRef<number>(0);
  const pendingCompareVersionAutoSelectRef = useRef(false);

  const stopExportProgressTimer = () => {
    if (exportProgressTimerRef.current != null) {
      window.clearInterval(exportProgressTimerRef.current);
      exportProgressTimerRef.current = null;
    }
  };

  const startExportProgressTimer = () => {
    stopExportProgressTimer();
    exportProgressStartAtRef.current = Date.now();
    exportProgressTimerRef.current = window.setInterval(() => {
      const elapsedMs = Date.now() - exportProgressStartAtRef.current;
      const t = Math.max(0, Math.min(1, elapsedMs / 60000));
      // 前快后慢：ease-out quadratic，60秒到95%。
      const eased = 1 - (1 - t) * (1 - t);
      const percent = eased * 95;
      setExportProgressPercent((prev) => Math.max(prev, percent));
    }, 200);
  };

  const loadSummary = async (syncFirst = false) => {
    setLoading(true);
    setError(null);
    try {
      if (dataSource === "budget") {
        const session = await apiGet<SessionInfo>("/api/session");
        setBudgetYear(session.budget_year);
        setCurrentVersionId(session.version_id);
        const rebuildResult = await apiPost<BudgetSummaryRebuildResultDto>(
          `/api/budget-summary/rebuild?version_id=${session.version_id}`,
          {},
        );
        setCurrentMonthWindow(rebuildResult.current_month ?? null);
        setSummaryRuleHint(rebuildResult.rule_message || null);
        try {
          const rows = await apiGet<BudgetSummaryRowDto[]>("/api/budget-summary");
          if (rows.length > 0) {
            setCurrentMonthWindow(rows[0].current_month ?? rebuildResult.current_month ?? null);
          }
          if (!rebuildResult.rule_message && rows.length > 0 && rows[0].rule_message) {
            setSummaryRuleHint(rows[0].rule_message);
          }
          setSummaryRows(rows);
          setPageFieldSelections((prev) => {
            if (prev.version_display === undefined || prev.version_display === "全部") return prev;
            return { ...prev, version_display: "全部" };
          });
        } catch (e) {
          const msg = e instanceof Error ? e.message : "";
          if (msg.includes("Not Found")) {
            throw new Error("后端缺少 /api/budget-summary/rebuild 接口，请重启后端服务加载最新代码。");
          }
          throw e;
        }
      } else {
        if (!syncFirst) {
          setSummaryRuleHint("可点击“同步并刷新”查看各展示层级版本与 current_month 口径。");
        }
        if (syncFirst) {
          const syncResult = await apiPost<CompareSummarySyncResultDto>(
            "/api/compare-summary/sync?trigger_source=manual",
            {},
          );
          setSummaryRuleHint(
            syncResult.rule_message || "同步完成，但未获取到展示层级口径说明。",
          );
        }
        const rows = await apiGet<CompareSummaryRowDto[]>("/api/compare-summary");
        setSummaryRows(rows);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载数据透视数据失败");
      setSummaryRows([]);
    } finally {
      setLoading(false);
    }
  };

  const buildExportPayload = () => ({
    row_field_ids: rowFields.map((f) => f.id),
    column_field_ids: columnFields.map((f) => f.id),
    page_field_ids: pageFields.map((f) => f.id),
    page_selections: pageFieldSelections,
    show_row_total: showRowTotal,
    show_column_total: showColumnTotal,
  });

  const downloadExportFile = async (endpoint: string, fallbackName: string) => {
    const proceed = confirm(
      "即将导出Excel文件。\n\n默认会保存到浏览器设置的下载目录（通常为系统“下载”文件夹）。\n如果你在浏览器中配置了其它下载路径，将保存到你配置的位置。\n\n是否继续导出？"
    );
    if (!proceed) return;
    try {
      const resp = await fetch(buildApiUrl(endpoint), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildExportPayload()),
      });
      if (!resp.ok) throw new Error((await resp.text()) || "导出失败");
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") ?? "";
      const fnMatch = cd.match(/filename="?([^"]+)"?/i);
      const fileName = fnMatch?.[1] || fallbackName;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "导出失败");
    }
  };

  const handleExportFullPivot = async () => {
    const endpoint =
      dataSource === "budget" ? "/api/budget-summary/export-full-pivot" : "/api/compare-summary/export-full-pivot";
    const filename =
      dataSource === "budget" ? "budget_summary_full_pivot.xlsx" : "compare_summary_full_pivot.xlsx";
    await downloadExportFile(endpoint, filename);
  };

  const handleExportFormulaWorkbook = async () => {
    if (dataSource !== "budget") {
      alert("多年度对比透视的带公式导出将于后续版本提供。");
      return;
    }
    const endpoint =
      currentVersionId != null
        ? `/api/budget-summary/export-formula-workbook?version_id=${encodeURIComponent(String(currentVersionId))}`
        : "/api/budget-summary/export-formula-workbook";
    await downloadExportFile(endpoint, "budget_summary_formula_workbook.xlsx");
  };
  const handleExportAllShowYearsFormulaWorkbook = async () => {
    if (dataSource !== "compare") return;
    const proceed = confirm(
      "即将导出所有展示年度带公式Excel。\n\n工作表较多时可能需要等待一段时间，将显示实时进度。\n\n是否继续导出？"
    );
    if (!proceed) return;
    setExportProgressOpen(true);
    setExportProgressText("正在创建导出任务...");
    setExportProgressDone(0);
    setExportProgressTotal(0);
    setExportProgressPercent(0);
    setExportProgressStatus("queued");
    startExportProgressTimer();
    try {
      const startResp = await fetch(buildApiUrl("/api/compare-summary/export-formula-workbook/start"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildExportPayload()),
      });
      if (!startResp.ok) throw new Error((await startResp.text()) || "创建导出任务失败");
      const startData = (await startResp.json()) as { job_id?: string };
      const jobId = (startData.job_id || "").trim();
      if (!jobId) throw new Error("导出任务ID为空");

      let finished = false;
      while (!finished) {
        const statusResp = await fetch(
          buildApiUrl(`/api/compare-summary/export-formula-workbook/status?job_id=${encodeURIComponent(jobId)}`),
          { method: "GET", credentials: "include" }
        );
        if (!statusResp.ok) throw new Error((await statusResp.text()) || "读取导出进度失败");
        const statusData = (await statusResp.json()) as {
          status?: string;
          processed_sheets?: number;
          total_sheets?: number;
          message?: string;
          error?: string;
        };
        const done = Number(statusData.processed_sheets || 0);
        const total = Number(statusData.total_sheets || 0);
        const status = (statusData.status || "running") as "queued" | "running" | "done" | "error";
        setExportProgressStatus(status);
        setExportProgressDone(done);
        setExportProgressTotal(total);
        setExportProgressText(statusData.message || "正在导出...");
        if (statusData.status === "done") {
          stopExportProgressTimer();
          setExportProgressPercent(100);
          finished = true;
          break;
        }
        if (statusData.status === "error") {
          throw new Error(statusData.error || statusData.message || "导出失败");
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }

      setExportProgressText("正在下载文件...");
      const downloadResp = await fetch(
        buildApiUrl(`/api/compare-summary/export-formula-workbook/download?job_id=${encodeURIComponent(jobId)}`),
        { method: "GET", credentials: "include" }
      );
      if (!downloadResp.ok) throw new Error((await downloadResp.text()) || "下载导出文件失败");
      const blob = await downloadResp.blob();
      const cd = downloadResp.headers.get("Content-Disposition") ?? "";
      const fnMatch = cd.match(/filename="?([^"]+)"?/i);
      const fileName = fnMatch?.[1] || "compare_summary_formula_workbook.xlsx";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);
      setExportProgressText("导出完成");
      setExportProgressPercent(100);
      setTimeout(() => setExportProgressOpen(false), 500);
    } catch (e) {
      stopExportProgressTimer();
      setExportProgressOpen(false);
      alert(e instanceof Error ? e.message : "导出失败");
    }
  };

  useEffect(() => {
    return () => {
      stopExportProgressTimer();
    };
  }, []);

  useEffect(() => {
    void loadSummary(dataSource === "compare");
  }, [dataSource]);

  useEffect(() => {
    if (dataSource !== "budget") return;
    const removeYear = (fields: PivotField[]) => fields.filter((f) => f.id !== "year");
    setRowFields((prev) => removeYear(prev));
    setColumnFields((prev) => removeYear(prev));
  }, [dataSource]);

  useEffect(() => {
    const onSnapshotChanged = () => {
      void loadSummary(dataSource === "compare");
    };
    window.addEventListener("budget-version-snapshot-changed", onSnapshotChanged);
    return () => {
      window.removeEventListener("budget-version-snapshot-changed", onSnapshotChanged);
    };
  }, [dataSource, loadSummary]);

  useEffect(() => {
    const pageFieldIdSet = new Set(pageFields.map((f) => f.id));
    const cleanedSelections = Object.fromEntries(
      Object.entries(pageFieldSelections).filter(([k]) => pageFieldIdSet.has(k)),
    );
    localStorage.setItem(
      settingsStorageKey,
      JSON.stringify({
        rowFieldIds: rowFields.map((f) => f.id),
        columnFieldIds: columnFields.map((f) => f.id),
        pageFieldIds: pageFields.map((f) => f.id),
        valueFieldIds: valueFields.map((f) => f.id),
        showRowTotal,
        showColumnTotal,
        pageFieldSelections: cleanedSelections,
        pivotSearchText: searchText,
      } satisfies PersistedPivotSettings),
    );
    if (Object.keys(cleanedSelections).length !== Object.keys(pageFieldSelections).length) {
      setPageFieldSelections(cleanedSelections);
    }
  }, [rowFields, columnFields, pageFields, valueFields, showRowTotal, showColumnTotal, pageFieldSelections, searchText, settingsStorageKey]);

  useEffect(() => {
    const byId = new Map(allFields.map((f) => [f.id, f]));
    const toFields = (ids: string[] | undefined, expected: PivotField["type"]): PivotField[] => {
      const out: PivotField[] = [];
      const seen = new Set<string>();
      for (const id of ids ?? []) {
        if (!id || seen.has(id)) continue;
        const field = byId.get(id);
        if (!field || field.type !== expected) continue;
        out.push(field);
        seen.add(id);
      }
      return out;
    };
    const buildFieldOptionsMap = (): Record<string, string[]> => {
      const map: Record<string, string[]> = {};
      for (const field of allFields) {
        if (field.type !== "dimension") continue;
        const values = new Set<string>();
        for (const row of summaryRows) {
          values.add(getFieldValue(row, field.id));
        }
        map[field.id] = ["全部", ...Array.from(values).sort()];
      }
      return map;
    };
    const applySuggestion = (suggestion: AgentPivotSuggestionDto | null | undefined) => {
      if (!suggestion) return;
      const nextRow = toFields(suggestion.row_field_ids, "dimension");
      const nextCol = toFields(suggestion.column_field_ids, "dimension");
      const nextPage = toFields(suggestion.page_field_ids, "dimension");
      const nextValue = toFields(suggestion.value_field_ids, "measure");
      const used = new Set([...nextRow, ...nextCol, ...nextPage, ...nextValue].map((f) => f.id));
      const nextPool = allFields.filter((f) => !used.has(f.id));
      const allowedPage = new Set(nextPage.map((f) => f.id));
      const optionsMap = buildFieldOptionsMap();
      const cleanedSelections = Object.fromEntries(
        Object.entries(suggestion.page_selections ?? {})
          .filter(([k]) => allowedPage.has(k))
          .map(([k, v]) => [k, resolveSelectionValueFromOptions(k, String(v ?? ""), optionsMap, true)]),
      );
      if (dataSource === "compare" && allowedPage.has("version_display")) {
        const rawVersionSelection = String((suggestion.page_selections ?? {}).version_display ?? "").trim();
        // 当 Agent 已明确给出版本筛选 token 时，避免被“自动选最新版本”覆盖。
        pendingCompareVersionAutoSelectRef.current =
          rawVersionSelection.length === 0 || rawVersionSelection === "全部";
      }
      setRowFields(nextRow);
      setColumnFields(nextCol);
      setPageFields(nextPage);
      setValueFields(nextValue.length > 0 ? nextValue : toFields(["value"], "measure"));
      setFieldPool(nextPool);
      setPageFieldSelections(cleanedSelections);
      const suggestedSearch = (suggestion.pivot_search_text ?? "").trim();
      if (suggestedSearch) {
        const keywords = splitSearchKeywords(suggestedSearch);
        const hasHit = summaryRows.some((row) => {
          const passPage = nextPage.every((f) => {
            const selected = cleanedSelections[f.id];
            if (!selected || selected === "全部") return true;
            const options = optionsMap[f.id] ?? ["全部"];
            if (!options.includes(selected)) return true;
            return getFieldValue(row, f.id) === selected;
          });
          if (!passPage) return false;
          const searchableValues = searchableFieldIds.map((fieldId) => getFieldValue(row, fieldId).toLowerCase());
          return keywords.some((kw) => searchableValues.some((v) => v.includes(kw)));
        });
        setSearchText(hasHit ? suggestedSearch : "");
      } else {
        setSearchText("");
      }
      if (dataSource === "compare") {
        void loadSummary(true);
      }
    };
    const onApply = (event: Event) => {
      const customEvent = event as CustomEvent<AgentPivotSuggestionDto | null>;
      applySuggestion(customEvent.detail);
    };
    const eventName = dataSource === "budget" ? PIVOT_APPLY_EVENT_BUDGET : PIVOT_APPLY_EVENT_COMPARE;
    window.addEventListener(eventName, onApply as EventListener);
    return () => {
      window.removeEventListener(eventName, onApply as EventListener);
    };
  }, [dataSource, allFields, summaryRows]);

  const getFieldValue = (row: PivotSummaryRow, fieldId: string): string => {
    switch (fieldId) {
      case "show_level":
        return "show_level" in row ? String(row.show_level) : "未设置";
      case "data_file_id":
        return "data_file_id" in row ? String(row.data_file_id) : "未设置";
      case "source_year":
        return "source_year" in row ? String(row.source_year) : "未设置";
      case "report_level1":
        return row.report_level1 ?? "未设置";
      case "report_level2":
        return row.report_level2 ?? "未设置";
      case "report_level3":
        return row.report_level3 ?? "未设置";
      case "report_level4":
        return row.report_level4 ?? "未设置";
      case "report_level5":
        return row.report_level5 ?? "未设置";
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
  };

  const searchableFieldIds = useMemo(
    () => allFields.filter((f) => f.type === "dimension").map((f) => f.id),
    [dataSource],
  );

  const fieldOptionsMap = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const field of allFields) {
      if (field.type !== "dimension") continue;
      const values = new Set<string>();
      for (const row of summaryRows) {
        values.add(getFieldValue(row, field.id));
      }
      map[field.id] = ["全部", ...Array.from(values).sort()];
    }
    return map;
  }, [summaryRows]);

  const getFieldOptions = (fieldId: string): string[] => fieldOptionsMap[fieldId] ?? ["全部"];

  useEffect(() => {
    const activePageIds = new Set(pageFields.map((f) => f.id));
    setPageFieldSelections((prev) => {
      let changed = false;
      const next: Record<string, string> = {};
      for (const [k, v] of Object.entries(prev)) {
        if (!activePageIds.has(k)) continue;
        const resolved = resolveSelectionValueFromOptions(k, String(v ?? ""), fieldOptionsMap, true);
        next[k] = resolved;
        if (resolved !== v) changed = true;
      }
      if (
        dataSource === "compare" &&
        activePageIds.has("version_display") &&
        pendingCompareVersionAutoSelectRef.current
      ) {
        const options = fieldOptionsMap.version_display ?? ["全部"];
        const current = String(next.version_display ?? "").trim();
        const isResolvedRealOption = !!current && current !== "全部" && options.includes(current);
        if (!isResolvedRealOption) {
          const preferred = pickLatestVersionOption(options);
          if (preferred && preferred !== current) {
            next.version_display = preferred;
            changed = true;
          }
        }
        pendingCompareVersionAutoSelectRef.current = false;
      }
      if (!changed && Object.keys(next).length === Object.keys(prev).length) return prev;
      return next;
    });
  }, [dataSource, fieldOptionsMap, pageFields]);

  const getFieldsForZone = (zone: DropZone): PivotField[] => {
    switch (zone) {
      case 'pool': return fieldPool;
      case 'row': return rowFields;
      case 'column': return columnFields;
      case 'page': return pageFields;
      case 'value': return valueFields;
      default: return [];
    }
  };

  const setFieldsForZone = (zone: DropZone, fields: PivotField[]) => {
    switch (zone) {
      case 'pool': setFieldPool(fields); break;
      case 'row': setRowFields(fields); break;
      case 'column': setColumnFields(fields); break;
      case 'page': setPageFields(fields); break;
      case 'value': setValueFields(fields); break;
    }
  };

  const handleDragStart = (field: PivotField, source: DropZone, index: number) => {
    setDraggedField(field);
    setDragSource(source);
    setDraggedIndex(index);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDrop = (targetZone: DropZone, targetIndex?: number) => {
    if (!draggedField || !dragSource) return;
    if (targetZone === "value" && draggedField.type !== "measure") {
      alert("数值字段区域只允许度量字段。");
      return;
    }
    if ((targetZone === "row" || targetZone === "column" || targetZone === "page") && draggedField.type !== "dimension") {
      alert("行/列/页字段区域只允许维度字段。");
      return;
    }

    const removeFromZone = (zone: DropZone, fieldId: string) => {
      const fields = getFieldsForZone(zone).filter((f) => f.id !== fieldId);
      setFieldsForZone(zone, fields);
    };

    const insertIntoZoneAt = (zone: DropZone, field: PivotField, insertIndex?: number) => {
      const deduped = getFieldsForZone(zone).filter((f) => f.id !== field.id);
      const idx = insertIndex == null ? deduped.length : Math.max(0, Math.min(insertIndex, deduped.length));
      const next = [...deduped.slice(0, idx), field, ...deduped.slice(idx)];
      setFieldsForZone(zone, next);
    };

    // Excel 数据透视规则：同一字段全局只能归属一个字段池
    removeFromZone("pool", draggedField.id);
    removeFromZone("row", draggedField.id);
    removeFromZone("column", draggedField.id);
    removeFromZone("page", draggedField.id);
    removeFromZone("value", draggedField.id);
    let insertIndex = targetIndex;
    if (dragSource === targetZone && draggedIndex != null && targetIndex != null && draggedIndex < targetIndex) {
      insertIndex = targetIndex - 1;
    }
    insertIntoZoneAt(targetZone, draggedField, insertIndex);

    setDraggedField(null);
    setDragSource(null);
    setDraggedIndex(null);
  };

  const removeFieldFromZone = (field: PivotField, zone: DropZone) => {
    const fields = getFieldsForZone(zone).filter(f => f.id !== field.id);
    setFieldsForZone(zone, fields);
    if (!fieldPool.some((f) => f.id === field.id)) {
      setFieldPool([...fieldPool, field]);
    }
  };

  const filteredRows = useMemo(() => {
    const keywords = splitSearchKeywords(searchText);
    return summaryRows.filter((row) => {
      const passPage = pageFields.every((f) => {
        const selected = pageFieldSelections[f.id];
        if (!selected || selected === "全部") return true;
        const options = fieldOptionsMap[f.id] ?? ["全部"];
        if (!options.includes(selected)) return true;
        return getFieldValue(row, f.id) === selected;
      });
      if (!passPage) return false;
      if (!keywords.length) return true;
      const searchableValues = searchableFieldIds.map((fieldId) => getFieldValue(row, fieldId).toLowerCase());
      return keywords.some((kw) => searchableValues.some((v) => v.includes(kw)));
    });
  }, [summaryRows, pageFields, pageFieldSelections, searchText, searchableFieldIds, fieldOptionsMap]);

  const pivotResult = useMemo(() => {
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

    const rowFieldDefs = rowFields.length ? rowFields : [{ id: "__all__", name: "行", type: "dimension" as const }];
    const defaultValueHeader = valueFields[0]?.name || "预算数值";
    const colFieldDefs = columnFields.length
      ? columnFields
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

    for (const row of filteredRows) {
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

    const rowNodes: Array<{
      key: string;
      level: number;
      path: string[];
      label: string;
      colMap: Map<string, number>;
      colFmtMap: Map<string, PivotValueFormatStats>;
      total: number;
      totalFmt: PivotValueFormatStats;
      isLeaf: boolean;
    }> = [];
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

    const colHeaderRows: Array<Array<{ key: string; label: string; span: number }>> = [];
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
  }, [filteredRows, rowFields, columnFields, valueFields]);

  const pivotColHeaderCanAlign =
    pivotResult.colHeaderRows.length > 0 &&
    (() => {
      const last = pivotResult.colHeaderRows[pivotResult.colHeaderRows.length - 1];
      return (
        last.length === pivotResult.colKeys.length && last.every((c) => c.span === 1)
      );
    })();

  const FieldItem = ({ field, zone, index, showRemove = false }: { field: PivotField; zone: DropZone; index: number; showRemove?: boolean }) => (
    <div
      draggable
      onDragStart={() => handleDragStart(field, zone, index)}
      onDragOver={handleDragOver}
      onDrop={() => handleDrop(zone, index)}
      className="inline-flex w-auto max-w-full items-center justify-start gap-1 px-2 py-1 bg-white border border-gray-300 rounded text-[11px] cursor-grab active:cursor-grabbing hover:bg-gray-50 group min-h-[30px]"
    >
      <GripVertical className="w-2.5 h-2.5 text-gray-400 flex-shrink-0" />
      <span className="whitespace-nowrap">{field.name}</span>
      {showRemove && (
        <button
          onClick={() => removeFieldFromZone(field, zone)}
          className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
        >
          <X className="w-2.5 h-2.5 text-gray-500 hover:text-red-600" />
        </button>
      )}
    </div>
  );

  const FieldItemWithDropdown = ({ field, zone, index }: { field: PivotField; zone: DropZone; index: number }) => {
    const options = getFieldOptions(field.id);
    const selectedValue = pageFieldSelections[field.id] || options[0] || "全部";

    return (
      <div
        draggable
        onDragStart={() => handleDragStart(field, zone, index)}
        onDragOver={handleDragOver}
        onDrop={() => handleDrop(zone, index)}
        className="inline-flex w-auto max-w-full items-center justify-start gap-1 px-2 py-1 bg-white border border-gray-300 rounded text-[11px] cursor-grab active:cursor-grabbing hover:bg-gray-50 group min-h-[30px]"
      >
        <GripVertical className="w-2.5 h-2.5 text-gray-400 flex-shrink-0" />
        <span className="text-gray-700 whitespace-nowrap">{field.name}:</span>
        <select
          value={selectedValue}
          onChange={(e) => setPageFieldSelections({ ...pageFieldSelections, [field.id]: e.target.value })}
          className="text-[11px] border-0 bg-transparent focus:outline-none cursor-pointer pr-1"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          {options.map(option => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <button
          onClick={() => removeFieldFromZone(field, zone)}
          className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
        >
          <X className="w-2.5 h-2.5 text-gray-500 hover:text-red-600" />
        </button>
      </div>
    );
  };

  const DropZoneBox = ({ zone, title, fields }: { zone: DropZone; title: string; fields: PivotField[] }) => (
    <div
      onDragOver={handleDragOver}
      onDrop={() => handleDrop(zone)}
      className="border-2 border-dashed border-gray-300 rounded p-1.5 min-h-[50px] bg-gray-50"
    >
      <div className="text-[11px] font-medium text-gray-700 mb-1">{title}</div>
      <div className="flex flex-wrap items-start gap-1">
        {fields.map((field, idx) => (
          zone === 'page' ? (
            <FieldItemWithDropdown key={field.id} field={field} zone={zone} index={idx} />
          ) : (
            <FieldItem key={field.id} field={field} zone={zone} index={idx} showRemove={true} />
          )
        ))}
        {fields.length === 0 && (
          <div className="text-[10px] text-gray-400 text-center py-1">拖拽字段到此处</div>
        )}
      </div>
    </div>
  );

  const monthFromRuleHint = useMemo(() => {
    if (!summaryRuleHint) return null;
    const match = summaryRuleHint.match(/current_month\s*=\s*(\d{1,2})/i);
    if (!match) return null;
    const month = Number(match[1]);
    if (!Number.isFinite(month) || month < 1 || month > 13) return null;
    return month;
  }, [summaryRuleHint]);
  const monthWindow = dataSource === "budget" ? (currentMonthWindow ?? monthFromRuleHint) : null;
  const currentMonthHintText =
    monthWindow != null
      ? `当前月份窗口为${monthWindow}月，${monthWindow}月之前为实际数，${monthWindow}月及之后为预算数`
      : null;

  const budgetTitle =
    dataSource === "budget"
      ? `当前可编辑年度多版本透视报表${budgetYear != null ? `（${budgetYear}）` : ""}`
      : "多年度对比透视报表";

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col">
            <div className="flex items-center gap-3">
              <h3 className="text-sm font-medium text-gray-800">{budgetTitle}</h3>
              {currentMonthHintText && (
                <div className="text-[11px] text-gray-600 whitespace-nowrap">{currentMonthHintText}</div>
              )}
            </div>
            {loading && (
              <span className="mt-1 text-xs text-gray-500">
                {dataSource === "budget" ? "正在重建 Data Summary..." : "正在加载 Compare Summary..."}
              </span>
            )}
          </div>
          <div className="flex items-center justify-end gap-2 ml-auto">
            <button
              type="button"
              onClick={() => void loadSummary(dataSource === "compare")}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded text-white bg-orange-500 hover:bg-orange-600"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {dataSource === "budget" ? "重新生成并刷新" : "同步并刷新"}
            </button>
            <button
              type="button"
              onClick={() => void handleExportFullPivot()}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded text-white bg-blue-500 hover:bg-blue-600"
            >
              <Download className="w-3.5 h-3.5" />
              导出该年度所有版本透视表
            </button>
            {dataSource === "compare" && (
              <button
                type="button"
                onClick={() => void handleExportAllShowYearsFormulaWorkbook()}
                className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded text-white bg-emerald-600 hover:bg-emerald-700"
              >
                <Download className="w-3.5 h-3.5" />
                导出所有展示年度带公式Excel
              </button>
            )}
            {dataSource === "budget" && (
              <button
                type="button"
                onClick={() => void handleExportFormulaWorkbook()}
                className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded text-white bg-green-500 hover:bg-green-600"
              >
                <Download className="w-3.5 h-3.5" />
                导出当前可编辑版本带公式Excel
              </button>
            )}
          </div>
        </div>
        {error && <div className="mt-1 text-xs text-red-600">{error}</div>}
      </div>
      {exportProgressOpen && (
        <div className="fixed inset-0 z-[100] bg-black/25 flex items-center justify-center">
          <div className="bg-white rounded border border-gray-300 shadow-xl w-[420px] p-4">
            <div className="text-sm font-medium text-gray-800 mb-2">正在导出所有展示年度带公式Excel</div>
            <div className="text-xs text-gray-600 mb-2">{exportProgressText}</div>
            <div className="w-full h-3 bg-gray-200 rounded overflow-hidden">
              <div
                className={`h-full bg-emerald-500 transition-all ${
                  exportProgressStatus === "done" || exportProgressStatus === "error" ? "" : "animate-pulse"
                }`}
                style={{
                  width: `${Math.max(0, Math.min(100, exportProgressPercent))}%`,
                }}
              />
            </div>
            <div className="mt-2 text-right text-xs text-gray-600">
              {exportProgressTotal > 0
                ? `${exportProgressDone}/${exportProgressTotal} 张工作表 · ${Math.round(exportProgressPercent)}%`
                : `正在准备工作表... ${Math.round(exportProgressPercent)}%`}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-[40%_1fr] items-start gap-4 mb-3">
        <div className="flex flex-col">
          <div
            onDragOver={handleDragOver}
            onDrop={() => handleDrop('pool')}
            className="border border-gray-300 rounded p-2 bg-white max-h-[32vh] overflow-auto"
          >
            <div className="text-xs font-medium text-gray-700 mb-2">字段列表</div>
            <div className="grid grid-cols-4 gap-1.5">
              {fieldPool.map((field, idx) => (
                <FieldItem key={field.id} field={field} zone="pool" index={idx} />
              ))}
            </div>
          </div>

          <div className="mt-2 grid grid-cols-1 gap-2 xl:grid-cols-[auto_minmax(0,1fr)] xl:items-center xl:gap-4">
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showRowTotal}
                  onChange={(e) => setShowRowTotal(e.target.checked)}
                  className="w-3.5 h-3.5"
                />
                显示行汇总
              </label>
              <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showColumnTotal}
                  onChange={(e) => setShowColumnTotal(e.target.checked)}
                  className="w-3.5 h-3.5"
                />
                显示列汇总
              </label>
            </div>
            <div className="flex items-center w-full xl:justify-self-end">
              <div className="relative w-full xl:w-[360px]">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                <input
                  className="w-full border border-gray-300 rounded px-7 pr-7 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="搜索（空格/逗号/分号/斜杠分隔，任一命中）"
                />
                {searchText && (
                  <button
                    type="button"
                    onClick={() => setSearchText("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    aria-label="清空搜索"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 max-h-[32vh] overflow-auto pr-1">
          <DropZoneBox zone="page" title="页字段" fields={pageFields} />
          <DropZoneBox zone="column" title="列字段" fields={columnFields} />
          <DropZoneBox zone="row" title="行字段" fields={rowFields} />
          <DropZoneBox zone="value" title="数值字段" fields={valueFields} />
        </div>
      </div>

      <div className="flex-1 border border-gray-300 rounded overflow-auto bg-white">
        <div className="p-3">
          <div className="text-xs font-medium text-gray-700 mb-2">数据透视表视图</div>

          {!loading && summaryRows.length > 0 && valueFields.length > 0 ? (
            <table className="text-xs border-collapse w-full">
              <thead className="bg-gray-100">
                {pivotResult.colHeaderRows.map((headerRow, headerIdx) => (
                  <tr key={`col-header-${headerIdx}`}>
                    {headerIdx === 0 &&
                      pivotResult.rowFieldDefs.map((f) => (
                        <th
                          key={`row-field-${f.id}`}
                          rowSpan={pivotResult.colHeaderRows.length}
                          className="relative border border-gray-300 px-2 py-1 pr-2.5 text-left font-medium text-gray-700"
                          style={colStyle(`rowfd-${f.id}`, 120)}
                        >
                          {f.name}
                          <ColumnResizeHandle
                            onResizeStart={(e) => beginColumnResize(`rowfd-${f.id}`, e, 120)}
                          />
                        </th>
                      ))}
                    {headerRow.map((cell, cellIdx) => {
                      const isLastColHeader = headerIdx === pivotResult.colHeaderRows.length - 1;
                      const ck =
                        pivotColHeaderCanAlign && isLastColHeader ? pivotResult.colKeys[cellIdx] : undefined;
                      const ckKey = ck !== undefined ? `ck-${ck}` : null;
                      return (
                        <th
                          key={`col-cell-${cell.key}`}
                          colSpan={cell.span}
                          className={`border border-gray-300 px-2 py-1 text-center font-medium text-gray-700 ${
                            ckKey ? "relative pr-2.5" : ""
                          }`}
                          style={ckKey ? colStyle(ckKey, 96) : undefined}
                        >
                          {cell.label}
                          {ckKey && (
                            <ColumnResizeHandle
                              onResizeStart={(e) => beginColumnResize(ckKey, e, 96)}
                            />
                          )}
                        </th>
                      );
                    })}
                    {headerIdx === 0 && showColumnTotal && (
                      <th
                        rowSpan={pivotResult.colHeaderRows.length}
                        className="relative border border-gray-300 px-2 py-1 pr-2.5 text-center font-medium text-gray-700 bg-blue-50"
                        style={colStyle("pivot-total", 88)}
                      >
                        合计
                        <ColumnResizeHandle
                          onResizeStart={(e) => beginColumnResize("pivot-total", e, 88)}
                        />
                      </th>
                    )}
                  </tr>
                ))}
              </thead>
              <tbody>
                {pivotResult.rowNodes.map((item) => (
                  <tr
                    key={item.key}
                    style={rowStyle(item.key)}
                    className={`${item.isLeaf ? "hover:bg-gray-50" : "bg-blue-50/40"}`}
                  >
                    {pivotResult.rowFieldDefs.map((f, idx) => (
                      <td
                        key={`${item.key}-rowdim-${idx}`}
                        className={`border border-gray-300 px-2 py-1 text-gray-700 ${!item.isLeaf ? "font-medium" : ""} ${
                          idx === 0 ? "relative pb-1.5" : ""
                        }`}
                        style={colStyle(`rowfd-${f.id}`, 120)}
                      >
                        {idx === item.level - 1 ? <span>{item.label}</span> : ""}
                        {idx === 0 && (
                          <TableRowResizeHandle
                            onResizeStart={(e) => beginResize(item.key, e)}
                          />
                        )}
                      </td>
                    ))}
                    {pivotResult.colKeys.map((ck) => {
                      const value = item.colMap.get(ck) ?? 0;
                      const kind = resolveDisplayKindFromStats(item.colFmtMap.get(ck));
                      return (
                        <td
                          key={`${item.key}-${ck}`}
                          className={`border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 ${!item.isLeaf ? "font-medium" : ""}`}
                          style={colStyle(`ck-${ck}`, 96)}
                        >
                          {formatPivotValue(value, kind)}
                        </td>
                      );
                    })}
                    {showColumnTotal && (
                      <td
                        className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 bg-blue-50 font-medium"
                        style={colStyle("pivot-total", 88)}
                      >
                        {formatPivotValue(item.total, resolveDisplayKindFromStats(item.totalFmt))}
                      </td>
                    )}
                  </tr>
                ))}
                {showRowTotal && (
                  <tr className="bg-blue-50">
                    <td
                      className="border border-gray-300 px-2 py-1 text-gray-700 font-medium"
                      colSpan={pivotResult.rowFieldDefs.length}
                    >
                      合计
                    </td>
                    {pivotResult.colKeys.map((ck) => (
                      <td
                        key={`total-${ck}`}
                        className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 font-medium"
                        style={colStyle(`ck-${ck}`, 96)}
                      >
                        {formatPivotValue(
                          pivotResult.colTotals.get(ck) ?? 0,
                          resolveDisplayKindFromStats(pivotResult.colTotalFmt.get(ck)),
                        )}
                      </td>
                    ))}
                    {showColumnTotal && (
                      <td
                        className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 font-medium"
                        style={colStyle("pivot-total", 88)}
                      >
                        {formatPivotValue(
                          pivotResult.grandTotal,
                          resolveDisplayKindFromStats(pivotResult.grandTotalFmt),
                        )}
                      </td>
                    )}
                  </tr>
                )}
              </tbody>
            </table>
          ) : (
            <div className="text-center py-12 text-gray-400 text-xs">
              {loading
                ? (dataSource === "budget" ? "正在重建 Data Summary，请稍候..." : "正在加载 Compare Summary，请稍候...")
                : (dataSource === "budget"
                  ? "暂无可用汇总数据，请先完成预算录入后再查看数据透视表。"
                  : "暂无可用对比数据，请先在系统设定中配置展示版本并刷新 compare 数据。")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// 智能分析报告内容
