import { Search } from "lucide-react";
import type {
  ExpenseBudgetExecutionAmountUnit,
  ExpenseBudgetExecutionMode,
} from "@/lib/expense/expenseBudgetExecutionApi";
import { expenseBudgetExecutionAmountUnitOptions as amountUnitOptions } from "@/lib/expense/expenseBudgetExecutionViewModel";
import {
  ExpenseBudgetExecutionEntitySelect,
  ExpenseBudgetExecutionMonthSelect,
  ExpenseBudgetExecutionScopeFilters,
  ExpenseBudgetExecutionSubjectScopePicker,
} from "@/app/components/expense/ExpenseBudgetExecutionFilterControls";
import type {
  ExpenseBudgetExecutionScopeFilterProps,
  ExpenseBudgetExecutionSubjectScopeFilterProps,
} from "@/app/components/expense/ExpenseBudgetExecutionFilterControls";

type ExpenseBudgetExecutionControlsProps = {
  reportMode: ExpenseBudgetExecutionMode;
  setReportMode: (mode: ExpenseBudgetExecutionMode) => void;
  loading: boolean;
  availableEntities: string[];
  currentMonth: number | null;
  query: ExpenseBudgetExecutionScopeFilterProps & {
    reportMonth: string;
    setReportMonth: (value: string) => void;
  };
  template: ExpenseBudgetExecutionScopeFilterProps & {
    reportMonth: string;
    setReportMonth: (value: string) => void;
  };
  subject: ExpenseBudgetExecutionSubjectScopeFilterProps & {
    reportMonth: string;
    setReportMonth: (value: string) => void;
  };
  amountUnit: ExpenseBudgetExecutionAmountUnit;
  setAmountUnit: (value: ExpenseBudgetExecutionAmountUnit) => void;
  activeKeyword: string;
  setActiveKeyword: (value: string) => void;
  includeZeroRows: boolean;
  setIncludeZeroRows: (value: boolean) => void;
  onQuery: () => void;
};

function keywordPlaceholder(reportMode: ExpenseBudgetExecutionMode): string {
  if (reportMode === "template") return "搜索费用类型/层级";
  if (reportMode === "subject") return "搜索部门/层级";
  return "搜索主体、事业群、费用归属部门或预算科目";
}

export function ExpenseBudgetExecutionControls({
  reportMode,
  setReportMode,
  loading,
  availableEntities,
  currentMonth,
  query,
  template,
  subject,
  amountUnit,
  setAmountUnit,
  activeKeyword,
  setActiveKeyword,
  includeZeroRows,
  setIncludeZeroRows,
  onQuery,
}: ExpenseBudgetExecutionControlsProps) {
  const isTreeReportMode = reportMode !== "query";

  return (
    <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex flex-wrap items-center gap-3 text-xs">
      <label className="flex items-center gap-2">
        <span className="text-gray-600">展示模式</span>
        <select
          value={reportMode}
          onChange={(e) => setReportMode(e.target.value as ExpenseBudgetExecutionMode)}
          className="border border-gray-300 rounded px-2 py-1 bg-white"
        >
          <option value="query">月报格式</option>
          <option value="template">部门模式</option>
          <option value="subject">科目模式</option>
        </select>
      </label>

      {reportMode === "query" ? (
        <>
          <ExpenseBudgetExecutionScopeFilters availableEntities={availableEntities} filters={query} />
          <ExpenseBudgetExecutionMonthSelect
            value={query.reportMonth}
            currentMonth={currentMonth}
            setValue={query.setReportMonth}
          />
        </>
      ) : null}

      {reportMode === "template" ? (
        <>
          <ExpenseBudgetExecutionScopeFilters availableEntities={availableEntities} filters={template} />
          <ExpenseBudgetExecutionMonthSelect
            value={template.reportMonth}
            currentMonth={currentMonth}
            setValue={template.setReportMonth}
          />
        </>
      ) : null}

      {reportMode === "subject" ? (
        <>
          <ExpenseBudgetExecutionEntitySelect
            value={subject.entityName}
            availableEntities={availableEntities}
            onChange={subject.setEntityName}
          />
          <ExpenseBudgetExecutionSubjectScopePicker
            selectedSubjectId={subject.selectedSubjectId}
            selectedSubjectNode={subject.selectedSubjectNode}
            scopeTree={subject.scopeTree}
            setSelectedSubjectId={subject.setSelectedSubjectId}
          />
          <ExpenseBudgetExecutionMonthSelect
            value={subject.reportMonth}
            currentMonth={currentMonth}
            setValue={subject.setReportMonth}
          />
        </>
      ) : null}

      <label className="flex items-center gap-2">
        <span className="text-gray-600">单位</span>
        <select
          value={amountUnit}
          onChange={(e) => setAmountUnit(e.target.value as ExpenseBudgetExecutionAmountUnit)}
          className="border border-gray-300 rounded px-2 py-1 bg-white"
        >
          {amountUnitOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      {isTreeReportMode ? (
        <label className="flex items-center gap-2">
          <span className="text-gray-600">关键字</span>
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2 top-1.5 text-gray-400" />
            <input
              value={activeKeyword}
              onChange={(e) => setActiveKeyword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onQuery();
              }}
              placeholder={keywordPlaceholder(reportMode)}
              className="pl-7 pr-2 py-1 border border-gray-300 rounded w-56 bg-white"
            />
          </div>
        </label>
      ) : null}

      {isTreeReportMode ? (
        <label className="flex items-center gap-2 text-gray-600">
          <input
            type="checkbox"
            checked={includeZeroRows}
            onChange={(e) => setIncludeZeroRows(e.target.checked)}
          />
          显示所有金额都为0的项
        </label>
      ) : null}

      <button
        onClick={onQuery}
        disabled={loading}
        className="px-3 py-1 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 disabled:opacity-60"
      >
        查询
      </button>
    </div>
  );
}
