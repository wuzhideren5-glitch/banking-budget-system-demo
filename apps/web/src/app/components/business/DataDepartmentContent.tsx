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
  Upload,
  X,
  ChevronsDown,
  ChevronsUp,
} from "lucide-react";
import {
  createDeptAccount,
  deleteDeptAccount,
  deptAccountImportWorkflow,
  exportDeptTree,
  listDeptAccounts,
  updateDeptAccount,
  type DeptAccountDto,
} from "@/lib/expense/masterDataApi";
import {
  MAX_DEPT_LEVEL,
  buildDeptTree,
  filterDeptTree,
  findDeptTreeNodeByCode,
  groupDeptTreeByEntity,
  nextChildDeptCode,
  sortDeptEntityNames,
  validateDeptCode,
  type DeptTreeNode,
} from "@/lib/business/deptCatalogViewModel";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableRowHeights } from "@/lib/shared/useTableRowHeights";
import { treeToolbarButtonClass } from "@/lib/shared/treeToolbarStyles";
import { ExcelUploadDialog } from "@/app/components/common/ExcelUploadDialog";
import { TableRowResizeHandle } from "@/app/components/common/TableRowResizeHandle";

type DeptEditorDraft = {
  originalCode: string;
  code: string;
  name: string;
  parentCode: string | null;
  level: number;
  entityName: string;
};

type NewDeptDraft = {
  code: string;
  name: string;
  parentCode: string | null;
  level: number;
  entityName: string;
};

type DeptContextMenuState =
  | {
      x: number;
      y: number;
      node: {
        type: "entity";
        entityName: string;
        isOpen: boolean;
      };
    }
  | {
      x: number;
      y: number;
      node: {
        type: "dept";
        deptCode: string;
        deptName: string;
        level: number;
        hasChildren: boolean;
        isOpen: boolean;
        canAddChild: boolean;
      };
    };

const TREE_INDENT = 20;
const deptExcelFields = [
  { key: "entityName", label: "主体", required: true },
  { key: "level1Code", label: "事业群代码", required: true },
  { key: "level1Name", label: "事业群名称", required: true },
  { key: "level2Code", label: "费用归属部门代码", required: true },
  { key: "level2Name", label: "费用归属部门名称", required: true },
];

