import { useMemo, type Dispatch, type SetStateAction } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronsDown,
  ChevronsUp,
  Maximize2,
  Minimize2,
} from "lucide-react";
import type { ExpenseBudgetExecutionMetricRowDto } from "@/lib/expense/expenseBudgetExecutionApi";
import {
  formatExpenseBudgetExecutionNumber,
  formatExpenseBudgetExecutionPercent,
} from "@/lib/expense/expenseBudgetExecutionViewModel";

type MetricCollapseState = Record<string, boolean>;

type MetricGroup = {
  key: string;
  label: string;
  level: number;
  rows: ExpenseBudgetExecutionMetricRowDto[];
  hasChildren: boolean;
  parentKeys: string[];
  canToggleRows: boolean;
};

type VisibleMetricRow = {
  row: ExpenseBudgetExecutionMetricRowDto;
  group: MetricGroup;
  groupVisibleRows: number;
  isFirstInGroup: boolean;
};

type ExpenseBudgetExecutionMetricTableProps = {
  title: string;
  rows: ExpenseBudgetExecutionMetricRowDto[];
  labelHeader: string;
  mergeLabelCells?: boolean;
  amountDivisor: number;
  visibleMonthlyLabels: string[];
  visibleLastYearMonthlyLabels: string[];
  collapsedMetricGroups: MetricCollapseState;
  setCollapsedMetricGroups: Dispatch<SetStateAction<MetricCollapseState>>;
  metricMonthlyExpanded: MetricCollapseState;
  setMetricMonthlyExpanded: Dispatch<SetStateAction<MetricCollapseState>>;
  metricLastYearExpanded: MetricCollapseState;
  setMetricLastYearExpanded: Dispatch<SetStateAction<MetricCollapseState>>;
};

function isSummarySubject(subjectName: string): boolean {
  return /合计|小计/.test(subjectName);
}

function buildMetricGroups(
  title: string,
  rows: ExpenseBudgetExecutionMetricRowDto[],
): MetricGroup[] {
  const groups = rows.reduce<MetricGroup[]>((acc, row) => {
    const previous = acc[acc.length - 1];
    if (previous && previous.label === row.label) {
      previous.rows.push(row);
      return acc;
    }
    acc.push({
      key: `${title}::${row.level}::${row.label}::${acc.length}`,
      label: row.label,
      level: row.level,
      rows: [row],
      hasChildren: false,
      parentKeys: [],
      canToggleRows: false,
    });
    return acc;
  }, []);

  const levelStack: Array<{ key: string; level: number }> = [];
  groups.forEach((group, idx) => {
    while (levelStack.length > 0 && levelStack[levelStack.length - 1]!.level >= group.level) {
      levelStack.pop();
    }
    group.parentKeys = levelStack.map((item) => item.key);
    const nextGroup = groups[idx + 1];
    group.hasChildren = Boolean(nextGroup && nextGroup.level > group.level);
    const hasSummaryRow = group.rows.some((item) => isSummarySubject(item.subject_name));
    group.canToggleRows = !group.hasChildren && hasSummaryRow && group.rows.length > 1;
    levelStack.push({ key: group.key, level: group.level });
  });

  return groups;
}

function buildVisibleMetricRows(
  groups: MetricGroup[],
  collapsedMetricGroups: MetricCollapseState,
): VisibleMetricRow[] {
  const visibleGroups = groups.filter(
    (group) => !group.parentKeys.some((key) => collapsedMetricGroups[key]),
  );
  return visibleGroups.flatMap((group) => {
    const isCollapsed = Boolean(collapsedMetricGroups[group.key]);
    if (isCollapsed && group.canToggleRows) {
      const summaryRows = group.rows.filter((item) => isSummarySubject(item.subject_name));
      return summaryRows.length > 0
        ? [{ row: summaryRows[0], group, groupVisibleRows: 1, isFirstInGroup: true }]
        : [];
    }
    return group.rows.map((row, idx) => ({
      row,
      group,
      groupVisibleRows: group.rows.length,
      isFirstInGroup: idx === 0,
    }));
  });
}

