import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { ChevronsDown, ChevronsUp, Maximize2, Minimize2 } from "lucide-react";
import type {
  ExpenseBudgetExecutionMode,
  ExpenseBudgetExecutionTemplateSubjectNodeDto,
} from "@/lib/expense/expenseBudgetExecutionApi";
import {
  formatExpenseBudgetExecutionNumber,
  formatExpenseBudgetExecutionPercent,
} from "@/lib/expense/expenseBudgetExecutionViewModel";
import {
  GridToolbar,
  ReportGrid,
  type FinancialGridColumn,
  type FinancialGridColumnGroup,
} from "@/app/components/ui/financial-grid";

type TreeContextMenuState = {
  x: number;
  y: number;
  node: {
    id: number;
    hasChildren: boolean;
    isOpen: boolean;
  };
};

type ExpenseBudgetExecutionTreeReportProps = {
  reportMode: ExpenseBudgetExecutionMode;
  title: string;
  nodeLabel: string;
  loading: boolean;
  loadingText: string;
  rows: ExpenseBudgetExecutionTemplateSubjectNodeDto[];
  amountDivisor: number;
  visibleMonthlyLabels: string[];
  visibleLastYearMonthlyLabels: string[];
  expandedRows: Record<number, boolean>;
  setExpandedRows: Dispatch<SetStateAction<Record<number, boolean>>>;
  selectedRowId: number | null;
  setSelectedRowId: Dispatch<SetStateAction<number | null>>;
  currentActualExpanded: boolean;
  setCurrentActualExpanded: Dispatch<SetStateAction<boolean>>;
  lastYearActualExpanded: boolean;
  setLastYearActualExpanded: Dispatch<SetStateAction<boolean>>;
};

function findTreeNodeById(
  nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[],
  id: number,
): ExpenseBudgetExecutionTemplateSubjectNodeDto | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = findTreeNodeById(node.children, id);
    if (child) return child;
  }
  return null;
}

function collectTreeNodeIds(node: ExpenseBudgetExecutionTemplateSubjectNodeDto): number[] {
  const ids = [node.id];
  node.children.forEach((child) => ids.push(...collectTreeNodeIds(child)));
  return ids;
}

function flattenVisibleRows(
  nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[],
  expandedRows: Record<number, boolean>,
): ExpenseBudgetExecutionTemplateSubjectNodeDto[] {
  return nodes.flatMap((node) => {
    const childrenVisible = (expandedRows[node.id] ?? false) && node.children.length > 0;
    return childrenVisible ? [node, ...flattenVisibleRows(node.children, expandedRows)] : [node];
  });
}

