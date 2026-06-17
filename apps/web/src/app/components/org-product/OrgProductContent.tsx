import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  BadgePlus,
  Building,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  Edit3,
  Loader2,
  Package2,
  RefreshCw,
  RotateCcw,
  Save,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import {
  buildOrgExpandedState,
  childTypeForParent,
  cloneDefaultOrgProductTree,
  collectOrgNodes,
  DEFAULT_ORG_PRODUCT_TREE,
  findOrgNodeById,
  findOrgNodePath,
  orgLevelBadgeClass,
  orgLevelLabel,
  prepareOrgProductTreeFromStorage,
  type OrgProductNode,
  type OrgProductNodeType,
} from "@/lib/org-product/orgProductTree";
import {
  getOrgProductTreeSnapshot,
  importOrgProductTreeExcel,
  exportOrgProductTreeExcel,
  saveRefreshOrgProductTree,
} from "@/lib/org-product/orgProductTreeApi";

type NodeDraft = {
  code: string;
  name: string;
};

type CreateDraft = {
  parentId: string;
  parentName: string;
  nodeType: OrgProductNodeType;
  code: string;
  name: string;
};

/** 工具栏按钮：按下缩放、悬停阴影，加载时显示处理中样式 */
function toolbarButtonClass(
  variant: "primary" | "secondary" | "neutral" | "danger",
  opts?: { compact?: boolean; loading?: boolean }
): string {
  const compact = opts?.compact ? "px-2.5 py-1 text-[11px]" : "px-3 py-1.5 text-xs";
  const base =
    `inline-flex items-center gap-1.5 rounded-md font-medium shadow-sm transition-all duration-100 select-none cursor-pointer ` +
    `hover:shadow-md active:scale-[0.97] active:shadow-inner focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 ` +
    `disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none disabled:active:scale-100`;
  const loading = opts?.loading ? " opacity-90 ring-2 ring-offset-1 ring-white/40" : "";
  if (variant === "primary") {
    return `${base} ${compact} bg-gradient-to-r from-sky-500 to-blue-600 text-white hover:from-sky-600 hover:to-blue-700 focus-visible:ring-sky-400${loading}`;
  }
  if (variant === "secondary") {
    return `${base} ${compact} bg-gradient-to-r from-emerald-500 to-teal-600 text-white hover:from-emerald-600 hover:to-teal-700 focus-visible:ring-emerald-400${loading}`;
  }
  if (variant === "danger") {
    return `${base} ${compact} bg-gradient-to-r from-rose-500 to-red-600 text-white hover:from-rose-600 hover:to-red-700 focus-visible:ring-rose-400${loading}`;
  }
  return `${base} ${compact} border border-gray-300 bg-white text-gray-700 hover:border-gray-400 hover:bg-gray-50 focus-visible:ring-gray-300${loading}`;
}

const primaryActionClass = toolbarButtonClass("primary");
const secondaryActionClass = toolbarButtonClass("secondary");
const neutralActionClass = toolbarButtonClass("neutral");
const dangerActionClass = toolbarButtonClass("danger");

/**
 * 表头与数据行共用列宽（展开 | 图标 | 代码 | 名称 | 层级 | 统计 | 操作），保证左对齐一致。
 * 表头采用靠左 + 略深底纹，与 Excel 列表习惯一致（非居中）。
 */
const ORG_TREE_ROW_GRID =
  "grid grid-cols-[1rem_0.875rem_10rem_minmax(10rem,1fr)_3.25rem_4rem_1.75rem] items-center gap-x-2";
const ORG_TREE_ROW_BASE_PL = 12;
const ORG_TREE_ROW_LEVEL_INDENT = 20;
const ORG_TREE_HEADER_CELL = "truncate text-left text-xs font-medium leading-snug text-slate-600";
const ORG_TREE_CODE_CELL = "truncate text-left font-mono text-xs tabular-nums text-gray-800";
const ORG_TREE_NAME_CELL = "min-w-0 truncate text-left text-xs text-gray-800";

