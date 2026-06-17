import { useMemo, type Dispatch, type SetStateAction } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronsDown,
  ChevronsUp,
  Maximize2,
  Minimize2,
} from "lucide-react";
import type { ExpenseBudgetExecutionMatrixRowDto } from "@/lib/expense/expenseBudgetExecutionApi";
import {
  formatExpenseBudgetExecutionNumber,
  formatExpenseBudgetExecutionPercent,
} from "@/lib/expense/expenseBudgetExecutionViewModel";

type MatrixCollapseState = Record<string, boolean>;

type MatrixGroup = {
  key: string;
  row: ExpenseBudgetExecutionMatrixRowDto;
  parentKeys: string[];
  hasChildren: boolean;
};

type ExpenseBudgetExecutionMatrixTableProps = {
  title: string;
  columns: string[];
  rows: ExpenseBudgetExecutionMatrixRowDto[];
  amountDivisor: number;
  visibleMonthlyLabels: string[];
  monthlyExpanded: boolean;
  setMonthlyExpanded: Dispatch<SetStateAction<boolean>>;
  collapsedMetricGroups: MatrixCollapseState;
  setCollapsedMetricGroups: Dispatch<SetStateAction<MatrixCollapseState>>;
};

function buildMatrixGroups(rows: ExpenseBudgetExecutionMatrixRowDto[]): MatrixGroup[] {
  const groups = rows.map((row, idx) => ({
    key: `3.2::${row.level}::${row.label}::${idx}`,
    row,
    parentKeys: [] as string[],
    hasChildren: false,
  }));

  const levelStack: Array<{ key: string; level: number }> = [];
  groups.forEach((group, idx) => {
    while (levelStack.length > 0 && levelStack[levelStack.length - 1]!.level >= group.row.level) {
      levelStack.pop();
    }
    group.parentKeys = levelStack.map((item) => item.key);
    const nextGroup = groups[idx + 1];
    group.hasChildren = Boolean(nextGroup && nextGroup.row.level > group.row.level);
    levelStack.push({ key: group.key, level: group.row.level });
  });

  return groups;
}