export function DataDepartmentContent() {
  const [depts, setDepts] = useState<DeptAccountDto[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [selectedEntityName, setSelectedEntityName] = useState<string | null>(null);
  const [selectedDeptCode, setSelectedDeptCode] = useState<string | null>(null);
  const [deptSearchInput, setDeptSearchInput] = useState("");
  const [deptSearch, setDeptSearch] = useState("");
  const [editingDept, setEditingDept] = useState<DeptEditorDraft | null>(null);
  const [newRootDraft, setNewRootDraft] = useState<NewDeptDraft | null>(null);
  const [newChildDraft, setNewChildDraft] = useState<NewDeptDraft | null>(null);
  const [contextMenu, setContextMenu] = useState<DeptContextMenuState | null>(null);
  const [showExcelDialog, setShowExcelDialog] = useState(false);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const uPfx = useUserStorageKeyPrefix();
  const { rowStyle, beginResize } = useTableRowHeights(`${uPfx}::dept-tree-main`, {
    minHeight: 28,
    maxHeight: 160,
  });

  const reload = async (opts?: { collapseAll?: boolean }) => {
    const rows = await listDeptAccounts();
    if (opts?.collapseAll) setExpanded({});
    setDepts(rows);
  };

  useEffect(() => {
    reload({ collapseAll: true }).catch((e) => alert(`加载部门科目失败：${e.message}`));
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

  const tree = useMemo(() => buildDeptTree(depts), [depts]);
  const visibleTree = useMemo(() => filterDeptTree(tree, deptSearch), [tree, deptSearch]);
  const entityGroups = useMemo(() => groupDeptTreeByEntity(visibleTree), [visibleTree]);
  const entityNames = useMemo(() => sortDeptEntityNames(depts.map((dept) => dept.entity_name || "微众银行")), [depts]);

  const resetEditorState = () => {
    setEditingDept(null);
    setNewRootDraft(null);
    setNewChildDraft(null);
  };

  const validateDraft = (draft: NewDeptDraft | DeptEditorDraft, opts?: { allowSameCode?: boolean }) => {
    const code = draft.code.trim().toUpperCase();
    const name = draft.name.trim();
    const codeError = validateDeptCode(code, draft.level, draft.parentCode ?? undefined);
    if (codeError) return codeError;
    if (!name) return "部门科目名称不能为空。";
    if (!draft.entityName.trim()) return "主体不能为空。";
    const originalCode = "originalCode" in draft ? draft.originalCode : null;
    const duplicated = depts.some((dept) => dept.dept_code === code && (!opts?.allowSameCode || dept.dept_code !== originalCode));
    if (duplicated) return `部门科目代码 ${code} 已存在，请修改。`;
    return null;
  };

  const startNewRootDraft = (entityName?: string) => {
    const targetEntity = entityName ?? selectedEntityName;
    if (!targetEntity) {
      alert("请先选择一个主体，再新增事业群。");
      return;
    }
    setSelectedEntityName(targetEntity);
    setSelectedDeptCode(null);
    setEditingDept(null);
    setNewChildDraft(null);
    setNewRootDraft({ code: "Y1", name: "", parentCode: null, level: 1, entityName: targetEntity });
  };

  const startNewChildDraft = (parent: DeptTreeNode) => {
    if (parent.level >= MAX_DEPT_LEVEL) {
      alert(`部门树最多 ${MAX_DEPT_LEVEL} 级部门节点，当前节点不能新增下级。`);
      return;
    }
    const defaultCode = nextChildDeptCode(parent.dept_code, parent.children) ?? `${parent.dept_code}01`;
    setNewRootDraft(null);
    setEditingDept(null);
    setExpanded((prev) => ({ ...prev, [parent.dept_code]: true }));
    setNewChildDraft({
      code: defaultCode,
      name: "",
      parentCode: parent.dept_code,
      level: parent.level + 1,
      entityName: parent.entity_name,
    });
  };

  const startEditDept = (node: DeptTreeNode) => {
    setNewRootDraft(null);
    setNewChildDraft(null);
    setEditingDept({
      originalCode: node.dept_code,
      code: node.dept_code,
      name: node.dept_name,
      parentCode: node.parent_code,
      level: node.level,
      entityName: node.entity_name,
    });
  };

  const saveNewDept = async (draft: NewDeptDraft) => {
    const error = validateDraft(draft);
    if (error) {
      alert(error);
      return false;
    }
    try {
      await createDeptAccount({
        dept_code: draft.code.trim().toUpperCase(),
        dept_name: draft.name.trim(),
        entity_name: draft.entityName,
        parent_code: draft.parentCode,
        level: draft.level,
        is_leaf: draft.level >= MAX_DEPT_LEVEL,
      });
      resetEditorState();
      await reload();
      return true;
    } catch (e) {
      alert(e instanceof Error ? e.message : "新增失败");
      return false;
    }
  };

  const saveEditedDept = async () => {
    if (!editingDept) return false;
    const error = validateDraft(editingDept, { allowSameCode: true });
    if (error) {
      alert(error);
      return false;
    }
    const originalCode = editingDept.originalCode;
    const nextCode = editingDept.code.trim().toUpperCase();
    const nextName = editingDept.name.trim();
    const node = depts.find((dept) => dept.dept_code === originalCode);
    if (!node) {
      alert("未找到当前部门科目，请刷新后重试。");
      return false;
    }
    const hasChildDept = depts.some((dept) => dept.parent_code === originalCode);
    try {
      if (nextCode === originalCode) {
        await updateDeptAccount(originalCode, { dept_name: nextName });
      } else {
        if (hasChildDept) {
          alert("存在下级部门时，不允许修改当前部门代码。");
          return false;
        }
        await createDeptAccount({
          dept_code: nextCode,
          dept_name: nextName,
          entity_name: node.entity_name,
          parent_code: node.parent_code,
          level: node.level,
          is_leaf: node.level >= MAX_DEPT_LEVEL,
        });
        await deleteDeptAccount(originalCode);
      }
      resetEditorState();
      await reload();
      return true;
    } catch (e) {
      alert(e instanceof Error ? e.message : "更新失败");
      return false;
    }
  };

  const deleteDept = async (node: DeptTreeNode) => {
    if (!confirm(`确认删除部门科目 ${node.dept_code} 吗？`)) return;
    try {
      await deleteDeptAccount(node.dept_code);
      setSelectedDeptCode((prev) => (prev === node.dept_code ? null : prev));
      await reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
  };

  const handleSaveAndRefresh = async () => {
    try {
      resetEditorState();
      setContextMenu(null);
      setSelectedDeptCode(null);
      setSelectedEntityName(null);
      await reload({ collapseAll: true });
      alert("已从数据库刷新部门树。\n\n当前结构为：主体 -> 事业群 -> 费用归属部门。");
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
      await exportDeptTree();
    } catch (e) {
      alert(e instanceof Error ? e.message : "导出失败");
    }
  };

  const collapseCurrentLevelOnly = () => {
    if (selectedDeptCode) {
      setExpanded((prev) => ({ ...prev, [selectedDeptCode]: false }));
      return;
    }
    if (selectedEntityName) {
      setExpanded((prev) => ({ ...prev, [`entity:${selectedEntityName}`]: false }));
      return;
    }
    setExpanded((prev) => {
      const next = { ...prev };
      entityNames.forEach((name) => {
        next[`entity:${name}`] = false;
      });
      return next;
    });
  };

  const expandNextLevelOnly = () => {
    if (selectedDeptCode) {
      setExpanded((prev) => ({ ...prev, [selectedDeptCode]: true }));
      return;
    }
    if (selectedEntityName) {
      setExpanded((prev) => ({ ...prev, [`entity:${selectedEntityName}`]: true }));
      return;
    }
    setExpanded((prev) => {
      const next = { ...prev };
      entityNames.forEach((name) => {
        next[`entity:${name}`] = true;
      });
      return next;
    });
  };

  const collapseAllFromCurrentLevel = () => {
    if (selectedEntityName) {
      setExpanded((prev) => ({ ...prev, [`entity:${selectedEntityName}`]: false }));
      return;
    }
    const selectedLevel = selectedDeptCode ? (depts.find((dept) => dept.dept_code === selectedDeptCode)?.level ?? 1) : 1;
    setExpanded((prev) => {
      const next = { ...prev };
      depts.forEach((dept) => {
        if (dept.level === selectedLevel) next[dept.dept_code] = false;
      });
      return next;
    });
  };

  const expandAllFromCurrentLevel = () => {
    if (selectedEntityName) {
      const next: Record<string, boolean> = { [`entity:${selectedEntityName}`]: true };
      const targetGroup = entityGroups.find((group) => group.entityName === selectedEntityName);
      const collect = (node: DeptTreeNode) => {
        next[node.dept_code] = true;
        node.children.forEach(collect);
      };
      targetGroup?.nodes.forEach(collect);
      setExpanded((prev) => ({ ...prev, ...next }));
      return;
    }
    if (selectedDeptCode) {
      const selectedNode = findDeptTreeNodeByCode(tree, selectedDeptCode);
      if (!selectedNode) return;
      const next: Record<string, boolean> = {};
      const collect = (node: DeptTreeNode) => {
        next[node.dept_code] = true;
        node.children.forEach(collect);
      };
      collect(selectedNode);
      setExpanded((prev) => ({ ...prev, ...next }));
      return;
    }
    expandEntireTree();
  };

  const collapseFullDeptTree = () => {
    setDeptSearchInput("");
    setDeptSearch("");
    setSelectedEntityName(null);
    setSelectedDeptCode(null);
    const next: Record<string, boolean> = {};
    entityNames.forEach((name) => {
      next[`entity:${name}`] = false;
    });
    depts.forEach((dept) => {
      next[dept.dept_code] = false;
    });
    setExpanded(next);
  };

  const expandFullDeptTree = () => {
    const next: Record<string, boolean> = {};
    entityNames.forEach((name) => {
      next[`entity:${name}`] = true;
    });
    depts.forEach((dept) => {
      next[dept.dept_code] = true;
    });
    setExpanded(next);
  };

  const collapseEntireTree = () => collapseFullDeptTree();
  const expandEntireTree = () => expandFullDeptTree();

  const toggleDeptExpanded = (deptCode: string) => {
    setExpanded((prev) => ({ ...prev, [deptCode]: !(prev[deptCode] ?? false) }));
  };

  const toggleEntityExpanded = (entityName: string) => {
    const key = `entity:${entityName}`;
    setExpanded((prev) => ({ ...prev, [key]: !(prev[key] ?? true) }));
  };

  const renderNode = (node: DeptTreeNode, displayLevel: number): JSX.Element => {
    const isOpen = expanded[node.dept_code] ?? false;
    const hasChildren = node.children.length > 0;
    const isSelected = selectedDeptCode === node.dept_code;
    const isEditing = editingDept?.originalCode === node.dept_code;
    return (
      <div key={node.dept_code}>
        <div
          className={`relative flex items-center gap-1 px-2 py-1 pb-1.5 border-b border-gray-100 group ${isSelected ? "bg-blue-100" : "hover:bg-gray-50"}`}
          style={{
            paddingLeft: `${(displayLevel - 1) * TREE_INDENT + 8}px`,
            ...rowStyle(`dept-${node.dept_code}`),
          }}
          onClick={() => {
            setSelectedEntityName(null);
            setSelectedDeptCode(node.dept_code);
          }}
          onContextMenu={(e) => {
            e.preventDefault();
            setSelectedEntityName(null);
            setSelectedDeptCode(node.dept_code);
            setContextMenu({
              x: e.clientX,
              y: e.clientY,
              node: {
                type: "dept",
                deptCode: node.dept_code,
                deptName: node.dept_name,
                level: node.level,
                hasChildren,
                isOpen,
                canAddChild: node.level < MAX_DEPT_LEVEL,
              },
            });
          }}
        >
          {hasChildren ? (
            <button className="p-0.5 hover:bg-gray-200 rounded" onClick={() => toggleDeptExpanded(node.dept_code)}>
              {isOpen ? <ChevronDown className="w-3 h-3 text-gray-600" /> : <ChevronRight className="w-3 h-3 text-gray-600" />}
            </button>
          ) : (
            <span className="w-4" />
          )}
          <FileText className="w-3 h-3 text-blue-600 flex-shrink-0 mr-1" />
          {isEditing && editingDept ? (
            <input
              value={editingDept.code}
              onChange={(e) => setEditingDept({ ...editingDept, code: e.target.value.toUpperCase() })}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void saveEditedDept();
                }
              }}
              className="w-24 font-mono text-xs text-gray-700 px-1 py-0.5 border border-blue-400 rounded"
              autoFocus
            />
          ) : (
            <span className="w-24 font-mono text-xs text-gray-700" onDoubleClick={() => startEditDept(node)}>
              {node.dept_code}
            </span>
          )}
          {isEditing && editingDept ? (
            <div className="flex items-center gap-1 flex-1">
              <input
                value={editingDept.name}
                onChange={(e) => setEditingDept({ ...editingDept, name: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void saveEditedDept();
                  }
                }}
                className="text-xs text-gray-700 flex-1 px-1 py-0.5 border border-blue-400 rounded"
              />
              <button className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]" onClick={() => void saveEditedDept()}>
                保存
              </button>
              <button className="px-2 py-0.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300" onClick={() => setEditingDept(null)}>
                取消
              </button>
            </div>
          ) : (
            <span className="text-xs text-gray-700 flex-1" onDoubleClick={() => startEditDept(node)}>
              {node.dept_name}
            </span>
          )}
          {node.level < MAX_DEPT_LEVEL && (
            <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => startNewChildDraft(node)} title="新增下级">
              <Plus className="w-3 h-3" />
            </button>
          )}
          <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => startEditDept(node)} title="编辑">
            <Edit className="w-3 h-3" />
          </button>
          <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => void deleteDept(node)} title="删除">
            <Trash2 className="w-3 h-3 text-red-600" />
          </button>
          <TableRowResizeHandle
            onResizeStart={(e) => beginResize(`dept-${node.dept_code}`, e, () => (e.currentTarget as HTMLElement).parentElement)}
          />
        </div>
        {isOpen && newChildDraft?.parentCode === node.dept_code && (
          <div className="flex items-center gap-2 px-2 py-1 border-b border-gray-100 bg-yellow-50" style={{ paddingLeft: `${displayLevel * TREE_INDENT + 8}px` }}>
            <FileText className="w-3 h-3 text-blue-600 flex-shrink-0 mr-1" />
            <input
              value={newChildDraft.code}
              onChange={(e) => setNewChildDraft({ ...newChildDraft, code: e.target.value.toUpperCase() })}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void saveNewDept(newChildDraft);
                }
              }}
              className="w-24 px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
              placeholder="费用归属部门代码"
            />
            <input
              value={newChildDraft.name}
              onChange={(e) => setNewChildDraft({ ...newChildDraft, name: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void saveNewDept(newChildDraft);
                }
              }}
              className="flex-1 px-1 py-0.5 text-xs border border-blue-400 rounded"
              placeholder="费用归属部门名称"
            />
            <button className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]" onClick={() => void saveNewDept(newChildDraft)}>
              保存
            </button>
            <button className="px-2 py-0.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300" onClick={() => setNewChildDraft(null)}>
              取消
            </button>
          </div>
        )}
        {isOpen && node.children.map((child) => renderNode(child, displayLevel + 1))}
      </div>
    );
  };

  return (
    <div className="bb-page">
      <div className="bb-page-header">
        <h3 className="bb-page-title">部门科目维护</h3>
      </div>
      <div className="bb-panel overflow-hidden flex flex-col flex-1">
        <div className="bb-panel-header block">
          <div className="flex items-center gap-2 mb-2">
            <div className="relative w-72">
              <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={deptSearchInput}
                onChange={(e) => {
                  setDeptSearchInput(e.target.value);
                  setDeptSearch(e.target.value);
                }}
                onKeyDown={(e) => e.key === "Enter" && setDeptSearch(deptSearchInput)}
                placeholder="搜索主体 / 事业群 / 费用归属部门..."
                className="bb-input w-full pl-8 pr-8"
              />
              {deptSearchInput && (
                <button
                  type="button"
                  onClick={() => {
                    setDeptSearchInput("");
                    setDeptSearch("");
                  }}
                  className="bb-icon-btn absolute right-1 top-1/2 h-6 w-6 -translate-y-1/2"
                  title="清除搜索"
                >
                  <X className="w-3.5 h-3.5 text-gray-500" />
                </button>
              )}
            </div>
            <button onClick={() => setDeptSearch(deptSearchInput)} className="bb-btn bb-btn-secondary">
              搜索
            </button>
            <div className="flex-1" />
            <button className="bb-btn bb-btn-primary" onClick={() => startNewRootDraft()}>
              <Plus className="w-3 h-3" />
              增加事业群
            </button>
            <button
              className="bb-btn bb-btn-success"
              onClick={() => setShowExcelDialog(true)}
            >
              <Upload className="w-3 h-3" />
              Excel上传科目
            </button>
            <button
              className="bb-btn bb-btn-secondary"
              onClick={() => void handleExportTree()}
            >
              <Download className="w-3 h-3" />
              Excel导出科目
            </button>
            <button className="bb-btn bb-btn-warning" onClick={() => void handleSaveAndRefresh()}>
              <Save className="w-3 h-3" />
              保存并刷新
            </button>
          </div>
          <div className="flex items-center">
            <div className="text-[11px] text-gray-600">树结构：主体 → 事业群 → 费用归属部门</div>
            <div className="ml-auto flex items-center gap-2">
              <button type="button" title="收起当前选中的主体或部门节点；未选中时收起全部主体" onClick={collapseCurrentLevelOnly} className={treeToolbarButtonClass}>
                <Minimize2 className="w-3 h-3" />
                <span>收起本级</span>
              </button>
              <button type="button" title="展开当前选中的主体或部门节点；未选中时展开全部主体" onClick={expandNextLevelOnly} className={treeToolbarButtonClass}>
                <Maximize2 className="w-3 h-3" />
                <span>展开下级</span>
              </button>
              <button type="button" title="收起当前层级下所有同级节点；未选中时收起全部主体" onClick={collapseAllFromCurrentLevel} className={treeToolbarButtonClass}>
                <ChevronsUp className="w-3 h-3" />
                <span>收起全部本级</span>
              </button>
              <button type="button" title="选中主体或部门时展开其下全部节点；未选中时展开整棵树" onClick={expandAllFromCurrentLevel} className={treeToolbarButtonClass}>
                <ChevronsDown className="w-3 h-3" />
                <span>展开全部下级</span>
              </button>
              <button type="button" title="清空搜索并收起整棵树中所有节点" onClick={collapseEntireTree} className={treeToolbarButtonClass}>
                <Minimize2 className="w-3 h-3" />
                <span>全部收起</span>
              </button>
              <button type="button" title="从主体起展开全部层级" onClick={expandEntireTree} className={treeToolbarButtonClass}>
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
              <span className="text-xs text-gray-600">主体：{newRootDraft.entityName}</span>
              <input
                value={newRootDraft.code}
                onChange={(e) => setNewRootDraft({ ...newRootDraft, code: e.target.value.toUpperCase() })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void saveNewDept(newRootDraft);
                  }
                }}
                className="bb-grid-input w-24 font-mono"
                placeholder="事业群代码"
              />
              <input
                value={newRootDraft.name}
                onChange={(e) => setNewRootDraft({ ...newRootDraft, name: e.target.value })}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void saveNewDept(newRootDraft);
                  }
                }}
                className="bb-grid-input flex-1"
                placeholder="事业群名称"
              />
              <button className="bb-btn bb-btn-primary h-7 px-2" onClick={() => void saveNewDept(newRootDraft)}>
                保存
              </button>
              <button className="bb-btn bb-btn-secondary h-7 px-2" onClick={() => setNewRootDraft(null)}>
                取消
              </button>
            </div>
          )}
          {entityGroups.map((group) => {
            const entityKey = `entity:${group.entityName}`;
            const entityOpen = expanded[entityKey] ?? true;
            const isEntitySelected = selectedEntityName === group.entityName;
            return (
              <div key={group.entityName}>
                <div
                  className={`relative flex items-center gap-1 px-2 py-1 pb-1.5 border-b border-gray-100 group ${isEntitySelected ? "bg-indigo-100" : "bg-indigo-50 hover:bg-indigo-100"}`}
                  style={rowStyle(entityKey)}
                  onClick={() => {
                    setSelectedEntityName(group.entityName);
                    setSelectedDeptCode(null);
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setSelectedEntityName(group.entityName);
                    setSelectedDeptCode(null);
                    setContextMenu({
                      x: e.clientX,
                      y: e.clientY,
                      node: { type: "entity", entityName: group.entityName, isOpen: entityOpen },
                    });
                  }}
                >
                  <button className="p-0.5 hover:bg-indigo-200 rounded" onClick={() => toggleEntityExpanded(group.entityName)}>
                    {entityOpen ? <ChevronDown className="w-3 h-3 text-gray-600" /> : <ChevronRight className="w-3 h-3 text-gray-600" />}
                  </button>
                  <FileText className="w-3 h-3 text-indigo-600 flex-shrink-0 mr-1" />
                  <span className="text-xs font-medium text-gray-800 flex-1">{group.entityName}</span>
                  <button className="p-1 hover:bg-indigo-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => startNewRootDraft(group.entityName)} title="新增事业群">
                    <Plus className="w-3 h-3" />
                  </button>
                  <TableRowResizeHandle onResizeStart={(e) => beginResize(entityKey, e, () => (e.currentTarget as HTMLElement).parentElement)} />
                </div>
                {entityOpen && group.nodes.map((node) => renderNode(node, 2))}
              </div>
            );
          })}
        </div>
      </div>
      {contextMenu && (
        <div ref={contextMenuRef} className="bb-popover fixed z-50 min-w-[180px] py-1" style={{ left: contextMenu.x, top: contextMenu.y }}>
          {contextMenu.node.type === "entity" &&
            (() => {
              const node = contextMenu.node;
              return (
            <>
              <button
                onClick={() => {
                  startNewRootDraft(node.entityName);
                  setContextMenu(null);
                }}
                className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
              >
                <Plus className="w-3 h-3" />
                增加事业群
              </button>
              <button
                onClick={() => {
                  toggleEntityExpanded(node.entityName);
                  setContextMenu(null);
                }}
                className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
              >
                <Minimize2 className="w-3 h-3" />
                {node.isOpen ? "收起主体" : "展开主体"}
              </button>
            </>
              );
            })()}
          {contextMenu.node.type === "dept" &&
            (() => {
              const node = contextMenu.node;
              return (
            <>
              <button
                onClick={() => {
                  const current = findDeptTreeNodeByCode(tree, node.deptCode);
                  if (current) startEditDept(current);
                  setContextMenu(null);
                }}
                className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
              >
                <Edit className="w-3 h-3" />
                编辑
              </button>
              {node.canAddChild && (
                <button
                  onClick={() => {
                    const current = findDeptTreeNodeByCode(tree, node.deptCode);
                    if (current) startNewChildDraft(current);
                    setContextMenu(null);
                  }}
                  className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
                >
                  <Plus className="w-3 h-3" />
                  增加下级部门
                </button>
              )}
              {node.hasChildren && (
                <button
                  onClick={() => {
                    toggleDeptExpanded(node.deptCode);
                    setContextMenu(null);
                  }}
                  className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
                >
                  <Minimize2 className="w-3 h-3" />
                  {node.isOpen ? "收起本级" : "展开下级"}
                </button>
              )}
              <div className="border-t border-gray-200 my-1" />
              <button
                onClick={() => {
                  const current = findDeptTreeNodeByCode(tree, node.deptCode);
                  if (current) void deleteDept(current);
                  setContextMenu(null);
                }}
                className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 text-red-600 flex items-center gap-2"
              >
                <Trash2 className="w-3 h-3" />
                删除本部门
              </button>
            </>
              );
            })()}
        </div>
      )}
      <ExcelUploadDialog
        isOpen={showExcelDialog}
        onClose={() => setShowExcelDialog(false)}
        title="部门科目维护"
        fields={deptExcelFields}
        importWorkflow={deptAccountImportWorkflow}
        onImportComplete={() => void reload()}
      />
    </div>
  );
}
