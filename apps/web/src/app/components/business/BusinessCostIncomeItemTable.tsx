import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Edit,
  FileText,
  FolderOpen,
  Plus,
  Trash2,
} from "lucide-react";

import type {
  BusinessCostIncomeItemDto,
  BusinessCostIncomeItemSection,
} from "@/lib/business/businessCostIncomeApi";
import {
  BUSINESS_COST_INCOME_SECTION_LABELS,
  buildBusinessCostIncomeItemTree,
  flattenVisibleBusinessCostIncomeTree,
} from "@/lib/business/businessCostIncomeAdminViewModel";

type Props = {
  section: BusinessCostIncomeItemSection;
  items: BusinessCostIncomeItemDto[];
  expanded: Record<string, boolean>;
  submitting: boolean;
  onSetSectionExpanded: (section: BusinessCostIncomeItemSection, open: boolean) => void;
  onToggleExpanded: (section: BusinessCostIncomeItemSection, id: number) => void;
  onAddTop: (section: BusinessCostIncomeItemSection) => void;
  onAddChild: (section: BusinessCostIncomeItemSection, parentId: number) => void;
  onAddParent: (item: BusinessCostIncomeItemDto) => void;
  onEdit: (item: BusinessCostIncomeItemDto) => void;
  onMove: (item: BusinessCostIncomeItemDto, direction: "up" | "down") => void;
  onToggle: (item: BusinessCostIncomeItemDto) => void;
  onDelete: (id: number) => void;
};

function sortedSiblings(
  items: BusinessCostIncomeItemDto[],
  section: BusinessCostIncomeItemSection,
  parentId: number | null
): BusinessCostIncomeItemDto[] {
  return items
    .filter((item) => item.section === section && item.parent_id === parentId)
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
}

