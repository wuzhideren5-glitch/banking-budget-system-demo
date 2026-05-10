import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Database as DatabaseIcon,
  Download,
  Edit,
  FileText,
  Plus,
  Save,
  Search,
  Trash2,
  X,
  Minimize2,
  Maximize2,
  ChevronsUp,
  ChevronsDown,
  Maximize,
  Upload,
} from "lucide-react";
import { apiDelete, apiGet, apiPatch, apiPost, buildApiUrl, type DeptAccountDto, type DeptProductMappingDto, type ProductTypeDto } from "@/lib/api";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableRowHeights } from "@/lib/useTableRowHeights";
import { treeToolbarButtonClass } from "@/lib/treeToolbarStyles";
import { ExcelUploadDialog } from "./ExcelUploadDialog";
import { TableRowResizeHandle } from "./TableRowResizeHandle";

type TreeNode = DeptAccountDto & { children: TreeNode[] };
type DeptEditorDraft = {
  originalCode: string;
  code: string;
  name: string;
  parentCode: string | null;
  level: number;
};
type NewDeptDraft = {
  code: string;
  name: string;
  parentCode: string | null;
  level: number;
};
type DeptContextMenuState =
  | {
      x: number;
      y: number;
      node: {
        type: "dept";
        deptCode: string;
        deptName: string;
        level: number;
        hasExpandableChildren: boolean;
        isOpen: boolean;
        canAddChild: boolean;
      };
    }
  | {
      x: number;
      y: number;
      node: {
        type: "mapping";
        deptCode: string;
        productCode: string;
        productName: string;
      };
    };

const MAX_DEPT_LEVEL = 3;
const TREE_INDENT = 20;
const deptExcelFields = [
  { key: "level1Code", label: "第1级部门科目代码", required: true },
  { key: "level1Name", label: "第1级部门科目名称", required: true },
  { key: "level2Code", label: "第2级部门科目代码", required: true },
  { key: "level2Name", label: "第2级部门科目名称", required: true },
  { key: "level3Code", label: "第3级部门科目代码", required: true },
  { key: "level3Name", label: "第3级部门科目名称", required: true },
  { key: "productCode", label: "产品科目代码", required: true },
  { key: "productName", label: "产品科目名称", required: true },
];

function buildTree(rows: DeptAccountDto[]): TreeNode[] {
  const map = new Map<string, TreeNode>();
  rows.forEach((r) => map.set(r.dept_code, { ...r, children: [] }));
  const roots: TreeNode[] = [];
  map.forEach((node) => {
    if (node.parent_code && map.has(node.parent_code)) map.get(node.parent_code)!.children.push(node);
    else roots.push(node);
  });
  const sortRec = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => a.dept_code.localeCompare(b.dept_code));
    nodes.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}

function filterTree(nodes: TreeNode[], term: string): TreeNode[] {
  const s = term.trim().toLowerCase();
  if (!s) return nodes;
  return nodes
    .map((n) => {
      const children = filterTree(n.children, term);
      const match = n.dept_code.toLowerCase().includes(s) || n.dept_name.toLowerCase().includes(s);
      if (match || children.length > 0) return { ...n, children };
      return null;
    })
    .filter((n): n is TreeNode => Boolean(n));
}

function validateDeptCode(codeRaw: string, level: number, parentCode?: string): string | null {
  const code = codeRaw.trim().toUpperCase();
  if (!code) return "部门科目代码不能为空";
  if (level < 1 || level > MAX_DEPT_LEVEL) return `部门科目层级必须在 1-${MAX_DEPT_LEVEL} 级`;
  if (level === 1) {
    if (!/^Y\d$/.test(code)) return "1级部门科目代码格式错误，应为 Y + 1位数字（例如 Y1）";
    return null;
  }
  if (!parentCode) return "缺少上级部门代码，无法校验";
  const escapedParent = parentCode.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`^${escapedParent}\\d$`);
  if (!pattern.test(code)) {
    return `下级部门科目代码格式错误，应为“上级代码 + 1位数字”（例如 ${parentCode}1）`;
  }
  return null;
}

function nextChildDeptCode(parentCode: string, children: TreeNode[]): string | null {
  const nums = children
    .map((c) => c.dept_code)
    .filter((code) => code.startsWith(parentCode) && code.length === parentCode.length + 1)
    .map((code) => Number.parseInt(code.slice(-1), 10))
    .filter((n) => Number.isFinite(n));
  const max = nums.length > 0 ? Math.max(...nums) : -1;
  if (max >= 9) return null;
  return `${parentCode}${max + 1}`;
}

