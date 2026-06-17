import { Fragment } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type {
  ExpenseForecastGroupOwnerViewDto,
  ExpenseForecastMonthCellDto,
  ExpenseForecastRowDto,
} from "@/lib/expense/expenseForecastApi";
import {
  formatNumber,
  formatPercent,
  monthCellButtonClass,
  monthCellStatusTitle,
} from "@/lib/expense/expenseForecastViewModel";

export type ExpenseForecastScopeEditingCell = {
  rowId: number;
  ownerName?: string;
  field: "month_forecast" | "business_submission" | "capital_advice";
  month?: number;
};

type AnnualField = "business_submission" | "capital_advice";

type ExpenseForecastScopeCompileTableProps = {
  loading: boolean;
  amountDivisor: number;
  savingCell: string;
  editingCell: ExpenseForecastScopeEditingCell | null;
  draftValue: string;
  rows: ExpenseForecastRowDto[];
  groupOwnerViews?: ExpenseForecastGroupOwnerViewDto[] | null;
  rowDepthById: Map<number, number>;
  expandableRowIds: Set<number>;
  expandedRowIds: Set<number>;
  selectedRowId: number | null;
  onSelectRow: (rowId: number) => void;
  onOpenContextMenu: (rowId: number, x: number, y: number) => void;
  onToggleExpandedRow: (rowId: number) => void;
  onStartMonthEdit: (row: ExpenseForecastRowDto, cell: ExpenseForecastMonthCellDto, ownerName?: string) => void;
  onStartAnnualEdit: (
    row: ExpenseForecastRowDto,
    field: AnnualField,
    value: number,
    editable: boolean,
    ownerName?: string,
  ) => void;
  onDraftValueChange: (value: string) => void;
  onSaveCell: () => void;
  onCancelEdit: () => void;
};

