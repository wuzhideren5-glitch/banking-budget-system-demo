import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import { Check, ChevronDown, ChevronRight, Download, Filter, Loader2, Plus, RefreshCw, Search, Settings2, Trash2, Upload } from "lucide-react";
import {
  type BudgetOutputDisplayCandidateDto,
  type BudgetOutputDisplayConfigItemDto,
  type BudgetOutputDisplayConfigResponseDto,
  type BudgetOutputDisplayReportResponseDto,
  type BudgetOutputProductNodeDto,
  type BudgetOutputReportNodeDto,
  type BudgetOutputReportRowDto,
  createBudgetOutputDisplayConfigItem,
  deleteBudgetOutputDisplayConfigItem,
  exportBudgetOutputDisplayConfig,
  exportBudgetOutputDisplayReport,
  fetchBudgetOutputDisplayConfig,
  fetchBudgetOutputDisplayReport,
  importBudgetOutputDisplayConfig,
  updateBudgetOutputDisplayConfigItem,
} from "@/lib/budget/budgetOutputApi";
import {
  GridToolbar,
  ReportGrid,
  type FinancialGridColumn,
  type FinancialGridColumnGroup,
} from "@/app/components/ui/financial-grid";

type ViewMode = "total" | "products" | "detail";
type OpenPanel = "forecast" | "product" | "config" | null;
type ConfigDisplayTreeRow = BudgetOutputDisplayConfigItemDto & { children: ConfigDisplayTreeRow[] };

const amountUnits = [
  { label: "亿元", divisor: 100_000_000 },
  { label: "万元", divisor: 10_000 },
  { label: "元", divisor: 1 },
];

function isPercentRow(row: BudgetOutputReportRowDto): boolean {
  const text = `${row.value_type ?? ""}${row.display_name}`;
  return text.includes("百分比") || text.includes("率") || text.includes("占比") || text.includes("%");
}

function formatValue(value: number | null | undefined, row: BudgetOutputReportRowDto, divisor: number): string {
  if (row.row_type === "GROUP") return "-";
  if (value == null || Number.isNaN(value)) return "-";
  if (isPercentRow(row)) return `${(value * 100).toFixed(2)}%`;
  return (value / divisor).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatRatio(numerator: number, denominator: number): string {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) return "-";
  return `${((numerator / denominator) * 100).toFixed(2)}%`;
}

function candidateMetricCode(candidate: BudgetOutputDisplayCandidateDto): string {
  return candidate.metric_code ?? candidate.org_product_metric_code ?? candidate.data_acct_code;
}

function candidateMetricName(candidate: BudgetOutputDisplayCandidateDto): string {
  return candidate.metric_name ?? candidate.org_product_metric_name ?? candidate.data_acct_name;
}

function configItemMetricCode(item: BudgetOutputDisplayConfigItemDto): string | null {
  return item.metric_code ?? item.org_product_metric_code ?? item.data_acct_code ?? null;
}

function configItemMetricName(item: BudgetOutputDisplayConfigItemDto): string | null {
  return item.metric_name ?? item.org_product_metric_name ?? item.data_acct_name ?? null;
}

function displayReportRowLabel(row: BudgetOutputReportRowDto): ReactNode {
  if (!row.org_product_ref) return row.display_name;
  const metricName = row.metric_name ?? row.org_product_metric_name ?? row.data_acct_name;
  const sourceText = metricName
    ? `${row.org_product_ref} ${metricName}`
    : row.org_product_ref;
  return (
    <span className="inline-flex min-w-0 max-w-full flex-col leading-tight">
      <span className="truncate">{row.display_name}</span>
      <span className="truncate font-mono text-[10px] font-normal text-blue-500">{sourceText}</span>
    </span>
  );
}

function flattenProducts(nodes: BudgetOutputProductNodeDto[]): BudgetOutputProductNodeDto[] {
  return nodes.flatMap((node) => [node, ...flattenProducts(node.children)]);
}

function filterProducts(nodes: BudgetOutputProductNodeDto[], term: string): BudgetOutputProductNodeDto[] {
  const s = term.trim().toLowerCase();
  if (!s) return nodes;
  return nodes
    .map((node) => {
      const children = filterProducts(node.children, term);
      const hit = node.product_code.toLowerCase().includes(s) || node.product_name.toLowerCase().includes(s);
      if (hit || children.length > 0) return { ...node, children };
      return null;
    })
    .filter((node): node is BudgetOutputProductNodeDto => Boolean(node));
}

function buildReportNodeMap(nodes: BudgetOutputReportNodeDto[]): Map<string, BudgetOutputReportNodeDto> {
  const map = new Map<string, BudgetOutputReportNodeDto>();
  const walk = (items: BudgetOutputReportNodeDto[]) => {
    items.forEach((item) => {
      map.set(item.row_key, item);
      walk(item.children);
    });
  };
  walk(nodes);
  return map;
}

function buildReportTreeFromRows(rows: BudgetOutputReportRowDto[]): BudgetOutputReportNodeDto[] {
  const nodes = new Map<string, BudgetOutputReportNodeDto>();
  rows.forEach((row) => {
    nodes.set(row.row_key, {
      row_key: row.row_key,
      display_name: row.display_name,
      parent_row_key: row.parent_row_key,
      level: row.level,
      is_summary: row.is_summary,
      is_minus: row.is_minus,
      children: [],
    });
  });
  const roots: BudgetOutputReportNodeDto[] = [];
  rows.forEach((row) => {
    const node = nodes.get(row.row_key);
    if (!node) return;
    if (row.parent_row_key && nodes.has(row.parent_row_key)) {
      nodes.get(row.parent_row_key)?.children.push(node);
    } else {
      roots.push(node);
    }
  });
  return roots;
}

function defaultExpandedRows(nodes: BudgetOutputReportNodeDto[]): Record<string, boolean> {
  return expandedRowsToLevel(nodes, 2);
}

function expandedRowsToLevel(nodes: BudgetOutputReportNodeDto[], targetLevel: number): Record<string, boolean> {
  const next: Record<string, boolean> = {};
  const walk = (items: BudgetOutputReportNodeDto[]) => {
    items.forEach((item) => {
      if (item.level < targetLevel && item.children.length > 0) next[item.row_key] = true;
      walk(item.children);
    });
  };
  walk(nodes);
  return next;
}

