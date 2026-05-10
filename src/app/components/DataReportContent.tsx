import { useEffect, useMemo, useRef, useState } from "react";
import {
  Search,
  Plus,
  Download,
  Edit,
  Trash2,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronRight,
  ChevronDown,
  Minimize2,
  Maximize2,
  ChevronsDown,
  ChevronsUp,
  Maximize,
  Database as DatabaseIcon,
  FileText,
  Upload,
  X,
  Save,
} from "lucide-react";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableRowHeights } from "@/lib/useTableRowHeights";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { TableRowResizeHandle } from "./TableRowResizeHandle";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  buildApiUrl,
  type DataAccountDto,
  type ReportAccountDto,
  type ReportDataMappingDto,
} from "@/lib/api";
import { ExcelUploadDialog } from "./ExcelUploadDialog";
import { treeToolbarButtonClass } from "@/lib/treeToolbarStyles";

type SortDirection = "asc" | "desc";

type ReportTreeNode = {
  id: string;
  code: string;
  name: string;
  type: "report" | "data";
  level: number;
  isSummary?: boolean;
  isMinus?: boolean;
  isExpanded?: boolean;
  children?: ReportTreeNode[];
  reportCode?: string;
  dataCode?: string;
};

type EditingNode = {
  id: string;
  code: string;
  name: string;
  type: "report" | "data";
  parentCode?: string;
  level: number;
};

