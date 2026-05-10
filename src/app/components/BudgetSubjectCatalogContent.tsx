import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Download,
  Edit,
  FileText,
  Maximize,
  Maximize2,
  Minimize2,
  Plus,
  Save,
  Search,
  Trash2,
  X,
  ChevronsDown,
  ChevronsUp,
} from "lucide-react";
import { apiDelete, apiGet, apiPatch, apiPost, buildApiUrl, type BudgetSubjectCatalogDto } from "@/lib/api";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableRowHeights } from "@/lib/useTableRowHeights";
import { treeToolbarButtonClass } from "@/lib/treeToolbarStyles";
import { TableRowResizeHandle } from "./TableRowResizeHandle";

type TreeNode = BudgetSubjectCatalogDto & { children: TreeNode[] };

type SubjectContextMenuState = {
  x: number;
  y: number;
  node: {
    id: number;
    name: string;
    level: number;
    hasExpandableChildren: boolean;
    isOpen: boolean;
    canAddChild: boolean;
  };
};

type SubjectEditorDraft = {
  id: number;
  name: string;
  formulaText: string;
};

type NewSubjectDraft = {
  parentId: number | null;
  level: number;
  name: string;
  formulaText: string;
};

const TREE_INDENT = 20;
const MAX_SUBJECT_LEVEL = 5;

function buildTree(rows: BudgetSubjectCatalogDto[]): TreeNode[] {
  const map = new Map<number, TreeNode>();
  rows.forEach((row) => map.set(row.id, { ...row, children: [] }));
  const roots: TreeNode[] = [];
  map.forEach((node) => {
    if (node.parent_id != null && map.has(node.parent_id)) {
      map.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  });
  const sortRec = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
    nodes.forEach((node) => sortRec(node.children));
  };
  sortRec(roots);
  return roots;
}

function filterTree(nodes: TreeNode[], term: string): TreeNode[] {
  const s = term.trim().toLowerCase();
  if (!s) return nodes;
  return nodes
    .map((node) => {
      const children = filterTree(node.children, term);
      const formulaText = (node.formula_text ?? "").toLowerCase();
      const match =
        node.subject_name.toLowerCase().includes(s) ||
        node.level_label.toLowerCase().includes(s) ||
        formulaText.includes(s);
      if (match || children.length > 0) return { ...node, children };
      return null;
    })
    .filter((node): node is TreeNode => Boolean(node));
}