export function ExpenseBudgetExecutionTreeReport({
  reportMode,
  title,
  nodeLabel,
  loading,
  loadingText,
  rows,
  amountDivisor,
  visibleMonthlyLabels,
  visibleLastYearMonthlyLabels,
  expandedRows,
  setExpandedRows,
  selectedRowId,
  setSelectedRowId,
  currentActualExpanded,
  setCurrentActualExpanded,
  lastYearActualExpanded,
  setLastYearActualExpanded,
}: ExpenseBudgetExecutionTreeReportProps) {
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const [contextMenu, setContextMenu] = useState<TreeContextMenuState | null>(null);
  const visibleRows = loading ? [] : flattenVisibleRows(rows, expandedRows);

  useEffect(() => {
    const onOutside = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, []);

  useEffect(() => {
    setContextMenu(null);
  }, [reportMode, rows]);

  const toggleExpanded = (id: number) => {
    setExpandedRows((prev) => ({ ...prev, [id]: !(prev[id] ?? false) }));
  };

  const collapseCurrentLevel = () => {
    if (selectedRowId != null) {
      setExpandedRows((prev) => ({ ...prev, [selectedRowId]: false }));
      return;
    }
    setExpandedRows((prev) => {
      const next = { ...prev };
      rows.forEach((node) => {
        next[node.id] = false;
      });
      return next;
    });
  };

  const expandNextLevel = () => {
    if (selectedRowId != null) {
      setExpandedRows((prev) => ({ ...prev, [selectedRowId]: true }));
      return;
    }
    setExpandedRows((prev) => {
      const next = { ...prev };
      rows.forEach((node) => {
        next[node.id] = true;
      });
      return next;
    });
  };

  const setAllRowsExpanded = (expanded: boolean) => {
    const next: Record<number, boolean> = {};
    const walk = (nodes: ExpenseBudgetExecutionTemplateSubjectNodeDto[]) => {
      nodes.forEach((node) => {
        next[node.id] = expanded;
        walk(node.children);
      });
    };
    walk(rows);
    setExpandedRows(next);
  };

  const setSelectedDescendantsExpanded = (expanded: boolean) => {
    if (selectedRowId == null) {
      setAllRowsExpanded(expanded);
      return;
    }
    const selectedNode = findTreeNodeById(rows, selectedRowId);
    if (!selectedNode) return;
    const ids = collectTreeNodeIds(selectedNode);
    setExpandedRows((prev) => {
      const next = { ...prev };
      ids.forEach((id) => {
        next[id] = expanded;
      });
      return next;
    });
  };

  const columnGroups: FinancialGridColumnGroup[] = [
    {
      id: "currentActual",
      header: "本年实际",
      collapsible: true,
      colSpanWhenCollapsed: 1,
    },
    { id: "budget", header: "预算口径" },
    { id: "yoy", header: "同比" },
    { id: "mom", header: "环比" },
    {
      id: "lastYearActual",
      header: "去年同期",
      collapsible: true,
      colSpanWhenCollapsed: 1,
    },
  ];
  const columns: FinancialGridColumn<ExpenseBudgetExecutionTemplateSubjectNodeDto>[] = [
    {
      id: "currentActual",
      header: "本年实际",
      groupId: "currentActual",
      minWidth: 108,
      align: "right",
      render: (node) => formatExpenseBudgetExecutionNumber(node.current_actual, amountDivisor),
    },
    ...visibleMonthlyLabels.map<FinancialGridColumn<ExpenseBudgetExecutionTemplateSubjectNodeDto>>((label, idx) => ({
      id: `currentActual-${idx + 1}`,
      header: label,
      groupId: "currentActual",
      hiddenWhenGroupCollapsed: true,
      minWidth: 88,
      align: "right",
      className: "text-[var(--bb-text-muted)]",
      render: (node) => formatExpenseBudgetExecutionNumber(node.monthly_actuals?.[idx] ?? 0, amountDivisor),
    })),
    {
      id: "annualBudget",
      header: "本年预算",
      groupId: "budget",
      minWidth: 108,
      align: "right",
      render: (node) => formatExpenseBudgetExecutionNumber(node.annual_budget, amountDivisor),
    },
    {
      id: "budgetProgress",
      header: "预算进度%",
      groupId: "budget",
      minWidth: 96,
      align: "right",
      render: (node) => formatExpenseBudgetExecutionPercent(node.budget_progress),
    },
    {
      id: "yoyChange",
      header: "本年同比增减额",
      groupId: "yoy",
      minWidth: 128,
      align: "right",
      render: (node) => formatExpenseBudgetExecutionNumber(node.yoy_change, amountDivisor),
    },
    {
      id: "yoyRate",
      header: "本年同比%",
      groupId: "yoy",
      minWidth: 96,
      align: "right",
      render: (node) => formatExpenseBudgetExecutionPercent(node.yoy_rate),
    },
    {
      id: "monthOverMonth",
      header: "本月环比增减额",
      groupId: "mom",
      minWidth: 128,
      align: "right",
      render: (node) => formatExpenseBudgetExecutionNumber(node.month_over_month, amountDivisor),
    },
    {
      id: "monthOverMonthRate",
      header: "本月环比%",
      groupId: "mom",
      minWidth: 96,
      align: "right",
      render: (node) => formatExpenseBudgetExecutionPercent(node.month_over_month_rate),
    },
    {
      id: "lastYearActual",
      header: "去年同期",
      groupId: "lastYearActual",
      minWidth: 108,
      align: "right",
      render: (node) => formatExpenseBudgetExecutionNumber(node.last_year_actual, amountDivisor),
    },
    ...visibleLastYearMonthlyLabels.map<FinancialGridColumn<ExpenseBudgetExecutionTemplateSubjectNodeDto>>((label, idx) => ({
      id: `lastYearActual-${idx + 1}`,
      header: label,
      groupId: "lastYearActual",
      hiddenWhenGroupCollapsed: true,
      minWidth: 104,
      align: "right",
      className: "text-[var(--bb-text-muted)]",
      render: (node) => formatExpenseBudgetExecutionNumber(node.previous_year_monthly_actuals?.[idx] ?? 0, amountDivisor),
    })),
  ];

  return (
    <>
      <section className="bb-panel overflow-hidden">
        <GridToolbar className="rounded-none border-0 border-b border-[var(--bb-border)]">
          <span className="mr-auto font-medium text-[var(--bb-text-strong)]">{title}</span>
          <button
            type="button"
            title={`收起当前选中的${nodeLabel}；未选中时收起所有一级${nodeLabel}`}
            onClick={collapseCurrentLevel}
            className="bb-btn bb-btn-secondary min-h-7 px-2 text-[11px]"
          >
            <Minimize2 className="w-3 h-3" />
            <span>收起本级</span>
          </button>
          <button
            type="button"
            title={`展开当前选中的${nodeLabel}下级；未选中时展开所有一级${nodeLabel}`}
            onClick={expandNextLevel}
            className="bb-btn bb-btn-secondary min-h-7 px-2 text-[11px]"
          >
            <Maximize2 className="w-3 h-3" />
            <span>展开下级</span>
          </button>
          <button
            type="button"
            title={`展开选中${nodeLabel}下全部层级；未选中时展开整棵树`}
            onClick={() => setSelectedDescendantsExpanded(true)}
            className="bb-btn bb-btn-secondary min-h-7 px-2 text-[11px]"
          >
            <ChevronsDown className="w-3 h-3" />
            <span>展开全部下级</span>
          </button>
          <button
            type="button"
            title={`收起选中${nodeLabel}及其全部下级；未选中时收起整棵树`}
            onClick={() => setSelectedDescendantsExpanded(false)}
            className="bb-btn bb-btn-secondary min-h-7 px-2 text-[11px]"
          >
            <ChevronsUp className="w-3 h-3" />
            <span>收起全部下级</span>
          </button>
        </GridToolbar>
        <ReportGrid
          rows={visibleRows}
          columns={columns}
          columnGroups={columnGroups}
          expandedColumnGroups={{
            currentActual: currentActualExpanded,
            budget: true,
            yoy: true,
            mom: true,
            lastYearActual: lastYearActualExpanded,
          }}
          onToggleColumnGroup={(groupId) => {
            if (groupId === "currentActual") setCurrentActualExpanded((prev) => !prev);
            if (groupId === "lastYearActual") setLastYearActualExpanded((prev) => !prev);
          }}
          getRowId={(node) => String(node.id)}
          getRowLevel={(node) => node.level_number}
          getRowLabel={(node) => (
            <span className="inline-flex min-w-0 items-center gap-1.5">
              {reportMode !== "subject" ? (
                <span className="rounded bg-[var(--bb-bg-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--bb-text-muted)]">
                  {node.level_label}
                </span>
              ) : null}
              <span className="truncate">{node.subject_name}</span>
            </span>
          )}
          getRowHasChildren={(node) => node.children.length > 0}
          getRowKind={(node) => (node.children.length > 0 ? "summary" : "normal")}
          isRowExpanded={(node) => Boolean(expandedRows[node.id])}
          onToggleRow={(node) => toggleExpanded(node.id)}
          onRowClick={(node) => setSelectedRowId(node.id)}
          onRowContextMenu={(event, node) => {
            event.preventDefault();
            setSelectedRowId(node.id);
            setContextMenu({
              x: event.clientX,
              y: event.clientY,
              node: {
                id: node.id,
                hasChildren: node.children.length > 0,
                isOpen: expandedRows[node.id] ?? false,
              },
            });
          }}
          getRowClassName={(node) => (selectedRowId === node.id ? "bg-[var(--bb-primary-soft)]" : undefined)}
          primaryHeader={nodeLabel}
          emptyMessage={loading ? loadingText : reportMode === "subject" ? "当前条件下没有可展示的部门数据。" : "当前条件下没有可展示的费用类型数据。"}
          className="rounded-none border-0"
          primaryColumnWidth={300}
        />
      </section>
      {contextMenu ? (
        <div
          ref={contextMenuRef}
          className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[180px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {contextMenu.node.hasChildren ? (
            <button
              type="button"
              onClick={() => {
                toggleExpanded(contextMenu.node.id);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100"
            >
              {contextMenu.node.isOpen ? "收起本级" : "展开下级"}
            </button>
          ) : null}
          {contextMenu.node.hasChildren ? (
            <button
              type="button"
              onClick={() => {
                const node = findTreeNodeById(rows, contextMenu.node.id);
                if (node) {
                  const ids = collectTreeNodeIds(node);
                  setExpandedRows((prev) => {
                    const next = { ...prev };
                    ids.forEach((id) => {
                      next[id] = true;
                    });
                    return next;
                  });
                }
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100"
            >
              展开全部下级
            </button>
          ) : null}
          {contextMenu.node.hasChildren ? (
            <button
              type="button"
              onClick={() => {
                const node = findTreeNodeById(rows, contextMenu.node.id);
                if (node) {
                  const ids = collectTreeNodeIds(node);
                  setExpandedRows((prev) => {
                    const next = { ...prev };
                    ids.forEach((id) => {
                      next[id] = false;
                    });
                    return next;
                  });
                }
                setContextMenu(null);
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
              setSelectedRowId(null);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100"
          >
            取消选中
          </button>
        </div>
      ) : null}
    </>
  );
}