export function ExpenseBudgetExecutionMetricTable({
  title,
  rows,
  labelHeader,
  mergeLabelCells = false,
  amountDivisor,
  visibleMonthlyLabels,
  visibleLastYearMonthlyLabels,
  collapsedMetricGroups,
  setCollapsedMetricGroups,
  metricMonthlyExpanded,
  setMetricMonthlyExpanded,
  metricLastYearExpanded,
  setMetricLastYearExpanded,
}: ExpenseBudgetExecutionMetricTableProps) {
  const monthlyExpanded = Boolean(metricMonthlyExpanded[title]);
  const lastYearExpanded = Boolean(metricLastYearExpanded[title]);
  const groups = useMemo(() => buildMetricGroups(title, rows), [rows, title]);
  const visibleRows = useMemo(
    () => buildVisibleMetricRows(groups, collapsedMetricGroups),
    [groups, collapsedMetricGroups],
  );
  const topLevelToggleGroups = groups.filter((group) => group.level === 0 && group.hasChildren);
  const allToggleGroups = groups.filter((group) => group.hasChildren || group.canToggleRows);
  const emptyColSpan =
    10 +
    (monthlyExpanded ? visibleMonthlyLabels.length : 0) +
    (lastYearExpanded ? visibleLastYearMonthlyLabels.length : 0);

  const setGroupsCollapsed = (targetGroups: MetricGroup[], collapsed: boolean) => {
    setCollapsedMetricGroups((prev) => {
      const next = { ...prev };
      targetGroups.forEach((group) => {
        next[group.key] = collapsed;
      });
      return next;
    });
  };

  return (
    <section className="rounded border border-gray-200 bg-white">
      <div className="px-4 py-2.5 border-b border-gray-200 bg-slate-50 flex items-center gap-2 text-xs">
        <span className="text-[13px] font-semibold text-slate-700">{title}</span>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setGroupsCollapsed(topLevelToggleGroups, true)}
            className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
            title="收起本级"
          >
            <Minimize2 className="w-3 h-3" />
            <span>收起本级</span>
          </button>
          <button
            type="button"
            onClick={() => setGroupsCollapsed(topLevelToggleGroups, false)}
            className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
            title="展开下级"
          >
            <Maximize2 className="w-3 h-3" />
            <span>展开下级</span>
          </button>
          <button
            type="button"
            onClick={() => setGroupsCollapsed(allToggleGroups, false)}
            className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
            title="展开全部下级"
          >
            <ChevronsDown className="w-3 h-3" />
            <span>展开全部下级</span>
          </button>
          <button
            type="button"
            onClick={() => setGroupsCollapsed(allToggleGroups, true)}
            className="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50 inline-flex items-center gap-1"
            title="收起全部下级"
          >
            <ChevronsUp className="w-3 h-3" />
            <span>收起全部下级</span>
          </button>
        </div>
      </div>
      <div className="overflow-auto">
        <table className="min-w-[980px] w-full border-collapse text-xs whitespace-nowrap">
          <thead className="bg-gray-100">
            <tr className="text-left text-gray-700">
              <th className="border border-gray-200 px-2 py-2 whitespace-nowrap">{labelHeader}</th>
              <th className="border border-gray-200 px-2 py-2 whitespace-nowrap">预算科目</th>
              <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">
                <button
                  type="button"
                  onClick={() => setMetricMonthlyExpanded((prev) => ({ ...prev, [title]: !prev[title] }))}
                  className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${
                    monthlyExpanded ? "bg-blue-100 text-blue-700 hover:bg-blue-200" : "bg-white text-gray-700 hover:bg-gray-100"
                  }`}
                >
                  {monthlyExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                  <span>本年实际</span>
                </button>
              </th>
              {monthlyExpanded
                ? visibleMonthlyLabels.map((label) => (
                    <th key={`${title}-${label}`} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">
                      {label}
                    </th>
                  ))
                : null}
              <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">本年预算</th>
              <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">预算进度%</th>
              <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">同比+-</th>
              <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">同比%</th>
              <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">本月环比增减额</th>
              <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">本月环比%</th>
              <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">
                <button
                  type="button"
                  onClick={() => setMetricLastYearExpanded((prev) => ({ ...prev, [title]: !prev[title] }))}
                  className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${
                    lastYearExpanded ? "bg-blue-100 text-blue-700 hover:bg-blue-200" : "bg-white text-gray-700 hover:bg-gray-100"
                  }`}
                >
                  {lastYearExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                  <span>去年同期</span>
                </button>
              </th>
              {lastYearExpanded
                ? visibleLastYearMonthlyLabels.map((label) => (
                    <th key={`${title}-${label}`} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">
                      {label}
                    </th>
                  ))
                : null}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={emptyColSpan} className="px-2 py-6 text-center text-gray-500">
                  当前条件下没有可展示的数据。
                </td>
              </tr>
            ) : (
              visibleRows.map(({ row, group, groupVisibleRows, isFirstInGroup }, idx) => {
                const isSummaryRow = isSummarySubject(row.subject_name);
                const rowClassName = isSummaryRow
                  ? "bg-amber-50 font-semibold text-slate-900 border-t-2 border-amber-200"
                  : "odd:bg-white even:bg-gray-50";
                const isCollapsed = Boolean(collapsedMetricGroups[group.key]);
                const canToggle = group.hasChildren || group.canToggleRows;
                return (
                  <tr key={`${title}-${row.label}-${row.subject_name}-${idx}`} className={rowClassName}>
                    {mergeLabelCells && !isFirstInGroup ? null : (
                      <td
                        rowSpan={mergeLabelCells ? groupVisibleRows : undefined}
                        className={`border border-gray-200 px-2 py-1.5 text-gray-800 ${
                          isSummaryRow
                            ? "align-middle font-semibold bg-amber-50 border-t-2 border-amber-200"
                            : mergeLabelCells
                              ? "align-middle"
                              : "align-top"
                        }`}
                      >
                        <div className="flex items-center gap-1 whitespace-nowrap" style={{ paddingLeft: `${group.level * 16}px` }}>
                          {canToggle ? (
                            <button
                              type="button"
                              className="p-0.5 hover:bg-gray-200 rounded"
                              onClick={() =>
                                setCollapsedMetricGroups((prev) => ({
                                  ...prev,
                                  [group.key]: !prev[group.key],
                                }))
                              }
                              title={isCollapsed ? "展开下级" : "收起下级"}
                            >
                              {isCollapsed ? (
                                <ChevronRight className="w-3 h-3 text-gray-600" />
                              ) : (
                                <ChevronDown className="w-3 h-3 text-gray-600" />
                              )}
                            </button>
                          ) : (
                            <span className="w-4" />
                          )}
                          <span>{row.label || "-"}</span>
                        </div>
                      </td>
                    )}
                    <td className={`border border-gray-200 px-2 py-1.5 whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{row.subject_name}</td>
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{formatExpenseBudgetExecutionNumber(row.current_actual, amountDivisor)}</td>
                    {monthlyExpanded
                      ? visibleMonthlyLabels.map((_, monthIdx) => (
                          <td
                            key={`${title}-${idx}-month-${monthIdx}`}
                            className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}
                          >
                            {formatExpenseBudgetExecutionNumber(row.monthly_actuals?.[monthIdx] ?? 0, amountDivisor)}
                          </td>
                        ))
                      : null}
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{formatExpenseBudgetExecutionNumber(row.annual_budget, amountDivisor)}</td>
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{formatExpenseBudgetExecutionPercent(row.budget_progress)}</td>
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{formatExpenseBudgetExecutionNumber(row.yoy_change, amountDivisor)}</td>
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{formatExpenseBudgetExecutionPercent(row.yoy_rate)}</td>
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{formatExpenseBudgetExecutionNumber(row.month_over_month, amountDivisor)}</td>
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{formatExpenseBudgetExecutionPercent(row.month_over_month_rate)}</td>
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}>{formatExpenseBudgetExecutionNumber(row.last_year_actual, amountDivisor)}</td>
                    {lastYearExpanded
                      ? visibleLastYearMonthlyLabels.map((_, monthIdx) => (
                          <td
                            key={`${title}-${idx}-last-year-month-${monthIdx}`}
                            className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${isSummaryRow ? "text-slate-900 border-t-2 border-amber-200" : "text-gray-700"}`}
                          >
                            {formatExpenseBudgetExecutionNumber(row.previous_year_monthly_actuals?.[monthIdx] ?? 0, amountDivisor)}
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
}