export function BudgetSubjectCatalogContent() {
  const [rows, setRows] = useState<BudgetSubjectCatalogDto[]>([]);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [searchInput, setSearchInput] = useState("");
  const [searchText, setSearchText] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [contextMenu, setContextMenu] = useState<SubjectContextMenuState | null>(null);
  const [editingSubject, setEditingSubject] = useState<SubjectEditorDraft | null>(null);
  const [newRootDraft, setNewRootDraft] = useState<NewSubjectDraft | null>(null);
  const [newChildDraft, setNewChildDraft] = useState<NewSubjectDraft | null>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const uPfx = useUserStorageKeyPrefix();
  const { rowStyle, beginResize } = useTableRowHeights(`${uPfx}::budget-subject-tree`, {
    minHeight: 28,
    maxHeight: 160,
  });

  const reload = async (opts?: { collapseAll?: boolean }) => {
    const data = await apiGet<BudgetSubjectCatalogDto[]>("/api/budget-subject-catalog");
    if (opts?.collapseAll) setExpanded({});
    setRows(data);
  };

  useEffect(() => {
    reload({ collapseAll: true }).catch((e) => alert(`加载部门预算科目失败：${e.message}`));
  }, []);

  useEffect(() => {
    const onOutside = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, []);

  const tree = useMemo(() => buildTree(rows), [rows]);
  const visibleTree = useMemo(() => filterTree(tree, searchText), [tree, searchText]);

  const resetEditorState = () => {
    setEditingSubject(null);
    setNewRootDraft(null);
    setNewChildDraft(null);
  };

  const startNewRootDraft = () => {
    setEditingSubject(null);
    setNewChildDraft(null);
    setNewRootDraft({ parentId: null, level: 1, name: "", formulaText: "" });
  };

  const startNewChildDraft = (node: TreeNode) => {
    if (node.level_number >= MAX_SUBJECT_LEVEL) {
      alert(`部门预算科目最多 ${MAX_SUBJECT_LEVEL} 级，当前节点不能新增下级。`);
      return;
    }
    setNewRootDraft(null);
    setEditingSubject(null);
    setExpanded((prev) => ({ ...prev, [node.id]: true }));
    setNewChildDraft({
      parentId: node.id,
      level: node.level_number + 1,
      name: "",
      formulaText: "",
    });
  };

  const startEditSubject = (node: TreeNode) => {
    setNewRootDraft(null);
    setNewChildDraft(null);
    setEditingSubject({
      id: node.id,
      name: node.subject_name,
      formulaText: node.formula_text ?? "",
    });
  };

  const saveNewSubject = async (draft: NewSubjectDraft) => {
    if (!draft.name.trim()) {
      alert("预算科目名称不能为空。");
      return false;
    }
    try {
      await apiPost<BudgetSubjectCatalogDto>("/api/budget-subject-catalog", {
        parent_id: draft.parentId,
        subject_name: draft.name.trim(),
        formula_text: draft.formulaText.trim() || null,
      });
      resetEditorState();
      await reload();
      return true;
    } catch (e) {
      alert(e instanceof Error ? e.message : "新增失败");
      return false;
    }
  };

  const saveEditedSubject = async () => {
    if (!editingSubject) return false;
    if (!editingSubject.name.trim()) {
      alert("预算科目名称不能为空。");
      return false;
    }
    try {
      await apiPatch<BudgetSubjectCatalogDto>(`/api/budget-subject-catalog/${editingSubject.id}`, {
        subject_name: editingSubject.name.trim(),
        formula_text: editingSubject.formulaText.trim() || null,
      });
      resetEditorState();
      await reload();
      return true;
    } catch (e) {
      alert(e instanceof Error ? e.message : "更新失败");
      return false;
    }
  };

  const deleteSubject = async (node: TreeNode) => {
    if (!confirm(`确认删除预算科目“${node.subject_name}”吗？`)) return;
    try {
      await apiDelete(`/api/budget-subject-catalog/${node.id}`);
      setSelectedId((prev) => (prev === node.id ? null : prev));
      await reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
  };

  const handleSaveAndRefresh = async () => {
    try {
      resetEditorState();
      setContextMenu(null);
      setSelectedId(null);
      await reload({ collapseAll: true });
      alert("已从数据库刷新部门预算科目体系。");
    } catch (e) {
      alert(e instanceof Error ? e.message : "刷新失败");
    }
  };

  const handleExportTree = async () => {
    const proceed = confirm(
      "即将导出Excel文件。\n\n默认会保存到浏览器设置的下载目录（通常为系统“下载”文件夹）。\n如果你在浏览器中配置了其它下载路径，将保存到你配置的位置。\n\n是否继续导出？"
    );
    if (!proceed) return;
    try {
      const resp = await fetch(buildApiUrl("/api/budget-subject-catalog/export"), { credentials: "include" });
      if (!resp.ok) throw new Error((await resp.text()) || "导出失败");
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") ?? "";
      const fnMatch = cd.match(/filename="?([^"]+)"?/i);
      const fileName = fnMatch?.[1] || "budget_subject_catalog.xlsx";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "导出失败");
    }
  };

  const collapseCurrentLevelOnly = () => {
    if (selectedId != null) {
      setExpanded((prev) => ({ ...prev, [selectedId]: false }));
      return;
    }
    setExpanded((prev) => {
      const next = { ...prev };
      rows.forEach((row) => {
        if (row.level_number === 1) next[row.id] = false;
      });
      return next;
    });
  };

  const expandNextLevelOnly = () => {
    if (selectedId != null) {
      setExpanded((prev) => ({ ...prev, [selectedId]: true }));
      return;
    }
    setExpanded((prev) => {
      const next = { ...prev };
      rows.forEach((row) => {
        if (row.level_number === 1) next[row.id] = true;
      });
      return next;
    });
  };

  const collapseAllFromCurrentLevel = () => {
    const selectedLevel = selectedId != null ? (rows.find((row) => row.id === selectedId)?.level_number ?? 1) : 1;
    setExpanded((prev) => {
      const next = { ...prev };
      rows.forEach((row) => {
        if (row.level_number === selectedLevel) next[row.id] = false;
      });
      return next;
    });
  };

  const expandAllFromCurrentLevel = () => {
    if (selectedId != null) {
      const selectedNode = findTreeNodeById(tree, selectedId);
      if (!selectedNode) return;
      const ids: number[] = [];
      const collect = (node: TreeNode) => {
        ids.push(node.id);
        node.children.forEach(collect);
      };
      collect(selectedNode);
      setExpanded((prev) => {
        const next = { ...prev };
        ids.forEach((id) => {
          next[id] = true;
        });
        return next;
      });
      return;
    }
    const next: Record<number, boolean> = {};
    rows.forEach((row) => {
      next[row.id] = true;
    });
    setExpanded(next);
  };

  const collapseEntireTree = () => {
    setSearchInput("");
    setSearchText("");
    const next: Record<number, boolean> = {};
    rows.forEach((row) => {
      next[row.id] = false;
    });
    setExpanded(next);
  };

  const expandEntireTree = () => {
    const next: Record<number, boolean> = {};
    rows.forEach((row) => {
      next[row.id] = true;
    });
    setExpanded(next);
  };

  const toggleExpanded = (id: number) => {
    setExpanded((prev) => ({ ...prev, [id]: !(prev[id] ?? false) }));
  };

  const renderNode = (node: TreeNode): JSX.Element => {
    const isOpen = expanded[node.id] ?? false;
    const hasChild = node.children.length > 0;
    const isSelected = selectedId === node.id;
    const isEditing = editingSubject?.id === node.id;
    return (
      <div key={node.id}>
        <div
          className={`relative flex items-center gap-1 px-2 py-1 pb-1.5 border-b border-gray-100 group ${isSelected ? "bg-blue-100" : "hover:bg-gray-50"}`}
          style={{
            paddingLeft: `${(node.level_number - 1) * TREE_INDENT + 8}px`,
            ...rowStyle(`budget-subject-${node.id}`),
          }}
          onClick={() => setSelectedId(node.id)}
          onContextMenu={(e) => {
            e.preventDefault();
            setSelectedId(node.id);
            setContextMenu({
              x: e.clientX,
              y: e.clientY,
              node: {
                id: node.id,
                name: node.subject_name,
                level: node.level_number,
                hasExpandableChildren: hasChild,
                isOpen,
                canAddChild: node.level_number < MAX_SUBJECT_LEVEL,
              },
            });
          }}
        >
          {hasChild ? (
            <button className="p-0.5 hover:bg-gray-200 rounded" onClick={() => toggleExpanded(node.id)}>
              {isOpen ? <ChevronDown className="w-3 h-3 text-gray-600" /> : <ChevronRight className="w-3 h-3 text-gray-600" />}
            </button>
          ) : (
            <span className="w-4" />
          )}
          <FileText className="w-3 h-3 text-blue-600 flex-shrink-0 mr-1" />
          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] text-slate-600 whitespace-nowrap">
            {node.level_label}
          </span>
          {isEditing && editingSubject ? (
            <div className="flex items-center gap-1 flex-1">
              <input
                value={editingSubject.name}
                onChange={(e) => setEditingSubject({ ...editingSubject, name: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void saveEditedSubject();
                  }
                }}
                className="flex-1 min-w-[160px] text-xs text-gray-700 px-1 py-0.5 border border-blue-400 rounded"
                autoFocus
              />
              <input
                value={editingSubject.formulaText}
                onChange={(e) => setEditingSubject({ ...editingSubject, formulaText: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void saveEditedSubject();
                  }
                }}
                className="w-40 text-xs text-gray-700 px-1 py-0.5 border border-blue-400 rounded"
                placeholder="公式"
              />
              <button className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]" onClick={() => void saveEditedSubject()}>
                保存
              </button>
              <button className="px-2 py-0.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300" onClick={() => setEditingSubject(null)}>
                取消
              </button>
            </div>
          ) : (
            <>
              <span className="text-xs text-gray-700 flex-1" onDoubleClick={() => startEditSubject(node)}>
                {node.subject_name}
              </span>
              <span className="w-40 text-[11px] text-gray-500 truncate">{node.formula_text || ""}</span>
            </>
          )}
          <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => startNewChildDraft(node)} title="新增下级">
            <Plus className="w-3 h-3" />
          </button>
          <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => startEditSubject(node)} title="编辑">
            <Edit className="w-3 h-3" />
          </button>
          <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => void deleteSubject(node)} title="删除">
            <Trash2 className="w-3 h-3 text-red-600" />
          </button>
          <TableRowResizeHandle
            onResizeStart={(e) =>
              beginResize(`budget-subject-${node.id}`, e, () => (e.currentTarget as HTMLElement).parentElement)
            }
          />
        </div>
        {isOpen && newChildDraft?.parentId === node.id && (
          <div
            className="flex items-center gap-2 px-2 py-1 border-b border-gray-100 bg-yellow-50"
            style={{ paddingLeft: `${node.level_number * TREE_INDENT + 8}px` }}
          >
            <FileText className="w-3 h-3 text-blue-600 flex-shrink-0 mr-1" />
            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] text-slate-600 whitespace-nowrap">
              {`${newChildDraft.level}级`}
            </span>
            <input
              value={newChildDraft.name}
              onChange={(e) => setNewChildDraft({ ...newChildDraft, name: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void saveNewSubject(newChildDraft);
                }
              }}
              className="flex-1 min-w-[160px] px-1 py-0.5 text-xs border border-blue-400 rounded"
              placeholder="下级预算科目名称"
            />
            <input
              value={newChildDraft.formulaText}
              onChange={(e) => setNewChildDraft({ ...newChildDraft, formulaText: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void saveNewSubject(newChildDraft);
                }
              }}
              className="w-40 px-1 py-0.5 text-xs border border-blue-400 rounded"
              placeholder="公式"
            />
            <button className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]" onClick={() => void saveNewSubject(newChildDraft)}>
              保存
            </button>
            <button className="px-2 py-0.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300" onClick={() => setNewChildDraft(null)}>
              取消
            </button>
          </div>
        )}
        {isOpen && node.children.map((child) => renderNode(child))}
      </div>
    );
  };

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-medium text-gray-800">部门预算科目维护</h3>
      </div>
      <div className="border border-gray-300 rounded overflow-hidden bg-white flex flex-col flex-1 min-h-0">
        <div className="px-3 py-2 bg-gray-100 border-b border-gray-300">
          <div className="flex items-center gap-2 mb-2">
            <div className="relative w-56">
              <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={searchInput}
                onChange={(e) => {
                  setSearchInput(e.target.value);
                  setSearchText(e.target.value);
                }}
                onKeyDown={(e) => e.key === "Enter" && setSearchText(searchInput)}
                placeholder="搜索预算科目/公式..."
                className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-full focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {searchInput && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchInput("");
                    setSearchText("");
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
                  title="清除搜索"
                >
                  <X className="w-3.5 h-3.5 text-gray-500" />
                </button>
              )}
            </div>
            <button onClick={() => setSearchText(searchInput)} className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50">
              搜索
            </button>
            <div className="flex-1" />
            <button className="px-3 py-1 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9] flex items-center gap-1" onClick={startNewRootDraft}>
              <Plus className="w-3 h-3" />
              增加一级预算科目
            </button>
            <button
              className="px-3 py-1 text-xs bg-[#16a085] text-white rounded hover:bg-[#138d75] flex items-center gap-1"
              onClick={() => void handleExportTree()}
            >
              <Download className="w-3 h-3" />
              Excel导出科目
            </button>
            <button className="px-3 py-1 text-xs bg-[#e67e22] text-white rounded hover:bg-[#d35400] flex items-center gap-1" onClick={() => void handleSaveAndRefresh()}>
              <Save className="w-3 h-3" />
              保存并刷新
            </button>
          </div>
          <div className="flex items-center">
            <div className="ml-auto flex items-center gap-2">
              <button type="button" title="收起当前选中的预算科目；未选中时收起所有一级科目" onClick={collapseCurrentLevelOnly} className={treeToolbarButtonClass}>
                <Minimize2 className="w-3 h-3" />
                <span>收起本级</span>
              </button>
              <button type="button" title="展开当前选中的预算科目；未选中时展开所有一级科目" onClick={expandNextLevelOnly} className={treeToolbarButtonClass}>
                <Maximize2 className="w-3 h-3" />
                <span>展开下级</span>
              </button>
              <button type="button" title="收起当前层级下所有同级预算科目；未选中时收起全部一级科目" onClick={collapseAllFromCurrentLevel} className={treeToolbarButtonClass}>
                <ChevronsUp className="w-3 h-3" />
                <span>收起全部本级</span>
              </button>
              <button type="button" title="选中预算科目时展开其下全部子科目；未选中时展开整棵树" onClick={expandAllFromCurrentLevel} className={treeToolbarButtonClass}>
                <ChevronsDown className="w-3 h-3" />
                <span>展开全部下级</span>
              </button>
              <button type="button" title="清空搜索并收起整棵树" onClick={collapseEntireTree} className={treeToolbarButtonClass}>
                <Minimize2 className="w-3 h-3" />
                <span>全部收起</span>
              </button>
              <button type="button" title="展开整棵树全部层级" onClick={expandEntireTree} className={treeToolbarButtonClass}>
                <Maximize className="w-3 h-3" />
                <span>全部展开</span>
              </button>
            </div>
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          {newRootDraft && (
            <div className="flex items-center gap-2 px-2 py-1 border-b border-gray-100 bg-yellow-50">
              <FileText className="w-3 h-3 text-blue-600 flex-shrink-0 mr-1" />
              <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] text-slate-600 whitespace-nowrap">一级</span>
              <input
                value={newRootDraft.name}
                onChange={(e) => setNewRootDraft({ ...newRootDraft, name: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void saveNewSubject(newRootDraft);
                  }
                }}
                className="flex-1 min-w-[160px] px-1 py-0.5 text-xs border border-blue-400 rounded"
                placeholder="一级预算科目名称"
              />
              <input
                value={newRootDraft.formulaText}
                onChange={(e) => setNewRootDraft({ ...newRootDraft, formulaText: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void saveNewSubject(newRootDraft);
                  }
                }}
                className="w-40 px-1 py-0.5 text-xs border border-blue-400 rounded"
                placeholder="公式"
              />
              <button className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]" onClick={() => void saveNewSubject(newRootDraft)}>
                保存
              </button>
              <button className="px-2 py-0.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300" onClick={() => setNewRootDraft(null)}>
                取消
              </button>
            </div>
          )}
          {visibleTree.map((node) => renderNode(node))}
        </div>
      </div>
      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[180px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              const node = findTreeNodeById(tree, contextMenu.node.id);
              if (node) startEditSubject(node);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
          >
            <Edit className="w-3 h-3" />
            编辑
          </button>
          {contextMenu.node.canAddChild && (
            <button
              onClick={() => {
                const node = findTreeNodeById(tree, contextMenu.node.id);
                if (node) startNewChildDraft(node);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <Plus className="w-3 h-3" />
              增加下级预算科目
            </button>
          )}
          {contextMenu.node.hasExpandableChildren && (
            <button
              onClick={() => {
                toggleExpanded(contextMenu.node.id);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <Minimize2 className="w-3 h-3" />
              {contextMenu.node.isOpen ? "收起本级" : "展开下级"}
            </button>
          )}
          <div className="border-t border-gray-200 my-1" />
          <button
            onClick={() => {
              const node = findTreeNodeById(tree, contextMenu.node.id);
              if (node) void deleteSubject(node);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 text-red-600 flex items-center gap-2"
          >
            <Trash2 className="w-3 h-3" />
            删除本预算科目
          </button>
        </div>
      )}
    </div>
  );
}

function findTreeNodeById(nodes: TreeNode[], id: number): TreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = findTreeNodeById(node.children, id);
    if (child) return child;
  }
  return null;
}
