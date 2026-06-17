import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Filter,
  FolderOpen,
  RefreshCw,
  Search,
  FileText,
  Download,
} from "lucide-react";
import {
  exportInputOutputTopicReport,
  getInputOutputTopicMeta,
  getInputOutputTopicReport,
  type InputOutputTopicMetaResponseDto,
  type InputOutputTopicReportResponseDto,
  type InputOutputTopicRowDto,
  type InputOutputTopicSectionType,
  type InputOutputTopicIndicatorFormat,
  type InputOutputTopicViewMode,
} from "@/lib/system/inputOutputTopicApi";
import { getOrgProductMetricSnapshot } from "@/lib/org-product/orgProductMetricApi";
import { deriveRuntimeRefFromOrgProductMetricCode } from "@/lib/org-product/orgProductMetricCode";

type ViewMode = InputOutputTopicViewMode;
type SectionType = InputOutputTopicSectionType;
type IndicatorFormatType = InputOutputTopicIndicatorFormat;
type RowDto = InputOutputTopicRowDto;
type OverviewMetaResponse = InputOutputTopicMetaResponseDto;
type OverviewReportResponse = InputOutputTopicReportResponseDto;

type TreeRowNode = RowDto & {
  depth: number;
  children: TreeRowNode[];
};

type VisibleTreeRow = TreeRowNode & {
  hasChildren: boolean;
  isExpanded: boolean;
};
type OrgProductMetricNodeDto = {
  code?: string;
  name?: string;
  children?: OrgProductMetricNodeDto[];
};
type OrgProductMetricSnapshotDto = {
  entities: Array<{
    entity_code: string;
    entity_name?: string;
    tables: Array<{
      table_name: string;
      metrics: OrgProductMetricNodeDto[];
    }>;
  }>;
};
type OrgProductMetricRef = {
  sourceRef: string;
  metricCode: string;
  metricName: string;
  dataAcctCode: string;
};

const SECTION_LABELS: Record<SectionType, string> = {
  indicator: "评估指标",
  input: "业务投入细项",
  output: "业务产出细项",
};

const MONTH_LABELS = Array.from({ length: 12 }, (_, index) => `${index + 1}月`);
const PRODUCT_SCOPE_STORAGE_KEY = "input_output_topic_overview_product_codes";

function readStoredProductCodes(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(PRODUCT_SCOPE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      : [];
  } catch {
    return [];
  }
}

function currentYearMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function alignReportMonthToYear(reportMonth: string, year: number): string {
  const monthPart = String(Math.min(Math.max(Number(reportMonth.split("-")[1] || 1), 1), 12)).padStart(2, "0");
  return `${year}-${monthPart}`;
}

function formatNumber(
  value: number | null | undefined,
  minimumFractionDigits = 2,
  maximumFractionDigits = 2
): string {
  if (value == null || Number.isNaN(value)) return "-";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits,
    maximumFractionDigits,
  });
}

