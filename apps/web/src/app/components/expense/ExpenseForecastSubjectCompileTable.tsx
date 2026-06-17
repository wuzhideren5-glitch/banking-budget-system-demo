import type { ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ExpenseForecastSubjectOwnerRowDto } from "@/lib/expense/expenseForecastApi";
import {
  formatNumber,
  formatPercent,
  monthCellButtonClass,
  monthCellStatusTitle,
  type SubjectOwnerTreeNode,
} from "@/lib/expense/expenseForecastViewModel";
import { renderHighlightedText } from "./ExpenseForecastSubjectPicker";

export type ExpenseForecastSubjectEditingCell = {
  ownerName: string;
  subjectId: number;
  field: "month_forecast" | "business_submission" | "capital_advice";
  month?: number;
};

type ExpenseForecastSubjectCompileTableProps = {
  loading: boolean;
  useOwnerTree: boolean;
  searchText: string;
  amountDivisor: number;
  savingCell: string;
  editingCell: ExpenseForecastSubjectEditingCell | null;
  draftValue: string;
  visibleRows: ExpenseForecastSubjectOwnerRowDto[];
  visibleOwnerNodes: SubjectOwnerTreeNode[];
  expandedOwnerKeys: Set<string>;
  onToggleOwnerExpanded: (key: string) => void;
  onStartEdit: (cell: ExpenseForecastSubjectEditingCell, value: number) => void;
  onDraftValueChange: (value: string) => void;
  onSaveCell: () => void;
  onCancelEdit: () => void;
};