function updateNodeById(
  node: OrgProductNode,
  id: string,
  updater: (current: OrgProductNode) => OrgProductNode
): OrgProductNode {
  if (node.id === id) return updater(node);
  return {
    ...node,
    children: node.children.map((child) => updateNodeById(child, id, updater)),
  };
}

function addChildToNode(node: OrgProductNode, parentId: string, child: OrgProductNode): OrgProductNode {
  if (node.id === parentId) {
    return { ...node, children: [...node.children, child] };
  }
  return {
    ...node,
    children: node.children.map((item) => addChildToNode(item, parentId, child)),
  };
}

function deleteNodeById(node: OrgProductNode, id: string): OrgProductNode {
  return {
    ...node,
    children: node.children
      .filter((child) => child.id !== id)
      .map((child) => deleteNodeById(child, id)),
  };
}

function countByType(nodes: OrgProductNode[], type: OrgProductNodeType): number {
  return nodes.filter((node) => node.type === type).length;
}

function childCountLabel(node: OrgProductNode): string {
  if (!node.children.length) return "";
  if (node.type === "level0") return `${node.children.length}个一级主体`;
  if (node.type === "level1") return `${node.children.length}个二级机构`;
  if (node.type === "level2") return `${node.children.length}个三级产品`;
  return "";
}