function allExpandableRows(nodes: BudgetOutputReportNodeDto[]): Record<string, boolean> {
  const next: Record<string, boolean> = {};
  const walk = (items: BudgetOutputReportNodeDto[]) => {
    items.forEach((item) => {
      if (item.children.length > 0) next[item.row_key] = true;
      walk(item.children);
    });
  };
  walk(nodes);
  return next;
}

function visibleRows(
  rows: BudgetOutputReportRowDto[],
  nodeMap: Map<string, BudgetOutputReportNodeDto>,
  expandedRows: Record<string, boolean>,
): BudgetOutputReportRowDto[] {
  const isVisible = (row: BudgetOutputReportRowDto): boolean => {
    if (row.level <= 1) return true;
    let parentCode = row.parent_row_key;
    while (parentCode) {
      if (!expandedRows[parentCode]) return false;
      parentCode = nodeMap.get(parentCode)?.parent_row_key ?? null;
    }
    return true;
  };
  return rows.filter(isVisible);
}

export function BudgetDisplayReportContent() {
  const [report, setReport] = useState<BudgetOutputDisplayReportResponseDto | null>(null);
  const [displayConfig, setDisplayConfig] = useState<BudgetOutputDisplayConfigResponseDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("total");
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [budgetVersionId, setBudgetVersionId] = useState<number | null>(null);
  const [forecastVersionIds, setForecastVersionIds] = useState<number[] | null>(null);
  const [selectedProductCodes, setSelectedProductCodes] = useState<string[]>([]);
  const [expandedProducts, setExpandedProducts] = useState<Record<string, boolean>>({});
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [expandedVersionKeys, setExpandedVersionKeys] = useState<Record<string, boolean>>({});
  const [productSearch, setProductSearch] = useState("");
  const [unitDivisor, setUnitDivisor] = useState(100_000_000);
  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);
  const [configSearch, setConfigSearch] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [configParentKey, setConfigParentKey] = useState<string>("");
  const [dropTargetKey, setDropTargetKey] = useState<string | null>(null);
  const [configExpandedRows, setConfigExpandedRows] = useState<Record<string, boolean>>({});
  const filterRef = useRef<HTMLDivElement>(null);
  const configImportInputRef = useRef<HTMLInputElement>(null);

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchBudgetOutputDisplayReport({
        year: selectedYear,
        budgetVersionId,
        forecastVersionIds,
        productCodes: selectedProductCodes,
      });
      setReport(next);
      setExpandedRows(defaultExpandedRows(next.report_tree));
      setExpandedProducts((prev) => {
        if (Object.keys(prev).length > 0) return prev;
        const roots: Record<string, boolean> = {};
        next.product_tree.forEach((node) => {
          roots[node.product_code] = true;
        });
        return roots;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载预算展示报表失败");
    } finally {
      setLoading(false);
    }
  };

  const loadDisplayConfig = async () => {
    setConfigLoading(true);
    setConfigError(null);
    try {
      const next = await fetchBudgetOutputDisplayConfig();
      setDisplayConfig(next);
      setConfigExpandedRows((prev) => {
        if (Object.keys(prev).length > 0) return prev;
        return Object.fromEntries(next.items.filter((item) => item.level <= 2).map((item) => [item.row_key, true]));
      });
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : "加载展示科目配置失败");
    } finally {
      setConfigLoading(false);
    }
  };

  const refreshAfterConfigChange = async () => {
    await loadDisplayConfig();
    await loadReport();
  };

  const addDisplayItem = async (
    candidate: BudgetOutputDisplayCandidateDto,
    placement: { parentRowKey?: string | null; insertAfterRowKey?: string | null } = { parentRowKey: configParentKey || null },
  ) => {
    setConfigSaving(true);
    setConfigError(null);
    try {
      await createBudgetOutputDisplayConfigItem({
        data_acct_code: candidate.data_acct_code,
        display_name: candidateMetricName(candidate),
        parent_row_key: placement.parentRowKey ?? null,
        insert_after_row_key: placement.insertAfterRowKey ?? null,
        org_product_ref: candidate.source_type === "org_product_metric" ? candidate.org_product_ref ?? candidate.source_ref ?? null : null,
        org_product_entity_code: candidate.org_product_entity_code ?? null,
        org_product_table_name: candidate.org_product_table_name ?? null,
        org_product_metric_code: candidate.org_product_metric_code ?? null,
        org_product_metric_name: candidate.org_product_metric_name ?? null,
      });
      await refreshAfterConfigChange();
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : "新增展示科目失败");
    } finally {
      setConfigSaving(false);
    }
  };

  const addDisplayGroup = async () => {
    const displayName = newGroupName.trim();
    if (!displayName) {
      setConfigError("请先填写展示分类名称");
      return;
    }
    setConfigSaving(true);
    setConfigError(null);
    try {
      await createBudgetOutputDisplayConfigItem({
        data_acct_code: "",
        display_name: displayName,
        parent_row_key: configParentKey || null,
      });
      setNewGroupName("");
      await refreshAfterConfigChange();
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : "新增展示分类失败");
    } finally {
      setConfigSaving(false);
    }
  };

  const candidateByCode = useMemo(
    () =>
      new Map(
        (displayConfig?.candidates ?? []).map((candidate) => [
          candidate.candidate_key ?? candidateMetricCode(candidate),
          candidate,
        ])
      ),
    [displayConfig],
  );

  const beginCandidateDrag = (event: DragEvent<HTMLDivElement>, candidate: BudgetOutputDisplayCandidateDto) => {
    event.dataTransfer.effectAllowed = "copy";
    const code = candidate.candidate_key ?? candidateMetricCode(candidate);
    event.dataTransfer.setData("application/x-budget-display-candidate", code);
    event.dataTransfer.setData("text/plain", candidateMetricCode(candidate));
  };

  const dropCandidateAfter = async (event: DragEvent<HTMLElement>, target: BudgetOutputDisplayConfigItemDto | null) => {
    event.preventDefault();
    event.stopPropagation();
    const code = event.dataTransfer.getData("application/x-budget-display-candidate") || event.dataTransfer.getData("text/plain");
    setDropTargetKey(null);
    const candidate = candidateByCode.get(code);
    if (!candidate) return;
    await addDisplayItem(candidate, target ? { insertAfterRowKey: target.row_key } : { parentRowKey: null });
  };

  const updateDisplayItem = async (item: BudgetOutputDisplayConfigItemDto, patch: Partial<Pick<BudgetOutputDisplayConfigItemDto, "display_name" | "sort_order" | "is_active">>) => {
    setConfigSaving(true);
    setConfigError(null);
    try {
      await updateBudgetOutputDisplayConfigItem(item.row_key, patch);
      await refreshAfterConfigChange();
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : "更新展示科目失败");
    } finally {
      setConfigSaving(false);
    }
  };

  const deleteDisplayItem = async (item: BudgetOutputDisplayConfigItemDto) => {
    setConfigSaving(true);
    setConfigError(null);
    try {
      await deleteBudgetOutputDisplayConfigItem(item.row_key);
      await refreshAfterConfigChange();
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : "删除展示科目失败");
    } finally {
      setConfigSaving(false);
    }
  };

  const exportFullWorkbook = async () => {
    setExporting(true);
    setError(null);
    try {
      await exportBudgetOutputDisplayReport({
        year: selectedYear,
        budgetVersionId,
        forecastVersionIds,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "导出预算展示报表失败");
    } finally {
      setExporting(false);
    }
  };

  const exportDisplayConfig = async () => {
    setConfigSaving(true);
    setConfigError(null);
    try {
      await exportBudgetOutputDisplayConfig();
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : "导出展示配置失败");
    } finally {
      setConfigSaving(false);
    }
  };

  const importDisplayConfig = async (file: File | null) => {
    if (!file) return;
    if (!window.confirm("将按上传文件覆盖当前预算展示配置，是否继续？")) {
      if (configImportInputRef.current) configImportInputRef.current.value = "";
      return;
    }
    setConfigSaving(true);
    setConfigError(null);
    try {
      const result = await importBudgetOutputDisplayConfig(file);
      alert(`预算展示配置导入完成：${result.saved_rows} 行，其中取数行 ${result.metric_rows} 行，展示分类 ${result.group_rows} 行。`);
      await refreshAfterConfigChange();
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : "导入展示配置失败");
    } finally {
      setConfigSaving(false);
      if (configImportInputRef.current) configImportInputRef.current.value = "";
    }
  };

  useEffect(() => {
    void loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear, budgetVersionId, forecastVersionIds, selectedProductCodes]);

  useEffect(() => {
    void loadDisplayConfig();
  }, []);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (!filterRef.current || !(event.target instanceof Node)) return;
      if (!filterRef.current.contains(event.target)) setOpenPanel(null);
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenPanel(null);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const currentTree = useMemo(() => {
    if (!report) return [];
    if (viewMode === "products") return report.product_overview_tree;
    if (viewMode === "detail") return report.product_detail_tree;
    return report.report_tree;
  }, [report, viewMode]);
  const budgetVersions = useMemo(() => report?.versions.filter((version) => version.source === "budget") ?? [], [report]);
  const showVersions = useMemo(() => report?.versions.filter((version) => version.source === "show" && version.selected_by_default) ?? [], [report]);
  const forecastVersions = useMemo(
    () => report?.versions.filter((version) => version.source === "forecast") ?? [],
    [report],
  );
  const activeBudgetVersion = budgetVersions.find((version) => version.version_id === report?.budget_version_id) ?? budgetVersions[0] ?? null;
  const activeForecastVersions = forecastVersions.filter((version) => report?.forecast_version_ids.includes(version.version_id));
  const allProducts = useMemo(() => (report ? flattenProducts(report.product_tree) : []), [report]);
  const selectedProductSet = useMemo(() => new Set(selectedProductCodes), [selectedProductCodes]);
  const selectedProductNames = allProducts.filter((product) => selectedProductSet.has(product.product_code)).map((product) => product.product_name);
  const detailBlocks = useMemo(
    () => (report?.product_detail_blocks?.length ? report.product_detail_blocks : report?.product_blocks ?? []),
    [report],
  );
  const displayParentOptions = useMemo(
    () => (displayConfig?.items ?? []).filter((item) => item.is_active === 1),
    [displayConfig],
  );
  const configChildrenByKey = useMemo(() => {
    const items = (displayConfig?.items ?? []).filter((item) => item.is_active === 1);
    const itemKeys = new Set(items.map((item) => item.row_key));
    const children = new Map<string | null, ConfigDisplayTreeRow[]>();
    items.forEach((item) => {
      const parentKey = item.parent_row_key && itemKeys.has(item.parent_row_key) ? item.parent_row_key : null;
      const row: ConfigDisplayTreeRow = { ...item, children: [] };
      children.set(parentKey, [...(children.get(parentKey) ?? []), row]);
    });
    children.forEach((siblings) => {
      siblings.sort((a, b) => {
        const viewOrder = (view: string) => {
          if (view === "TOTAL") return 1;
          if (view === "OVERVIEW") return 2;
          if (view.startsWith("PRODUCT.")) return 3;
          return 9;
        };
        return (
          viewOrder(a.display_view) - viewOrder(b.display_view) ||
          a.display_view.localeCompare(b.display_view) ||
          a.sort_order - b.sort_order ||
          a.row_key.localeCompare(b.row_key)
        );
      });
    });
    const attach = (rows: ConfigDisplayTreeRow[]): ConfigDisplayTreeRow[] =>
      rows.map((row) => ({ ...row, children: attach(children.get(row.row_key) ?? []) }));
    return new Map(Array.from(children, ([key, rows]) => [key, attach(rows)]));
  }, [displayConfig]);
  const visibleConfigRows = useMemo(() => {
    const result: ConfigDisplayTreeRow[] = [];
    const walk = (rows: ConfigDisplayTreeRow[]) => {
      rows.forEach((row) => {
        result.push(row);
        if (configExpandedRows[row.row_key]) walk(row.children);
      });
    };
    walk(configChildrenByKey.get(null) ?? []);
    return result;
  }, [configChildrenByKey, configExpandedRows]);
  const filteredDisplayCandidates = useMemo(() => {
    const s = configSearch.trim().toLowerCase();
    return (displayConfig?.candidates ?? [])
      .filter((candidate) => {
        if (!s) return true;
        return [
          candidate.metric_code ?? "",
          candidate.metric_name ?? "",
          candidate.data_acct_code,
          candidate.data_acct_name,
          candidate.metric_node_code,
          candidate.metric_node_name,
          candidate.scope_code,
          candidate.scope_name ?? "",
          candidate.source_label ?? "",
          candidate.source_ref ?? "",
        ]
          .join(" ")
          .toLowerCase()
          .includes(s);
      })
      .slice(0, 80);
  }, [configSearch, displayConfig]);

  useEffect(() => {
    if (!report) return;
    setExpandedRows(defaultExpandedRows(currentTree));
  }, [currentTree, report]);

  const toggleForecastVersion = (versionId: number) => {
    const current = forecastVersionIds ?? report?.forecast_version_ids ?? [];
    const next = current.includes(versionId) ? current.filter((item) => item !== versionId) : [...current, versionId];
    if (next.length === 0) return;
    setForecastVersionIds(next);
  };

  const toggleProduct = (code: string) => {
    setSelectedProductCodes((prev) => (prev.includes(code) ? prev.filter((item) => item !== code) : [...prev, code]));
  };

  const toggleRow = (code: string) => {
    setExpandedRows((prev) => ({ ...prev, [code]: !prev[code] }));
  };

  const toggleVersionColumns = (key: string) => {
    setExpandedVersionKeys((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const renderProductNode = (node: BudgetOutputProductNodeDto, depth = 0): JSX.Element => {
    const hasChildren = node.children.length > 0;
    const isOpen = Boolean(expandedProducts[node.product_code]);
    const isChecked = selectedProductSet.has(node.product_code);
    return (
      <div key={node.product_code}>
        <div className="flex items-center gap-1 py-0.5 text-[11px]" style={{ paddingLeft: depth * 12 }}>
          <button
            type="button"
            className="h-5 w-5 inline-flex items-center justify-center text-gray-500 hover:bg-gray-100 disabled:opacity-0"
            onClick={() => setExpandedProducts((prev) => ({ ...prev, [node.product_code]: !prev[node.product_code] }))}
            disabled={!hasChildren}
          >
            {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
          <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5">
            <input type="checkbox" checked={isChecked} onChange={() => toggleProduct(node.product_code)} />
            <span className="truncate text-gray-700">
              {node.product_code} {node.product_name}
            </span>
          </label>
        </div>
        {hasChildren && isOpen ? node.children.map((child) => renderProductNode(child, depth + 1)) : null}
      </div>
    );
  };

  const renderTable = (rowsRaw: BudgetOutputReportRowDto[], title: string, tree: BudgetOutputReportNodeDto[] = currentTree) => {
    const effectiveTree = tree.length > 0 ? tree : buildReportTreeFromRows(rowsRaw);
    const nodeMap = buildReportNodeMap(effectiveTree);
    const rows = visibleRows(rowsRaw, nodeMap, expandedRows);
    const lastActualVersion = showVersions[showVersions.length - 1] ?? null;
    const columnGroups: FinancialGridColumnGroup[] = [];
    const columns: FinancialGridColumn<BudgetOutputReportRowDto>[] = [];
    showVersions.forEach((version) => {
      columnGroups.push({
        id: version.key,
        header: version.version_name,
        collapsible: true,
        colSpanWhenCollapsed: 1,
      });
      columns.push({
        id: `${version.key}-annual`,
        header: "实际",
        groupId: version.key,
        minWidth: 96,
        align: "right",
        render: (row) => formatValue(row.values_by_version[version.key]?.annual_value ?? 0, row, unitDivisor),
      });
      Array.from({ length: 12 }, (_, idx) => {
        columns.push({
          id: `${version.key}-m${idx + 1}`,
          header: `${idx + 1}月`,
          groupId: version.key,
          hiddenWhenGroupCollapsed: true,
          minWidth: 76,
          align: "right",
          className: "text-[var(--bb-text-muted)]",
          render: (row) => formatValue(row.values_by_version[version.key]?.monthly_values[idx] ?? 0, row, unitDivisor),
        });
      });
    });
    if (activeBudgetVersion) {
      columnGroups.push({
        id: activeBudgetVersion.key,
        header: activeBudgetVersion.version_name,
        collapsible: true,
        colSpanWhenCollapsed: 1,
      });
      columns.push({
        id: `${activeBudgetVersion.key}-annual`,
        header: "预算",
        groupId: activeBudgetVersion.key,
        minWidth: 96,
        align: "right",
        render: (row) => formatValue(row.values_by_version[activeBudgetVersion.key]?.annual_value ?? 0, row, unitDivisor),
      });
      Array.from({ length: 12 }, (_, idx) => {
        columns.push({
          id: `${activeBudgetVersion.key}-m${idx + 1}`,
          header: `${idx + 1}月`,
          groupId: activeBudgetVersion.key,
          hiddenWhenGroupCollapsed: true,
          minWidth: 76,
          align: "right",
          className: "text-[var(--bb-text-muted)]",
          render: (row) => formatValue(row.values_by_version[activeBudgetVersion.key]?.monthly_values[idx] ?? 0, row, unitDivisor),
        });
      });
    }
    activeForecastVersions.forEach((version) => {
      columnGroups.push({
        id: version.key,
        header: version.version_name,
        collapsible: true,
        colSpanWhenCollapsed: 4,
      });
      columns.push(
        {
          id: `${version.key}-forecast`,
          header: "预测",
          groupId: version.key,
          minWidth: 96,
          align: "right",
          render: (row) => formatValue(row.values_by_version[version.key]?.annual_value ?? 0, row, unitDivisor),
        },
        {
          id: `${version.key}-diff`,
          header: "预测-预算",
          groupId: version.key,
          minWidth: 92,
          align: "right",
          render: (row) => {
            const budgetAnnual = activeBudgetVersion ? row.values_by_version[activeBudgetVersion.key]?.annual_value ?? 0 : 0;
            const forecastAnnual = row.values_by_version[version.key]?.annual_value ?? 0;
            const diff = forecastAnnual - budgetAnnual;
            return <span className={diff >= 0 ? "text-emerald-700" : "text-rose-700"}>{formatValue(diff, row, unitDivisor)}</span>;
          },
        },
        {
          id: `${version.key}-ratio`,
          header: "预算达成",
          groupId: version.key,
          minWidth: 88,
          align: "right",
          render: (row) => {
            const budgetAnnual = activeBudgetVersion ? row.values_by_version[activeBudgetVersion.key]?.annual_value ?? 0 : 0;
            const forecastAnnual = row.values_by_version[version.key]?.annual_value ?? 0;
            return formatRatio(forecastAnnual, budgetAnnual);
          },
        },
        {
          id: `${version.key}-yoy`,
          header: "同比",
          groupId: version.key,
          minWidth: 88,
          align: "right",
          render: (row) => {
            const actualAnnual = lastActualVersion ? row.values_by_version[lastActualVersion.key]?.annual_value ?? 0 : 0;
            const forecastAnnual = row.values_by_version[version.key]?.annual_value ?? 0;
            return actualAnnual === 0 ? "-" : formatRatio(forecastAnnual - actualAnnual, actualAnnual);
          },
        },
      );
      Array.from({ length: 12 }, (_, idx) => {
        columns.push({
          id: `${version.key}-m${idx + 1}`,
          header: `${idx + 1}月`,
          groupId: version.key,
          hiddenWhenGroupCollapsed: true,
          minWidth: 76,
          align: "right",
          className: "text-[var(--bb-text-muted)]",
          render: (row) => formatValue(row.values_by_version[version.key]?.monthly_values[idx] ?? 0, row, unitDivisor),
        });
      });
    });
    return (
      <div className="bb-panel overflow-hidden">
        <GridToolbar className="rounded-none border-0 border-b border-[var(--bb-border)]">
          <div className="mr-auto text-xs font-semibold text-[var(--bb-text-strong)]">{title}</div>
          <div className="flex items-center gap-1 text-[11px]">
            <span className="text-[var(--bb-text-muted)]">展开层级</span>
            {[1, 2, 3, 4, 5].map((level) => (
              <button
                key={level}
                type="button"
                onClick={() => setExpandedRows(expandedRowsToLevel(effectiveTree, level))}
                className="bb-btn bb-btn-secondary min-h-6 px-1.5 text-[11px]"
                title={`展开到第${level}级指标科目`}
              >
                {level}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setExpandedRows(allExpandableRows(effectiveTree))}
              className="bb-btn bb-btn-secondary min-h-6 px-2 text-[11px]"
            >
              全展开
            </button>
            <button
              type="button"
              onClick={() => setExpandedRows({})}
              className="bb-btn bb-btn-secondary min-h-6 px-2 text-[11px]"
            >
              全收起
            </button>
          </div>
        </GridToolbar>
        <ReportGrid
          rows={rows}
          columns={columns}
          columnGroups={columnGroups}
          expandedColumnGroups={expandedVersionKeys}
          onToggleColumnGroup={toggleVersionColumns}
          getRowId={(row) => row.row_key}
          getRowLabel={displayReportRowLabel}
          getRowLevel={(row) => row.level}
          getRowHasChildren={(row) => Boolean(nodeMap.get(row.row_key)?.children.length)}
          getRowKind={(row) => (row.is_summary || Boolean(nodeMap.get(row.row_key)?.children.length) ? "summary" : "normal")}
          isRowExpanded={(row) => Boolean(expandedRows[row.row_key])}
          onToggleRow={(row) => toggleRow(row.row_key)}
          primaryHeader="指标科目"
          emptyMessage="当前条件下暂无可展示数据。"
          className="rounded-none border-0"
        />
      </div>
    );
  };

  const renderProductOverviewTable = () => {
    const blocks = report?.product_overview_blocks ?? [];
    const tree = report?.product_overview_tree ?? [];
    const nodeMap = buildReportNodeMap(tree);
    const templateRows = blocks[0]?.rows ?? [];
    const rows = visibleRows(templateRows, nodeMap, expandedRows);
    const blockRows = new Map(
      blocks.map((block) => [block.product_code, new Map(block.rows.map((row) => [row.row_key, row]))]),
    );
    const versionColumns = [
      ...showVersions,
      ...(activeBudgetVersion ? [activeBudgetVersion] : []),
      ...activeForecastVersions,
    ];
    const columnGroups: FinancialGridColumnGroup[] = blocks.map((block) => ({
      id: block.product_code,
      header: `${block.product_name} ${block.product_code}`,
      collapsible: false,
    }));
    const columns: FinancialGridColumn<BudgetOutputReportRowDto>[] = [];
    blocks.forEach((block) => {
      versionColumns.forEach((version) => {
        columns.push({
          id: `${block.product_code}-${version.key}`,
          header: version.version_name,
          groupId: block.product_code,
          minWidth: 92,
          align: "right",
          render: (row) => {
            const productRow = blockRows.get(block.product_code)?.get(row.row_key);
            return formatValue(productRow?.values_by_version[version.key]?.annual_value ?? 0, productRow ?? row, unitDivisor);
          },
        });
      });
      const forecast = activeForecastVersions[0];
      const lastActual = showVersions[showVersions.length - 1];
      if (forecast && lastActual) {
        columns.push({
          id: `${block.product_code}-${forecast.key}-yoy`,
          header: "同比",
          groupId: block.product_code,
          minWidth: 80,
          align: "right",
          render: (row) => {
            const productRow = blockRows.get(block.product_code)?.get(row.row_key);
            const forecastAnnual = productRow?.values_by_version[forecast.key]?.annual_value ?? 0;
            const actualAnnual = productRow?.values_by_version[lastActual.key]?.annual_value ?? 0;
            return actualAnnual === 0 ? "-" : formatRatio(forecastAnnual - actualAnnual, actualAnnual);
          },
        });
      }
    });
    return (
      <div className="bb-panel overflow-hidden">
        <GridToolbar className="rounded-none border-0 border-b border-[var(--bb-border)]">
          <div className="mr-auto text-xs font-semibold text-[var(--bb-text-strong)]">分产品概览</div>
          <div className="flex items-center gap-1 text-[11px]">
            <span className="text-[var(--bb-text-muted)]">展开层级</span>
            {[1, 2, 3, 4].map((level) => (
              <button key={level} type="button" onClick={() => setExpandedRows(expandedRowsToLevel(tree, level))} className="bb-btn bb-btn-secondary min-h-6 px-1.5 text-[11px]">
                {level}
              </button>
            ))}
          </div>
        </GridToolbar>
        <ReportGrid
          rows={rows}
          columns={columns}
          columnGroups={columnGroups}
          expandedColumnGroups={expandedVersionKeys}
          onToggleColumnGroup={toggleVersionColumns}
          getRowId={(row) => row.row_key}
          getRowLabel={displayReportRowLabel}
          getRowLevel={(row) => row.level}
          getRowHasChildren={(row) => Boolean(nodeMap.get(row.row_key)?.children.length)}
          getRowKind={(row) => (row.is_summary || Boolean(nodeMap.get(row.row_key)?.children.length) ? "summary" : "normal")}
          isRowExpanded={(row) => Boolean(expandedRows[row.row_key])}
          onToggleRow={(row) => toggleRow(row.row_key)}
          primaryHeader="指标科目"
          emptyMessage="当前条件下暂无可展示数据。"
          className="rounded-none border-0"
        />
      </div>
    );
  };

  const renderProductDetailModule = () => {
    if (!report) return null;
    if (selectedProductCodes.length === 0) {
      return (
        <div className="border border-gray-200 bg-white px-4 py-8 text-center text-gray-500">
          请使用上方“产品范围”选择一个或多个产品后查看产品明细。
        </div>
      );
    }
    if (detailBlocks.length === 0) {
      return <div className="border border-gray-200 bg-white px-4 py-8 text-center text-gray-500">当前产品范围下暂无产品明细。</div>;
    }
    return (
      <div className="space-y-3">
        <div className="bb-panel px-3 py-2 text-[11px] text-[var(--bb-text-muted)]">
          产品明细模块使用上方“产品范围”作为唯一产品入口；当前展示 {detailBlocks.length} 个产品明细。
        </div>
        {detailBlocks.map((block) => (
          <div key={block.product_code}>
            {renderTable(block.rows, `${block.product_name}（${block.product_code}）`, buildReportTreeFromRows(block.rows))}
          </div>
        ))}
      </div>
    );
  };

  const visibleProductTree = report ? filterProducts(report.product_tree, productSearch) : [];
  const renderDisplayConfigPanel = () => (
    <div className="absolute right-0 top-8 z-50 grid max-h-[72vh] w-[min(920px,calc(100vw-320px))] min-w-[720px] grid-cols-[300px_minmax(0,1fr)] overflow-hidden border border-gray-300 bg-white shadow-lg">
      <div className="min-w-0 border-r border-gray-200">
        <div className="border-b border-gray-200 px-3 py-2">
          <div className="text-[11px] font-semibold text-gray-800">从机构产品指标选择</div>
          <label className="mt-2 block text-[11px] text-gray-600">
            加入到
            <select
              value={configParentKey}
              onChange={(event) => setConfigParentKey(event.target.value)}
              className="mt-1 h-7 w-full border border-gray-300 bg-white px-2 text-[11px] text-gray-800"
            >
              <option value="">根级展示行</option>
              {displayParentOptions.map((item) => (
                <option key={item.row_key} value={item.row_key}>
                  {"　".repeat(Math.max(0, item.level - 1))}
                  {item.display_name}
                </option>
              ))}
            </select>
          </label>
          <div className="mt-2 flex h-7 items-center gap-1 border border-gray-300 px-2">
            <Search className="h-3.5 w-3.5 text-gray-400" />
            <input
              value={configSearch}
              onChange={(event) => setConfigSearch(event.target.value)}
              placeholder="搜索机构产品指标、运行编码、科目名称、产品范围"
              className="min-w-0 flex-1 text-[11px] outline-none"
            />
          </div>
          <div className="mt-2 border-t border-gray-200 pt-2">
            <div className="text-[11px] font-semibold text-gray-800">新增展示分类</div>
            <div className="mt-1 flex h-7 items-center gap-1">
              <input
                value={newGroupName}
                onChange={(event) => setNewGroupName(event.target.value)}
                placeholder="例如：资产业务"
                className="min-w-0 flex-1 border border-gray-300 px-2 text-[11px] outline-none"
              />
              <button
                type="button"
                onClick={() => void addDisplayGroup()}
                disabled={configSaving}
                className="inline-flex h-7 items-center gap-1 border border-slate-300 bg-white px-2 text-[11px] text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                title="新增不取数的展示分类"
              >
                <Plus className="h-3.5 w-3.5" />
                新增
              </button>
            </div>
          </div>
        </div>
        <div className="max-h-[58vh] overflow-auto">
          {configLoading ? (
            <div className="flex items-center justify-center px-3 py-8 text-[11px] text-gray-500">
              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              正在加载机构产品指标...
            </div>
          ) : filteredDisplayCandidates.length ? (
            filteredDisplayCandidates.map((candidate) => (
              <div
                key={candidate.candidate_key ?? candidateMetricCode(candidate)}
                draggable={!configSaving}
                onDragStart={(event) => beginCandidateDrag(event, candidate)}
                onDragEnd={() => setDropTargetKey(null)}
                className="grid cursor-grab grid-cols-[1fr_auto] gap-2 border-b border-gray-100 px-3 py-2 text-[11px] hover:bg-gray-50 active:cursor-grabbing"
                title="拖到右侧展示科目下方"
              >
                <div className="min-w-0">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate font-medium text-gray-800">{candidateMetricName(candidate)}</span>
                    <span
                      className={`shrink-0 rounded border px-1 py-0.5 text-[10px] ${
                        candidate.source_type === "org_product_metric"
                          ? "border-blue-200 bg-blue-50 text-blue-700"
                          : "border-gray-200 bg-gray-50 text-gray-500"
                      }`}
                    >
                      {candidate.source_label ?? "机构产品指标"}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-gray-500">
                    {candidateMetricCode(candidate)} / {candidate.scope_name ?? candidate.scope_code} / {candidate.value_type}
                  </div>
                  {candidate.source_ref ? (
                    <div className="mt-0.5 truncate font-mono text-[10px] text-blue-500">{candidate.source_ref}</div>
                  ) : null}
                </div>
                <button
                  type="button"
                  disabled={configSaving}
                  onClick={() => addDisplayItem(candidate)}
                  className="inline-flex h-7 items-center gap-1 border border-blue-200 bg-blue-50 px-2 text-blue-700 hover:bg-blue-100 disabled:opacity-50"
                  title="加入预算展示报表"
                >
                  <Plus className="h-3.5 w-3.5" />
                  加入
                </button>
              </div>
            ))
          ) : (
            <div className="px-3 py-8 text-center text-[11px] text-gray-500">没有可加入的科目。</div>
          )}
        </div>
      </div>
      <div className="min-w-0">
        <div className="border-b border-gray-200 px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-[11px] font-semibold text-gray-800">已展示科目</div>
              <div className="mt-1 text-[11px] text-gray-500">按父子层级维护预算展示行；拖到某行即插入到该行下方。</div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => void exportDisplayConfig()}
                disabled={configSaving}
                className="inline-flex h-7 items-center gap-1 border border-gray-300 bg-white px-2 text-[11px] text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                title="导出当前数据库展示配置，作为标准导入模板"
              >
                <Download className="h-3.5 w-3.5" />
                导出
              </button>
              <button
                type="button"
                onClick={() => configImportInputRef.current?.click()}
                disabled={configSaving}
                className="inline-flex h-7 items-center gap-1 border border-gray-300 bg-white px-2 text-[11px] text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                title="上传标准展示配置模板并覆盖导入"
              >
                <Upload className="h-3.5 w-3.5" />
                导入
              </button>
              <input
                ref={configImportInputRef}
                type="file"
                accept=".xlsx,.xlsm"
                className="hidden"
                onChange={(event) => void importDisplayConfig(event.target.files?.[0] ?? null)}
              />
              <span className="pl-1 text-[11px] text-gray-500">{displayConfig?.items.length ?? 0} 项</span>
            </div>
          </div>
          {configError ? <div className="mt-2 border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">{configError}</div> : null}
        </div>
        <div
          className={`max-h-[58vh] overflow-auto ${dropTargetKey === "__root__" ? "bg-blue-50/60" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
            setDropTargetKey("__root__");
          }}
          onDragLeave={() => setDropTargetKey(null)}
          onDrop={(event) => dropCandidateAfter(event, null)}
        >
          {(displayConfig?.items ?? []).length ? (
            <table className="w-full table-fixed text-left text-[11px]">
              <thead className="sticky top-0 z-10 bg-gray-50 text-gray-500">
                <tr>
                  <th className="w-[46%] border-b border-gray-200 px-2 py-1.5 font-medium">展示名称/层级</th>
                  <th className="w-[88px] border-b border-gray-200 px-2 py-1.5 font-medium">排序</th>
                  <th className="border-b border-gray-200 px-2 py-1.5 font-medium">来源科目</th>
                  <th className="w-10 border-b border-gray-200 px-2 py-1.5 font-medium" />
                </tr>
              </thead>
              <tbody>
                {visibleConfigRows.map((item) => {
                  const hasChildren = item.children.length > 0;
                  const isExpanded = Boolean(configExpandedRows[item.row_key]);
                  return (
                  <tr
                    key={item.row_key}
                    onDragOver={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      event.dataTransfer.dropEffect = "copy";
                      setDropTargetKey(item.row_key);
                    }}
                    onDragLeave={() => setDropTargetKey(null)}
                    onDrop={(event) => dropCandidateAfter(event, item)}
                    className={`border-b border-gray-100 align-top hover:bg-gray-50 ${
                      dropTargetKey === item.row_key ? "bg-blue-50 outline outline-1 outline-blue-300" : ""
                    }`}
                    title="拖到这里会插入到此行下方，并继承此行的父级层级"
                  >
                    <td className="px-2 py-2">
                      <div className="flex min-w-0 items-center gap-1" style={{ paddingLeft: Math.max(0, item.level - 1) * 12 }}>
                        <button
                          type="button"
                          disabled={!hasChildren}
                          onClick={(event) => {
                            event.stopPropagation();
                            setConfigExpandedRows((prev) => ({ ...prev, [item.row_key]: !prev[item.row_key] }));
                          }}
                          className="inline-flex h-5 w-5 items-center justify-center text-gray-500 hover:bg-gray-100 disabled:opacity-20"
                        >
                          {hasChildren ? (isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />) : <ChevronRight className="h-3 w-3" />}
                        </button>
                        <input
                          defaultValue={item.display_name}
                          onBlur={(event) => {
                            const next = event.currentTarget.value.trim();
                            if (next && next !== item.display_name) void updateDisplayItem(item, { display_name: next });
                          }}
                          className="h-7 min-w-0 flex-1 border border-gray-300 bg-white px-2 text-[11px] text-gray-800"
                        />
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <input
                        type="number"
                        defaultValue={item.sort_order}
                        onBlur={(event) => {
                          const next = Number(event.currentTarget.value);
                          if (Number.isFinite(next) && next !== item.sort_order) void updateDisplayItem(item, { sort_order: next });
                        }}
                        className="h-7 w-full border border-gray-300 bg-white px-2 text-right text-[11px] text-gray-800"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <div className="max-w-[220px] truncate font-medium text-gray-700">
                        {configItemMetricName(item) ?? "展示层级"}
                      </div>
                      <div className="mt-0.5 max-w-[220px] truncate text-gray-500">
                        {configItemMetricCode(item) ?? "展示分类（不取数）"}
                      </div>
                      {item.org_product_ref ? (
                        <div className="mt-0.5 max-w-[220px] truncate font-mono text-[10px] text-blue-500">
                          {item.org_product_ref}
                        </div>
                      ) : null}
                      <div className="mt-0.5 max-w-[220px] truncate text-gray-400">
                        {item.row_type} / {item.display_view} / {item.value_type ?? "-"}
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <button
                        type="button"
                        onClick={() => deleteDisplayItem(item)}
                        disabled={configSaving}
                        className="inline-flex h-7 w-7 items-center justify-center border border-rose-200 bg-white text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                        title="删除展示科目"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                );
                })}
              </tbody>
            </table>
          ) : (
            <div className="px-3 py-8 text-center text-[11px] text-gray-500">还没有配置展示科目，左侧加入后报表将按配置展示。</div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-white text-xs">
      <div ref={filterRef} className="border-b border-gray-300 bg-white px-4 py-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">预算展示报表</h3>
            <div className="mt-1 text-[11px] text-gray-500">{report?.note ?? "按年份、预算基准和预测版本展示预算输出。"}</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={exportFullWorkbook}
              disabled={exporting || loading}
              className="inline-flex items-center gap-1 border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-60"
            >
              {exporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              导出全套Excel
            </button>
            <button
              type="button"
              onClick={loadReport}
              disabled={loading}
              className="inline-flex items-center gap-1 border border-gray-300 bg-white px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              刷新
            </button>
            <div className="relative">
              <button
                type="button"
                onClick={() => setOpenPanel(openPanel === "config" ? null : "config")}
                className="inline-flex items-center gap-1 border border-gray-300 bg-white px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50"
              >
                <Settings2 className="h-3.5 w-3.5" />
                展示科目配置
                <ChevronDown className="h-3 w-3" />
              </button>
              {openPanel === "config" ? renderDisplayConfigPanel() : null}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1 text-[11px] text-gray-600">
            年份
            <select
              value={selectedYear ?? report?.selected_year ?? ""}
              onChange={(event) => {
                setSelectedYear(Number(event.target.value));
                setBudgetVersionId(null);
                setForecastVersionIds(null);
                setSelectedProductCodes([]);
              }}
              className="h-7 border border-gray-300 bg-white px-2 text-[11px] text-gray-800"
            >
              {(report?.available_years ?? []).map((year) => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1 text-[11px] text-gray-600">
            预算基准
            <select
              value={budgetVersionId ?? report?.budget_version_id ?? ""}
              onChange={(event) => setBudgetVersionId(Number(event.target.value))}
              className="h-7 max-w-[240px] border border-gray-300 bg-white px-2 text-[11px] text-gray-800"
            >
              {budgetVersions.map((version) => (
                <option key={version.version_id} value={version.version_id}>{version.version_name}</option>
              ))}
            </select>
          </label>
          <div className="relative">
            <button
              type="button"
              onClick={() => setOpenPanel(openPanel === "forecast" ? null : "forecast")}
              className="inline-flex h-7 items-center gap-1 border border-gray-300 bg-white px-2 text-[11px] text-gray-700 hover:bg-gray-50"
            >
              <Filter className="h-3.5 w-3.5" />
              预测版本：{activeForecastVersions.length ? `已选 ${activeForecastVersions.length} 个` : "未选择"}
              <ChevronDown className="h-3 w-3" />
            </button>
            {openPanel === "forecast" ? (
              <div className="absolute left-0 top-8 z-40 w-[360px] border border-gray-300 bg-white p-2 shadow-lg">
                <div className="mb-2 text-[11px] font-medium text-gray-700">选择预测版本</div>
                <div className="max-h-64 overflow-auto">
                  {forecastVersions.map((version) => {
                    const checked = (forecastVersionIds ?? report?.forecast_version_ids ?? []).includes(version.version_id);
                    return (
                      <label key={version.version_id} className="flex cursor-pointer items-center gap-2 px-2 py-1 text-[11px] hover:bg-gray-50">
                        <input type="checkbox" checked={checked} onChange={() => toggleForecastVersion(version.version_id)} />
                        <span className="min-w-0 flex-1 truncate">{version.version_name}</span>
                        {checked ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : null}
                      </label>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </div>
          <div className="relative">
            <button
              type="button"
              onClick={() => setOpenPanel(openPanel === "product" ? null : "product")}
              className="inline-flex h-7 items-center gap-1 border border-gray-300 bg-white px-2 text-[11px] text-gray-700 hover:bg-gray-50"
            >
              <Filter className="h-3.5 w-3.5" />
              产品范围：{selectedProductCodes.length === 0 ? "全行" : selectedProductNames.slice(0, 2).join("、") + (selectedProductCodes.length > 2 ? ` 等${selectedProductCodes.length}个` : "")}
              <ChevronDown className="h-3 w-3" />
            </button>
            {openPanel === "product" ? (
              <div className="absolute left-0 top-8 z-40 w-[380px] border border-gray-300 bg-white p-2 shadow-lg">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-[11px] font-medium text-gray-700">选择产品节点</span>
                  <button
                    type="button"
                    className="text-[11px] text-blue-700 hover:underline"
                    onClick={() => {
                      setSelectedProductCodes([]);
                      setOpenPanel(null);
                    }}
                  >
                    全行
                  </button>
                </div>
                <div className="mb-2 flex h-7 items-center gap-1 border border-gray-300 px-2">
                  <Search className="h-3.5 w-3.5 text-gray-400" />
                  <input value={productSearch} onChange={(event) => setProductSearch(event.target.value)} placeholder="搜索产品" className="min-w-0 flex-1 outline-none" />
                </div>
                <div className="max-h-72 overflow-auto">{visibleProductTree.map((node) => renderProductNode(node))}</div>
                <div className="mt-2 flex items-center justify-between border-t border-gray-200 pt-2">
                  <span className="text-[11px] text-gray-500">
                    {selectedProductCodes.length === 0 ? "当前为全行范围" : `已选 ${selectedProductCodes.length} 个产品范围`}
                  </span>
                  <button
                    type="button"
                    className="inline-flex h-7 items-center gap-1 border border-blue-200 bg-blue-50 px-2 text-[11px] font-medium text-blue-700 hover:bg-blue-100"
                    onClick={() => setOpenPanel(null)}
                  >
                    <Check className="h-3.5 w-3.5" />
                    完成
                  </button>
                </div>
              </div>
            ) : null}
          </div>
          <select value={unitDivisor} onChange={(event) => setUnitDivisor(Number(event.target.value))} className="h-7 border border-gray-300 bg-white px-2 text-[11px]">
            {amountUnits.map((unit) => <option key={unit.label} value={unit.divisor}>单位：{unit.label}</option>)}
          </select>
        </div>
        <div className="mt-3 flex items-center gap-1 border-b border-gray-300">
          {[
            { id: "total" as const, label: "全行总表" },
            { id: "products" as const, label: "分产品概览" },
            { id: "detail" as const, label: "产品明细模块" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setViewMode(tab.id)}
              className={`border-x border-t border-gray-300 px-3 py-1.5 text-[11px] ${
                viewMode === tab.id ? "bg-white font-semibold text-gray-900" : "bg-gray-100 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      {error ? <div className="m-4 border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div> : null}
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {!report && loading ? (
          <div className="flex h-full items-center justify-center text-gray-500"><Loader2 className="mr-2 h-4 w-4 animate-spin" />正在加载预算展示报表...</div>
        ) : report ? (
          <div className="space-y-4">
            <div className="text-[11px] text-gray-500">{report.title} / 默认展开到指标科目 2 级 / 月度明细在版本表头展开</div>
            {viewMode === "total" ? renderTable(report.total_rows, "全行总表", report.report_tree) : null}
            {viewMode === "products" ? (
              (report.product_overview_blocks?.length ?? 0) > 0 ? renderProductOverviewTable() : <div className="border border-gray-200 bg-white px-4 py-8 text-center text-gray-500">当前条件下暂无分产品概览数据。</div>
            ) : null}
            {viewMode === "detail" ? renderProductDetailModule() : null}
          </div>
        ) : (
          <div className="py-10 text-center text-gray-500">暂无报表数据。</div>
        )}
      </div>
    </div>
  );
}