export function ExpenseBudgetExecutionMatrixTable({
  title,
  columns,
  rows,
  amountDivisor,
  visibleMonthlyLabels,
  monthlyExpanded,
  setMonthlyExpanded,
  collapsedMetricGroups,
  setCollapsedMetricGroups,
}: ExpenseBudgetExecutionMatrixTableProps) {
  const groups = useMemo(() => buildMatrixGroups(rows), [rows]);
  const visibleGroups = groups.filter(
    (group) => !group.parentKeys.some((key) => collapsedMetricGroups[key]),
  );
  const topLevelToggleGroups = groups.filter((group) => group.row.level === 0 && group.hasChildren);
  const allToggleGroups = groups.filter((group) => group.hasChildren);
  const actualColSpan = monthlyExpanded
    ? columns.length * (visibleMonthlyLabels.length + 1) + 1
    : columns.length + 1;
  const emptyColSpan = 1 + actualColSpan + (columns.length + 1) * 2;

  const setGroupsCollapsed = (targetGroups: MatrixGroup[], collapsed: boolean) => {
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
        <table className="min-w-[1600px] w-full border-collapse text-xs whitespace-nowrap">
          <thead className="bg-gray-100">
            <tr className="text-left text-gray-700">
              <th rowSpan={monthlyExpanded ? 3 : 2} className="border border-gray-200 px-2 py-2 whitespace-nowrap">
                部门
              </th>
              <th colSpan={actualColSpan} className="border border-gray-200 px-2 py-2 text-center whitespace-nowrap">
                <button
                  type="button"
                  onClick={() => setMonthlyExpanded((prev) => !prev)}
                  className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${
                    monthlyExpanded ? "bg-blue-100 text-blue-700 hover:bg-blue-200" : "bg-white text-gray-700 hover:bg-gray-100"
                  }`}
                >
                  {monthlyExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                  <span>本年实际</span>
                </button>
              </th>
              <th colSpan={columns.length + 1} className="border border-gray-200 px-2 py-2 text-center whitespace-nowrap">本年预算</th>
              <th colSpan={columns.length + 1} className="border border-gray-200 px-2 py-2 text-center whitespace-nowrap">预算进度%</th>
            </tr>
            <tr className="text-left text-gray-700">
              {monthlyExpanded ? (
                <>
                  {columns.map((column) => (
                    <th
                      key={`actual-group-${column}`}
                      colSpan={visibleMonthlyLabels.length + 1}
                      className="border border-gray-200 px-2 py-2 text-center whitespace-nowrap"
                    >
                      {column}
                    </th>
                  ))}
                  <th rowSpan={2} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">合计</th>
                  {columns.map((column) => (
                    <th key={`budget-${column}`} rowSpan={2} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">{column}</th>
                  ))}
                  <th rowSpan={2} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">合计</th>
                  {columns.map((column) => (
                    <th key={`progress-${column}`} rowSpan={2} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">{column}</th>
                  ))}
                  <th rowSpan={2} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">合计</th>
                </>
              ) : (
                <>
                  {columns.map((column) => (
                    <th key={`actual-${column}`} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">{column}</th>
                  ))}
                  <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">合计</th>
                  {columns.map((column) => (
                    <th key={`budget-${column}`} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">{column}</th>
                  ))}
                  <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">合计</th>
                  {columns.map((column) => (
                    <th key={`progress-${column}`} className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">{column}</th>
                  ))}
                  <th className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap">合计</th>
                </>
              )}
            </tr>
            {monthlyExpanded ? (
              <tr className="text-left text-gray-700">
                {columns.flatMap((column) => [
                  <th
                    key={`actual-total-${column}`}
                    className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap"
                  >
                    累计
                  </th>,
                  ...visibleMonthlyLabels.map((label) => (
                    <th
                      key={`actual-month-${column}-${label}`}
                      className="border border-gray-200 px-2 py-2 text-right whitespace-nowrap"
                    >
                      {label.replace("实际", "")}
                    </th>
                  )),
                ])}
              </tr>
            ) : null}
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={emptyColSpan} className="px-2 py-6 text-center text-gray-500">
                  当前条件下没有可展示的数据。
                </td>
              </tr>
            ) : (
              visibleGroups.map(({ row, key, hasChildren }, idx) => {
                const isSummaryRow = row.level <= 1;
                const cellClassName = isSummaryRow ? "text-slate-900 font-semibold bg-amber-50" : "text-gray-700";
                const isCollapsed = Boolean(collapsedMetricGroups[key]);
                return (
                  <tr
                    key={`daily-other-${row.label}-${idx}`}
                    className={isSummaryRow ? "bg-amber-50 border-t-2 border-amber-200" : "odd:bg-white even:bg-gray-50"}
                  >
                    <td className={`border border-gray-200 px-2 py-1.5 text-gray-800 whitespace-nowrap ${isSummaryRow ? "font-semibold bg-amber-50" : ""}`}>
                      <div className="flex items-center gap-1 whitespace-nowrap" style={{ paddingLeft: `${row.level * 16}px` }}>
                        {hasChildren ? (
                          <button
                            type="button"
                            className="p-0.5 hover:bg-gray-200 rounded"
                            onClick={() =>
                              setCollapsedMetricGroups((prev) => ({
                                ...prev,
                                [key]: !prev[key],
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
                        <span>{row.label}</span>
                      </div>
                    </td>
                    {monthlyExpanded ? (
                      <>
                        {columns.flatMap((column) => [
                          <td
                            key={`a-${idx}-${column}`}
                            className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}
                          >
                            {formatExpenseBudgetExecutionNumber(row.actuals[column], amountDivisor)}
                          </td>,
                          ...visibleMonthlyLabels.map((_, monthIdx) => (
                            <td
                              key={`m-${idx}-${column}-${monthIdx}`}
                              className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}
                            >
                              {formatExpenseBudgetExecutionNumber(row.monthly_actuals_by_subject?.[column]?.[monthIdx] ?? 0, amountDivisor)}
                            </td>
                          )),
                        ])}
                        <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}>{formatExpenseBudgetExecutionNumber(row.actual_total, amountDivisor)}</td>
                      </>
                    ) : (
                      <>
                        {columns.map((column) => (
                          <td key={`a-${idx}-${column}`} className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}>
                            {formatExpenseBudgetExecutionNumber(row.actuals[column], amountDivisor)}
                          </td>
                        ))}
                        <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}>{formatExpenseBudgetExecutionNumber(row.actual_total, amountDivisor)}</td>
                      </>
                    )}
                    {columns.map((column) => (
                      <td key={`b-${idx}-${column}`} className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}>
                        {formatExpenseBudgetExecutionNumber(row.budgets[column], amountDivisor)}
                      </td>
                    ))}
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}>{formatExpenseBudgetExecutionNumber(row.budget_total, amountDivisor)}</td>
                    {columns.map((column) => (
                      <td key={`p-${idx}-${column}`} className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}>
                        {formatExpenseBudgetExecutionPercent(row.progresses[column])}
                      </td>
                    ))}
                    <td className={`border border-gray-200 px-2 py-1.5 text-right whitespace-nowrap ${cellClassName}`}>{formatExpenseBudgetExecutionPercent(row.budget_progress_total)}</td>
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
