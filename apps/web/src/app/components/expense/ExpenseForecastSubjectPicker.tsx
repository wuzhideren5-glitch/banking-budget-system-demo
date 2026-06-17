import type { ReactNode, Ref } from "react";
import { Check, ChevronDown, ChevronRight, Search } from "lucide-react";
import type {
  BudgetSubjectSearchMatch,
  BudgetSubjectTreeNode,
} from "@/lib/expense/expenseForecastViewModel";

type ExpenseForecastSubjectPickerProps = {
  pickerRef: Ref<HTMLLabelElement>;
  isOpen: boolean;
  selectedSubjectId: string;
  selectedSubjectName: string;
  selectedSubjectPath: string;
  searchText: string;
  expandedIds: Set<number>;
  tree: BudgetSubjectTreeNode[];
  searchMatches: BudgetSubjectSearchMatch[];
  onToggleOpen: () => void;
  onSearchChange: (value: string) => void;
  onSelectSubject: (subjectId: number) => void;
  onToggleExpanded: (subjectId: number) => void;
};

export function renderHighlightedText(text: string, keyword: string): ReactNode {
  const query = keyword.trim();
  if (!query) return text;
  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const index = lowerText.indexOf(lowerQuery);
  if (index === -1) return text;
  const before = text.slice(0, index);
  const match = text.slice(index, index + query.length);
  const after = text.slice(index + query.length);
  return (
    <>
      {before}
      <mark className="rounded bg-yellow-100 px-0.5 text-inherit">{match}</mark>
      {after}
    </>
  );
}

export function ExpenseForecastSubjectPicker({
  pickerRef,
  isOpen,
  selectedSubjectId,
  selectedSubjectName,
  selectedSubjectPath,
  searchText,
  expandedIds,
  tree,
  searchMatches,
  onToggleOpen,
  onSearchChange,
  onSelectSubject,
  onToggleExpanded,
}: ExpenseForecastSubjectPickerProps) {
  const renderTree = (nodes: BudgetSubjectTreeNode[], depth = 0): JSX.Element[] => {
    return nodes.flatMap((node) => {
      const hasChildren = node.children.length > 0;
      const expanded = expandedIds.has(node.id);
      const selected = String(node.id) === selectedSubjectId;
      const row = (
        <div key={node.id}>
          <button
            type="button"
            className={`flex w-full items-center gap-1 rounded px-2 py-1 text-left hover:bg-gray-100 ${
              selected ? "bg-blue-50 text-blue-700" : ""
            } ${node.is_leaf ? "" : "text-gray-700"}`}
            style={{ paddingLeft: `${8 + depth * 18}px` }}
            onClick={() => {
              if (node.is_leaf) {
                onSelectSubject(node.id);
                return;
              }
              onToggleExpanded(node.id);
            }}
          >
            {hasChildren ? (
              expanded ? (
                <ChevronDown className="h-3.5 w-3.5 shrink-0" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 shrink-0" />
              )
            ) : (
              <span className="inline-block w-3.5 shrink-0" />
            )}
            <span className={node.is_leaf ? "text-gray-900" : "font-medium"}>{node.subject_name}</span>
            {selected && node.is_leaf ? <Check className="h-3.5 w-3.5 shrink-0 text-blue-600" /> : null}
            {!node.is_leaf ? <span className="ml-auto text-[10px] text-gray-400">仅展开</span> : null}
          </button>
        </div>
      );
      if (!hasChildren || !expanded) return [row];
      return [row, ...renderTree(node.children, depth + 1)];
    });
  };

  return (
    <label className="relative flex flex-col gap-1" ref={pickerRef}>
      <span className="text-gray-500">预算科目</span>
      <button
        type="button"
        className="flex min-h-8 min-w-[280px] items-center justify-between rounded border border-gray-300 bg-white px-3 py-1.5 text-left hover:border-gray-400"
        onClick={onToggleOpen}
      >
        <span className="min-w-0">
          <span className="block truncate text-sm text-gray-900">{selectedSubjectName}</span>
          <span className="block truncate text-[11px] text-gray-500">
            {selectedSubjectPath || "仅支持选择叶子科目"}
          </span>
        </span>
        <ChevronDown className={`ml-3 h-4 w-4 shrink-0 text-gray-400 ${isOpen ? "rotate-180" : ""}`} />
      </button>
      {isOpen ? (
        <div className="absolute left-0 top-full z-30 mt-1 w-[380px] rounded border border-gray-200 bg-white shadow-xl">
          <div className="border-b border-gray-100 p-2">
            <div className="relative">
              <Search className="absolute left-2 top-2 h-4 w-4 text-gray-400" />
              <input
                autoFocus
                className="h-8 w-full rounded border border-gray-300 pl-8 pr-2"
                placeholder="搜索预算科目或层级路径"
                value={searchText}
                onChange={(event) => onSearchChange(event.target.value)}
              />
            </div>
          </div>
          <div className="max-h-[320px] overflow-auto py-1">
            {searchText.trim() ? (
              searchMatches.length > 0 ? (
                searchMatches.map(({ row, path }) => (
                  <button
                    key={row.id}
                    type="button"
                    className={`block w-full px-3 py-2 text-left hover:bg-gray-50 ${
                      String(row.id) === selectedSubjectId ? "bg-blue-50 text-blue-700" : ""
                    }`}
                    onClick={() => onSelectSubject(row.id)}
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <span>{renderHighlightedText(row.subject_name, searchText)}</span>
                      {String(row.id) === selectedSubjectId ? <Check className="h-3.5 w-3.5 text-blue-600" /> : null}
                    </div>
                    <div className="text-[11px] text-gray-500">{renderHighlightedText(path, searchText)}</div>
                  </button>
                ))
              ) : (
                <div className="px-3 py-4 text-[12px] text-gray-400">未找到匹配的叶子预算科目</div>
              )
            ) : (
              renderTree(tree)
            )}
          </div>
        </div>
      ) : null}
    </label>
  );
}
