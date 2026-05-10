import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronsDown,
  ChevronsUp,
  Download,
  Maximize2,
  Minimize2,
  RefreshCw,
  Search,
} from "lucide-react";
import { apiGet, apiPostBlob } from "@/lib/api";

type ExpenseBudgetExecutionMode = "query" | "template";
type ExpenseBudgetExecutionPerspective = "entity" | "group" | "owner_dept";
type AmountUnit = "yuan" | "thousand" | "ten_thousand" | "million" | "hundred_million";

type ExpenseBudgetExecutionRowDto = {
  perspective: ExpenseBudgetExecutionPerspective;
  dimension_value: string;
  entity_name: string;
  group_name: string;
  owner_dept: string;
  budget_subject: string;
  monthly_actuals: number[];
  cumulative_actual: number;
  annual_budget: number;
  execution_rate: number | null;
};

type ExpenseBudgetExecutionTemplateSubjectNodeDto = {
  id: number;
  parent_id: number | null;
  level_number: number;
  level_label: string;
  subject_name: string;
  formula_text: string | null;
  sort_order: number;
  is_leaf: boolean;
  monthly_actuals: number[];
  previous_year_monthly_actuals: number[];
  current_actual: number;
  annual_budget: number;
  budget_progress: number | null;
  yoy_change: number;
  yoy_rate: number | null;
  last_year_actual: number;
  children: ExpenseBudgetExecutionTemplateSubjectNodeDto[];
};

type ExpenseBudgetExecutionResponseDto = {
  mode?: ExpenseBudgetExecutionMode;
  perspective: ExpenseBudgetExecutionPerspective;
  budget_year: number;
  version_id: number;
  version_name: string;
  current_month: number;
  framework_source_mode: "internal" | "source";
  actual_source_mode: "internal" | "source";
  framework_source_file: string;
  actual_source_file: string;
  previous_actual_source_file?: string;
  available_entities?: string[];
  selected_entity_name?: string;
  template_title?: string;
  rows?: ExpenseBudgetExecutionRowDto[];
  subject_tree?: ExpenseBudgetExecutionTemplateSubjectNodeDto[];
  note: string;
};

type TemplateSubjectContextMenuState = {
  x: number;
  y: number;
  node: {
    id: number;
    name: string;
    hasChildren: boolean;
    isOpen: boolean;
  };
};

const monthLabels = Array.from({ length: 12 }, (_, idx) => `${idx + 1}月实际`);
const TEMPLATE_REPORT_MONTH_STORAGE_KEY = "expense-budget-execution-template-report-month";
const TEMPLATE_ENTITY_STORAGE_KEY = "expense-budget-execution-template-entity";
const AMOUNT_UNIT_STORAGE_KEY = "expense-budget-execution-amount-unit";
const amountUnitOptions: Array<{ value: AmountUnit; label: string; divisor: number }> = [
  { value: "yuan", label: "元", divisor: 1 },
  { value: "thousand", label: "千元", divisor: 1_000 },
  { value: "ten_thousand", label: "万元", divisor: 10_000 },
  { value: "million", label: "百万元", divisor: 1_000_000 },
  { value: "hundred_million", label: "亿元", divisor: 100_000_000 },
];

function formatNumber(value: number | null | undefined, divisor = 1): string {
  if (value == null || Number.isNaN(value)) return "-";
  return (value / divisor).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function findTemplateNodeById(
  nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[],
  id: number,
): ExpenseBudgetExecutionTemplateSubjectNodeDto | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = findTemplateNodeById(node.children, id);
    if (child) return child;
  }
  return null;
}

function collectTemplateNodeIds(
  node: ExpenseBudgetExecutionTemplateSubjectNodeDto,
): number[] {
  const ids = [node.id];
  node.children.forEach((child) => ids.push(...collectTemplateNodeIds(child)));
  return ids;
}

