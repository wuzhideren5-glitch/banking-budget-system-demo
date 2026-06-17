import { type DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { Download, GripVertical, RefreshCw, Search, X } from "lucide-react";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableColumnWidths } from "@/lib/shared/useTableColumnWidths";
import { useTableRowHeights } from "@/lib/shared/useTableRowHeights";
import { ColumnResizeHandle } from "@/app/components/common/ColumnResizeHandle";
import { TableRowResizeHandle } from "@/app/components/common/TableRowResizeHandle";
import {
  downloadPivotSummaryExport,
  fetchBudgetSummaryAggregate,
  fetchCompareSummaryAggregate,
  type PivotSummaryAggregateRequestDto,
  type PivotSummaryExportRequestDto,
} from "@/lib/org-product/pivotSummaryApi";
import { getSession } from "@/lib/system/systemApi";
import { type AgentPivotSuggestionDto } from "@/lib/agent/agentApi";
import {
  buildFieldOptionsMap,
  buildPivotResult,
  filterPivotRows,
  formatPivotValue,
  getFieldValue,
  getPivotFields,
  pickLatestVersionOption,
  resolveDisplayKindFromStats,
  resolveSelectionValueFromOptions,
  splitSearchKeywords,
  type DropZone,
  type PivotDataSource,
  type PivotField,
  type PivotSummaryRow,
} from "@/app/components/pivotTableModel";