function formatPercentFromRatio(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function formatValueByDisplayFormat(
  value: number | null | undefined,
  displayFormat: IndicatorFormatType
): string {
  if (displayFormat === "percent") {
    if (value == null || Number.isNaN(value)) return "-";
    return `${formatNumber(value, 2, 2)}%`;
  }
  if (displayFormat === "ratio") {
    return formatNumber(value, 4, 4);
  }
  return formatNumber(value);
}

function sectionExpandKey(blockKey: string, section: SectionType, id: number): string {
  return `${blockKey}:${section}:${id}`;
}

function normalizeCode(value: string | null | undefined): string {
  return String(value ?? "").trim().toUpperCase();
}

function parseOrgProductRefLabel(rawLabel: string, dataAcctCode: string): OrgProductMetricRef {
  const label = String(rawLabel || "").trim();
  const parts = label.split(":");
  if (parts.length >= 3) {
    const entityCode = normalizeCode(parts[0]);
    const tableName = parts[1];
    const metricText = parts.slice(2).join(":").trim();
    const [metricCodeRaw, ...metricNameParts] = metricText.split(/\s+/);
    const metricCode = normalizeCode(metricCodeRaw);
    return {
      sourceRef: entityCode && tableName && metricCode ? `${entityCode}:${tableName}:${metricCode}` : label,
      metricCode,
      metricName: metricNameParts.join(" ").trim() || metricCode || label,
      dataAcctCode,
    };
  }
  return {
    sourceRef: label,
    metricCode: "",
    metricName: "",
    dataAcctCode,
  };
}

function orgProductRefsForTopicRow(
  row: RowDto,
  dataAcctCode: string,
  fallbackRefsByDataAcctCode: Map<string, OrgProductMetricRef[]>
): OrgProductMetricRef[] {
  const rowRefs = (row.org_product_refs ?? [])
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .map((item) => parseOrgProductRefLabel(item, dataAcctCode));
  if (rowRefs.length > 0) return rowRefs;
  return dataAcctCode ? fallbackRefsByDataAcctCode.get(dataAcctCode) ?? [] : [];
}

function buildSectionTreeRows(rows: RowDto[], section: SectionType): (RowDto & { depth: number })[] {
  const sectionRows = rows.filter((row) => row.section === section);
  const childrenMap = new Map<number | null, RowDto[]>();
  for (const row of sectionRows) {
    const siblings = childrenMap.get(row.parent_id) ?? [];
    siblings.push(row);
    childrenMap.set(row.parent_id, siblings);
  }
  for (const siblings of childrenMap.values()) {
    siblings.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  }
  const result: (RowDto & { depth: number })[] = [];
  const walk = (parentId: number | null, depth: number) => {
    for (const child of childrenMap.get(parentId) ?? []) {
      result.push({ ...child, depth });
      walk(child.id, depth + 1);
    }
  };
  walk(null, 0);
  return result;
}

function buildSectionTree(rows: RowDto[], section: SectionType): TreeRowNode[] {
  const treeRows = buildSectionTreeRows(rows, section);
  const nodeMap = new Map<number, TreeRowNode>();
  const roots: TreeRowNode[] = [];
  for (const row of treeRows) {
    nodeMap.set(row.id, { ...row, children: [] });
  }
  for (const row of treeRows) {
    const node = nodeMap.get(row.id)!;
    if (row.parent_id != null && nodeMap.has(row.parent_id)) {
      nodeMap.get(row.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

function flattenVisibleTree(
  nodes: TreeRowNode[],
  expanded: Record<string, boolean>,
  blockKey: string,
  section: SectionType
): VisibleTreeRow[] {
  const rows: VisibleTreeRow[] = [];
  const walk = (list: TreeRowNode[]) => {
    for (const node of list) {
      const hasChildren = node.children.length > 0;
      const isExpanded = expanded[sectionExpandKey(blockKey, section, node.id)] ?? true;
      rows.push({ ...node, hasChildren, isExpanded });
      if (hasChildren && isExpanded) walk(node.children);
    }
  };
  walk(nodes);
  return rows;
}

export function InputOutputTopicOverviewContent() {
  const [meta, setMeta] = useState<OverviewMetaResponse | null>(null);
  const [report, setReport] = useState<OverviewReportResponse | null>(null);
  const [entityName, setEntityName] = useState("");
  const [groupName, setGroupName] = useState("");
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [reportMonth, setReportMonth] = useState(currentYearMonth());
  const [amountUnit, setAmountUnit] = useState("ten_thousand");
  const [selectedProductCodes, setSelectedProductCodes] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("total");
  const [loading, setLoading] = useState(false);
  const [metaLoading, setMetaLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [expandedMonthColumns, setExpandedMonthColumns] = useState<Record<string, boolean>>({});
  const [productPanelOpen, setProductPanelOpen] = useState(false);
  const [pendingProductCodes, setPendingProductCodes] = useState<string[]>([]);
  const [productSearch, setProductSearch] = useState("");
  const [productSelectionHydrated, setProductSelectionHydrated] = useState(false);
  const [orgProductMetricSnapshot, setOrgProductMetricSnapshot] = useState<OrgProductMetricSnapshotDto | null>(null);
  const productPanelRef = useRef<HTMLDivElement | null>(null);

  const selectedMonthNumber = Number(reportMonth.split("-")[1] || 12);
  const visibleActualMonthLabels = useMemo(
    () => MONTH_LABELS.slice(0, Math.min(Math.max(selectedMonthNumber, 1), 12)),
    [selectedMonthNumber]
  );

  const productNameMap = useMemo(
    () =>
      new Map((meta?.product_options ?? []).map((item) => [item.product_code, item.product_name])),
    [meta]
  );

  const selectedProductNames = useMemo(
    () =>
      selectedProductCodes
        .map((code) => productNameMap.get(code) ?? code)
        .filter(Boolean),
    [productNameMap, selectedProductCodes]
  );

  const visibleProductOptions = useMemo(() => {
    const keyword = productSearch.trim().toLowerCase();
    const groupFiltered = groupName
      ? (meta?.product_options ?? []).filter(
          (item) => item.group_name === groupName || item.group_code === groupName
        )
      : meta?.product_options ?? [];
    if (!keyword) return groupFiltered;
    return groupFiltered.filter((item) =>
      `${item.product_code} ${item.product_name} ${item.group_name ?? ""}`.toLowerCase().includes(keyword)
    );
  }, [groupName, meta, productSearch]);

  const yearOptions = useMemo(() => {
    const years = new Set(meta?.available_years ?? []);
    const reportYear = Number(reportMonth.split("-")[0]);
    if (Number.isFinite(reportYear) && reportYear > 0) years.add(reportYear);
    if (selectedYear) years.add(selectedYear);
    return Array.from(years).sort((a, b) => b - a);
  }, [meta, reportMonth, selectedYear]);

  const orgProductRefsByDataAcctCode = useMemo(() => {
    const refsByCode = new Map<string, OrgProductMetricRef[]>();
    const seen = new Set<string>();
    for (const entity of orgProductMetricSnapshot?.entities ?? []) {
      const entityCode = normalizeCode(entity.entity_code);
      for (const table of entity.tables ?? []) {
        const walk = (metrics: OrgProductMetricNodeDto[]) => {
          for (const metric of metrics) {
            const metricCode = normalizeCode(metric.code);
            const dataAcctCode = deriveRuntimeRefFromOrgProductMetricCode(entityCode, metricCode);
            if (metricCode && dataAcctCode) {
              const sourceRef = `${entityCode}:${table.table_name}:${metricCode}`;
              const key = `${sourceRef}:${dataAcctCode}`;
              if (!seen.has(key)) {
                seen.add(key);
                const current = refsByCode.get(dataAcctCode) ?? [];
                current.push({
                  sourceRef,
                  metricCode,
                  metricName: String(metric.name || dataAcctCode),
                  dataAcctCode,
                });
                refsByCode.set(dataAcctCode, current);
              }
            }
            if (metric.children?.length) walk(metric.children);
          }
        };
        walk(table.metrics ?? []);
      }
    }
    for (const refs of refsByCode.values()) {
      refs.sort((a, b) => a.sourceRef.localeCompare(b.sourceRef, "zh-CN"));
    }
    return refsByCode;
  }, [orgProductMetricSnapshot]);

  const loadOrgProductMetricSnapshot = async () => {
    const snapshot = await (getOrgProductMetricSnapshot() as Promise<OrgProductMetricSnapshotDto>).catch(() => ({ entities: [] }));
    setOrgProductMetricSnapshot(snapshot);
  };

  const loadMeta = async () => {
    setMetaLoading(true);
    try {
      const [data] = await Promise.all([getInputOutputTopicMeta(), loadOrgProductMetricSnapshot()]);
      setMeta(data);
      setSelectedProductCodes(() => {
        const availableCodes = new Set(data.product_options.map((item) => item.product_code));
        return readStoredProductCodes().filter((code) => availableCodes.has(code));
      });
      setProductSelectionHydrated(true);
      setAmountUnit((prev) =>
        data.amount_unit_options.some((item) => item.value === prev)
          ? prev
          : data.amount_unit_options[0]?.value ?? "ten_thousand"
      );
      if (!entityName && data.entity_options.length > 0) {
        const defaultEntity =
          data.entity_options.find((item) => item === "微众银行") ?? data.entity_options[0];
        setEntityName(defaultEntity);
      }
      if (!selectedYear && data.available_years.length > 0) {
        const current = currentYearMonth();
        const currentYear = Number(current.split("-")[0]);
        const nextYear = data.available_years.includes(currentYear)
          ? currentYear
          : data.available_years[0];
        setSelectedYear(nextYear);
        setReportMonth(alignReportMonthToYear(current, nextYear));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载专题元数据失败");
    } finally {
      setMetaLoading(false);
    }
  };

  const loadReport = async () => {
    if (!reportMonth) return;
    setLoading(true);
    setError("");
    try {
      const data = await getInputOutputTopicReport({
        reportMonth,
        groupName,
        amountUnit,
        productCodes: selectedProductCodes,
      });
      setReport(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载投入产出专题总览失败");
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  const exportCurrentView = async () => {
    if (!reportMonth) return;
    setError("");
    try {
      await exportInputOutputTopicReport({
        reportMonth,
        groupName,
        amountUnit,
        productCodes: selectedProductCodes,
        viewMode,
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "导出失败");
    }
  };

  useEffect(() => {
    void loadMeta();
  }, []);

  useEffect(() => {
    if (reportMonth) {
      void loadReport();
    }
  }, [groupName, reportMonth, amountUnit, selectedProductCodes]);

  useEffect(() => {
    if (!productSelectionHydrated || typeof window === "undefined") return;
    window.localStorage.setItem(PRODUCT_SCOPE_STORAGE_KEY, JSON.stringify(selectedProductCodes));
  }, [productSelectionHydrated, selectedProductCodes]);

  useEffect(() => {
    if (!groupName || !meta) return;
    const allowedCodes = new Set(
      meta.product_options
        .filter((item) => item.group_name === groupName || item.group_code === groupName)
        .map((item) => item.product_code)
    );
    setSelectedProductCodes((prev) => prev.filter((code) => allowedCodes.has(code)));
  }, [groupName, meta]);

  const openProductPanel = () => {
    setPendingProductCodes(selectedProductCodes);
    setProductSearch("");
    setProductPanelOpen(true);
  };

  const closeProductPanel = (apply: boolean) => {
    if (apply) {
      setSelectedProductCodes(pendingProductCodes);
    }
    setProductPanelOpen(false);
    setProductSearch("");
  };

  const togglePendingProductCode = (code: string) => {
    setPendingProductCodes((prev) =>
      prev.includes(code) ? prev.filter((item) => item !== code) : [...prev, code]
    );
  };

  useEffect(() => {
    if (!productPanelOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeProductPanel(false);
      }
    };
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (productPanelRef.current?.contains(target)) return;
      closeProductPanel(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("mousedown", onPointerDown);
    };
  }, [productPanelOpen, pendingProductCodes, selectedProductCodes]);

  const setSectionExpanded = (blockKey: string, section: SectionType, open: boolean, rows: RowDto[]) => {
    const parentIds = new Set<number>();
    for (const row of rows) {
      if (row.section !== section || row.parent_id == null) continue;
      parentIds.add(row.parent_id);
    }
    setExpandedRows((prev) => {
      const next = { ...prev };
      parentIds.forEach((id) => {
        next[sectionExpandKey(blockKey, section, id)] = open;
      });
      return next;
    });
  };

  const toggleExpanded = (blockKey: string, section: SectionType, id: number) => {
    setExpandedRows((prev) => ({
      ...prev,
      [sectionExpandKey(blockKey, section, id)]: !(prev[sectionExpandKey(blockKey, section, id)] ?? true),
    }));
  };

  const toggleMonthColumn = (section: SectionType, kind: "actual" | "lastYear") => {
    const key = `${section}:${kind}`;
    setExpandedMonthColumns((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const renderValue = (
    row: RowDto,
    value: number | null | undefined,
    cellDisplayFormat: IndicatorFormatType,
    emphasize = false
  ) => {
    if (row.display_group) return <span className="text-gray-400">-</span>;
    const text = formatValueByDisplayFormat(value, cellDisplayFormat);
    return <span className={emphasize ? "text-blue-600" : ""}>{text}</span>;
  };

  const renderMonthSeriesValue = (
    row: RowDto,
    value: number | null | undefined,
    displayFormat: IndicatorFormatType,
    monthIndex: number,
    options?: { limitToSelectedMonth?: boolean }
  ) => {
    if (row.display_group) {
      return <span className="text-gray-400">-</span>;
    }
    if (options?.limitToSelectedMonth !== false && monthIndex + 1 > selectedMonthNumber) {
      return <span className="text-gray-400">-</span>;
    }
    return formatValueByDisplayFormat(value, displayFormat);
  };

  const renderSectionTable = (
    blockKey: string,
    rowsSource: RowDto[],
    section: SectionType,
    options?: { maxDepth?: number }
  ) => {
    const tree = buildSectionTree(rowsSource, section);
    let rows = flattenVisibleTree(tree, expandedRows, blockKey, section);
    if (options?.maxDepth != null) {
      rows = rows.filter((row) => row.depth <= options.maxDepth!);
    }
    const showActualMonths = Boolean(expandedMonthColumns[`${section}:actual`]);
    const showLastYearMonths = Boolean(expandedMonthColumns[`${section}:lastYear`]);

    return (
      <section className="rounded border border-gray-200 bg-white">
        <div className="flex items-center justify-between gap-2 border-b border-gray-200 bg-slate-50 px-4 py-2.5 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-slate-700">{SECTION_LABELS[section]}</span>
            <span className="text-gray-400">({rows.length}项)</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSectionExpanded(blockKey, section, false, rowsSource)}
              className="rounded border border-gray-300 bg-white px-2 py-0.5 text-gray-700 hover:bg-gray-50"
            >
              全部收起
            </button>
            <button
              type="button"
              onClick={() => setSectionExpanded(blockKey, section, true, rowsSource)}
              className="rounded border border-gray-300 bg-white px-2 py-0.5 text-gray-700 hover:bg-gray-50"
            >
              全部展开
            </button>
          </div>
        </div>
        <div className="overflow-auto">
          <table className="min-w-[1500px] w-full border-collapse text-xs whitespace-nowrap">
            <thead className="bg-gray-100">
              <tr className="text-left text-gray-700">
                <th className="w-[260px] border border-gray-200 px-2 py-2">细项名称</th>
                <th className="border border-gray-200 px-2 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => toggleMonthColumn(section, "actual")}
                    className="inline-flex items-center gap-1 hover:text-blue-600"
                  >
                    {showActualMonths ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                    本年实际
                  </button>
                </th>
                {showActualMonths
                  ? visibleActualMonthLabels.map((label) => (
                      <th key={`${section}-actual-${label}`} className="border border-gray-200 px-2 py-2 text-right text-[11px]">
                        {label}
                      </th>
                    ))
                  : null}
                <th className="border border-gray-200 px-2 py-2 text-right">本年预算</th>
                <th className="border border-gray-200 px-2 py-2 text-right">预算进度</th>
                <th className="border border-gray-200 px-2 py-2 text-right">本年预测</th>
                <th className="border border-gray-200 px-2 py-2 text-right">差异额</th>
                <th className="border border-gray-200 px-2 py-2 text-right">差异率</th>
                <th className="border border-gray-200 px-2 py-2 text-right">同比</th>
                <th className="border border-gray-200 px-2 py-2 text-right">同比%</th>
                <th className="border border-gray-200 px-2 py-2 text-right">本月环比增减额</th>
                <th className="border border-gray-200 px-2 py-2 text-right">本月环比%</th>
                <th className="border border-gray-200 px-2 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => toggleMonthColumn(section, "lastYear")}
                    className="inline-flex items-center gap-1 hover:text-blue-600"
                  >
                    {showLastYearMonths ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                    去年同期
                  </button>
                </th>
                {showLastYearMonths
                  ? MONTH_LABELS.map((label) => (
                      <th key={`${section}-last-${label}`} className="border border-gray-200 px-2 py-2 text-right text-[11px]">
                        {label}
                      </th>
                    ))
                  : null}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={
                      12 + (showActualMonths ? visibleActualMonthLabels.length : 0) + (showLastYearMonths ? 12 : 0)
                    }
                    className="px-2 py-6 text-center text-gray-500"
                  >
                    {rowsSource.some((row) => row.section === section)
                      ? "当前筛选下暂无可展示行"
                      : "当前年份/产品下暂无细项模板，请切换到有数据的年份或先在「细项与指标维护」配置该产品"}
                  </td>
                </tr>
              ) : (
                rows.map((row) => {
                  const isParent = row.hasChildren;
                  const showFolder = isParent || row.display_group;
                  const displayFormat =
                    row.section === "indicator" ? row.display_format ?? "ratio" : "number";
                  const dataAcctCode = normalizeCode(row.data_acct_code);
                  const orgProductRefs = orgProductRefsForTopicRow(row, dataAcctCode, orgProductRefsByDataAcctCode);
                  const metricCode = row.metric_code || orgProductRefs[0]?.metricCode || dataAcctCode;
                  return (
                    <tr
                      key={`${blockKey}:${row.section}:${row.id}`}
                      className={`hover:bg-gray-50 ${showFolder ? "bg-blue-50/50" : ""}`}
                    >
                      <td className="border border-gray-200 px-2 py-1.5 font-medium text-gray-800">
                        <div className="flex items-center" style={{ paddingLeft: `${row.depth * 20}px` }}>
                          {isParent ? (
                            <button
                              type="button"
                              onClick={() => toggleExpanded(blockKey, section, row.id)}
                              className="mr-1 rounded p-0.5 hover:bg-blue-100"
                              title={row.isExpanded ? "收起下级" : "展开下级"}
                            >
                              {row.isExpanded ? (
                                <ChevronDown className="h-3.5 w-3.5 text-blue-500" />
                              ) : (
                                <ChevronRight className="h-3.5 w-3.5 text-blue-500" />
                              )}
                            </button>
                          ) : (
                            <span className="mr-1 inline-block w-4" />
                          )}
                          {showFolder ? (
                            <FolderOpen className="mr-1.5 h-3.5 w-3.5 shrink-0 text-blue-500" />
                          ) : (
                            <FileText className="mr-1.5 h-3.5 w-3.5 shrink-0 text-gray-400" />
                          )}
                          <span className={showFolder ? "font-semibold text-blue-700" : ""}>{row.name}</span>
                          {row.display_group ? (
                            <span className="ml-1 text-[10px] text-violet-500">(展示分组)</span>
                          ) : isParent ? (
                            <span className="ml-1 text-[10px] text-blue-400">(汇总)</span>
                          ) : null}
                        </div>
                        {row.section === "indicator" && row.topic_metric_node_code ? (
                          <div
                            className="mt-0.5 font-mono text-[10px] font-normal text-slate-400"
                            style={{ paddingLeft: `${row.depth * 20 + 38}px` }}
                          >
                            {row.topic_metric_node_code}
                          </div>
                        ) : null}
                        {row.section !== "indicator" && dataAcctCode ? (
                          <div
                            className="mt-0.5 flex min-w-0 items-center gap-1 text-[10px] font-normal"
                            style={{ paddingLeft: `${row.depth * 20 + 38}px` }}
                            title={orgProductRefs
                              .map((ref) => `${ref.metricCode || ref.sourceRef} ${ref.metricName} -> ${ref.dataAcctCode}`)
                              .join("\n")}
                          >
                            <span className="font-mono text-slate-400">{metricCode}</span>
                            {orgProductRefs.length > 0 ? (
                              <>
                                <span className="rounded border border-emerald-200 bg-emerald-50 px-1 text-emerald-700">
                                  机构产品
                                </span>
                                <span className="truncate font-mono text-emerald-700">
                                  {orgProductRefs[0].metricCode || orgProductRefs[0].sourceRef}
                                </span>
                                {orgProductRefs.length > 1 ? (
                                  <span className="shrink-0 text-gray-500">+{orgProductRefs.length - 1}</span>
                                ) : null}
                              </>
                            ) : null}
                          </div>
                        ) : null}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {renderValue(row, row.metrics.current_actual, displayFormat, isParent && !row.display_group)}
                      </td>
                      {showActualMonths
                        ? visibleActualMonthLabels.map((label, index) => (
                            <td
                              key={`${blockKey}:${section}:actual:${row.id}:${label}`}
                              className="border border-gray-200 px-2 py-1.5 text-right text-gray-600"
                            >
                              {renderMonthSeriesValue(
                                row,
                                row.monthly_series.actual[index] ?? null,
                                displayFormat,
                                index
                              )}
                            </td>
                          ))
                        : null}
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {renderValue(row, row.metrics.annual_budget, displayFormat, isParent && !row.display_group)}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {row.display_group ? <span className="text-gray-400">-</span> : formatPercentFromRatio(row.metrics.budget_progress)}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {renderValue(row, row.metrics.annual_forecast, displayFormat, isParent && !row.display_group)}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {renderValue(row, row.metrics.forecast_budget_gap, displayFormat, isParent && !row.display_group)}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {row.display_group ? <span className="text-gray-400">-</span> : formatPercentFromRatio(row.metrics.gap_rate)}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {renderValue(row, row.metrics.yoy_change, displayFormat, isParent && !row.display_group)}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {row.display_group ? <span className="text-gray-400">-</span> : formatPercentFromRatio(row.metrics.yoy_rate)}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {row.display_group || row.metrics.month_over_month == null ? (
                          <span className="text-gray-400">-</span>
                        ) : (
                          renderValue(row, row.metrics.month_over_month, displayFormat, isParent && !row.display_group)
                        )}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {row.display_group ? (
                          <span className="text-gray-400">-</span>
                        ) : (
                          formatPercentFromRatio(row.metrics.month_over_month_rate)
                        )}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                        {renderValue(row, row.metrics.last_year_actual, displayFormat, isParent && !row.display_group)}
                      </td>
                      {showLastYearMonths
                        ? MONTH_LABELS.map((label, index) => (
                            <td
                              key={`${blockKey}:${section}:last:${row.id}:${label}`}
                              className="border border-gray-200 px-2 py-1.5 text-right text-gray-600"
                            >
                              {renderMonthSeriesValue(
                                row,
                                row.monthly_series.last_year_actual[index] ?? null,
                                displayFormat,
                                index,
                                { limitToSelectedMonth: false }
                              )}
                            </td>
                          ))
                        : null}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  };

  const renderBlock = (
    title: string,
    blockKey: string,
    rows: RowDto[],
    options?: { maxDepth?: number; description?: string }
  ) => (
    <div className="space-y-4">
      <div className="rounded border border-gray-200 bg-white px-4 py-3">
        <div className="text-sm font-semibold text-gray-800">{title}</div>
        {options?.description ? (
          <div className="mt-1 text-xs text-gray-500">{options.description}</div>
        ) : null}
      </div>
      {(["indicator", "input", "output"] as SectionType[]).map((section) => (
        <div key={`${blockKey}:${section}`}>
          {renderSectionTable(blockKey, rows, section, {
            maxDepth: options?.maxDepth,
          })}
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="border-b border-gray-200 bg-gray-50 px-4 py-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">投入产出专题概览</h3>
            <div className="mt-1 text-[11px] text-gray-500">
              统一按评估指标、业务投入细项、业务产出细项三部分展示。
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void exportCurrentView()}
              disabled={loading || !reportMonth || !report}
              className="inline-flex items-center gap-1 rounded border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-60"
            >
              <Download className="h-3.5 w-3.5" />
              导出Excel
            </button>
            <button
              type="button"
              onClick={() => void loadReport()}
              disabled={loading || !reportMonth}
              className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              刷新
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <label className="flex items-center gap-1 text-gray-600">
            年份
            <select
              value={selectedYear ?? ""}
              onChange={(event) => {
                const year = Number(event.target.value);
                setSelectedYear(year);
                setReportMonth((prev) => alignReportMonthToYear(prev || currentYearMonth(), year));
              }}
              className="h-7 border border-gray-300 bg-white px-2 text-gray-800"
            >
              {(yearOptions).map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1 text-gray-600">
            费用月份
            <input
              type="month"
              value={reportMonth}
              onChange={(event) => {
                setReportMonth(event.target.value);
                setSelectedYear(Number(event.target.value.split("-")[0]));
              }}
              className="h-7 border border-gray-300 bg-white px-2 text-gray-800"
            />
          </label>
          <label className="flex items-center gap-1 text-gray-600">
            产品群
            <select
              value={groupName}
              onChange={(event) => setGroupName(event.target.value)}
              className="h-7 min-w-[9rem] border border-gray-300 bg-white px-2 text-gray-800"
            >
              <option value="">全部</option>
              {(meta?.group_options ?? []).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <div className="relative" ref={productPanelRef}>
            <button
              type="button"
              onClick={() => (productPanelOpen ? closeProductPanel(false) : openProductPanel())}
              className={`inline-flex h-7 items-center gap-1 border px-2 ${
                productPanelOpen
                  ? "border-blue-300 bg-blue-50 text-blue-800"
                  : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
              }`}
            >
              <Filter className="h-3.5 w-3.5" />
              产品范围：
              {selectedProductCodes.length === 0
                ? "全部"
                : selectedProductNames.slice(0, 2).join("、") +
                  (selectedProductCodes.length > 2 ? ` 等${selectedProductCodes.length}个` : "")}
              <ChevronDown className={`h-3 w-3 ${productPanelOpen ? "rotate-180" : ""}`} />
            </button>
            {productPanelOpen ? (
              <div className="absolute left-0 top-8 z-40 flex w-[380px] flex-col overflow-hidden rounded border border-gray-300 bg-white shadow-lg">
                <div className="border-b border-gray-200 p-2">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-[11px] font-medium text-gray-700">选择产品范围</span>
                    <button
                      type="button"
                      className="text-[11px] text-blue-700 hover:underline"
                      onClick={() => setPendingProductCodes([])}
                    >
                      清空
                    </button>
                  </div>
                  <div className="flex h-7 items-center gap-1 border border-gray-300 px-2">
                    <Search className="h-3.5 w-3.5 text-gray-400" />
                    <input
                      value={productSearch}
                      onChange={(event) => setProductSearch(event.target.value)}
                      placeholder="搜索产品编码或名称"
                      className="min-w-0 flex-1 outline-none"
                    />
                  </div>
                  <div className="mt-2 text-[10px] text-gray-500">勾选后请点击「确定」应用并关闭面板</div>
                </div>
                <div className="max-h-72 overflow-auto p-2 pt-1">
                  {visibleProductOptions.map((item) => {
                    const checked = pendingProductCodes.includes(item.product_code);
                    return (
                      <label
                        key={item.product_code}
                        className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-gray-50"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => togglePendingProductCode(item.product_code)}
                        />
                        <span className="min-w-0 flex-1 truncate">
                          {item.product_code} {item.product_name}
                        </span>
                        {checked ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : null}
                      </label>
                    );
                  })}
                </div>
                <div className="sticky bottom-0 border-t border-gray-200 bg-gray-50 px-2 py-2">
                  <div className="mb-2 text-[11px] text-gray-500">
                    {pendingProductCodes.length === 0
                      ? "未选产品时将展示全部产品"
                      : `已选 ${pendingProductCodes.length} 个产品`}
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      className="inline-flex h-7 items-center border border-gray-300 bg-white px-3 text-[11px] text-gray-700 hover:bg-gray-50"
                      onClick={() => closeProductPanel(false)}
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      className="inline-flex h-7 items-center gap-1 bg-blue-600 px-3 text-[11px] font-medium text-white hover:bg-blue-700"
                      onClick={() => closeProductPanel(true)}
                    >
                      <Check className="h-3.5 w-3.5" />
                      确定
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
          <label className="flex items-center gap-1 text-gray-600">
            单位
            <select
              value={amountUnit}
              onChange={(event) => setAmountUnit(event.target.value)}
              className="h-7 border border-gray-300 bg-white px-2 text-gray-800"
            >
              {(meta?.amount_unit_options ?? []).map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-3 flex items-center gap-1 border-b border-gray-300">
          {[
            { id: "total" as const, label: "全行总表" },
            { id: "detail" as const, label: "分产品明细" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setViewMode(tab.id)}
              className={`border-x border-t border-gray-300 px-3 py-1.5 text-[11px] ${
                viewMode === tab.id
                  ? "bg-white font-semibold text-gray-900"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <div className="mx-4 mt-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      ) : null}

      {report?.note ? (
        <div className="mx-4 mt-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {report.note}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {metaLoading && !meta ? (
          <div className="flex h-full items-center justify-center text-sm text-gray-500">加载专题配置中...</div>
        ) : loading && !report ? (
          <div className="flex h-full items-center justify-center text-sm text-gray-500">加载专题总览中...</div>
        ) : report ? (
          <div className="space-y-4">
            {viewMode === "total"
              ? renderBlock(
                  `全行总表${selectedProductCodes.length > 0 ? `（${selectedProductCodes.length}个产品汇总）` : "（全部产品）"}`,
                  "total",
                  report.total_rows,
                  { description: "按照当前费用月份、产品群和产品范围汇总展示，不再按主体过滤。" }
                )
              : null}
            {viewMode === "detail"
              ? report.product_blocks.length > 0
                ? (
                    <div className="space-y-4">
                      {report.product_blocks.map((block) =>
                        renderBlock(
                          `${block.product_name}（${block.product_code}）`,
                          `detail:${block.product_code}`,
                          block.rows,
                          {
                            description: "产品明细模块按所选产品逐行展示投入产出细项。",
                          }
                        )
                      )}
                    </div>
                  )
                : <div className="rounded border border-gray-200 bg-white px-4 py-8 text-center text-gray-500">当前产品范围下暂无产品明细。</div>
              : null}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-gray-500">请选择费用月份后查看投入产出专题总览。</div>
        )}
      </div>
    </div>
  );
}