export function DataDepartmentContent() {
  const [depts, setDepts] = useState<DeptAccountDto[]>([]);
  const [mappings, setMappings] = useState<DeptProductMappingDto[]>([]);
  const [products, setProducts] = useState<ProductTypeDto[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [deptSearchInput, setDeptSearchInput] = useState("");
  const [deptSearch, setDeptSearch] = useState("");
  const [productSearchInput, setProductSearchInput] = useState("");
  const [productSearch, setProductSearch] = useState("");
  const [selectedDeptCode, setSelectedDeptCode] = useState<string | null>(null);
  const [selectedMapping, setSelectedMapping] = useState<{ deptCode: string; productCode: string; name: string } | null>(null);
  const [dragTargetDeptCode, setDragTargetDeptCode] = useState<string | null>(null);
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
    const [d, m, p] = await Promise.all([
      apiGet<DeptAccountDto[]>("/api/dept-accounts"),
      apiGet<DeptProductMappingDto[]>("/api/dept-product-mappings"),
      apiGet<ProductTypeDto[]>("/api/product-types"),
    ]);
    if (opts?.collapseAll) setExpanded({});
    setDepts(d);
    setMappings(m);
    setProducts(p);
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

  const tree = useMemo(() => buildTree(depts), [depts]);
  const visibleTree = useMemo(() => filterTree(tree, deptSearch), [tree, deptSearch]);
  const productMap = useMemo(() => new Map(products.map((p) => [p.product_code, p])), [products]);
  const mappedProductCodes = useMemo(() => new Set(mappings.map((m) => m.product_code)), [mappings]);
  const availableProducts = useMemo(
    () => products.filter((p) => !mappedProductCodes.has(p.product_code)),
    [products, mappedProductCodes]
  );
  const filteredProducts = useMemo(() => {
    const s = productSearch.trim().toLowerCase();
    if (!s) return availableProducts;
    return availableProducts.filter(
      (p) => p.product_code.toLowerCase().includes(s) || p.product_name.toLowerCase().includes(s)
    );
  }, [availableProducts, productSearch]);

  const mappedSet = useMemo(() => {
    const set = new Set<string>();
    mappings.forEach((m) => set.add(`${m.dept_code}__${m.product_code}`));
    return set;
  }, [mappings]);
  const mappedDeptByProduct = useMemo(() => {
    const map = new Map<string, string>();
    mappings.forEach((m) => map.set(m.product_code, m.dept_code));
    return map;
  }, [mappings]);

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
    const originalCode = "originalCode" in draft ? draft.originalCode : null;
    const duplicated = depts.some((d) => d.dept_code === code && (!opts?.allowSameCode || d.dept_code !== originalCode));
    if (duplicated) return `部门科目代码 ${code} 已存在，请修改。`;
    return null;
  };

  const startNewRootDraft = () => {
    setEditingDept(null);
    setNewChildDraft(null);
    setNewRootDraft({ code: "Y1", name: "", parentCode: null, level: 1 });
  };

  const startNewChildDraft = (parent: TreeNode) => {
    if (parent.level >= MAX_DEPT_LEVEL) {
      alert(`部门科目最多 ${MAX_DEPT_LEVEL} 级，当前节点不能新增下级。`);
      return;
    }
    if (mappings.some((m) => m.dept_code === parent.dept_code)) {
      alert("当前部门科目已挂接产品科目，不能再新增下级部门科目。");
      return;
    }
    const defaultCode = nextChildDeptCode(parent.dept_code, parent.children) ?? `${parent.dept_code}1`;
    setNewRootDraft(null);
    setEditingDept(null);
    setExpanded((prev) => ({ ...prev, [parent.dept_code]: true }));
    setNewChildDraft({
      code: defaultCode,
      name: "",
      parentCode: parent.dept_code,
      level: parent.level + 1,
    });
  };

  const startEditDept = (node: TreeNode) => {
    setNewRootDraft(null);
    setNewChildDraft(null);
    setEditingDept({
      originalCode: node.dept_code,
      code: node.dept_code,
      name: node.dept_name,
      parentCode: node.parent_code,
      level: node.level,
    });
  };

  const saveNewDept = async (draft: NewDeptDraft) => {
    const error = validateDraft(draft);
    if (error) {
      alert(error);
      return false;
    }
    try {
      await apiPost<DeptAccountDto>("/api/dept-accounts", {
        dept_code: draft.code.trim().toUpperCase(),
        dept_name: draft.name.trim(),
        parent_code: draft.parentCode,
        level: draft.level,
        is_leaf: false,
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
    const node = depts.find((d) => d.dept_code === originalCode);
    if (!node) {
      alert("未找到当前部门科目，请刷新后重试。");
      return false;
    }
    const hasChildDept = depts.some((d) => d.parent_code === originalCode);
    try {
      if (nextCode === originalCode) {
        await apiPatch<DeptAccountDto>(`/api/dept-accounts/${originalCode}`, { dept_name: nextName });
      } else {
        if (hasChildDept) {
          alert("存在下级部门科目时，不允许修改当前部门科目代码。");
          return false;
        }
        await apiPost<DeptAccountDto>("/api/dept-accounts", {
          dept_code: nextCode,
          dept_name: nextName,
          parent_code: node.parent_code,
          level: node.level,
          is_leaf: node.is_leaf,
        });
        const oldMappings = mappings.filter((m) => m.dept_code === originalCode);
        for (const mapping of oldMappings) {
          await apiPost<DeptProductMappingDto>("/api/dept-product-mappings", {
            dept_code: nextCode,
            product_code: mapping.product_code,
          });
          await apiDelete(`/api/dept-product-mappings/${encodeURIComponent(mapping.dept_code)}/${encodeURIComponent(mapping.product_code)}`);
        }
        await apiDelete(`/api/dept-accounts/${encodeURIComponent(originalCode)}`);
      }
      resetEditorState();
      await reload();
      return true;
    } catch (e) {
      alert(e instanceof Error ? e.message : "更新失败");
      return false;
    }
  };

  const deleteDept = async (node: TreeNode) => {
    if (!confirm(`确认删除部门科目 ${node.dept_code} 吗？`)) return;
    try {
      await apiDelete(`/api/dept-accounts/${node.dept_code}`);
      setSelectedDeptCode((prev) => (prev === node.dept_code ? null : prev));
      await reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
  };

  const addMapping = async (deptCode: string, productCode: string) => {
    const node = depts.find((d) => d.dept_code === deptCode);
    if (!node) return;
    const hasChildDept = depts.some((d) => d.parent_code === deptCode);
    if (hasChildDept) {
      alert("该部门科目已有下级部门科目，不能再挂接产品科目。");
      return;
    }
    if (mappedSet.has(`${deptCode}__${productCode}`)) {
      alert("该产品科目已挂接到当前部门。");
      return;
    }
    const mappedDept = mappedDeptByProduct.get(productCode);
    if (mappedDept && mappedDept !== deptCode) {
      alert(`该产品科目已映射到部门 ${mappedDept}，不能重复映射到其他部门。`);
      return;
    }
    try {
      await apiPost<DeptProductMappingDto>("/api/dept-product-mappings", { dept_code: deptCode, product_code: productCode });
      await reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "映射失败");
    }
  };

  const removeMapping = async (deptCode: string, productCode: string, askConfirm = true) => {
    if (askConfirm && !confirm(`确认解除映射 ${deptCode} -> ${productCode} 吗？`)) return;
    try {
      await apiDelete(`/api/dept-product-mappings/${deptCode}/${productCode}`);
      setSelectedMapping((prev) => (prev?.deptCode === deptCode && prev?.productCode === productCode ? null : prev));
      await reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "解除映射失败");
    }
  };

  const handleSaveAndRefresh = async () => {
    try {
      resetEditorState();
      setContextMenu(null);
      setSelectedDeptCode(null);
      setSelectedMapping(null);
      await reload({ collapseAll: true });
      alert("已从数据库刷新部门科目体系。");
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
      const resp = await fetch(buildApiUrl("/api/dept-tree/export"));
      if (!resp.ok) throw new Error((await resp.text()) || "导出失败");
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") ?? "";
      const fnMatch = cd.match(/filename="?([^"]+)"?/i);
      const fileName = fnMatch?.[1] || "dept_tree_export.xlsx";
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
    if (selectedDeptCode) {
      setExpanded((prev) => ({ ...prev, [selectedDeptCode]: false }));
      return;
    }
    setExpanded((prev) => {
      const next = { ...prev };
      depts.forEach((d) => {
        if (d.level === 1) next[d.dept_code] = false;
      });
      return next;
    });
  };

  const expandNextLevelOnly = () => {
    if (selectedDeptCode) {
      setExpanded((prev) => ({ ...prev, [selectedDeptCode]: true }));
      return;
    }
    setExpanded((prev) => {
      const next = { ...prev };
      depts.forEach((d) => {
        if (d.level === 1) next[d.dept_code] = true;
      });
      return next;
    });
  };

  const collapseAllFromCurrentLevel = () => {
    const selectedLevel = selectedDeptCode
      ? (depts.find((d) => d.dept_code === selectedDeptCode)?.level ?? 1)
      : 1;
    setExpanded((prev) => {
      const next = { ...prev };
      depts.forEach((d) => {
        if (d.level === selectedLevel) next[d.dept_code] = false;
      });
      return next;
    });
  };

  const expandAllFromCurrentLevel = () => {
    if (selectedDeptCode) {
      const selectedNode = findTreeNodeByCode(tree, selectedDeptCode);
      if (!selectedNode) return;
      const codes: string[] = [];
      const collect = (node: TreeNode) => {
        codes.push(node.dept_code);
        node.children.forEach(collect);
      };
      collect(selectedNode);
      setExpanded((prev) => {
        const next = { ...prev };
        codes.forEach((c) => {
          next[c] = true;
        });
        return next;
      });
      return;
    }
    const next: Record<string, boolean> = {};
    depts.forEach((d) => {
      next[d.dept_code] = true;
    });
    setExpanded(next);
  };

  /** 收起整棵树中所有部门节点（含多级与映射区）；与当前选中项无关。 */
  const collapseFullDeptTree = () => {
    setDeptSearchInput("");
    setDeptSearch("");
    const next: Record<string, boolean> = {};
    depts.forEach((d) => {
      next[d.dept_code] = false;
    });
    setExpanded(next);
  };

  /** 展开整棵树至最底层（所有部门节点均展开）。 */
  const expandFullDeptTree = () => {
    const next: Record<string, boolean> = {};
    depts.forEach((d) => {
      next[d.dept_code] = true;
    });
    setExpanded(next);
  };

  const collapseEntireTree = () => collapseFullDeptTree();
  const expandEntireTree = () => expandFullDeptTree();
  const toggleDeptExpanded = (deptCode: string) => {
    setExpanded((prev) => ({ ...prev, [deptCode]: !(prev[deptCode] ?? false) }));
  };

  const handleDropToUnmap = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData("mappedProductNode");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as { deptCode?: string; productCode?: string };
      if (!parsed.deptCode || !parsed.productCode) return;
      await removeMapping(parsed.deptCode, parsed.productCode, false);
    } catch {
      // ignore malformed payload
    }
  };

  const renderNode = (n: TreeNode): JSX.Element => {
    const isOpen = expanded[n.dept_code] ?? false;
    const mapped = mappings.filter((m) => m.dept_code === n.dept_code);
    const hasChildDept = n.children.length > 0;
    const hasExpandableChildren = hasChildDept || mapped.length > 0;
    const canAcceptDrop = !hasChildDept;
    const isSelected = selectedDeptCode === n.dept_code;
    const isDragTarget = dragTargetDeptCode === n.dept_code;
    const isEditing = editingDept?.originalCode === n.dept_code;
    return (
      <div key={n.dept_code}>
        <div
          className={`relative flex items-center gap-1 px-2 py-1 pb-1.5 border-b border-gray-100 group ${isDragTarget ? "bg-blue-200" : isSelected ? "bg-blue-100" : "hover:bg-gray-50"}`}
          style={{
            paddingLeft: `${(n.level - 1) * TREE_INDENT + 8}px`,
            ...rowStyle(`dept-${n.dept_code}`),
          }}
          onClick={() => setSelectedDeptCode(n.dept_code)}
          onContextMenu={(e) => {
            e.preventDefault();
            setSelectedDeptCode(n.dept_code);
            const hasMapped = mapped.length > 0;
            setContextMenu({
              x: e.clientX,
              y: e.clientY,
              node: {
                type: "dept",
                deptCode: n.dept_code,
                deptName: n.dept_name,
                level: n.level,
                hasExpandableChildren: hasChildDept || hasMapped,
                isOpen,
                canAddChild: n.level < MAX_DEPT_LEVEL && !hasMapped,
              },
            });
          }}
          onDragOver={(e) => {
            if (!canAcceptDrop) return;
            e.preventDefault();
            setDragTargetDeptCode(n.dept_code);
          }}
          onDragEnter={(e) => {
            if (!canAcceptDrop) return;
            e.preventDefault();
            setDragTargetDeptCode(n.dept_code);
          }}
          onDrop={(e) => {
            if (!canAcceptDrop) return;
            e.preventDefault();
            setDragTargetDeptCode(null);
            const code = e.dataTransfer.getData("productCode");
            if (code) void addMapping(n.dept_code, code);
          }}
        >
          {hasExpandableChildren ? (
            <button className="p-0.5 hover:bg-gray-200 rounded" onClick={() => toggleDeptExpanded(n.dept_code)}>
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
            <span className="w-24 font-mono text-xs text-gray-700" onDoubleClick={() => startEditDept(n)}>
              {n.dept_code}
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
            <span className="text-xs text-gray-700 flex-1" onDoubleClick={() => startEditDept(n)}>
              {n.dept_name}
            </span>
          )}
          <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => startNewChildDraft(n)} title="新增下级">
            <Plus className="w-3 h-3" />
          </button>
          <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => startEditDept(n)} title="编辑">
            <Edit className="w-3 h-3" />
          </button>
          <button className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => void deleteDept(n)} title="删除">
            <Trash2 className="w-3 h-3 text-red-600" />
          </button>
          <TableRowResizeHandle
            onResizeStart={(e) =>
              beginResize(`dept-${n.dept_code}`, e, () => (e.currentTarget as HTMLElement).parentElement)
            }
          />
        </div>
        {isOpen &&
          mapped.map((m) => {
            const p = productMap.get(m.product_code);
            const isSelectedMapping = selectedMapping?.deptCode === m.dept_code && selectedMapping?.productCode === m.product_code;
            return (
              <div
                key={`${m.dept_code}-${m.product_code}`}
                draggable
                onContextMenu={(e) => {
                  e.preventDefault();
                  setSelectedMapping({
                    deptCode: m.dept_code,
                    productCode: m.product_code,
                    name: p?.product_name ?? "",
                  });
                  setContextMenu({
                    x: e.clientX,
                    y: e.clientY,
                    node: {
                      type: "mapping",
                      deptCode: m.dept_code,
                      productCode: m.product_code,
                      productName: p?.product_name ?? "",
                    },
                  });
                }}
                onDragStart={(e) => {
                  e.dataTransfer.setData("mappedProductNode", JSON.stringify({ deptCode: m.dept_code, productCode: m.product_code }));
                }}
                className={`relative flex items-center gap-2 px-2 py-1 pb-1.5 text-xs border-b border-gray-100 ${isSelectedMapping ? "bg-amber-100" : "bg-amber-50 hover:bg-amber-100"} cursor-move`}
                style={{
                  paddingLeft: `${(n.level + 1) * TREE_INDENT + 8}px`,
                  ...rowStyle(`map-${m.dept_code}-${m.product_code}`),
                }}
                onClick={() =>
                  setSelectedMapping({
                    deptCode: m.dept_code,
                    productCode: m.product_code,
                    name: p?.product_name ?? "",
                  })
                }
              >
                <DatabaseIcon className="w-3 h-3 text-green-600 flex-shrink-0" />
                <span className="w-24 font-mono">{m.product_code}</span>
                <span className="flex-1 truncate">{p?.product_name ?? "（已删除产品）"}</span>
                <button className="p-1 hover:bg-gray-200 rounded" onClick={() => void removeMapping(m.dept_code, m.product_code, true)} title="解除映射">
                  <Trash2 className="w-3 h-3 text-red-600" />
                </button>
                <TableRowResizeHandle
                  onResizeStart={(e) =>
                    beginResize(`map-${m.dept_code}-${m.product_code}`, e, () => (e.currentTarget as HTMLElement).parentElement)
                  }
                />
              </div>
            );
          })}
        {isOpen && newChildDraft?.parentCode === n.dept_code && (
          <div className="flex items-center gap-2 px-2 py-1 border-b border-gray-100 bg-yellow-50" style={{ paddingLeft: `${(n.level + 1) * TREE_INDENT + 8}px` }}>
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
              placeholder="下级部门科目名称"
            />
            <button className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]" onClick={() => void saveNewDept(newChildDraft)}>
              保存
            </button>
            <button className="px-2 py-0.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300" onClick={() => setNewChildDraft(null)}>
              取消
            </button>
          </div>
        )}
        {isOpen && n.children.map((c) => renderNode(c))}
      </div>
    );
  };

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-medium text-gray-800">部门科目维护</h3>
      </div>
      <div
        className="grid gap-3 flex-1 min-h-0"
        style={{ gridTemplateColumns: "minmax(0, calc(60% + 1.5cm)) minmax(320px, calc(40% - 1.5cm))" }}
      >
        <div className="border border-gray-300 rounded overflow-hidden bg-white flex flex-col">
          <div className="px-3 py-2 bg-gray-100 border-b border-gray-300">
            <div className="flex items-center gap-2 mb-2">
            <div className="relative w-56">
              <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                value={deptSearchInput}
                onChange={(e) => {
                  setDeptSearchInput(e.target.value);
                  setDeptSearch(e.target.value);
                }}
                onKeyDown={(e) => e.key === "Enter" && setDeptSearch(deptSearchInput)}
                placeholder="搜索部门科目..."
                className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-full focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {deptSearchInput && (
                <button
                  type="button"
                  onClick={() => {
                    setDeptSearchInput("");
                    setDeptSearch("");
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
                  title="清除搜索"
                >
                  <X className="w-3.5 h-3.5 text-gray-500" />
                </button>
              )}
            </div>
            <button onClick={() => setDeptSearch(deptSearchInput)} className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50">
              搜索
            </button>
              <div className="flex-1" />
              <button className="px-3 py-1 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9] flex items-center gap-1" onClick={startNewRootDraft}>
                <Plus className="w-3 h-3" />
                增加1级部门科目
              </button>
              <button
                className="px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954] flex items-center gap-1"
                onClick={() => setShowExcelDialog(true)}
              >
                <Upload className="w-3 h-3" />
                Excel上传科目
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
                <button
                  type="button"
                  title="收起当前选中的部门节点；未选中时收起所有一级根部门"
                  onClick={collapseCurrentLevelOnly}
                  className={treeToolbarButtonClass}
                >
                  <Minimize2 className="w-3 h-3" />
                  <span>收起本级</span>
                </button>
                <button
                  type="button"
                  title="展开当前选中的部门；未选中时展开所有一级根部门"
                  onClick={expandNextLevelOnly}
                  className={treeToolbarButtonClass}
                >
                  <Maximize2 className="w-3 h-3" />
                  <span>展开下级</span>
                </button>
                <button
                  type="button"
                  title="收起当前层级下所有同级部门；未选中时收起全部一级根部门"
                  onClick={collapseAllFromCurrentLevel}
                  className={treeToolbarButtonClass}
                >
                  <ChevronsUp className="w-3 h-3" />
                  <span>收起全部本级</span>
                </button>
                <button
                  type="button"
                  title="选中部门时展开其下全部子部门；未选中时展开整棵树"
                  onClick={expandAllFromCurrentLevel}
                  className={treeToolbarButtonClass}
                >
                  <ChevronsDown className="w-3 h-3" />
                  <span>展开全部下级</span>
                </button>
                <button
                  type="button"
                  title="清空搜索并收起整棵树中所有部门节点（与当前选中项无关）"
                  onClick={collapseEntireTree}
                  className={treeToolbarButtonClass}
                >
                  <Minimize2 className="w-3 h-3" />
                  <span>全部收起</span>
                </button>
                <button
                  type="button"
                  title="从一级部门起展开全部层级，直至最底层产品映射均可见"
                  onClick={expandEntireTree}
                  className={treeToolbarButtonClass}
                >
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
                <input
                  value={newRootDraft.code}
                  onChange={(e) => setNewRootDraft({ ...newRootDraft, code: e.target.value.toUpperCase() })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void saveNewDept(newRootDraft);
                    }
                  }}
                  className="w-24 px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
                  placeholder="1级代码"
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
                  className="flex-1 px-1 py-0.5 text-xs border border-blue-400 rounded"
                  placeholder="1级部门科目名称"
                />
                <button className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]" onClick={() => void saveNewDept(newRootDraft)}>
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
        <div className="border border-gray-300 rounded overflow-hidden bg-white flex flex-col">
          <div className="px-3 py-2 bg-gray-100 border-b border-gray-300">
            <div className="flex items-center gap-2">
              <h4 className="text-xs font-medium text-gray-800">产品科目列表</h4>
              <div className="flex-1" />
              <div className="relative w-44">
                <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  value={productSearchInput}
                  onChange={(e) => {
                    setProductSearchInput(e.target.value);
                    setProductSearch(e.target.value);
                  }}
                  onKeyDown={(e) => e.key === "Enter" && setProductSearch(productSearchInput)}
                  placeholder="搜索产品科目..."
                  className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-full focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                {productSearchInput && (
                  <button
                    type="button"
                    onClick={() => {
                      setProductSearchInput("");
                      setProductSearch("");
                    }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
                    title="清除搜索"
                  >
                    <X className="w-3.5 h-3.5 text-gray-500" />
                  </button>
                )}
              </div>
              <button onClick={() => setProductSearch(productSearchInput)} className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50">
                搜索
              </button>
            </div>
            <p className="text-[10px] text-gray-500 mt-0.5">拖拽到左侧部门科目增添映射，从左侧拖回产品科目将删除映射</p>
            {selectedMapping && (
              <div className="mt-1.5 flex items-center gap-2 text-[11px] text-gray-700">
                <span className="flex-1 truncate">
                  当前选中：{selectedMapping.deptCode} {"->"} {selectedMapping.productCode} {selectedMapping.name}
                </span>
                <button
                  className="px-2 py-0.5 text-[11px] bg-red-600 text-white rounded hover:bg-red-700"
                  onClick={() => void removeMapping(selectedMapping.deptCode, selectedMapping.productCode, true)}
                >
                  删除
                </button>
              </div>
            )}
          </div>
          <div
            className="flex-1 overflow-auto"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              void handleDropToUnmap(e);
            }}
          >
            {filteredProducts.map((p) => (
              <div
                key={p.product_code}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("productCode", p.product_code);
                }}
                onDragEnd={() => setDragTargetDeptCode(null)}
                className="px-3 py-1.5 text-xs border-b border-gray-100 hover:bg-blue-50 cursor-move flex items-center gap-2"
              >
                <DatabaseIcon className="w-3 h-3 text-green-600 flex-shrink-0" />
                <span className="w-20 font-mono">{p.product_code}</span>
                <span className="flex-1 truncate">{p.product_name}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[180px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {contextMenu.node.type === "dept" && (
            <>
              <button
                onClick={() => {
                  const current = depts.find((d) => d.dept_code === contextMenu.node.deptCode);
                  if (current) {
                    const treeNode: TreeNode = { ...current, children: [] };
                    startEditDept(treeNode);
                  }
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
                    const node = findTreeNodeByCode(tree, contextMenu.node.deptCode);
                    if (node) startNewChildDraft(node);
                    setContextMenu(null);
                  }}
                  className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
                >
                  <Plus className="w-3 h-3" />
                  增加下级部门科目
                </button>
              )}
              {contextMenu.node.hasExpandableChildren && (
                <button
                  onClick={() => {
                    toggleDeptExpanded(contextMenu.node.deptCode);
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
                  const node = findTreeNodeByCode(tree, contextMenu.node.deptCode);
                  if (node) void deleteDept(node);
                  setContextMenu(null);
                }}
                className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 text-red-600 flex items-center gap-2"
              >
                <Trash2 className="w-3 h-3" />
                删除本部门科目
              </button>
            </>
          )}
          {contextMenu.node.type === "mapping" && (
            <button
              onClick={() => {
                void removeMapping(contextMenu.node.deptCode, contextMenu.node.productCode, true);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 text-red-600 flex items-center gap-2"
            >
              <Trash2 className="w-3 h-3" />
              删除本产品映射
            </button>
          )}
        </div>
      )}
      <ExcelUploadDialog
        isOpen={showExcelDialog}
        onClose={() => setShowExcelDialog(false)}
        title="部门科目维护"
        fields={deptExcelFields}
        templateName="dept_acct_temp"
        previewEndpoint="/api/dept-accounts/import-preview"
        importEndpoint="/api/dept-accounts/import-apply"
        onImportComplete={() => void reload()}
      />
    </div>
  );
}

function findTreeNodeByCode(nodes: TreeNode[], code: string): TreeNode | null {
  for (const node of nodes) {
    if (node.dept_code === code) return node;
    const child = findTreeNodeByCode(node.children, code);
    if (child) return child;
  }
  return null;
}