const BUDGET_PIVOT_KEY_BASE = "budget_pivot_settings_v1";
const COMPARE_PIVOT_KEY_BASE = "budget_pivot_compare_settings_v1";
const PIVOT_APPLY_EVENT_BUDGET = "budget-agent-apply-pivot-suggestion";
const PIVOT_APPLY_EVENT_COMPARE = "budget-agent-apply-pivot-suggestion-compare";

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
  const allFields = useMemo(() => getPivotFields(dataSource), [dataSource]);
  const [initialPivotState] = useState(() => {
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingCompareVersionAutoSelectRef = useRef(false);
  const aggregateRequestKey = JSON.stringify({
    row: rowFields.map((f) => f.id),
    column: columnFields.map((f) => f.id),
    page: pageFields.map((f) => f.id),
    search: searchText,
  });
  const lastLoadedAggregateKeyRef = useRef("");

  const buildAggregatePayload = (): PivotSummaryAggregateRequestDto => ({
    row_field_ids: rowFields.map((f) => f.id),
    column_field_ids: columnFields.map((f) => f.id),
    page_field_ids: pageFields.map((f) => f.id),
    page_selections: pageFieldSelections,
    pivot_search_text: searchText,
  });

  const loadSummary = async (syncFirst = false) => {
    setLoading(true);
    setError(null);
    try {
      if (dataSource === "budget") {
        const session = await getSession();
        setBudgetYear(session.budget_year);
        try {
          const rows = await fetchBudgetSummaryAggregate(buildAggregatePayload());
          if (rows.length > 0) {
            setCurrentMonthWindow(rows[0].current_month ?? null);
          }
          setSummaryRuleHint(rows[0]?.rule_message || "读取多维聚合表；如数据未更新，请先在“预算事实刷新跑批”执行跑批。");
          setSummaryRows(rows);
          lastLoadedAggregateKeyRef.current = aggregateRequestKey;
          setPageFieldSelections((prev) => {
            if (prev.version_display === undefined || prev.version_display === "全部") return prev;
            return { ...prev, version_display: "全部" };
          });
        } catch (e) {
          const msg = e instanceof Error ? e.message : "";
          if (msg.includes("Not Found") || msg.includes("404")) {
            throw new Error("预算透视聚合服务未加载，请重启后端服务加载最新代码。");
          }
          throw e;
        }
      } else {
        if (!syncFirst) {
          setSummaryRuleHint("读取多年度对比聚合表；如展示版本或底层数据已变化，请先在“预算事实刷新跑批”执行跑批。");
        }
        const rows = await fetchCompareSummaryAggregate(buildAggregatePayload());
        setSummaryRows(rows);
        lastLoadedAggregateKeyRef.current = aggregateRequestKey;
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载数据透视数据失败");
      setSummaryRows([]);
    } finally {
      setLoading(false);
    }
  };

  const buildExportPayload = (): PivotSummaryExportRequestDto => ({
    row_field_ids: rowFields.map((f) => f.id),
    column_field_ids: columnFields.map((f) => f.id),
    page_field_ids: pageFields.map((f) => f.id),
    page_selections: pageFieldSelections,
    show_row_total: showRowTotal,
    show_column_total: showColumnTotal,
    pivot_search_text: searchText,
  });

  const downloadExportFile = async () => {
    const proceed = confirm(
      "即将导出Excel文件。\n\n默认会保存到浏览器设置的下载目录（通常为系统“下载”文件夹）。\n如果你在浏览器中配置了其它下载路径，将保存到你配置的位置。\n\n是否继续导出？"
    );
    if (!proceed) return;
    try {
      await downloadPivotSummaryExport(dataSource, buildExportPayload());
    } catch (e) {
      alert(e instanceof Error ? e.message : "导出失败");
    }
  };

  const handleExportFullPivot = async () => {
    await downloadExportFile();
  };

  useEffect(() => {
    void loadSummary(dataSource === "compare");
  }, [dataSource]);

  useEffect(() => {
    if (!summaryRows.length) return;
    if (lastLoadedAggregateKeyRef.current === aggregateRequestKey) return;
    const timer = window.setTimeout(() => {
      void loadSummary(false);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [aggregateRequestKey]);

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
    const applySuggestion = (suggestion: AgentPivotSuggestionDto | null | undefined) => {
      if (!suggestion) return;
      const nextRow = toFields(suggestion.row_field_ids, "dimension");
      const nextCol = toFields(suggestion.column_field_ids, "dimension");
      const nextPage = toFields(suggestion.page_field_ids, "dimension");
      const nextValue = toFields(suggestion.value_field_ids, "measure");
      const used = new Set([...nextRow, ...nextCol, ...nextPage, ...nextValue].map((f) => f.id));
      const nextPool = allFields.filter((f) => !used.has(f.id));
      const allowedPage = new Set(nextPage.map((f) => f.id));
      const optionsMap = buildFieldOptionsMap(allFields, summaryRows);
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

  const searchableFieldIds = useMemo(
    () => allFields.filter((f) => f.type === "dimension").map((f) => f.id),
    [allFields],
  );

  const fieldOptionsMap = useMemo(() => buildFieldOptionsMap(allFields, summaryRows), [allFields, summaryRows]);

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

  const filteredRows = useMemo(
    () =>
      filterPivotRows({
        rows: summaryRows,
        pageFields,
        pageFieldSelections,
        searchText,
        searchableFieldIds,
        fieldOptionsMap,
      }),
    [summaryRows, pageFields, pageFieldSelections, searchText, searchableFieldIds, fieldOptionsMap],
  );

  const pivotResult = useMemo(
    () =>
      buildPivotResult({
        rows: filteredRows,
        rowFields,
        columnFields,
        valueFields,
      }),
    [filteredRows, rowFields, columnFields, valueFields],
  );

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
      className="bb-grid-chip cursor-grab active:cursor-grabbing group"
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
        className="bb-grid-chip cursor-grab active:cursor-grabbing group"
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
      className="border border-dashed border-[var(--bb-border)] rounded p-1.5 min-h-[50px] bg-[var(--bb-bg-subtle)]"
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
    <div className="bb-page">
      <div className="mb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col">
            <div className="flex items-center gap-3">
              <h3 className="bb-page-title">{budgetTitle}</h3>
              {currentMonthHintText && (
                <div className="text-[11px] text-gray-600 whitespace-nowrap">{currentMonthHintText}</div>
              )}
            </div>
            {loading && (
              <span className="bb-page-subtitle">
                {dataSource === "budget" ? "正在读取预算聚合表..." : "正在读取对比聚合表..."}
              </span>
            )}
          </div>
          <div className="flex items-center justify-end gap-2 ml-auto">
            <button
              type="button"
              onClick={() => void loadSummary(dataSource === "compare")}
              className="bb-btn bb-btn-warning"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              刷新聚合视图
            </button>
            <button
              type="button"
              onClick={() => void handleExportFullPivot()}
              className="bb-btn bb-btn-primary"
            >
              <Download className="w-3.5 h-3.5" />
              导出当前透视聚合结果
            </button>
          </div>
        </div>
        {error && <div className="mt-1 text-xs text-red-600">{error}</div>}
      </div>

      <div className="grid grid-cols-[40%_1fr] items-start gap-4 mb-3">
        <div className="flex flex-col">
          <div
            onDragOver={handleDragOver}
            onDrop={() => handleDrop('pool')}
            className="bb-panel p-2 max-h-[32vh] overflow-auto"
          >
            <div className="bb-panel-title mb-2">字段列表</div>
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
                  className="bb-input w-full pl-7 pr-7"
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

      <div className="bb-table-wrap bb-table-wrap-fill">
        <div className="p-3">
          <div className="bb-panel-title mb-2">数据透视表视图</div>

          {!loading && summaryRows.length > 0 && valueFields.length > 0 ? (
            <table className="bb-table bb-table-dense">
              <thead >
                {pivotResult.colHeaderRows.map((headerRow, headerIdx) => (
                  <tr key={`col-header-${headerIdx}`}>
                    {headerIdx === 0 &&
                      pivotResult.rowFieldDefs.map((f) => (
                        <th
                          key={`row-field-${f.id}`}
                          rowSpan={pivotResult.colHeaderRows.length}
                          className="relative pr-2.5"
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
                        className="relative pr-2.5 text-center bg-[var(--bb-primary-soft)]"
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
                        className={`bb-text-cell ${!item.isLeaf ? "font-medium" : ""} ${
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
                          className={`bb-cell-number font-mono text-gray-700 ${!item.isLeaf ? "font-medium" : ""}`}
                          style={colStyle(`ck-${ck}`, 96)}
                        >
                          {formatPivotValue(value, kind)}
                        </td>
                      );
                    })}
                    {showColumnTotal && (
                      <td
                        className="bb-cell-number font-mono text-gray-700 bg-blue-50 font-medium"
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
                      className="bb-text-cell font-medium"
                      colSpan={pivotResult.rowFieldDefs.length}
                    >
                      合计
                    </td>
                    {pivotResult.colKeys.map((ck) => (
                      <td
                        key={`total-${ck}`}
                        className="bb-cell-number font-mono text-gray-700 font-medium"
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
                        className="bb-cell-number font-mono text-gray-700 font-medium"
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
            <div className="py-12 text-center text-xs text-[var(--bb-text-muted)]">
              {loading
                ? (dataSource === "budget" ? "正在读取预算聚合表，请稍候..." : "正在读取对比聚合表，请稍候...")
                : (dataSource === "budget"
                  ? "暂无可用聚合数据，请先在预算事实刷新跑批中生成聚合表。"
                  : "暂无可用对比聚合数据，请先在预算事实刷新跑批中同步并生成聚合表。")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// 智能分析报告内容