export function ExpenseBudgetExecutionContent() {
  const [reportMode, setReportMode] = useState<ExpenseBudgetExecutionMode>("query");
  const [perspective, setPerspective] = useState<ExpenseBudgetExecutionPerspective>("group");
  const [queryKeyword, setQueryKeyword] = useState("");
  const [templateKeyword, setTemplateKeyword] = useState("");
  const [templateEntityName, setTemplateEntityName] = useState("");
  const [templateReportMonth, setTemplateReportMonth] = useState("");
  const [amountUnit, setAmountUnit] = useState<AmountUnit>("yuan");
  const [includeZeroRows, setIncludeZeroRows] = useState(false);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [report, setReport] = useState<ExpenseBudgetExecutionResponseDto | null>(null);
  const [templateMonthlyExpanded, setTemplateMonthlyExpanded] = useState(false);
  const [templateLastYearMonthlyExpanded, setTemplateLastYearMonthlyExpanded] = useState(false);
  const [templateExpanded, setTemplateExpanded] = useState<Record<number, boolean>>({});
  const [selectedTemplateSubjectId, setSelectedTemplateSubjectId] = useState<number | null>(null);
  const [templateContextMenu, setTemplateContextMenu] = useState<TemplateSubjectContextMenuState | null>(null);
  const templateContextMenuRef = useRef<HTMLDivElement>(null);
  const activeKeyword = reportMode === "template" ? templateKeyword : queryKeyword;
  const amountDivisor = amountUnitOptions.find((option) => option.value === amountUnit)?.divisor ?? 1;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedUnit = window.localStorage.getItem(AMOUNT_UNIT_STORAGE_KEY) as AmountUnit | null;
    if (savedUnit && amountUnitOptions.some((option) => option.value === savedUnit)) {
      setAmountUnit(savedUnit);
    }
  }, []);

  const loadReport = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        mode: reportMode,
        perspective,
        keyword: activeKeyword,
        include_zero_rows: String(includeZeroRows),
      });
      if (reportMode === "template" && templateEntityName) {
        params.set("entity_name", templateEntityName);
      }
      if (reportMode === "template" && templateReportMonth) {
        params.set("report_month", templateReportMonth);
      }
      const result = await apiGet<ExpenseBudgetExecutionResponseDto>(`/api/expense-budget-execution?${params.toString()}`);
      setReport(result);
    } catch (e) {
      alert(e instanceof Error ? `加载费用预算执行报表失败：${e.message}` : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [activeKeyword, includeZeroRows, perspective, reportMode, templateEntityName, templateReportMonth]);

  useEffect(() => {
    if (reportMode !== "template") return;
    if (!report?.current_month) return;
    if (!templateReportMonth) {
      const savedMonth =
        typeof window !== "undefined"
          ? window.localStorage.getItem(TEMPLATE_REPORT_MONTH_STORAGE_KEY)
          : null;
      const savedMonthNumber = Number(savedMonth || 0);
      if (savedMonth && savedMonthNumber >= 1 && savedMonthNumber <= 12) {
        setTemplateReportMonth(String(savedMonthNumber));
        return;
      }
      setTemplateReportMonth(String(report.current_month));
    }
  }, [report?.current_month, reportMode, templateReportMonth]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!templateReportMonth) return;
    window.localStorage.setItem(TEMPLATE_REPORT_MONTH_STORAGE_KEY, templateReportMonth);
  }, [templateReportMonth]);

  useEffect(() => {
    if (reportMode !== "template") return;
    const availableEntities = report?.available_entities ?? [];
    if (availableEntities.length === 0) return;
    if (templateEntityName) return;
    const savedEntity =
      typeof window !== "undefined"
        ? window.localStorage.getItem(TEMPLATE_ENTITY_STORAGE_KEY)
        : null;
    if (savedEntity && availableEntities.includes(savedEntity)) {
      setTemplateEntityName(savedEntity);
    }
  }, [report?.available_entities, reportMode, templateEntityName]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(TEMPLATE_ENTITY_STORAGE_KEY, templateEntityName);
  }, [templateEntityName]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(AMOUNT_UNIT_STORAGE_KEY, amountUnit);
  }, [amountUnit]);

  useEffect(() => {
    void loadReport();
  }, [loadReport]);

  useEffect(() => {
    const onOutside = (e: MouseEvent) => {
      if (
        templateContextMenuRef.current &&
        !templateContextMenuRef.current.contains(e.target as Node)
      ) {
        setTemplateContextMenu(null);
      }
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, []);

  useEffect(() => {
    if (reportMode !== "template") return;
    const subjectTree = report?.subject_tree ?? [];
    if (subjectTree.length === 0) return;
    setTemplateExpanded((prev) => {
      if (Object.keys(prev).length > 0) return prev;
      const next: Record<number, boolean> = {};
      const walk = (nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[]) => {
        nodes.forEach((node) => {
          if (node.level_number <= 2) next[node.id] = true;
          walk(node.children);
        });
      };
      walk(subjectTree);
      return next;
    });
  }, [report, reportMode]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const { blob, filename } = await apiPostBlob("/api/expense-budget-execution/export", {
        mode: reportMode,
        perspective,
        keyword: activeKeyword,
        include_zero_rows: includeZeroRows,
        entity_name: reportMode === "template" ? templateEntityName : "",
        report_month: reportMode === "template" && templateReportMonth ? Number(templateReportMonth) : undefined,
        include_monthly_actuals: reportMode === "template" ? templateMonthlyExpanded : false,
        include_last_year_monthly_actuals: reportMode === "template" ? templateLastYearMonthlyExpanded : false,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || "expense_budget_execution.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? `导出失败：${e.message}` : "导出失败");
    } finally {
      setExporting(false);
    }
  };

  const summaryText = useMemo(() => {
    if (!report) return "";
    if (reportMode === "template") {
      const entityText = report.selected_entity_name ? ` / 主体 ${report.selected_entity_name}` : " / 全部主体";
      return `${report.template_title || `${report.budget_year}年${report.current_month}月费用统计表`}${entityText} / 费用类型共 ${
        report.subject_tree?.length ?? 0
      } 个一级节点`;
    }
    const dimLabel =
      perspective === "entity" ? "主体" : perspective === "group" ? "事业群" : "费用归属部门";
    return `${report.budget_year}年 / 版本${report.version_id} ${report.version_name} / 当前月窗口 ${report.current_month} / ${dimLabel}视角共 ${report.rows?.length ?? 0} 行`;
  }, [perspective, report, reportMode]);

  const templateTree = report?.subject_tree ?? [];
  const visibleMonthlyLabels = useMemo(
    () => Array.from({ length: report?.current_month ?? 0 }, (_, idx) => `${idx + 1}月实际`),
    [report?.current_month],
  );
  const visibleLastYearMonthlyLabels = useMemo(
    () => {
      const previousYearShort = String((report?.budget_year ?? new Date().getFullYear()) - 1).slice(-2);
      return Array.from({ length: 12 }, (_, idx) => `${previousYearShort}年${idx + 1}月实际`);
    },
    [report?.budget_year],
  );

  const toggleTemplateExpanded = (id: number) => {
    setTemplateExpanded((prev) => ({ ...prev, [id]: !(prev[id] ?? false) }));
  };

  const collapseTemplateCurrentLevel = () => {
    if (selectedTemplateSubjectId != null) {
      setTemplateExpanded((prev) => ({ ...prev, [selectedTemplateSubjectId]: false }));
      return;
    }
    setTemplateExpanded((prev) => {
      const next = { ...prev };
      templateTree.forEach((node) => {
        next[node.id] = false;
      });
      return next;
    });
  };

  const expandTemplateNextLevel = () => {
    if (selectedTemplateSubjectId != null) {
      setTemplateExpanded((prev) => ({ ...prev, [selectedTemplateSubjectId]: true }));
      return;
    }
    setTemplateExpanded((prev) => {
      const next = { ...prev };
      templateTree.forEach((node) => {
        next[node.id] = true;
      });
      return next;
    });
  };

  const collapseTemplateAll = () => {
    const next: Record<number, boolean> = {};
    const walk = (nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[]) => {
      nodes.forEach((node) => {
        next[node.id] = false;
        walk(node.children);
      });
    };
    walk(templateTree);
    setTemplateExpanded(next);
  };

  const expandTemplateAll = () => {
    const next: Record<number, boolean> = {};
    const walk = (nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[]) => {
      nodes.forEach((node) => {
        next[node.id] = true;
        walk(node.children);
      });
    };
    walk(templateTree);
    setTemplateExpanded(next);
  };

  const expandTemplateDescendants = () => {
    if (selectedTemplateSubjectId == null) {
      expandTemplateAll();
      return;
    }
    const selectedNode = findTemplateNodeById(templateTree, selectedTemplateSubjectId);
    if (!selectedNode) return;
    const ids = collectTemplateNodeIds(selectedNode);
    setTemplateExpanded((prev) => {
      const next = { ...prev };
      ids.forEach((id) => {
        next[id] = true;
      });
      return next;
    });
  };

  const collapseTemplateDescendants = () => {
    if (selectedTemplateSubjectId == null) {
      collapseTemplateAll();
      return;
    }
    const selectedNode = findTemplateNodeById(templateTree, selectedTemplateSubjectId);
    if (!selectedNode) return;
    const ids = collectTemplateNodeIds(selectedNode);
    setTemplateExpanded((prev) => {
      const next = { ...prev };
      ids.forEach((id) => {
        next[id] = false;
      });
      return next;
    });
  };

  const renderTemplateRows = (
    nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[],
  ): JSX.Element[] =>
    nodes.flatMap((node) => {
      const isOpen = templateExpanded[node.id] ?? false;
      const hasChildren = node.children.length > 0;
      const isSelected = selectedTemplateSubjectId === node.id;
      const row = (
        <tr
          key={node.id}
          className={`${isSelected ? "bg-blue-50" : "odd:bg-white even:bg-gray-50"} cursor-pointer`}
          onClick={() => setSelectedTemplateSubjectId(node.id)}
          onContextMenu={(e) => {
            e.preventDefault();
            setSelectedTemplateSubjectId(node.id);
            setTemplateContextMenu({
              x: e.clientX,
              y: e.clientY,
              node: {
                id: node.id,
                name: node.subject_name,
                hasChildren,
                isOpen,
              },
            });
          }}
        >
          <td className="border border-gray-200 px-2 py-1.5 text-gray-800">
            <div
              className="flex items-center gap-1"
              style={{ paddingLeft: `${Math.max(node.level_number - 1, 0) * 20}px` }}
            >
              {hasChildren ? (
                <button
                  type="button"
                  className="p-0.5 hover:bg-gray-200 rounded"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleTemplateExpanded(node.id);
                  }}
                >
                  {isOpen ? (
                    <ChevronDown className="w-3 h-3 text-gray-600" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-gray-600" />
                  )}
                </button>
              ) : (
                <span className="w-4" />
              )}
              <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] text-slate-600 whitespace-nowrap">
                {node.level_label}
              </span>
              <span>{node.subject_name}</span>
            </div>
          </td>
          <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
            {formatNumber(node.current_actual, amountDivisor)}
          </td>
          {templateMonthlyExpanded
            ? visibleMonthlyLabels.map((_, idx) => (
                <td key={`${node.id}-month-${idx}`} className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                  {formatNumber(node.monthly_actuals?.[idx] ?? 0, amountDivisor)}
                </td>
              ))
            : null}
          <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
            {formatNumber(node.annual_budget, amountDivisor)}
          </td>
          <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
            {formatPercent(node.budget_progress)}
          </td>
          <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
            {formatNumber(node.yoy_change, amountDivisor)}
          </td>
          <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
            {formatPercent(node.yoy_rate)}
          </td>
          <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
            {formatNumber(node.last_year_actual, amountDivisor)}
          </td>
          {templateLastYearMonthlyExpanded
            ? visibleLastYearMonthlyLabels.map((_, idx) => (
                <td
                  key={`${node.id}-last-year-month-${idx}`}
                  className="border border-gray-200 px-2 py-1.5 text-right text-gray-700"
                >
                  {formatNumber(node.previous_year_monthly_actuals?.[idx] ?? 0, amountDivisor)}
                </td>
              ))
            : null}
        </tr>
      );
      if (!hasChildren || !isOpen) return [row];
      return [row, ...renderTemplateRows(node.children)];
    });

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-gray-800">费用预算执行报表</h3>
          <p className="text-xs text-gray-500 mt-1">
            {summaryText ||
              "保留原查询模式，同时支持月报模式按部门预算科目层级查看费用类型执行情况"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void loadReport()}
            disabled={loading}
            className="px-3 py-1.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 disabled:opacity-60 inline-flex items-center gap-1"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || loading}
            className="px-3 py-1.5 text-xs rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 inline-flex items-center gap-1"
          >
            <Download className="w-3.5 h-3.5" />
            {exporting ? "导出中..." : "导出Excel"}
          </button>
        </div>
      </div>

      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex flex-wrap items-center gap-3 text-xs">
        <label className="flex items-center gap-2">
          <span className="text-gray-600">展示模式</span>
          <select
            value={reportMode}
            onChange={(e) => {
              setReportMode(e.target.value as ExpenseBudgetExecutionMode);
              setTemplateContextMenu(null);
            }}
            className="border border-gray-300 rounded px-2 py-1 bg-white"
          >
            <option value="query">查询模式</option>
            <option value="template">月报模式</option>
          </select>
        </label>
        {reportMode === "query" ? (
        <label className="flex items-center gap-2">
          <span className="text-gray-600">报表视角</span>
          <select
            value={perspective}
            onChange={(e) => setPerspective(e.target.value as ExpenseBudgetExecutionPerspective)}
            className="border border-gray-300 rounded px-2 py-1 bg-white"
          >
            <option value="entity">主体</option>
            <option value="group">事业群</option>
            <option value="owner_dept">费用归属部门</option>
          </select>
        </label>
        ) : null}
        {reportMode === "template" ? (
        <label className="flex items-center gap-2">
          <span className="text-gray-600">主体</span>
          <select
            value={templateEntityName}
            onChange={(e) => setTemplateEntityName(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 bg-white min-w-[10rem]"
          >
            <option value="">全部主体</option>
            {(report?.available_entities ?? []).map((entityName) => (
              <option key={entityName} value={entityName}>
                {entityName}
              </option>
            ))}
          </select>
        </label>
        ) : null}
        {reportMode === "template" ? (
        <label className="flex items-center gap-2">
          <span className="text-gray-600">费用月份</span>
          <select
            value={templateReportMonth || String(report?.current_month ?? "")}
            onChange={(e) => setTemplateReportMonth(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 bg-white"
          >
            {Array.from({ length: 12 }, (_, idx) => {
              const month = idx + 1;
              return (
                <option key={month} value={String(month)}>
                  {month}月
                </option>
              );
            })}
          </select>
        </label>
        ) : null}
        <label className="flex items-center gap-2">
          <span className="text-gray-600">单位</span>
          <select
            value={amountUnit}
            onChange={(e) => setAmountUnit(e.target.value as AmountUnit)}
            className="border border-gray-300 rounded px-2 py-1 bg-white"
          >
            {amountUnitOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-gray-600">关键字</span>
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2 top-1.5 text-gray-400" />
            <input
              value={activeKeyword}
              onChange={(e) => {
                const value = e.target.value;
                if (reportMode === "template") {
                  setTemplateKeyword(value);
                } else {
                  setQueryKeyword(value);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") void loadReport();
              }}
              placeholder={
                reportMode === "template"
                  ? "搜索费用类型/层级"
                  : "搜索主体、事业群、费用归属部门或预算科目"
              }
              className="pl-7 pr-2 py-1 border border-gray-300 rounded w-56 bg-white"
            />
          </div>
        </label>
        {reportMode === "query" ? (
        <label className="flex items-center gap-2 text-gray-600">
          <input
            type="checkbox"
            checked={includeZeroRows}
            onChange={(e) => setIncludeZeroRows(e.target.checked)}
          />
          包含预算和实际都为0的行
        </label>
        ) : null}
        <button
          onClick={() => void loadReport()}
          disabled={loading}
          className="px-3 py-1 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 disabled:opacity-60"
        >
          查询
        </button>
      </div>

      <div className="flex-1 overflow-auto">
        {reportMode === "template" ? (
          <div className="h-full flex flex-col">
            <div className="px-4 py-2 border-b border-gray-200 bg-slate-50 flex items-center gap-2 text-xs">
              <span className="font-medium text-slate-700">
                {report?.template_title || "月报模式"}
              </span>
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  title="收起当前选中的费用类型；未选中时收起所有一级费用类型"
                  onClick={collapseTemplateCurrentLevel}
                  className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
                >
                  <Minimize2 className="w-3 h-3" />
                  <span>收起本级</span>
                </button>
                <button
                  type="button"
                  title="展开当前选中的费用类型；未选中时展开所有一级费用类型"
                  onClick={expandTemplateNextLevel}
                  className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
                >
                  <Maximize2 className="w-3 h-3" />
                  <span>展开下级</span>
                </button>
                <button
                  type="button"
                  title="展开选中费用类型下全部层级；未选中时展开整棵树"
                  onClick={expandTemplateDescendants}
                  className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
                >
                  <ChevronsDown className="w-3 h-3" />
                  <span>展开全部下级</span>
                </button>
                <button
                  type="button"
                  title="收起选中费用类型及其全部下级；未选中时收起整棵树"
                  onClick={collapseTemplateDescendants}
                  className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
                >
                  <ChevronsUp className="w-3 h-3" />
                  <span>收起全部下级</span>
                </button>
              </div>
            </div>
            <table className="min-w-[1200px] w-full border-collapse text-xs">
              <thead className="sticky top-0 z-10 bg-gray-100">
                <tr className="text-left text-gray-700">
                  <th className="border border-gray-200 px-2 py-2">费用类型</th>
                  <th className="border border-gray-200 px-2 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => setTemplateMonthlyExpanded((prev) => !prev)}
                      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${
                        templateMonthlyExpanded
                          ? "bg-blue-100 text-blue-700 hover:bg-blue-200"
                          : "bg-white text-gray-700 hover:bg-gray-100"
                      }`}
                      title={templateMonthlyExpanded ? "收起分月实际" : "展开分月实际"}
                    >
                      {templateMonthlyExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5" />
                      )}
                      <span>本年实际</span>
                    </button>
                  </th>
                  {templateMonthlyExpanded
                    ? visibleMonthlyLabels.map((label) => (
                        <th key={label} className="border border-gray-200 px-2 py-2 text-right">
                          {label}
                        </th>
                      ))
                    : null}
                  <th className="border border-gray-200 px-2 py-2 text-right">本年预算</th>
                  <th className="border border-gray-200 px-2 py-2 text-right">预算进度%</th>
                  <th className="border border-gray-200 px-2 py-2 text-right">本年同比增减额</th>
                  <th className="border border-gray-200 px-2 py-2 text-right">本年同比%</th>
                  <th className="border border-gray-200 px-2 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => setTemplateLastYearMonthlyExpanded((prev) => !prev)}
                      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${
                        templateLastYearMonthlyExpanded
                          ? "bg-blue-100 text-blue-700 hover:bg-blue-200"
                          : "bg-white text-gray-700 hover:bg-gray-100"
                      }`}
                      title={templateLastYearMonthlyExpanded ? "收起去年分月实际" : "展开去年分月实际"}
                    >
                      {templateLastYearMonthlyExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5" />
                      )}
                      <span>去年同期</span>
                    </button>
                  </th>
                  {templateLastYearMonthlyExpanded
                    ? visibleLastYearMonthlyLabels.map((label) => (
                        <th key={label} className="border border-gray-200 px-2 py-2 text-right">
                          {label}
                        </th>
                      ))
                    : null}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td
                      colSpan={
                        7 +
                        (templateMonthlyExpanded ? visibleMonthlyLabels.length : 0) +
                        (templateLastYearMonthlyExpanded ? visibleLastYearMonthlyLabels.length : 0)
                      }
                      className="px-2 py-8 text-center text-gray-500"
                    >
                      正在加载月报模式报表...
                    </td>
                  </tr>
                ) : templateTree.length === 0 ? (
                  <tr>
                    <td
                      colSpan={
                        7 +
                        (templateMonthlyExpanded ? visibleMonthlyLabels.length : 0) +
                        (templateLastYearMonthlyExpanded ? visibleLastYearMonthlyLabels.length : 0)
                      }
                      className="px-2 py-8 text-center text-gray-500"
                    >
                      当前条件下没有可展示的费用类型数据。
                    </td>
                  </tr>
                ) : (
                  renderTemplateRows(templateTree)
                )}
              </tbody>
            </table>
          </div>
        ) : (
        <table className="min-w-[1800px] w-full border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-gray-100">
            <tr className="text-left text-gray-700">
              <th className="border border-gray-200 px-2 py-2">查询维度值</th>
              <th className="border border-gray-200 px-2 py-2">主体</th>
              <th className="border border-gray-200 px-2 py-2">事业群</th>
              <th className="border border-gray-200 px-2 py-2">费用归属部门</th>
              <th className="border border-gray-200 px-2 py-2">部门预算科目</th>
              {monthLabels.map((label) => (
                <th key={label} className="border border-gray-200 px-2 py-2 text-right">
                  {label}
                </th>
              ))}
              <th className="border border-gray-200 px-2 py-2 text-right">累计实际</th>
              <th className="border border-gray-200 px-2 py-2 text-right">年度预算</th>
              <th className="border border-gray-200 px-2 py-2 text-right">年度预算执行率</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={20} className="px-2 py-8 text-center text-gray-500">
                  正在加载费用预算执行报表...
                </td>
              </tr>
            ) : !report || (report.rows?.length ?? 0) === 0 ? (
              <tr>
                <td colSpan={20} className="px-2 py-8 text-center text-gray-500">
                  当前条件下没有可展示的数据。
                </td>
              </tr>
            ) : (
              (report.rows ?? []).map((row, idx) => (
                <tr key={`${row.dimension_value}-${row.budget_subject}-${idx}`} className="odd:bg-white even:bg-gray-50">
                  <td className="border border-gray-200 px-2 py-1.5 text-gray-800">{row.dimension_value}</td>
                  <td className="border border-gray-200 px-2 py-1.5 text-gray-700">{row.entity_name || "-"}</td>
                  <td className="border border-gray-200 px-2 py-1.5 text-gray-700">{row.group_name || "-"}</td>
                  <td className="border border-gray-200 px-2 py-1.5 text-gray-700">{row.owner_dept || "-"}</td>
                  <td className="border border-gray-200 px-2 py-1.5 text-gray-700">{row.budget_subject}</td>
                  {row.monthly_actuals.map((value, monthIdx) => (
                    <td key={`${idx}-${monthIdx}`} className="border border-gray-200 px-2 py-1.5 text-right text-gray-700">
                      {formatNumber(value, amountDivisor)}
                    </td>
                  ))}
                  <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-800">{formatNumber(row.cumulative_actual, amountDivisor)}</td>
                  <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-800">{formatNumber(row.annual_budget, amountDivisor)}</td>
                  <td className="border border-gray-200 px-2 py-1.5 text-right text-gray-800">{formatPercent(row.execution_rate)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        )}
      </div>
      {reportMode === "template" && templateContextMenu ? (
        <div
          ref={templateContextMenuRef}
          className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[180px]"
          style={{ left: templateContextMenu.x, top: templateContextMenu.y }}
        >
          {templateContextMenu.node.hasChildren ? (
            <button
              type="button"
              onClick={() => {
                toggleTemplateExpanded(templateContextMenu.node.id);
                setTemplateContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100"
            >
              {templateContextMenu.node.isOpen ? "收起本级" : "展开下级"}
            </button>
          ) : null}
          {templateContextMenu.node.hasChildren ? (
            <button
              type="button"
              onClick={() => {
                const node = findTemplateNodeById(templateTree, templateContextMenu.node.id);
                if (node) {
                  const ids = collectTemplateNodeIds(node);
                  setTemplateExpanded((prev) => {
                    const next = { ...prev };
                    ids.forEach((id) => {
                      next[id] = true;
                    });
                    return next;
                  });
                }
                setTemplateContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100"
            >
              展开全部下级
            </button>
          ) : null}
          {templateContextMenu.node.hasChildren ? (
            <button
              type="button"
              onClick={() => {
                const node = findTemplateNodeById(templateTree, templateContextMenu.node.id);
                if (node) {
                  const ids = collectTemplateNodeIds(node);
                  setTemplateExpanded((prev) => {
                    const next = { ...prev };
                    ids.forEach((id) => {
                      next[id] = false;
                    });
                    return next;
                  });
                }
                setTemplateContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100"
            >
              收起全部下级
            </button>
          ) : null}
          <div className="border-t border-gray-200 my-1" />
          <button
            type="button"
            onClick={() => {
              setSelectedTemplateSubjectId(null);
              setTemplateContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100"
          >
            取消选中
          </button>
        </div>
      ) : null}
    </div>
  );
}