export function ExpenseForecastSubjectCompileTable({
  loading,
  useOwnerTree,
  searchText,
  amountDivisor,
  savingCell,
  editingCell,
  draftValue,
  visibleRows,
  visibleOwnerNodes,
  expandedOwnerKeys,
  onToggleOwnerExpanded,
  onStartEdit,
  onDraftValueChange,
  onSaveCell,
  onCancelEdit,
}: ExpenseForecastSubjectCompileTableProps) {
  const renderRow = (row: ExpenseForecastSubjectOwnerRowDto, ownerDisplayName: ReactNode) => (
    <tr key={`${row.owner_name}-${row.subject_id}`} className="odd:bg-white even:bg-gray-50">
      <td className="sticky left-0 z-[1] border-b border-r border-gray-200 bg-inherit px-3 py-1.5">
        {ownerDisplayName}
      </td>
      {row.months.map((cell) => {
        const isEditing =
          editingCell?.ownerName === row.owner_name &&
          editingCell?.subjectId === row.subject_id &&
          editingCell?.field === "month_forecast" &&
          editingCell?.month === cell.month;
        const cellKey = `${row.owner_name}:month_forecast:${cell.month}`;
        const readOnlyCell = cell.source === "actual" || !cell.editable;
        return (
          <td
            key={cell.month}
            className={`border-b border-r border-gray-200 px-2 py-1.5 text-right ${
              readOnlyCell ? "bg-gray-100 text-gray-600" : "bg-white"
            }`}
          >
            {isEditing ? (
              <input
                autoFocus
                className="h-7 w-full rounded border border-blue-300 px-1 text-right"
                value={draftValue}
                onChange={(event) => onDraftValueChange(event.target.value)}
                onBlur={onSaveCell}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    onSaveCell();
                  }
                  if (event.key === "Escape") {
                    onCancelEdit();
                  }
                }}
              />
            ) : (
              <button
                type="button"
                className={`w-full text-right ${cell.editable ? "hover:text-blue-600" : ""} ${monthCellButtonClass(cell)}`}
                title={monthCellStatusTitle(cell)}
                onClick={() => {
                  if (!cell.editable) return;
                  onStartEdit(
                    {
                      ownerName: row.owner_name,
                      subjectId: row.subject_id,
                      field: "month_forecast",
                      month: cell.month,
                    },
                    cell.value,
                  );
                }}
                disabled={!cell.editable}
              >
                {savingCell === cellKey ? "保存中..." : formatNumber(cell.value, amountDivisor)}
              </button>
            )}
          </td>
        );
      })}
      <td className="border-b border-gray-200 px-2 py-1.5 text-right font-medium">
        {formatNumber(row.total_value, amountDivisor)}
      </td>
      <td className="border-b border-gray-200 px-2 py-1.5 text-right font-medium">
        {formatNumber(row.annual_budget, amountDivisor)}
      </td>
      <td className="border-b border-gray-200 px-2 py-1.5 text-right font-medium">
        {formatNumber(row.forecast_budget_gap, amountDivisor)}
      </td>
      <td className="border-b border-gray-200 px-2 py-1.5 text-right font-medium">
        {formatPercent(row.budget_execution_rate)}
      </td>
      {renderAnnualCell(row, "business_submission", row.business_submission, row.business_submission_editable)}
      {renderAnnualCell(row, "capital_advice", row.capital_advice, row.capital_advice_editable)}
      <td className="border-b border-gray-200 px-2 py-1.5 text-right font-medium">
        {formatNumber(row.capital_advice_gap, amountDivisor)}
      </td>
    </tr>
  );

  const renderAnnualCell = (
    row: ExpenseForecastSubjectOwnerRowDto,
    field: "business_submission" | "capital_advice",
    value: number,
    editable: boolean,
  ) => {
    const isEditing =
      editingCell?.ownerName === row.owner_name &&
      editingCell?.subjectId === row.subject_id &&
      editingCell.field === field;
    return (
      <td className={`border-b border-gray-200 px-2 py-1.5 text-right ${editable ? "bg-white" : "bg-gray-100 text-gray-600"}`}>
        {isEditing ? (
          <input
            autoFocus
            className="h-7 w-full rounded border border-blue-300 px-1 text-right"
            value={draftValue}
            onChange={(event) => onDraftValueChange(event.target.value)}
            onBlur={onSaveCell}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSaveCell();
              }
              if (event.key === "Escape") {
                onCancelEdit();
              }
            }}
          />
        ) : (
          <button
            type="button"
            className={`w-full text-right ${editable ? "hover:text-blue-600" : ""}`}
            onClick={() => {
              if (!editable) return;
              onStartEdit(
                {
                  ownerName: row.owner_name,
                  subjectId: row.subject_id,
                  field,
                },
                value,
              );
            }}
          >
            {savingCell === `${row.owner_name}:${field}` ? "保存中..." : formatNumber(value, amountDivisor)}
          </button>
        )}
      </td>
    );
  };

  const isEmpty = useOwnerTree ? visibleOwnerNodes.length === 0 : visibleRows.length === 0;

  return (
    <table className="min-w-full border-collapse">
      <thead className="sticky top-0 z-10 bg-[#f8fafc]">
        <tr>
          <th className="sticky left-0 z-20 min-w-[220px] border-b border-r border-gray-200 bg-[#f8fafc] px-3 py-2 text-left font-medium">
            费用归属部门
          </th>
          {Array.from({ length: 12 }, (_, idx) => idx + 1).map((month) => (
            <th key={month} className="min-w-[90px] border-b border-r border-gray-200 px-2 py-2 text-right font-medium">
              {month}月
            </th>
          ))}
          <th className="min-w-[110px] border-b border-gray-200 px-2 py-2 text-right font-medium">全年预测</th>
          <th className="min-w-[110px] border-b border-gray-200 px-2 py-2 text-right font-medium">年度预算</th>
          <th className="min-w-[140px] border-b border-gray-200 px-2 py-2 text-right font-medium">全年预测-年度预算</th>
          <th className="min-w-[110px] border-b border-gray-200 px-2 py-2 text-right font-medium">预算执行率</th>
          <th className="min-w-[110px] border-b border-gray-200 px-2 py-2 text-right font-medium">业务报送</th>
          <th className="min-w-[110px] border-b border-gray-200 px-2 py-2 text-right font-medium">资划建议</th>
          <th className="min-w-[140px] border-b border-gray-200 px-2 py-2 text-right font-medium">资划建议-业务报送</th>
        </tr>
      </thead>
      <tbody>
        {useOwnerTree
          ? visibleOwnerNodes.map((node) =>
              renderRow(
                node.row,
                <div className="flex items-center gap-1" style={{ paddingLeft: `${(node.level - 1) * 18}px` }}>
                  {node.children.length > 0 ? (
                    <button
                      type="button"
                      className="rounded p-0.5 hover:bg-gray-200"
                      onClick={() => onToggleOwnerExpanded(node.key)}
                    >
                      {expandedOwnerKeys.has(node.key) ? (
                        <ChevronDown className="h-3.5 w-3.5" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5" />
                      )}
                    </button>
                  ) : (
                    <span className="inline-block w-4" />
                  )}
                  <span>{renderHighlightedText(node.name, searchText)}</span>
                </div>,
              ),
            )
          : visibleRows.map((row) => renderRow(row, row.owner_name))}
        {!loading && isEmpty ? (
          <tr>
            <td colSpan={20} className="px-3 py-10 text-center text-gray-400">
              当前没有可展示的数据
            </td>
          </tr>
        ) : null}
      </tbody>
    </table>
  );
}