export function BusinessCostIncomeItemTable({
  section,
  items,
  expanded,
  submitting,
  onSetSectionExpanded,
  onToggleExpanded,
  onAddTop,
  onAddChild,
  onAddParent,
  onEdit,
  onMove,
  onToggle,
  onDelete,
}: Props) {
  const tree = buildBusinessCostIncomeItemTree(items, section);
  const treeRows = flattenVisibleBusinessCostIncomeTree(tree, expanded, section);
  const label = BUSINESS_COST_INCOME_SECTION_LABELS[section];
  const canMoveUp = (row: BusinessCostIncomeItemDto) =>
    sortedSiblings(items, section, row.parent_id).findIndex((candidate) => candidate.id === row.id) > 0;
  const canMoveDown = (row: BusinessCostIncomeItemDto) => {
    const siblings = sortedSiblings(items, section, row.parent_id);
    const index = siblings.findIndex((candidate) => candidate.id === row.id);
    return index >= 0 && index < siblings.length - 1;
  };

  return (
    <section className="rounded border border-gray-200 bg-white">
      <div className="px-4 py-2.5 border-b border-gray-200 bg-slate-50 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-slate-700">{label}细项</span>
          <span className="text-gray-400">({treeRows.length}项)</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onSetSectionExpanded(section, false)}
            className="px-2 py-0.5 border border-gray-300 bg-white text-gray-700 rounded hover:bg-gray-50"
          >
            全部收起
          </button>
          <button
            type="button"
            onClick={() => onSetSectionExpanded(section, true)}
            className="px-2 py-0.5 border border-gray-300 bg-white text-gray-700 rounded hover:bg-gray-50"
          >
            全部展开
          </button>
          <button
            type="button"
            onClick={() => onAddTop(section)}
            className="px-2 py-0.5 bg-blue-500 text-white rounded hover:bg-blue-600 inline-flex items-center gap-1"
          >
            <Plus className="w-3.5 h-3.5" />
            添加顶级
          </button>
        </div>
      </div>
      <div className="overflow-auto">
        <table className="w-full border-collapse text-xs whitespace-nowrap">
          <thead className="bg-gray-100">
            <tr className="text-left text-gray-700">
              <th className="border border-gray-200 px-2 py-2 w-[40px]">ID</th>
              <th className="border border-gray-200 px-2 py-2">名称</th>
              <th className="border border-gray-200 px-2 py-2 w-[60px]">层级</th>
              <th className="border border-gray-200 px-2 py-2 w-[80px]">排序</th>
              <th className="border border-gray-200 px-2 py-2 w-[60px]">启用</th>
              <th className="border border-gray-200 px-2 py-2 w-[80px]">操作</th>
            </tr>
          </thead>
          <tbody>
            {treeRows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-2 py-6 text-center text-gray-500">
                  暂无细项，点击右上角"+ 添加"新增
                </td>
              </tr>
            ) : (
              treeRows.map((item) => {
                const isParent = item.hasChildren;
                return (
                  <tr
                    key={item.id}
                    className={isParent ? "bg-blue-50/40 hover:bg-blue-50/60" : "hover:bg-gray-50"}
                  >
                    <td className="border border-gray-200 px-2 py-1.5 text-gray-500">{item.id}</td>
                    <td className="border border-gray-200 px-2 py-1.5">
                      <div className="flex items-center" style={{ paddingLeft: `${item.depth * 20}px` }}>
                        {isParent ? (
                          <button
                            type="button"
                            onClick={() => onToggleExpanded(section, item.id)}
                            className="mr-1 rounded p-0.5 hover:bg-blue-100"
                            title={item.isExpanded ? "收起下级" : "展开下级"}
                          >
                            {item.isExpanded ? (
                              <ChevronDown className="w-3.5 h-3.5 text-blue-500" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5 text-blue-500" />
                            )}
                          </button>
                        ) : (
                          <span className="mr-1 inline-block w-4" />
                        )}
                        {isParent ? (
                          <FolderOpen className="w-3.5 h-3.5 text-blue-500 mr-1.5 flex-shrink-0" />
                        ) : (
                          <FileText className="w-3.5 h-3.5 text-gray-400 mr-1.5 flex-shrink-0" />
                        )}
                        <span className={`font-medium ${isParent ? "text-blue-700" : "text-gray-800"}`}>
                          {item.name}
                        </span>
                        {isParent && <span className="ml-1.5 text-[10px] text-blue-400">(汇总)</span>}
                      </div>
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5 text-gray-500">
                      {item.depth === 0 ? "父级" : `子${item.depth}`}
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5">
                      <div className="flex items-center gap-1">
                        <span className="text-gray-700">{item.sort_order}</span>
                        <button
                          type="button"
                          onClick={() => onMove(item, "up")}
                          disabled={!canMoveUp(item) || submitting}
                          className="p-0.5 text-gray-400 hover:text-blue-600 disabled:opacity-20 disabled:cursor-not-allowed"
                          title="上移"
                        >
                          <ChevronUp className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onMove(item, "down")}
                          disabled={!canMoveDown(item) || submitting}
                          className="p-0.5 text-gray-400 hover:text-blue-600 disabled:opacity-20 disabled:cursor-not-allowed"
                          title="下移"
                        >
                          <ChevronDown className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5">
                      <button
                        type="button"
                        onClick={() => onToggle(item)}
                        disabled={submitting}
                        className={`px-2 py-0.5 rounded text-xs ${
                          item.enabled
                            ? "bg-green-100 text-green-700 hover:bg-green-200"
                            : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                        }`}
                      >
                        {item.enabled ? "启用" : "停用"}
                      </button>
                    </td>
                    <td className="border border-gray-200 px-2 py-1.5">
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => onEdit(item)}
                          disabled={submitting}
                          className="px-1.5 py-0.5 rounded text-xs bg-amber-50 text-amber-700 hover:bg-amber-100 inline-flex items-center gap-1 disabled:opacity-50"
                          title="编辑父级或名称"
                        >
                          <Edit className="w-3 h-3" />
                          编辑
                        </button>
                        <button
                          type="button"
                          onClick={() => onAddParent(item)}
                          disabled={submitting}
                          className="px-1.5 py-0.5 rounded text-xs bg-violet-50 text-violet-700 hover:bg-violet-100 inline-flex items-center gap-1 disabled:opacity-50"
                          title="在当前节点上方插入一个新上级"
                        >
                          <Plus className="w-3 h-3" />
                          上级
                        </button>
                        <button
                          type="button"
                          onClick={() => onAddChild(section, item.id)}
                          disabled={submitting}
                          className="px-1.5 py-0.5 rounded text-xs bg-blue-50 text-blue-600 hover:bg-blue-100 inline-flex items-center gap-1 disabled:opacity-50"
                          title="新增下级"
                        >
                          <Plus className="w-3 h-3" />
                          下级
                        </button>
                        <button
                          type="button"
                          onClick={() => onDelete(item.id)}
                          disabled={submitting}
                          className="px-1.5 py-0.5 rounded text-xs bg-red-50 text-red-600 hover:bg-red-100 inline-flex items-center gap-1 disabled:opacity-50"
                        >
                          <Trash2 className="w-3 h-3" />
                          删除
                        </button>
                      </div>
                    </td>
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