export function ExpenseForecastScopeCompileTable({
  loading,
  amountDivisor,
  savingCell,
  editingCell,
  draftValue,
  rows,
  groupOwnerViews,
  rowDepthById,
  expandableRowIds,
  expandedRowIds,
  selectedRowId,
  onSelectRow,
  onOpenContextMenu,
  onToggleExpandedRow,
  onStartMonthEdit,
  onStartAnnualEdit,
  onDraftValueChange,
  onSaveCell,
  onCancelEdit,
}: ExpenseForecastScopeCompileTableProps) {
  const renderEditInput = () => (
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
  );

  const matchesOwner = (ownerName?: string) =>
    ownerName ? editingCell?.ownerName === ownerName : !editingCell?.ownerName;

  const renderSubjectCell = (row: ExpenseForecastRowDto, ownerName?: string) => {
    const isGroupRow = Boolean(ownerName);
    const depth = isGroupRow ? Math.max(0, row.level_number - 1) : rowDepthById.get(row.id) ?? 0;
    const hasChildren = !isGroupRow && expandableRowIds.has(row.id);
    const isExpanded = expandedRowIds.has(row.id);

    return (
      <td className="sticky left-0 z-[1] border-b border-r border-gray-200 bg-inherit px-3 py-1.5">
        <div className="flex items-center gap-1" style={{ paddingLeft: `${depth * 18}px` }}>
          {hasChildren ? (
            <button
              type="button"
              className="rounded p-0.5 hover:bg-gray-200"
              onClick={(event) => {
                event.stopPropagation();
                onToggleExpandedRow(row.id);
              }}
            >
              {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </button>
          ) : (
            <span className="inline-block w-4" />
          )}
          <span className={row.is_leaf ? "" : "font-medium text-gray-800"}>{row.subject_name}</span>
          {row.formula_text ? <span className="rounded bg-amber-100 px-1 text-[10px] text-amber-700">公式</span> : null}
        </div>
      </td>
    );
  };

  const renderMonthCell = (row: ExpenseForecastRowDto, cell: ExpenseForecastMonthCellDto, ownerName?: string) => {
    const isEditing =
      matchesOwner(ownerName) &&
      editingCell?.rowId === row.id &&
      editingCell?.field === "month_forecast" &&
      editingCell?.month === cell.month;
    const cellKey = ownerName
      ? `${ownerName}:${row.id}:month_forecast:${cell.month}`
      : `${row.id}:month_forecast:${cell.month}`;
    const readOnlyCell = cell.source === "actual" || !cell.editable;

    return (
      <td
        key={cell.month}
        className={`border-b border-r border-gray-200 px-2 py-1.5 text-right ${
          readOnlyCell ? "bg-gray-100 text-gray-600" : "bg-white"
        }`}
        title={monthCellStatusTitle(cell)}
        onDoubleClick={() => onStartMonthEdit(row, cell, ownerName)}
      >
        {isEditing ? (
          renderEditInput()
        ) : (
          <button
            type="button"
            className={`w-full text-right ${cell.editable ? "hover:text-blue-600" : ""} ${monthCellButtonClass(cell)}`}
            title={monthCellStatusTitle(cell)}
            onClick={() => onStartMonthEdit(row, cell, ownerName)}
            disabled={!cell.editable}
          >
            {savingCell === cellKey ? "保存中..." : formatNumber(cell.value, amountDivisor)}
          </button>
        )}
      </td>
    );
  };

  const renderAnnualCell = (
    row: ExpenseForecastRowDto,
    ownerName: string | undefined,
    field: AnnualField,
    value: number,
    editable: boolean,
    editTitle: string,
  ) => {
    const isEditing = matchesOwner(ownerName) && editingCell?.rowId === row.id && editingCell.field === field;
    const cellKey = ownerName ? `${ownerName}:${row.id}:${field}` : `${row.id}:${field}`;

    return (
      <td
        className={`border-b border-gray-200 px-2 py-1.5 text-right ${editable ? "bg-white" : "bg-gray-100 text-gray-600"}`}
        title={editable ? editTitle : "汇总单元格，只读"}
        onDoubleClick={() => onStartAnnualEdit(row, field, value, editable, ownerName)}
      >
        {isEditing ? (
          renderEditInput()
        ) : (
          <button
            type="button"
            className={`w-full text-right ${editable ? "hover:text-blue-600" : ""}`}
            onClick={() => onStartAnnualEdit(row, field, value, editable, ownerName)}
            disabled={!editable}
          >
            {savingCell === cellKey ? "保存中..." : formatNumber(value, amountDivisor)}
          </button>
        )}
      </td>
    );
  };

  const renderDataRow = (row: ExpenseForecastRowDto, ownerName?: string) => {
    const isGroupRow = Boolean(ownerName);
    const isSelected = !isGroupRow && selectedRowId === row.id;

    return (
      <tr
        key={ownerName ? `${ownerName}-${row.id}` : row.id}
        className={`${isSelected ? "bg-blue-50" : "odd:bg-white even:bg-gray-50"}`}
        onClick={() => {
          if (!isGroupRow) onSelectRow(row.id);
        }}
        onContextMenu={(event) => {
          if (isGroupRow) return;
          event.preventDefault();
          onSelectRow(row.id);
          onOpenContextMenu(row.id, event.clientX, event.clientY);
        }}
      >
        {renderSubjectCell(row, ownerName)}
        {row.months.map((cell) => renderMonthCell(row, cell, ownerName))}
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
        {renderAnnualCell(row, ownerName, "business_submission", row.business_submission, row.business_submission_editable, "双击或单击录入业务报送")}
        {renderAnnualCell(row, ownerName, "capital_advice", row.capital_advice, row.capital_advice_editable, "双击或单击录入资划建议")}
        <td className="border-b border-gray-200 px-2 py-1.5 text-right font-medium">
          {formatNumber(row.capital_advice_gap, amountDivisor)}
        </td>
      </tr>
    );
  };

  const isEmpty = groupOwnerViews ? groupOwnerViews.length === 0 : rows.length === 0;

  return (
    <table className="min-w-full border-collapse">
      <thead className="sticky top-0 z-10 bg-[#f8fafc]">
        <tr>
          <th className="sticky left-0 z-20 min-w-[360px] border-b border-r border-gray-200 bg-[#f8fafc] px-3 py-2 text-left font-medium">
            预算科目
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
        {groupOwnerViews
          ? groupOwnerViews.map((ownerView) => (
              <Fragment key={ownerView.owner_name}>
                <tr className="bg-gray-100">
                  <td colSpan={20} className="border-b border-gray-300 px-3 py-2 font-medium text-gray-800">
                    {ownerView.owner_name}
                  </td>
                </tr>
                {ownerView.rows.map((row) => renderDataRow(row, ownerView.owner_name))}
              </Fragment>
            ))
          : rows.map((row) => renderDataRow(row))}
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