function normalizeReportTree(
  reports: ReportAccountDto[],
  mappings: ReportDataMappingDto[],
  dataAccounts: DataAccountDto[],
  expandedPrev: Record<string, boolean>
): ReportTreeNode[] {
  const reportMap = new Map<string, ReportTreeNode>();
  reports.forEach((r) => {
    reportMap.set(r.report_acct_code, {
      id: `report-${r.report_acct_code}`,
      code: r.report_acct_code,
      name: r.report_acct_name,
      type: "report",
      level: r.level,
      isSummary: Boolean(r.is_summary),
      isMinus: Boolean(r.is_minus),
      isExpanded: expandedPrev[r.report_acct_code] ?? false,
      children: [],
      reportCode: r.report_acct_code,
    });
  });

  const dataMap = new Map<string, DataAccountDto>();
  dataAccounts.forEach((d) => dataMap.set(d.data_acct_code, d));
  mappings.forEach((m) => {
    const parent = reportMap.get(m.report_acct_code);
    const data = dataMap.get(m.data_acct_code);
    if (!parent || !data) return;
    parent.children = parent.children ?? [];
    parent.children.push({
      id: `mapping-${m.report_acct_code}-${m.data_acct_code}`,
      code: m.data_acct_code,
      name: data.data_acct_name,
      type: "data",
      level: parent.level + 1,
      reportCode: m.report_acct_code,
      dataCode: m.data_acct_code,
    });
  });

  const roots: ReportTreeNode[] = [];
  reports.forEach((r) => {
    const node = reportMap.get(r.report_acct_code);
    if (!node) return;
    if (r.parent_code && reportMap.has(r.parent_code)) {
      reportMap.get(r.parent_code)!.children!.push(node);
    } else {
      roots.push(node);
    }
  });

  const sortRec = (nodes: ReportTreeNode[]) => {
    nodes.sort((a, b) => a.code.localeCompare(b.code, "zh-CN"));
    nodes.forEach((n) => n.children && sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}

function findParentCode(nodes: ReportTreeNode[], targetId: string): string | undefined {
  for (const node of nodes) {
    if (node.children?.some((c) => c.id === targetId)) return node.code;
    if (node.children) {
      const found = findParentCode(node.children, targetId);
      if (found) return found;
    }
  }
  return undefined;
}

function filterTree(nodes: ReportTreeNode[], term: string): ReportTreeNode[] {
  if (!term.trim()) return nodes;
  const s = term.trim().toLowerCase();
  return nodes
    .map((node) => {
      const children = node.children ? filterTree(node.children, term) : [];
      const match = node.code.toLowerCase().includes(s) || node.name.toLowerCase().includes(s);
      if (match || children.length > 0) {
        // 保留 treeData 中的展开状态，避免「全部收起」后搜索层仍强制展开
        return {
          ...node,
          children,
        };
      }
      return null;
    })
    .filter((n): n is ReportTreeNode => Boolean(n));
}

/** 展开整棵树：所有带子节点的报告科目均展开，直至最底层数据科目可见。 */
function expandReportTreeFully(nodes: ReportTreeNode[]): ReportTreeNode[] {
  return nodes.map((n) => {
    const children = n.children ? expandReportTreeFully(n.children) : undefined;
    const hasKids = children && children.length > 0;
    return {
      ...n,
      isExpanded: n.type === "report" && hasKids ? true : n.isExpanded,
      children,
    };
  });
}

/** 收起整棵树：所有报告科目节点均收起。 */
function collapseReportTreeFully(nodes: ReportTreeNode[]): ReportTreeNode[] {
  return nodes.map((n) => ({
    ...n,
    isExpanded: n.type === "report" ? false : n.isExpanded,
    children: n.children ? collapseReportTreeFully(n.children) : undefined,
  }));
}

const MAX_REPORT_LEVEL = 5;
const reportExcelFields = [
  { key: "level1Code", label: "第1级报告科目代码", required: true },
  { key: "level1Name", label: "第1级报告科目名称", required: true },
  { key: "level2Code", label: "第2级报告科目代码", required: true },
  { key: "level2Name", label: "第2级报告科目名称", required: true },
  { key: "level3Code", label: "第3级报告科目代码", required: true },
  { key: "level3Name", label: "第3级报告科目名称", required: true },
  { key: "level4Code", label: "第4级报告科目代码", required: true },
  { key: "level4Name", label: "第4级报告科目名称", required: true },
  { key: "level5Code", label: "第5级报告科目代码", required: true },
  { key: "level5Name", label: "第5级报告科目名称", required: true },
  { key: "dataCode", label: "数据科目代码", required: true },
  { key: "dataName", label: "数据科目名称", required: true },
  { key: "isSummary", label: "是否汇总", required: true },
  { key: "isMinus", label: "是否减项", required: true },
  { key: "remark", label: "备注", required: true },
];

function validateReportCodeForNode(codeRaw: string, level: number, parentCode?: string): string | null {
  const code = codeRaw.trim().toUpperCase();
  if (!code) return "报告科目代码不能为空";
  if (level < 1 || level > MAX_REPORT_LEVEL) return `报告科目层级必须在 1-${MAX_REPORT_LEVEL} 级`;
  if (level === 1) {
    if (!/^[A-Z]\d{2}$/.test(code)) {
      return "1级报告科目代码格式错误，应为 1 位大写字母 + 2 位数字（示例：A01）";
    }
    return null;
  }
  if (!parentCode) return "缺少上级科目代码，无法校验当前级次编码";
  const escapedParent = parentCode.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`^${escapedParent}\\d{2}$`);
  if (!pattern.test(code)) {
    return `第${level}级报告科目代码格式错误，应为“上级代码 + 2位数字”（示例：${parentCode}01）`;
  }
  return null;
}

function nextChildReportCode(parentCode: string, children?: ReportTreeNode[]): string | null {
  const suffixes = (children ?? [])
    .filter((c) => c.type === "report")
    .map((c) => c.code)
    .filter((code) => code.startsWith(parentCode) && code.length === parentCode.length + 2)
    .map((code) => Number.parseInt(code.slice(-2), 10))
    .filter((n) => Number.isFinite(n));
  const max = suffixes.length > 0 ? Math.max(...suffixes) : 0;
  if (max >= 99) return null;
  return `${parentCode}${String(max + 1).padStart(2, "0")}`;
}

function ReportTreeItem({
  node,
  onToggle,
  onEdit,
  onSaveEdit,
  onContextMenu,
  editingNode,
  onDrop,
  onDelete,
  onUpdateReportFlag,
  onSelectDataNode,
  onSelectReportNode,
  onDragTargetChange,
  selectedDataNodeId,
  selectedReportNodeId,
  dragTargetReportId,
  rowHeightStyle,
  onRowResizeStart,
}: {
  node: ReportTreeNode;
  onToggle: (id: string) => void;
  onEdit: (node: ReportTreeNode) => void;
  onSaveEdit: (id: string, code: string, name: string) => void;
  onContextMenu: (e: React.MouseEvent, node: ReportTreeNode) => void;
  editingNode: EditingNode | null;
  onDrop: (reportCode: string, dataCode: string) => void;
  onDelete: (node: ReportTreeNode) => void;
  onUpdateReportFlag: (reportCode: string, field: "is_summary" | "is_minus", value: boolean) => void;
  onSelectDataNode: (node: ReportTreeNode) => void;
  onSelectReportNode: (node: ReportTreeNode) => void;
  onDragTargetChange: (reportNodeId: string | null) => void;
  selectedDataNodeId?: string;
  selectedReportNodeId?: string;
  dragTargetReportId?: string;
  rowHeightStyle?: (nodeId: string) => React.CSSProperties;
  onRowResizeStart?: (nodeId: string, e: React.MouseEvent) => void;
}) {
  const hasChildren = (node.children?.length ?? 0) > 0;
  const isEditing = editingNode?.id === node.id;
  const [localCode, setLocalCode] = useState(node.code);
  const [localName, setLocalName] = useState(node.name);
  const hasReportChildren = (node.children ?? []).some((c) => c.type === "report");
  const canAcceptDrop = node.type === "report" && !hasReportChildren;

  useEffect(() => {
    if (isEditing && editingNode) {
      setLocalCode(editingNode.code);
      setLocalName(editingNode.name);
    }
  }, [isEditing, editingNode]);

  const isSelectedDataNode = node.type === "data" && selectedDataNodeId === node.id;
  const isSelectedReportNode = node.type === "report" && selectedReportNodeId === node.id;
  const isDragTargetNode = node.type === "report" && dragTargetReportId === node.id;
  const rowClass = isDragTargetNode
    ? "bg-blue-200"
    : isSelectedReportNode || isSelectedDataNode
      ? "bg-blue-100"
      : "hover:bg-gray-50";

  return (
    <div>
      <div
        className={`relative flex items-center gap-1 px-2 py-1 border-b border-gray-100 group ${rowClass}`}
        style={{
          paddingLeft: `${node.level * 12 + 4}px`,
          ...(rowHeightStyle?.(node.id) ?? {}),
        }}
        onContextMenu={(e) => onContextMenu(e, node)}
        draggable={node.type === "data"}
        onClick={() => {
          if (node.type === "data") onSelectDataNode(node);
          if (node.type === "report") onSelectReportNode(node);
        }}
        onMouseEnter={() => {
          if (node.type === "data") onSelectDataNode(node);
        }}
        onDragStart={(e) => {
          if (node.type !== "data" || !node.reportCode || !node.dataCode) return;
          e.dataTransfer.setData(
            "mappedDataNode",
            JSON.stringify({
              reportCode: node.reportCode,
              dataCode: node.dataCode,
              nodeId: node.id,
            })
          );
        }}
        onDragEnd={() => {
          onDragTargetChange(null);
        }}
        onDragOver={(e) => {
          if (!canAcceptDrop) return;
          e.preventDefault();
          onDragTargetChange(node.id);
        }}
        onDragEnter={(e) => {
          if (!canAcceptDrop) return;
          e.preventDefault();
          onDragTargetChange(node.id);
        }}
        onDrop={(e) => {
          if (!canAcceptDrop || !node.reportCode) return;
          e.preventDefault();
          onDragTargetChange(null);
          const dataCode = e.dataTransfer.getData("dataSubjectCode");
          if (dataCode) onDrop(node.reportCode, dataCode);
        }}
      >
        {hasChildren ? (
          <button onClick={() => onToggle(node.id)} className="p-0.5 hover:bg-gray-200 rounded flex-shrink-0">
            {node.isExpanded ? (
              <ChevronDown className="w-3 h-3 text-gray-600" />
            ) : (
              <ChevronRight className="w-3 h-3 text-gray-600" />
            )}
          </button>
        ) : (
          <span className="w-4" />
        )}

        {node.type === "report" ? (
          <FileText className="w-3 h-3 text-blue-600 flex-shrink-0 mr-1" />
        ) : (
          <DatabaseIcon className="w-3 h-3 text-green-600 flex-shrink-0 mr-1" />
        )}

        {isEditing ? (
          <input
            value={localCode}
            onChange={(e) => setLocalCode(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onSaveEdit(node.id, localCode, localName);
              }
            }}
            className="font-mono text-xs text-gray-700 w-24 px-1 py-0.5 border border-blue-400 rounded"
            autoFocus
          />
        ) : (
          <span
            className="font-mono text-xs text-gray-700 w-24"
            onDoubleClick={() => node.type === "report" && onEdit(node)}
          >
            {node.code}
          </span>
        )}
        {isEditing ? (
          <div className="flex items-center gap-1 flex-1">
            <input
              value={localName}
              onChange={(e) => setLocalName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  onSaveEdit(node.id, localCode, localName);
                }
              }}
              className="px-1 py-0.5 text-xs border border-blue-400 rounded flex-1"
            />
            <button
              onClick={() => onSaveEdit(node.id, localCode, localName)}
              className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]"
            >
              保存
            </button>
          </div>
        ) : (
          <>
            <span
              className="text-xs text-gray-700 flex-1"
              onDoubleClick={() => node.type === "report" && onEdit(node)}
            >
              {node.name}
            </span>
            {node.type === "report" && (
              <>
                <select
                  value={node.isSummary ? "1" : "0"}
                  onChange={(e) => {
                    if (!node.reportCode) return;
                    onUpdateReportFlag(node.reportCode, "is_summary", e.target.value === "1");
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className={`px-1 py-0.5 text-[11px] border rounded ${
                    node.isSummary
                      ? "border-gray-300 bg-white text-gray-700"
                      : "border-green-300 bg-green-50 text-green-700"
                  }`}
                  title="是否汇总"
                >
                  <option value="1">是否汇总：是</option>
                  <option value="0">是否汇总：否</option>
                </select>
                <select
                  value={node.isMinus ? "1" : "0"}
                  onChange={(e) => {
                    if (!node.reportCode) return;
                    onUpdateReportFlag(node.reportCode, "is_minus", e.target.value === "1");
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className={`px-1 py-0.5 text-[11px] border rounded ${
                    node.isMinus
                      ? "border-blue-300 bg-blue-50 text-blue-700"
                      : "border-gray-300 bg-white text-gray-700"
                  }`}
                  title="是否减项"
                >
                  <option value="1">是否减项：是</option>
                  <option value="0">是否减项：否</option>
                </select>
                <button
                  onClick={() => onEdit(node)}
                  className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                  title="编辑"
                >
                  <Edit className="w-3 h-3 text-gray-600" />
                </button>
                <button
                  onClick={() => onDelete(node)}
                  className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                  title="删除"
                >
                  <Trash2 className="w-3 h-3 text-red-600" />
                </button>
              </>
            )}
          </>
        )}
        {onRowResizeStart && (
          <TableRowResizeHandle
            onResizeStart={(e) =>
              onRowResizeStart(node.id, e)
            }
          />
        )}
      </div>
      {hasChildren && node.isExpanded && (
        <div>
          {node.children!.map((child) => (
            <ReportTreeItem
              key={child.id}
              node={child}
              onToggle={onToggle}
              onEdit={onEdit}
              onSaveEdit={onSaveEdit}
              onContextMenu={onContextMenu}
              editingNode={editingNode}
              onDrop={onDrop}
              onDelete={onDelete}
              onUpdateReportFlag={onUpdateReportFlag}
              onSelectDataNode={onSelectDataNode}
              onSelectReportNode={onSelectReportNode}
              onDragTargetChange={onDragTargetChange}
              selectedDataNodeId={selectedDataNodeId}
              selectedReportNodeId={selectedReportNodeId}
              dragTargetReportId={dragTargetReportId}
              rowHeightStyle={rowHeightStyle}
              onRowResizeStart={onRowResizeStart}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function DataReportContent() {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [reportSearchInput, setReportSearchInput] = useState("");
  const [reportSearch, setReportSearch] = useState("");
  const [dataSearchInput, setDataSearchInput] = useState("");
  const [dataSearch, setDataSearch] = useState("");
  const [treeData, setTreeData] = useState<ReportTreeNode[]>([]);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; node: ReportTreeNode } | null>(null);
  const [editingNode, setEditingNode] = useState<EditingNode | null>(null);
  const [newRootDraft, setNewRootDraft] = useState<{ id: string; code: string; name: string } | null>(null);
  const [dataSubjects, setDataSubjects] = useState<DataAccountDto[]>([]);
  const [selectedDataNode, setSelectedDataNode] = useState<{
    id: string;
    reportCode: string;
    dataCode: string;
    name: string;
  } | null>(null);
  const [selectedReportNodeId, setSelectedReportNodeId] = useState<string | null>(null);
  const [dragTargetReportId, setDragTargetReportId] = useState<string | null>(null);
  const [mappingHint, setMappingHint] = useState<{ dataCode: string; x: number; y: number } | null>(null);
  const [reportsRaw, setReportsRaw] = useState<ReportAccountDto[]>([]);
  const [mappingsRaw, setMappingsRaw] = useState<ReportDataMappingDto[]>([]);
  const [showExcelDialog, setShowExcelDialog] = useState(false);
  const [importMode, setImportMode] = useState<"upsert" | "replace">("upsert");
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const uPfx = useUserStorageKeyPrefix();
  const { rowStyle, beginResize } = useTableRowHeights(`${uPfx}::data-report-tree`, {
    minHeight: 28,
    maxHeight: 180,
  });

  const refresh = async (opts?: { collapseAll?: boolean }) => {
    const [reports, mappings, dataAccounts] = await Promise.all([
      apiGet<ReportAccountDto[]>("/api/report-accounts"),
      apiGet<ReportDataMappingDto[]>("/api/report-data-mappings"),
      apiGet<DataAccountDto[]>("/api/data-accounts"),
    ]);
    const expandedPrev = opts?.collapseAll ? {} : collectExpanded(treeData);
    setReportsRaw(reports);
    setMappingsRaw(mappings);
    setDataSubjects(dataAccounts);
    setTreeData(normalizeReportTree(reports, mappings, dataAccounts, expandedPrev));
  };

  useEffect(() => {
    void refresh().catch((e) => alert(`加载报告科目失败：${e.message}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const visibleTree = useMemo(() => filterTree(treeData, reportSearch), [treeData, reportSearch]);

  const sortedDataSubjects = useMemo(() => {
    const s = dataSearch.trim().toLowerCase();
    const list = dataSubjects.filter((d) => {
      if (!s) return true;
      return d.data_acct_code.toLowerCase().includes(s) || d.data_acct_name.toLowerCase().includes(s);
    });
    if (!sortColumn) return list;
    return list.sort((a, b) => {
      const av = sortColumn === "code" ? a.data_acct_code : a.data_acct_name;
      const bv = sortColumn === "code" ? b.data_acct_code : b.data_acct_name;
      const c = av.localeCompare(bv, "zh-CN");
      return sortDirection === "asc" ? c : -c;
    });
  }, [dataSubjects, sortColumn, sortDirection, dataSearch]);

  const dataSubjectMappingCount = useMemo(() => {
    const countMap: Record<string, number> = {};
    for (const mapping of mappingsRaw) {
      const key = mapping.data_acct_code;
      countMap[key] = (countMap[key] ?? 0) + 1;
    }
    return countMap;
  }, [mappingsRaw]);

  const reportNameByCode = useMemo(() => {
    const map: Record<string, string> = {};
    for (const report of reportsRaw) {
      map[report.report_acct_code] = report.report_acct_name;
    }
    return map;
  }, [reportsRaw]);

  const mappedReportsByDataCode = useMemo(() => {
    const result: Record<string, Array<{ code: string; name: string }>> = {};
    const dedupe: Record<string, Set<string>> = {};
    for (const mapping of mappingsRaw) {
      const dataCode = mapping.data_acct_code;
      const reportCode = mapping.report_acct_code;
      if (!dedupe[dataCode]) dedupe[dataCode] = new Set<string>();
      if (dedupe[dataCode]!.has(reportCode)) continue;
      dedupe[dataCode]!.add(reportCode);
      if (!result[dataCode]) result[dataCode] = [];
      result[dataCode]!.push({
        code: reportCode,
        name: reportNameByCode[reportCode] ?? "",
      });
    }
    for (const dataCode of Object.keys(result)) {
      result[dataCode]!.sort((a, b) => a.code.localeCompare(b.code, "zh-CN"));
    }
    return result;
  }, [mappingsRaw, reportNameByCode]);

  const toggleNode = (id: string) => {
    const toggle = (nodes: ReportTreeNode[]): ReportTreeNode[] =>
      nodes.map((n) =>
        n.id === id
          ? { ...n, isExpanded: !n.isExpanded }
          : n.children
            ? { ...n, children: toggle(n.children) }
            : n
      );
    setTreeData((prev) => toggle(prev));
  };

  const setNodeExpandedById = (id: string, expanded: boolean, recursive = false) => {
    const walk = (nodes: ReportTreeNode[]): ReportTreeNode[] =>
      nodes.map((n) => {
        if (n.id === id) {
          if (!recursive) return { ...n, isExpanded: expanded };
          const walkChild = (children?: ReportTreeNode[]): ReportTreeNode[] | undefined =>
            children?.map((c) => ({
              ...c,
              isExpanded: c.type === "report" ? expanded : c.isExpanded,
              children: walkChild(c.children),
            }));
          return {
            ...n,
            isExpanded: expanded,
            children: walkChild(n.children),
          };
        }
        return n.children ? { ...n, children: walk(n.children) } : n;
      });
    setTreeData((prev) => walk(prev));
  };

  const setExpandedByLevel = (targetLevel: number, expanded: boolean) => {
    const walk = (nodes: ReportTreeNode[]): ReportTreeNode[] =>
      nodes.map((n) => ({
        ...n,
        isExpanded: n.type === "report" && n.level === targetLevel ? expanded : n.isExpanded,
        children: n.children ? walk(n.children) : undefined,
      }));
    setTreeData((prev) => walk(prev));
  };

  const collapseCurrentLevelOnly = () => {
    const selected = selectedReportNodeId ? findNodeById(treeData, selectedReportNodeId) : null;
    if (selected?.type === "report") {
      setNodeExpandedById(selected.id, false);
      return;
    }
    setExpandedByLevel(1, false);
  };

  const expandNextLevelOnly = () => {
    const selected = selectedReportNodeId ? findNodeById(treeData, selectedReportNodeId) : null;
    if (selected?.type === "report") {
      setNodeExpandedById(selected.id, true);
      return;
    }
    setExpandedByLevel(1, true);
  };

  const collapseAllFromCurrentLevel = () => {
    const selected = selectedReportNodeId ? findNodeById(treeData, selectedReportNodeId) : null;
    const level = selected?.type === "report" ? selected.level : 1;
    setExpandedByLevel(level, false);
  };

  const expandAllFromCurrentLevel = () => {
    const selected = selectedReportNodeId ? findNodeById(treeData, selectedReportNodeId) : null;
    if (selected?.type === "report") {
      setNodeExpandedById(selected.id, true, true);
      return;
    }
    const walk = (nodes: ReportTreeNode[]): ReportTreeNode[] =>
      nodes.map((n) => ({
        ...n,
        isExpanded: n.type === "report" ? true : n.isExpanded,
        children: n.children ? walk(n.children) : undefined,
      }));
    setTreeData((prev) => walk(prev));
  };

  const collapseEntireTree = () => {
    setReportSearchInput("");
    setReportSearch("");
    setTreeData((prev) => collapseReportTreeFully(prev));
  };

  const expandEntireTree = () => {
    setTreeData((prev) => expandReportTreeFully(prev));
  };

  /** 提交搜索关键词；有关键词时展开整棵树以便命中节点可见（与原先搜索体验一致）。 */
  const commitReportSearch = () => {
    const q = reportSearchInput;
    setReportSearch(q);
    if (q.trim()) {
      setTreeData((prev) => expandReportTreeFully(prev));
    }
  };

  const handleEdit = (node: ReportTreeNode) => {
    if (node.type !== "report") return;
    setEditingNode({
      id: node.id,
      code: node.code,
      name: node.name,
      type: node.type,
      parentCode: findParentCode(treeData, node.id),
      level: node.level,
    });
  };

  const handleSaveEdit = async (id: string, codeInput: string, nameInput: string) => {
    const target = findNodeById(treeData, id);
    if (!target || target.type !== "report" || !target.reportCode) {
      setEditingNode(null);
      return;
    }
    const code = codeInput.trim().toUpperCase();
    const name = nameInput.trim();
    const parentCode = findParentCode(treeData, id);
    const codeError = validateReportCodeForNode(code, target.level, parentCode);
    if (codeError) return alert(codeError);
    if (!name) return alert("报告科目名称不能为空");
    try {
      if (code === target.reportCode) {
        await apiPatch<ReportAccountDto>(`/api/report-accounts/${encodeURIComponent(target.reportCode)}`, {
          report_acct_name: name,
        });
      } else {
        if ((target.children ?? []).some((c) => c.type === "report")) {
          alert("存在下级报告科目时，不允许直接修改当前科目代码");
          return;
        }
        const current = reportsRaw.find((r) => r.report_acct_code === target.reportCode);
        if (!current) {
          alert("未找到当前报告科目原始信息，请刷新后重试");
          return;
        }
        await apiPost<ReportAccountDto>("/api/report-accounts", {
          report_acct_code: code,
          report_acct_name: name,
          parent_code: current.parent_code,
          is_summary: current.is_summary,
          is_minus: current.is_minus,
          level: current.level,
          is_leaf: current.is_leaf,
          remark: current.remark ?? null,
        });
        const oldMappings = mappingsRaw.filter((m) => m.report_acct_code === target.reportCode);
        for (const mapping of oldMappings) {
          await apiPost<ReportDataMappingDto>("/api/report-data-mappings", {
            report_acct_code: code,
            data_acct_code: mapping.data_acct_code,
          });
          await apiDelete(
            `/api/report-data-mappings/${encodeURIComponent(mapping.report_acct_code)}/${encodeURIComponent(mapping.data_acct_code)}`
          );
        }
        await apiDelete(`/api/report-accounts/${encodeURIComponent(target.reportCode)}`);
      }
      setEditingNode(null);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleDropDataSubject = async (reportCode: string, dataCode: string) => {
    const target = findNodeByCode(treeData, reportCode);
    if (!target) {
      alert("目标报告科目不存在，请刷新后重试");
      return;
    }
    const hasReportChildren = (target.children ?? []).some((c) => c.type === "report");
    if (hasReportChildren) {
      alert("该报告科目已有下级报告科目，不能再挂接数据科目");
      return;
    }
    try {
      await apiPost<ReportDataMappingDto>("/api/report-data-mappings", {
        report_acct_code: reportCode,
        data_acct_code: dataCode,
      });
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "挂接失败");
    }
  };

  const handleUpdateReportFlag = async (
    reportCode: string,
    field: "is_summary" | "is_minus",
    value: boolean
  ) => {
    try {
      await apiPatch<ReportAccountDto>(`/api/report-accounts/${encodeURIComponent(reportCode)}`, {
        [field]: value,
      });
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "更新失败");
    }
  };

  const handleDeleteNode = async (node: ReportTreeNode) => {
    if (node.type === "data" && node.reportCode && node.dataCode) {
      await handleDeleteMapping(node.reportCode, node.dataCode, true);
      return;
    }
    if (node.type === "report" && node.reportCode) {
      if (!confirm(`确定删除报告科目 ${node.reportCode} ?`)) return;
      try {
        await apiDelete(`/api/report-accounts/${encodeURIComponent(node.reportCode)}`);
        await refresh();
      } catch (e) {
        alert(e instanceof Error ? e.message : "删除失败");
      }
    }
  };

  const handleDeleteMapping = async (reportCode: string, dataCode: string, showConfirm = true) => {
    if (showConfirm && !confirm(`确定解除映射 ${reportCode} -> ${dataCode} ?`)) return;
    try {
      await apiDelete(`/api/report-data-mappings/${encodeURIComponent(reportCode)}/${encodeURIComponent(dataCode)}`);
      setSelectedDataNode((prev) => (prev?.reportCode === reportCode && prev.dataCode === dataCode ? null : prev));
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "解除映射失败");
    }
  };

  const handleAddChildReport = async (node: ReportTreeNode) => {
    if (node.type !== "report" || !node.reportCode) return;
    if (node.level >= MAX_REPORT_LEVEL) {
      alert(`报告科目最多 ${MAX_REPORT_LEVEL} 级，当前节点不能再新增下级报告科目`);
      return;
    }
    const defaultCode = nextChildReportCode(node.reportCode, node.children) ?? `${node.reportCode}01`;
    let code = "";
    while (true) {
      const input = prompt(
        `请输入下级报告科目代码（格式：上级代码 + 2位数字，例如 ${node.reportCode}01）`,
        code || defaultCode
      );
      if (input === null) {
        return;
      }
      const candidate = input.trim().toUpperCase();
      const codeError = validateReportCodeForNode(candidate, node.level + 1, node.reportCode);
      if (codeError) {
        alert(codeError);
        continue;
      }
      const existed = findNodeByCode(treeData, candidate);
      if (existed) {
        alert(`报告科目代码 ${candidate} 已存在，请重新输入`);
        continue;
      }
      code = candidate;
      break;
    }

    let name = "";
    while (true) {
      const input = prompt("请输入下级报告科目名称");
      if (input === null) {
        return;
      }
      const candidate = input.trim();
      if (!candidate) {
        alert("报告科目名称不能为空");
        continue;
      }
      name = candidate;
      break;
    }

    try {
      await apiPost<ReportAccountDto>("/api/report-accounts", {
        report_acct_code: code,
        report_acct_name: name,
        parent_code: node.reportCode,
        is_summary: true,
        is_minus: false,
        level: node.level + 1,
        is_leaf: false,
        remark: null,
      });
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "新增失败");
    }
  };

  const handleCreateRoot = async () => {
    if (!newRootDraft) return;
    const code = newRootDraft.code.trim().toUpperCase();
    const name = newRootDraft.name.trim();
    const codeError = validateReportCodeForNode(code, 1);
    if (codeError) return alert(codeError);
    if (!name) return alert("1级报告科目名称不能为空");
    try {
      await apiPost<ReportAccountDto>("/api/report-accounts", {
        report_acct_code: code,
        report_acct_name: name,
        parent_code: null,
        is_summary: true,
        is_minus: false,
        level: 1,
        is_leaf: false,
        remark: null,
      });
      setNewRootDraft(null);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "新增失败");
    }
  };

  const handleSaveRefresh = async () => {
    if ((editingNode || newRootDraft) && !confirm("当前存在未完成编辑，继续将放弃未保存输入并刷新树结构。是否继续？")) {
      return;
    }
    try {
      setEditingNode(null);
      setNewRootDraft(null);
      setSelectedDataNode(null);
      setSelectedReportNodeId(null);
      await refresh({ collapseAll: true });
      alert("已从数据库刷新报告科目体系。");
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
      const resp = await fetch(buildApiUrl("/api/report-tree/export"), { credentials: "include" });
      if (!resp.ok) throw new Error((await resp.text()) || "导出失败");
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") ?? "";
      const fnMatch = cd.match(/filename="?([^"]+)"?/i);
      const fileName = fnMatch?.[1] || "report_tree_export.xlsx";
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

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
  };

  const getSortIcon = (column: string) => {
    if (sortColumn !== column) return <ArrowUpDown className="w-3 h-3 text-gray-400" />;
    return sortDirection === "asc" ? (
      <ArrowUp className="w-3 h-3 text-blue-600" />
    ) : (
      <ArrowDown className="w-3 h-3 text-blue-600" />
    );
  };

  const handleMappedNodeDropToDelete = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragTargetReportId(null);
    const raw = e.dataTransfer.getData("mappedDataNode");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as { reportCode?: string; dataCode?: string };
      if (!parsed.reportCode || !parsed.dataCode) return;
      await handleDeleteMapping(parsed.reportCode, parsed.dataCode, false);
    } catch {
      // ignore malformed drag payload
    }
  };

  const showMappingHint = (dataCode: string, target: HTMLElement) => {
    const rect = target.getBoundingClientRect();
    setMappingHint({
      dataCode,
      x: rect.left + rect.width / 2,
      y: rect.top - 6,
    });
  };

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="flex-1 overflow-hidden">
        <PanelGroup direction="horizontal">
          <Panel id="report-tree" order={1} defaultSize={60} minSize={30}>
            <div className="h-full border border-gray-300 rounded overflow-hidden bg-white flex flex-col">
              <div className="px-3 py-2 bg-gray-100 border-b border-gray-300">
                <div className="mb-2 flex items-center gap-2">
                  <h3 className="text-sm font-medium text-gray-800">报告科目维护</h3>
                  <div className="flex-1" />
                  <button
                    onClick={() =>
                      setNewRootDraft({
                        id: `new-root-${Date.now()}`,
                        code: "",
                        name: "",
                      })
                    }
                    className="flex items-center gap-1 px-3 py-1 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]"
                  >
                    <Plus className="w-3 h-3" />
                    增加1级报告科目
                  </button>
                  <button
                    onClick={() => setShowExcelDialog(true)}
                    className="flex items-center gap-1 px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954]"
                  >
                    <Upload className="w-3 h-3" />
                    Excel上传科目
                  </button>
                  <button
                    onClick={() => void handleExportTree()}
                    className="flex items-center gap-1 px-3 py-1 text-xs bg-[#16a085] text-white rounded hover:bg-[#138d75]"
                  >
                    <Download className="w-3 h-3" />
                    Excel导出
                  </button>
                  <button onClick={() => void handleSaveRefresh()} className="flex items-center gap-1 px-3 py-1 text-xs bg-[#e67e22] text-white rounded hover:bg-[#d35400]">
                    <Save className="w-3 h-3" />
                    保存并刷新
                  </button>
                  <button
                    onClick={() => setImportMode((m) => (m === "upsert" ? "replace" : "upsert"))}
                    className={`flex items-center gap-1 px-3 py-1 text-xs border rounded transition-colors ${
                      importMode === "replace"
                        ? "bg-red-50 border-red-400 text-red-700"
                        : "border-gray-300 text-gray-500 hover:bg-gray-50"
                    }`}
                    title={importMode === "replace" ? "覆盖模式：导入前先清空全部报告科目和映射，再写入新数据" : "追加模式：只新增/更新，不删除已有报告科目"}
                  >
                    {importMode === "replace" ? "覆盖模式" : "追加模式"}
                  </button>
                </div>
                <div className="flex items-center gap-2 mb-2">
                  <div className="relative w-56">
                    <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                      type="text"
                      placeholder="搜索报告科目..."
                      value={reportSearchInput}
                      onChange={(e) => {
                        setReportSearchInput(e.target.value);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitReportSearch();
                      }}
                      className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-full focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    {reportSearchInput && (
                      <button
                        type="button"
                        onClick={() => {
                          setReportSearchInput("");
                          setReportSearch("");
                        }}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
                        title="清除搜索"
                      >
                        <X className="w-3.5 h-3.5 text-gray-500" />
                      </button>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => commitReportSearch()}
                    className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50"
                  >
                    搜索
                  </button>
                  <div className="flex-1" />
                  <button
                    type="button"
                    title="收起当前选中的报告科目节点；未选中时收起所有一级根节点"
                    onClick={collapseCurrentLevelOnly}
                    className={treeToolbarButtonClass}
                  >
                    <Minimize2 className="w-3 h-3" />
                    <span>收起本级</span>
                  </button>
                  <button
                    type="button"
                    title="展开当前选中的报告科目；未选中时展开所有一级根节点"
                    onClick={expandNextLevelOnly}
                    className={treeToolbarButtonClass}
                  >
                    <Maximize2 className="w-3 h-3" />
                    <span>展开下级</span>
                  </button>
                  <button
                    type="button"
                    title="收起当前层级：选中节点时收起该层同级；未选中时收起全部一级根节点"
                    onClick={collapseAllFromCurrentLevel}
                    className={treeToolbarButtonClass}
                  >
                    <ChevronsUp className="w-3 h-3" />
                    <span>收起全部本级</span>
                  </button>
                  <button
                    type="button"
                    title="选中报告科目时展开其下全部多级子树；未选中时展开整棵树（含所有层级）"
                    onClick={expandAllFromCurrentLevel}
                    className={treeToolbarButtonClass}
                  >
                    <ChevronsDown className="w-3 h-3" />
                    <span>展开全部下级</span>
                  </button>
                  <button
                    type="button"
                    title="清空搜索并收起整棵树中所有报告科目节点（与当前选中项无关）"
                    onClick={collapseEntireTree}
                    className={treeToolbarButtonClass}
                  >
                    <Minimize2 className="w-3 h-3" />
                    <span>全部收起</span>
                  </button>
                  <button
                    type="button"
                    title="从一级科目起展开全部层级，直至最底层数据科目均可见"
                    onClick={expandEntireTree}
                    className={treeToolbarButtonClass}
                  >
                    <Maximize className="w-3 h-3" />
                    <span>全部展开</span>
                  </button>
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
                          void handleCreateRoot();
                        }
                      }}
                      placeholder="1级代码"
                      className="w-24 px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
                    />
                    <input
                      value={newRootDraft.name}
                      onChange={(e) => setNewRootDraft({ ...newRootDraft, name: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void handleCreateRoot();
                        }
                      }}
                      placeholder="1级报告科目名称"
                      className="flex-1 px-1 py-0.5 text-xs border border-blue-400 rounded"
                    />
                    <button onClick={() => void handleCreateRoot()} className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]">
                      保存
                    </button>
                    <button onClick={() => setNewRootDraft(null)} className="px-2 py-0.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300">
                      取消
                    </button>
                  </div>
                )}
              {visibleTree.map((node) => (
                <ReportTreeItem
                  key={node.id}
                  node={node}
                  onToggle={toggleNode}
                  onEdit={handleEdit}
                  onSaveEdit={handleSaveEdit}
                  onDelete={(n) => {
                    void handleDeleteNode(n);
                  }}
                  onUpdateReportFlag={(reportCode, field, value) => {
                    void handleUpdateReportFlag(reportCode, field, value);
                  }}
                  onSelectDataNode={(n) => {
                    if (n.type !== "data" || !n.reportCode || !n.dataCode) return;
                    setSelectedDataNode({
                      id: n.id,
                      reportCode: n.reportCode,
                      dataCode: n.dataCode,
                      name: n.name,
                    });
                  }}
                  onSelectReportNode={(n) => {
                    if (n.type !== "report") return;
                    setSelectedReportNodeId(n.id);
                  }}
                  onDragTargetChange={(nodeId) => {
                    setDragTargetReportId(nodeId);
                  }}
                  selectedDataNodeId={selectedDataNode?.id}
                  selectedReportNodeId={selectedReportNodeId ?? undefined}
                  dragTargetReportId={dragTargetReportId ?? undefined}
                  onContextMenu={(e, n) => {
                    e.preventDefault();
                    if (n.type === "report") setSelectedReportNodeId(n.id);
                    if (n.type === "data" && n.reportCode && n.dataCode) {
                      setSelectedDataNode({
                        id: n.id,
                        reportCode: n.reportCode,
                        dataCode: n.dataCode,
                        name: n.name,
                      });
                    }
                    setContextMenu({ x: e.clientX, y: e.clientY, node: n });
                  }}
                  editingNode={editingNode}
                  onDrop={handleDropDataSubject}
                  rowHeightStyle={rowStyle}
                  onRowResizeStart={(id, e) =>
                    beginResize(id, e, () => (e.currentTarget as HTMLElement).parentElement)
                  }
                />
              ))}
              </div>
            </div>
          </Panel>

          <PanelResizeHandle className="w-1 bg-gray-300 hover:bg-[#3498db] transition-colors mx-2" />

          <Panel id="data-subject-list" order={2} defaultSize={40} minSize={20}>
            <div className="h-full border border-gray-300 rounded bg-white flex flex-col">
              <div className="px-3 py-2 bg-gray-100 border-b border-gray-300">
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-medium text-gray-800">数据科目列表</h4>
                  <div className="flex-1" />
                  <div className="relative w-48">
                    <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                      type="text"
                      placeholder="搜索数据科目..."
                      value={dataSearchInput}
                      onChange={(e) => {
                        setDataSearchInput(e.target.value);
                        setDataSearch(e.target.value);
                      }}
                      onKeyDown={(e) => e.key === "Enter" && setDataSearch(dataSearchInput)}
                      className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-full focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    {dataSearchInput && (
                      <button
                        type="button"
                        onClick={() => {
                          setDataSearchInput("");
                          setDataSearch("");
                        }}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
                        title="清除搜索"
                      >
                        <X className="w-3.5 h-3.5 text-gray-500" />
                      </button>
                    )}
                  </div>
                  <button
                    onClick={() => setDataSearch(dataSearchInput)}
                    className="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50"
                  >
                    搜索
                  </button>
                </div>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  拖拽到左侧报告科目增添映射，从左侧拖回数据科目将删除映射
                </p>
                {selectedDataNode && (
                  <div className="mt-2 flex items-center gap-2 text-[11px] text-gray-700">
                    <span className="flex-1 truncate">
                      当前选中：{selectedDataNode.reportCode} {"->"} {selectedDataNode.dataCode} {selectedDataNode.name}
                    </span>
                    <button
                      onClick={() => {
                        void handleDeleteMapping(selectedDataNode.reportCode, selectedDataNode.dataCode, true);
                      }}
                      className="px-2 py-0.5 text-[11px] bg-red-600 text-white rounded hover:bg-red-700"
                    >
                      删除
                    </button>
                  </div>
                )}
              </div>
              <div className="flex items-center bg-gray-50 border-b border-gray-300 px-3 py-1.5">
                <div className="w-3 flex-shrink-0" />
                <button onClick={() => handleSort("code")} className="flex items-center gap-1 text-xs font-medium text-gray-700 hover:text-blue-600 transition-colors w-24 ml-2">
                  数据科目代码
                  {getSortIcon("code")}
                </button>
                <button onClick={() => handleSort("name")} className="flex items-center gap-1 justify-center text-xs font-medium text-gray-700 hover:text-blue-600 transition-colors flex-1 ml-2">
                  数据科目名称
                  {getSortIcon("name")}
                </button>
                <div className="w-16 text-right text-xs font-medium text-gray-700">映射次数</div>
              </div>
              <div
                className="flex-1 overflow-y-auto"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  void handleMappedNodeDropToDelete(e);
                }}
              >
                {sortedDataSubjects.map((subject) => {
                  const mappingCount = dataSubjectMappingCount[subject.data_acct_code] ?? 0;
                  return (
                  <div
                    key={subject.data_acct_code}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("dataSubjectCode", subject.data_acct_code);
                    }}
                    onDragEnd={() => {
                      setDragTargetReportId(null);
                    }}
                    className="flex items-center gap-2 px-3 py-1.5 border-b border-gray-100 hover:bg-blue-50 cursor-move"
                  >
                    <DatabaseIcon className="w-3 h-3 text-green-600 flex-shrink-0" />
                    <span className="font-mono text-xs text-gray-700 w-24">{subject.data_acct_code}</span>
                    <span className="text-xs text-gray-700 flex-1 truncate">{subject.data_acct_name}</span>
                    <span
                      className={`w-16 text-right text-xs font-medium ${mappingCount === 0 ? "text-red-600" : "text-gray-700"}`}
                      title={`被报告科目引用 ${mappingCount} 次`}
                      onMouseEnter={(e) => showMappingHint(subject.data_acct_code, e.currentTarget)}
                      onMouseLeave={() => setMappingHint(null)}
                      onClick={(e) => showMappingHint(subject.data_acct_code, e.currentTarget)}
                      onDoubleClick={(e) => showMappingHint(subject.data_acct_code, e.currentTarget)}
                    >
                      {mappingCount}
                    </span>
                  </div>
                  );
                })}
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>

      {mappingHint && (
        <div
          className="fixed z-50 max-w-[420px] min-w-[260px] rounded border border-gray-300 bg-white shadow-lg p-2 pointer-events-none"
          style={{ left: mappingHint.x, top: mappingHint.y, transform: "translate(-50%, -100%)" }}
        >
          <div className="text-[11px] font-medium text-gray-800 mb-1">
            {mappingHint.dataCode} 被以下报告科目引用：
          </div>
          {(mappedReportsByDataCode[mappingHint.dataCode] ?? []).length === 0 ? (
            <div className="text-[11px] text-red-600">暂无引用</div>
          ) : (
            <div className="max-h-44 overflow-y-auto space-y-0.5">
              {(mappedReportsByDataCode[mappingHint.dataCode] ?? []).map((report) => (
                <div key={`${mappingHint.dataCode}-${report.code}`} className="text-[11px] text-gray-700 font-mono">
                  {report.code} {report.name}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[160px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {contextMenu.node.type === "report" && (
            <button
              onClick={() => {
                handleEdit(contextMenu.node);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <Edit className="w-3 h-3" />
              编辑
            </button>
          )}
          {(contextMenu.node.children?.length ?? 0) > 0 && (
            <button
              onClick={() => {
                toggleNode(contextMenu.node.id);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <Minimize2 className="w-3 h-3" />
              {contextMenu.node.isExpanded ? "收起本级" : "展开下级"}
            </button>
          )}
          {contextMenu.node.type === "report" &&
            contextMenu.node.level < MAX_REPORT_LEVEL &&
            !(contextMenu.node.children ?? []).some((c) => c.type === "data") && (
            <button
              onClick={() => {
                void handleAddChildReport(contextMenu.node);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <Plus className="w-3 h-3" />
              增加下级报告科目
            </button>
            )}
          <div className="border-t border-gray-200 my-1" />
          <button
            onClick={() => {
              void handleDeleteNode(contextMenu.node);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 text-red-600 flex items-center gap-2"
          >
            <Trash2 className="w-3 h-3" />
            删除本{contextMenu.node.type === "report" ? "报告" : "数据"}科目
          </button>
        </div>
      )}
      <ExcelUploadDialog
        isOpen={showExcelDialog}
        onClose={() => setShowExcelDialog(false)}
        title="报告科目维护"
        fields={reportExcelFields}
        templateName="report_acct_temp"
        previewEndpoint="/api/report-accounts/import-preview"
        importEndpoint="/api/report-accounts/import-apply"
        importMode={importMode}
        onImportComplete={() => void refresh()}
      />
    </div>
  );
}

function collectExpanded(nodes: ReportTreeNode[]): Record<string, boolean> {
  const acc: Record<string, boolean> = {};
  const walk = (list: ReportTreeNode[]) => {
    list.forEach((n) => {
      if (n.type === "report" && n.reportCode) acc[n.reportCode] = Boolean(n.isExpanded);
      if (n.children) walk(n.children);
    });
  };
  walk(nodes);
  return acc;
}

function findNodeById(nodes: ReportTreeNode[], id: string): ReportTreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const found = findNodeById(node.children, id);
      if (found) return found;
    }
  }
  return null;
}

function findNodeByCode(nodes: ReportTreeNode[], code: string): ReportTreeNode | null {
  for (const node of nodes) {
    if (node.type === "report" && node.code === code) return node;
    if (node.children) {
      const found = findNodeByCode(node.children, code);
      if (found) return found;
    }
  }
  return null;
}
