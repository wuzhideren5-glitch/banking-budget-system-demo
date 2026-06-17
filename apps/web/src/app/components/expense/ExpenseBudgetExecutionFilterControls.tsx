import { useRef } from "react";
import type { ExpenseBudgetExecutionSubjectScopeNodeDto } from "@/lib/expense/expenseBudgetExecutionApi";

export type ExpenseBudgetExecutionScopeFilterProps = {
  entityName: string;
  groupName: string;
  ownerDept: string;
  groupOptions: string[];
  ownerOptions: string[];
  hasSelectedEntity: boolean;
  hasSelectedGroup: boolean;
  setEntityName: (value: string) => void;
  setGroupName: (value: string) => void;
  setOwnerDept: (value: string) => void;
};

export type ExpenseBudgetExecutionSubjectScopeFilterProps = {
  entityName: string;
  selectedSubjectId: string;
  selectedSubjectNode: ExpenseBudgetExecutionSubjectScopeNodeDto | null;
  scopeTree: ExpenseBudgetExecutionSubjectScopeNodeDto[];
  setEntityName: (value: string) => void;
  setSelectedSubjectId: (value: string) => void;
};

export function ExpenseBudgetExecutionMonthSelect({
  value,
  currentMonth,
  setValue,
}: {
  value: string;
  currentMonth: number | null;
  setValue: (value: string) => void;
}) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-gray-600">费用月份</span>
      <select
        value={value || String(currentMonth ?? "")}
        onChange={(e) => setValue(e.target.value)}
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
  );
}

export function ExpenseBudgetExecutionEntitySelect({
  value,
  availableEntities,
  onChange,
}: {
  value: string;
  availableEntities: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-gray-600">主体</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="border border-gray-300 rounded px-2 py-1 bg-white min-w-[10rem]"
      >
        <option value="">全部主体</option>
        {availableEntities.map((entityName) => (
          <option key={entityName} value={entityName}>
            {entityName}
          </option>
        ))}
      </select>
    </label>
  );
}

export function ExpenseBudgetExecutionScopeFilters({
  availableEntities,
  filters,
}: {
  availableEntities: string[];
  filters: ExpenseBudgetExecutionScopeFilterProps;
}) {
  return (
    <>
      <ExpenseBudgetExecutionEntitySelect
        value={filters.entityName}
        availableEntities={availableEntities}
        onChange={(value) => {
          filters.setEntityName(value);
          filters.setGroupName("");
          filters.setOwnerDept("");
        }}
      />
      {filters.hasSelectedEntity ? (
        <label className="flex items-center gap-2">
          <span className="text-gray-600">事业群</span>
          <select
            value={filters.groupName}
            onChange={(e) => {
              filters.setGroupName(e.target.value);
              filters.setOwnerDept("");
            }}
            className="border border-gray-300 rounded px-2 py-1 bg-white min-w-[10rem]"
          >
            <option value="">全部事业群</option>
            {filters.groupOptions.map((groupName) => (
              <option key={groupName} value={groupName}>
                {groupName}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {filters.hasSelectedEntity && filters.hasSelectedGroup ? (
        <label className="flex items-center gap-2">
          <span className="text-gray-600">费用归属部门</span>
          <select
            value={filters.ownerDept}
            onChange={(e) => filters.setOwnerDept(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 bg-white min-w-[12rem]"
          >
            <option value="">全部费用归属部门</option>
            {filters.ownerOptions.map((ownerDept) => (
              <option key={ownerDept} value={ownerDept}>
                {ownerDept}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    </>
  );
}

export function ExpenseBudgetExecutionSubjectScopePicker({
  selectedSubjectId,
  selectedSubjectNode,
  scopeTree,
  setSelectedSubjectId,
}: Pick<
  ExpenseBudgetExecutionSubjectScopeFilterProps,
  "selectedSubjectId" | "selectedSubjectNode" | "scopeTree" | "setSelectedSubjectId"
>) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const closeDropdown = () => {
    detailsRef.current?.removeAttribute("open");
  };
  const renderNodes = (nodes: ExpenseBudgetExecutionSubjectScopeNodeDto[]): JSX.Element[] =>
    nodes.flatMap((node) => [
      <button
        key={`scope-${node.id}`}
        type="button"
        onClick={() => {
          setSelectedSubjectId(String(node.id));
          closeDropdown();
        }}
        className={`w-full text-left px-2 py-1 rounded hover:bg-gray-100 ${
          selectedSubjectId === String(node.id) ? "bg-blue-50 text-blue-700" : "text-gray-700"
        }`}
        style={{ paddingLeft: `${Math.max(node.level_number - 1, 0) * 16 + 8}px` }}
      >
        <span className="mr-2 inline-block rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
          {node.level_label}
        </span>
        <span>{node.subject_name}</span>
      </button>,
      ...renderNodes(node.children),
    ]);

  return (
    <label className="flex items-center gap-2">
      <span className="text-gray-600">预算科目</span>
      <details ref={detailsRef} className="relative min-w-[16rem]">
        <summary className="list-none cursor-pointer border border-gray-300 rounded px-2 py-1 bg-white text-gray-700">
          {selectedSubjectNode ? selectedSubjectNode.subject_name : "全部科目"}
        </summary>
        <div className="absolute left-0 top-[calc(100%+4px)] z-20 w-[22rem] max-h-80 overflow-auto rounded border border-gray-200 bg-white p-2 shadow-lg">
          <button
            type="button"
            onClick={() => {
              setSelectedSubjectId("");
              closeDropdown();
            }}
            className={`mb-1 w-full rounded px-2 py-1 text-left hover:bg-gray-100 ${
              selectedSubjectId ? "text-gray-700" : "bg-blue-50 text-blue-700"
            }`}
          >
            全部科目
          </button>
          {renderNodes(scopeTree)}
        </div>
      </details>
    </label>
  );
}