function generateNodeId(): string {
  return `node-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function nextOrgCode(children: OrgProductNode[]): string {
  const used = new Set(children.map((child) => child.code.toUpperCase()));
  for (let i = 65; i <= 90; i += 1) {
    const candidate = String.fromCharCode(i);
    if (!used.has(candidate)) return candidate;
  }
  return `ORG${children.length + 1}`;
}

function nextProductCode(parentCode: string, children: OrgProductNode[]): string {
  const suffixNumbers = children
    .map((child) => {
      const suffix = child.code.slice(parentCode.length);
      const parsed = Number.parseInt(suffix, 10);
      return Number.isFinite(parsed) ? parsed : null;
    })
    .filter((value): value is number => value !== null);
  const next = (suffixNumbers.length ? Math.max(...suffixNumbers) : 0) + 1;
  return `${parentCode}${String(next).padStart(2, "0")}`;
}

function collectAllCodes(node: OrgProductNode, excludeId?: string): string[] {
  return collectOrgNodes(node)
    .filter((item) => item.id !== excludeId)
    .map((item) => item.code.trim().toUpperCase());
}

function filterOrgTree(node: OrgProductNode, query: string): OrgProductNode | null {
  const keywords = query
    .toLowerCase()
    .split(/[\s,，;；/\\]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (!keywords.length) return node;
  const text = `${node.code} ${node.name}`.toLowerCase();
  const selfHit = keywords.some((kw) => text.includes(kw));
  const kids = node.children
    .map((c) => filterOrgTree(c, query))
    .filter((c): c is OrgProductNode => Boolean(c));
  if (selfHit || kids.length) {
    return { ...node, children: kids };
  }
  return null;
}

export function OrgProductContent() {
  const userStorageKeyPrefix = useUserStorageKeyPrefix();
  const storageKey = `${userStorageKeyPrefix}::org-product-tree-v3`;
  const [tree, setTree] = useState<OrgProductNode>(() => cloneDefaultOrgProductTree());
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    buildOrgExpandedState(DEFAULT_ORG_PRODUCT_TREE)
  );
  const [selectedId, setSelectedId] = useState<string>(DEFAULT_ORG_PRODUCT_TREE.id);
  const [editDraft, setEditDraft] = useState<NodeDraft>({
    code: DEFAULT_ORG_PRODUCT_TREE.code,
    name: DEFAULT_ORG_PRODUCT_TREE.name,
  });
  const [createDraft, setCreateDraft] = useState<CreateDraft | null>(null);
  const [dirty, setDirty] = useState(false);
  const [savingRefresh, setSavingRefresh] = useState(false);
  const [importingExcel, setImportingExcel] = useState(false);
  const [exportingExcel, setExportingExcel] = useState(false);
  const [exportNotice, setExportNotice] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const [treeSearch, setTreeSearch] = useState("");
  const importExcelRef = useRef<HTMLInputElement>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const snap = await getOrgProductTreeSnapshot();
        if (cancelled) return;
        if (snap?.found && snap.tree) {
          const prepared = prepareOrgProductTreeFromStorage(snap.tree);
          setTree(prepared);
          setExpanded(buildOrgExpandedState(prepared));
          setSelectedId(prepared.id);
          setDirty(false);
          return;
        }
      } catch {
        // ignore
      }
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (!raw) return;
        const parsed = JSON.parse(raw) as unknown;
        const prepared = prepareOrgProductTreeFromStorage(parsed);
        setTree(prepared);
        setExpanded(buildOrgExpandedState(prepared));
        setSelectedId(prepared.id);
        setDirty(false);
      } catch {
        // ignore malformed local storage
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [storageKey]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDetailOpen(false);
    };
    if (!detailOpen) return;
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [detailOpen]);

  useEffect(() => {
    if (!exportNotice) return;
    const timer = window.setTimeout(() => setExportNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [exportNotice]);

  const allNodes = useMemo(() => collectOrgNodes(tree), [tree]);
  const selectedNode = useMemo(() => findOrgNodeById(tree, selectedId) ?? tree, [tree, selectedId]);
  const selectedPath = useMemo(() => findOrgNodePath(tree, selectedId), [tree, selectedId]);
  const visibleTree = useMemo(() => {
    const q = treeSearch.trim();
    if (!q) return tree;
    return filterOrgTree(tree, q);
  }, [tree, treeSearch]);
  const entityCount = useMemo(() => countByType(allNodes, "level1"), [allNodes]);
  const orgCount = useMemo(() => countByType(allNodes, "level2"), [allNodes]);
  const productCount = useMemo(() => countByType(allNodes, "level3"), [allNodes]);
  const isEditingDirty =
    editDraft.code.trim() !== selectedNode.code || editDraft.name.trim() !== selectedNode.name;
  const childType = childTypeForParent(selectedNode.type);
  const canAddChild = Boolean(childType);

  useEffect(() => {
    setEditDraft({ code: selectedNode.code, name: selectedNode.name });
  }, [selectedNode]);

  useEffect(() => {
    if (!findOrgNodeById(tree, selectedId)) {
      setSelectedId(tree.id);
    }
  }, [tree, selectedId]);

  const openCreateDraft = (node: OrgProductNode, options?: { openDetail?: boolean }) => {
    const nextType = childTypeForParent(node.type);
    if (!nextType) return;
    if (options?.openDetail !== false) setDetailOpen(true);
    setCreateDraft({
      parentId: node.id,
      parentName: node.name,
      nodeType: nextType,
      code:
        nextType === "level3"
          ? nextProductCode(node.code, node.children)
          : nextType === "level2"
            ? nextOrgCode(node.children)
            : "",
      name: "",
    });
  };

  const validateNodeDraft = (codeRaw: string, nameRaw: string, excludeId?: string): string | null => {
    const code = codeRaw.trim().toUpperCase();
    const name = nameRaw.trim();
    if (!code) return "代码不能为空。";
    if (!name) return "名称不能为空。";
    const usedCodes = new Set(collectAllCodes(tree, excludeId));
    if (usedCodes.has(code)) return `代码 ${code} 已存在，请修改。`;
    return null;
  };

  const handleSaveCurrent = () => {
    const nextCode = editDraft.code.trim().toUpperCase();
    const nextName = editDraft.name.trim();
    const error = validateNodeDraft(nextCode, nextName, selectedNode.id);
    if (error) {
      alert(error);
      return;
    }
    const oldCode = selectedNode.code;
    const nextTree = updateNodeById(tree, selectedNode.id, (current) => {
      const updatedChildren =
        current.type === "level2" && oldCode !== nextCode
          ? current.children.map((child) => ({
              ...child,
              code: child.code.startsWith(oldCode)
                ? `${nextCode}${child.code.slice(oldCode.length)}`
                : child.code,
            }))
          : current.children;
      return {
        ...current,
        code: nextCode,
        name: nextName,
        children: updatedChildren,
      };
    });
    const duplicateChildrenCodes = collectOrgNodes(nextTree)
      .map((node) => node.code.trim().toUpperCase())
      .filter((code, index, array) => array.indexOf(code) !== index);
    if (duplicateChildrenCodes.length > 0) {
      alert(`保存后出现重复代码：${duplicateChildrenCodes[0]}，请调整后再试。`);
      return;
    }
    setTree(nextTree);
    setDirty(true);
  };

  const handleCreateChild = () => {
    if (!createDraft) return;
    const nextCode = createDraft.code.trim().toUpperCase();
    const nextName = createDraft.name.trim();
    const error = validateNodeDraft(nextCode, nextName);
    if (error) {
      alert(error);
      return;
    }
    const newNode: OrgProductNode = {
      id: generateNodeId(),
      code: nextCode,
      name: nextName,
      type: createDraft.nodeType,
      children: [],
    };
    setTree((prev) => addChildToNode(prev, createDraft.parentId, newNode));
    setExpanded((prev) => ({ ...prev, [createDraft.parentId]: true }));
    setSelectedId(newNode.id);
    setCreateDraft(null);
    setDirty(true);
  };

  const handleDeleteCurrent = () => {
    if (selectedNode.type === "level0") {
      alert("集团根节点不支持删除。");
      return;
    }
    const confirmText =
      selectedNode.type === "level1"
        ? `确认删除一级主体 ${selectedNode.code} 吗？其下全部下级会一起删除。`
        : selectedNode.type === "level2"
          ? `确认删除二级机构 ${selectedNode.code} 吗？其下全部三级产品会一起删除。`
          : `确认删除三级产品 ${selectedNode.code} 吗？`;
    if (!confirm(confirmText)) return;
    const parentId = selectedPath[selectedPath.length - 2]?.id ?? tree.id;
    setTree((prev) => deleteNodeById(prev, selectedNode.id));
    setSelectedId(parentId);
    setCreateDraft(null);
    setDirty(true);
  };

  const triggerImportExcel = () => {
    importExcelRef.current?.click();
  };

  const handleImportExcel = async (file: File) => {
    if (!file.name.match(/\.(xlsx|xlsm|xls)$/i)) {
      alert("请选择Excel文件（.xlsx/.xlsm/.xls）。");
      return;
    }
    if (
      !window.confirm(
        `将使用文件「${file.name}」覆盖当前机构及产品树（尚未写入数据库，需再点「保存刷新」）。是否继续？`
      )
    ) {
      if (importExcelRef.current) importExcelRef.current.value = "";
      return;
    }
    if (importingExcel) return;
    setImportingExcel(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await importOrgProductTreeExcel(form);
      const prepared = prepareOrgProductTreeFromStorage(resp.tree);
      setTree(prepared);
      setExpanded(buildOrgExpandedState(prepared));
      setSelectedId(prepared.id);
      setCreateDraft(null);
      setDirty(true);
    } catch (e) {
      alert(e instanceof Error ? `Excel导入失败：${e.message}` : "Excel导入失败");
    } finally {
      setImportingExcel(false);
      if (importExcelRef.current) importExcelRef.current.value = "";
    }
  };

  const handleExpandAll = () => {
    setExpanded(buildOrgExpandedState(tree));
  };

  const handleCollapseAll = () => {
    setExpanded({ [tree.id]: true });
  };

  const handleExportExcel = async () => {
    if (exportingExcel) return;
    const nodeCount = allNodes.length;
    const dirtyHint = dirty
      ? "\n\n提示：当前有未保存修改，将导出页面上的最新机构树（与数据库可能不一致）。"
      : "";
    const proceed = window.confirm(
      `即将导出机构及产品树为 Excel（共 ${nodeCount} 个节点）。\n\n文件将保存到浏览器默认下载位置（一般为「下载」文件夹）。${dirtyHint}\n\n是否继续导出？`
    );
    if (!proceed) return;

    setExportNotice(null);
    setExportingExcel(true);
    try {
      const { blob, filename } = await exportOrgProductTreeExcel(tree);
      const downloadName = filename || "机构及产品.xlsx";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = downloadName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setExportNotice({
        kind: "success",
        message: `已开始下载「${downloadName}」。若未看到文件，请查看浏览器下载栏或系统「下载」文件夹。`,
      });
    } catch (e) {
      setExportNotice({
        kind: "error",
        message: e instanceof Error ? e.message : "Excel 导出失败",
      });
    } finally {
      setExportingExcel(false);
    }
  };

  const handleSaveRefresh = async () => {
    if (savingRefresh) return;
    setSavingRefresh(true);
    try {
      await saveRefreshOrgProductTree(tree);
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(tree));
      } catch {
        // ignore
      }
      window.dispatchEvent(new Event("org-product-tree-saved"));
      setDirty(false);
      alert("保存刷新成功。");
    } catch (e) {
      alert(e instanceof Error ? `保存刷新失败：${e.message}` : "保存刷新失败");
    } finally {
      setSavingRefresh(false);
    }
  };

  const renderNode = (node: OrgProductNode, level = 0): JSX.Element => {
    const isOpen = expanded[node.id] ?? false;
    const isSelected = selectedId === node.id;
    const hasChildren = node.children.length > 0;
    const shouldShowChildren = isOpen;
    const Icon =
      node.type === "level0" || node.type === "level1"
        ? Building2
        : node.type === "level2"
          ? Building
          : Package2;
    const countLabel = childCountLabel(node);

    const rowPadLeft = level * ORG_TREE_ROW_LEVEL_INDENT + ORG_TREE_ROW_BASE_PL;

    return (
      <div key={node.id}>
        <div
          className={`${ORG_TREE_ROW_GRID} border-b border-gray-100 py-2 pr-3 ${
            isSelected ? "bg-blue-50 ring-1 ring-inset ring-blue-200" : "hover:bg-gray-50"
          }`}
          style={{ paddingLeft: `${rowPadLeft}px` }}
          onClick={() => setSelectedId(node.id)}
        >
          {hasChildren ? (
            <button
              type="button"
              className="flex h-4 w-4 items-center justify-center rounded p-0 hover:bg-gray-200"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded((prev) => ({ ...prev, [node.id]: !isOpen }));
              }}
            >
              {shouldShowChildren ? <ChevronDown className="h-3 w-3 text-gray-600" /> : <ChevronRight className="h-3 w-3 text-gray-600" />}
            </button>
          ) : (
            <span className="h-4 w-4" aria-hidden />
          )}
          <Icon className={`h-3.5 w-3.5 ${node.type === "level3" ? "text-amber-600" : "text-blue-600"}`} />
          <span className={ORG_TREE_CODE_CELL}>{node.code}</span>
          <span className={ORG_TREE_NAME_CELL}>{node.name.trim()}</span>
          <span className={`justify-self-start rounded-full px-1.5 py-0.5 text-[10px] leading-none ${orgLevelBadgeClass(node.type)}`}>
            {orgLevelLabel(node.type)}
          </span>
          {countLabel ? (
            <span className="hidden truncate text-left text-[10px] text-gray-500 xl:block">{countLabel}</span>
          ) : (
            <span className="hidden xl:block" aria-hidden />
          )}
          <button
            type="button"
            className="flex h-6 w-7 items-center justify-center justify-self-end rounded border border-gray-200 bg-white text-gray-600 shadow-sm transition hover:bg-gray-50"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedId(node.id);
              setDetailOpen(true);
            }}
            aria-label="维护详情"
            title="维护详情"
          >
            <Edit3 className="h-3.5 w-3.5" />
          </button>
        </div>
        {hasChildren && shouldShowChildren ? node.children.map((child) => renderNode(child, level + 1)) : null}
      </div>
    );
  };

  const renderTreeColumnHeader = () => (
    <div
      className={`sticky top-0 z-20 ${ORG_TREE_ROW_GRID} border-b border-slate-200 bg-slate-50/95 py-2 pr-3 shadow-[0_1px_0_0_rgba(15,23,42,0.08)] backdrop-blur-[1px]`}
      style={{ paddingLeft: `${ORG_TREE_ROW_BASE_PL}px` }}
    >
      <span className="h-4 w-4" aria-hidden />
      <span className="h-3.5 w-3.5" aria-hidden />
      <span className={ORG_TREE_HEADER_CELL}>机构及产品代码</span>
      <span className={ORG_TREE_HEADER_CELL}>机构及产品名称</span>
      <span className="hidden xl:block" aria-hidden />
      <span className="hidden xl:block" aria-hidden />
      <span aria-hidden />
    </div>
  );

  const relationText =
    selectedNode.type === "level0"
      ? `${selectedNode.name}为集团根节点，下辖 ${selectedNode.children.length} 个一级主体（如 AA、AB）。`
      : selectedNode.type === "level1"
        ? `${selectedNode.name}为一级主体，下辖 ${selectedNode.children.length} 个二级机构。`
        : selectedNode.type === "level2"
          ? `${selectedNode.name}为二级机构，下辖 ${selectedNode.children.length} 个三级产品。`
          : `${selectedNode.name}为三级产品，归属于 ${selectedPath[selectedPath.length - 2]?.name ?? "所属机构"}。`;

  return (
    <div className="flex h-full flex-col bg-slate-50 p-3">
      <input
        ref={importExcelRef}
        type="file"
        accept=".xlsx,.xlsm,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleImportExcel(file);
        }}
      />

      <div
        className="grid min-h-0 flex-1 gap-3"
        style={{ gridTemplateColumns: "minmax(0, 1fr)" }}
      >
        <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 space-y-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-600">
              <span>
                一级主体 <strong className="text-gray-800">{entityCount}</strong>
              </span>
              <span>
                二级机构 <strong className="text-gray-800">{orgCount}</strong>
              </span>
              <span>
                三级产品 <strong className="text-gray-800">{productCount}</strong>
              </span>
              {dirty ? <span className="text-amber-700">· 有未保存修改</span> : null}
            </div>
            <input
              value={treeSearch}
              onChange={(e) => setTreeSearch(e.target.value)}
              placeholder="搜索代码或名称..."
              className="w-full max-w-md rounded border border-gray-300 px-2 py-1 text-[11px] focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => canAddChild && openCreateDraft(selectedNode, { openDetail: true })}
                className={toolbarButtonClass("primary", { compact: true })}
                disabled={!canAddChild}
                title={
                  canAddChild && childType
                    ? `在「${orgLevelLabel(selectedNode.type)}」下新增「${orgLevelLabel(childType)}」`
                    : "三级产品不能再新增下级"
                }
              >
                <BadgePlus className="h-3 w-3 shrink-0" />
                <span className="whitespace-nowrap">新增下级</span>
              </button>
              <button
                type="button"
                onClick={handleDeleteCurrent}
                className={toolbarButtonClass("danger", { compact: true })}
                disabled={selectedNode.type === "level0"}
                title={selectedNode.type === "level0" ? "集团根节点不可删除" : "删除当前节点及其全部下级"}
              >
                <Trash2 className="h-3 w-3 shrink-0" />
                <span className="whitespace-nowrap">删除当前节点</span>
              </button>
              <button
                type="button"
                onClick={triggerImportExcel}
                className={toolbarButtonClass("neutral", { compact: true, loading: importingExcel })}
                disabled={importingExcel}
                title="选择本机 Excel 导入（表头：层级、机构及产品代码、机构及产品名称）"
              >
                <Download className="h-3 w-3 shrink-0" />
                <span className="whitespace-nowrap">{importingExcel ? "导入中…" : "Excel导入"}</span>
              </button>
              <button
                type="button"
                onClick={() => void handleExportExcel()}
                className={toolbarButtonClass("neutral", { compact: true, loading: exportingExcel })}
                disabled={exportingExcel}
                title="将当前机构树导出为 Excel 并下载"
              >
                {exportingExcel ? (
                  <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                ) : (
                  <Upload className="h-3 w-3 shrink-0" />
                )}
                <span className="whitespace-nowrap">{exportingExcel ? "正在生成…" : "Excel导出"}</span>
              </button>
              <button
                type="button"
                onClick={() => void handleSaveRefresh()}
                className={toolbarButtonClass("neutral", { compact: true, loading: savingRefresh })}
                disabled={savingRefresh || !dirty}
                title={dirty ? "将当前树写入数据库并通知其他模块" : "暂无修改，无需保存"}
              >
                <RefreshCw className={`h-3 w-3 shrink-0 ${savingRefresh ? "animate-spin" : ""}`} />
                <span className="whitespace-nowrap">{savingRefresh ? "保存中…" : "保存刷新"}</span>
              </button>
              <button
                type="button"
                onClick={handleExpandAll}
                className={toolbarButtonClass("neutral", { compact: true })}
              >
                全部展开
              </button>
              <button
                type="button"
                onClick={handleCollapseAll}
                className={toolbarButtonClass("neutral", { compact: true })}
              >
                折叠下级
              </button>
            </div>
            {exportNotice ? (
              <div
                className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs ${
                  exportNotice.kind === "success"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                    : "border-rose-200 bg-rose-50 text-rose-900"
                }`}
                role="status"
              >
                {exportNotice.kind === "success" ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                ) : (
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
                )}
                <p className="min-w-0 flex-1 leading-relaxed">{exportNotice.message}</p>
                <button
                  type="button"
                  className="shrink-0 rounded p-0.5 opacity-70 hover:bg-black/5 hover:opacity-100"
                  onClick={() => setExportNotice(null)}
                  aria-label="关闭提示"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : null}
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {renderTreeColumnHeader()}
            {visibleTree ? (
              renderNode(visibleTree)
            ) : (
              <div className="px-4 py-8 text-center text-xs text-gray-500">未找到匹配的机构或产品。</div>
            )}
          </div>
        </div>
      </div>

      {detailOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onMouseDown={(e) => {
            if (e.currentTarget === e.target) setDetailOpen(false);
          }}
        >
          <div className="flex w-full max-w-2xl max-h-[calc(100vh-48px)] flex-col overflow-hidden rounded-lg bg-white shadow-xl">
            <div className="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-3">
              <div className="text-sm font-medium text-gray-800">维护详情</div>
              <div className="flex-1" />
              <button
                type="button"
                onClick={() => setDetailOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded hover:bg-gray-200"
                aria-label="关闭"
                title="关闭"
              >
                <X className="h-4 w-4 text-gray-600" />
              </button>
            </div>
            <div className="min-h-0 flex-1 space-y-3 overflow-auto p-4">
              <div className="rounded border border-gray-200 bg-white p-3">
                <div className="mb-2 flex items-center gap-2">
                  <div className="text-sm font-medium text-gray-800">
                    {selectedNode.code} {selectedNode.name}
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] ${orgLevelBadgeClass(selectedNode.type)}`}>
                    {orgLevelLabel(selectedNode.type)}
                  </span>
                </div>
                <div className="text-xs leading-6 text-gray-600">
                  <div>汇总说明：{relationText}</div>
                  <div>直属下级：{selectedNode.children.length} 个</div>
                </div>
              </div>

              <div className="rounded border border-gray-200 bg-white p-3">
                <div className="mb-3 flex items-center gap-2 text-xs font-medium text-gray-800">
                  <Edit3 className="h-3.5 w-3.5 text-gray-600" />
                  <span>当前节点编辑</span>
                </div>
                <div className="space-y-3">
                  <div>
                    <div className="mb-1 text-[11px] text-gray-500">机构及产品代码</div>
                    <input
                      value={editDraft.code}
                      onChange={(e) => setEditDraft((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))}
                      className="w-full rounded border border-gray-300 px-3 py-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <div className="mb-1 text-[11px] text-gray-500">机构及产品名称</div>
                    <input
                      value={editDraft.name}
                      onChange={(e) => setEditDraft((prev) => ({ ...prev, name: e.target.value }))}
                      className="w-full rounded border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div className="rounded border border-dashed border-blue-200 bg-blue-50 px-3 py-2 text-[11px] leading-5 text-gray-600">
                    {selectedNode.type === "level2"
                      ? "提示：修改二级机构代码时，其下三级产品会按原前缀自动同步更新。"
                      : selectedNode.type === "level0"
                        ? "提示：集团根节点一般仅调整名称；结构批量变更请用 Excel 导入。"
                        : "提示：支持直接编辑代码和名称；保存刷新后会同步到数据库并通知指标、录入模块。"}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={handleSaveCurrent} className={primaryActionClass}>
                      <Save className="h-3.5 w-3.5" />
                      <span>保存当前节点</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditDraft({ code: selectedNode.code, name: selectedNode.name })}
                      className={neutralActionClass}
                      disabled={!isEditingDirty}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      <span>撤销编辑</span>
                    </button>
                    {selectedNode.type !== "level0" ? (
                      <button type="button" onClick={handleDeleteCurrent} className={dangerActionClass}>
                        <Trash2 className="h-3.5 w-3.5" />
                        <span>删除当前节点</span>
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="rounded border border-gray-200 bg-white p-3">
                <div className="mb-3 flex items-center gap-2 text-xs font-medium text-gray-800">
                  <BadgePlus className="h-3.5 w-3.5 text-gray-600" />
                  <span>新增下级节点</span>
                </div>
                {createDraft ? (
                  <div className="space-y-3">
                    <div className="rounded border border-dashed border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-gray-700">
                      正在为 {createDraft.parentName} 新增 {orgLevelLabel(createDraft.nodeType)} 节点。
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] text-gray-500">新节点代码</div>
                      <input
                        value={createDraft.code}
                        onChange={(e) => setCreateDraft((prev) => (prev ? { ...prev, code: e.target.value.toUpperCase() } : prev))}
                        className="w-full rounded border border-gray-300 px-3 py-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] text-gray-500">新节点名称</div>
                      <input
                        value={createDraft.name}
                        onChange={(e) => setCreateDraft((prev) => (prev ? { ...prev, name: e.target.value } : prev))}
                        className="w-full rounded border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" onClick={handleCreateChild} className={secondaryActionClass}>
                        <Save className="h-3.5 w-3.5" />
                        <span>保存新增节点</span>
                      </button>
                      <button type="button" onClick={() => setCreateDraft(null)} className={neutralActionClass}>
                        <X className="h-3.5 w-3.5" />
                        <span>取消新增</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="text-xs text-gray-600">
                      {canAddChild
                        ? `当前可在「${orgLevelLabel(selectedNode.type)}」下新增「${childType ? orgLevelLabel(childType) : ""}」。`
                        : "当前节点已是三级产品，不能再新增下级。"}
                    </div>
                    <button type="button" onClick={() => canAddChild && openCreateDraft(selectedNode)} className={secondaryActionClass} disabled={!canAddChild}>
                      <BadgePlus className="h-3.5 w-3.5" />
                      <span>新增下级</span>
                    </button>
                  </div>
                )}
              </div>

              <div className="rounded border border-gray-200 bg-white p-3">
                <div className="mb-2 text-xs font-medium text-gray-800">层级路径</div>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {selectedPath.map((node, index) => (
                    <div key={node.id} className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedId(node.id)}
                        className={`rounded border px-2 py-1 ${
                          node.id === selectedId ? "border-blue-300 bg-blue-50 text-blue-700" : "border-gray-200 bg-gray-50 text-gray-700"
                        }`}
                      >
                        {node.code} {node.name}
                      </button>
                      {index < selectedPath.length - 1 ? <ChevronRight className="h-3 w-3 text-gray-400" /> : null}
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded border border-dashed border-blue-200 bg-blue-50 p-3 text-xs leading-6 text-gray-700">
                <div className="font-medium text-blue-800">当前维护规则</div>
                <div>1. 集团（AAA）为根；一级主体含 AA 微众银行、AB 微众科技等。</div>
                <div>2. 二级为机构群（A 个金群…）；三级为产品（A01…）。</div>
                <div>3. 与 Excel 保持一致时请用「Excel 导入」；保存刷新后同步全系统。</div>
                <div>4. 国际业务（整体）不进机构树，见矩阵报表方案（方案 B）。</div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
