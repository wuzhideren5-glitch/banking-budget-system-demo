import { useEffect, useMemo, useState } from "react";
import { X, ChevronRight, ChevronDown, Database, Search } from "lucide-react";
import type { ProductTypeDto } from "@/lib/api";
import { treeToolbarButtonCompactClass } from "@/lib/treeToolbarStyles";

type ProductNode = {
  id: string;
  code: string;
  name: string;
  type: "department" | "product";
  deptCode?: string;
  level?: number;
  children: ProductNode[];
};

/** 数据科目「适用所有产品」选项码 */
export const ALL_PRODUCTS_PRODUCT_CODE = "__ALL__";

/** 构建产品层级树（按 product_type 的 parent_code） */
function buildProductHierarchyTree(productTypes: ProductTypeDto[]): ProductNode[] {
  const nodeMap = new Map<string, ProductNode>();

  // 先创建所有节点
  productTypes.forEach((pt) => {
    nodeMap.set(pt.product_code, {
      id: `prod-${pt.product_code}`,
      code: pt.product_code,
      name: pt.product_name,
      type: "product",
      level: pt.level,
      children: [],
    });
  });

  // 构建树结构
  const roots: ProductNode[] = [];
  productTypes.forEach((pt) => {
    const node = nodeMap.get(pt.product_code)!;
    if (pt.parent_code && nodeMap.has(pt.parent_code)) {
      nodeMap.get(pt.parent_code)!.children.push(node);
    } else {
      roots.push(node);
    }
  });

  // 排序
  const sortRec = (nodes: ProductNode[]) => {
    nodes.sort((a, b) => a.code.localeCompare(b.code, "zh-CN"));
    nodes.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);

  return roots;
}

interface ProductMultiSelectDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** 确认回调，products 为空数组且 isAllSelected=true 表示全行 */
  onConfirm: (products: { code: string; name: string }[], isAllSelected: boolean) => void;
  /** 当前选中的 product_codes 字符串（逗号分隔），用于回显 */
  initialProductCodes?: string | null;
  flatProducts: { code: string; name: string }[];
  /** 产品类型层级数据 */
  productTypes: ProductTypeDto[];
}

export function ProductMultiSelectDialog({
  isOpen,
  onClose,
  onConfirm,
  initialProductCodes,
  flatProducts,
  productTypes,
}: ProductMultiSelectDialogProps) {
  // isAllSelected = true 表示"适用所有产品科目"
  const [isAllSelected, setIsAllSelected] = useState(false);
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [searchText, setSearchText] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // 使用产品层级树（而非部门-产品映射树）
  const tree = useMemo(() => buildProductHierarchyTree(productTypes), [productTypes]);

  /** 将节点代码展开为叶子代码（处理父级代码自动展开为所有叶子） */
  const expandToLeaves = (codeSet: Set<string>): Set<string> => {
    const result = new Set<string>();
    const walk = (nodes: ProductNode[]) => {
      nodes.forEach((n) => {
        if (codeSet.has(n.code)) {
          // 如果是叶子或父级被选中，展开到所有叶子
          if (n.children.length === 0) {
            result.add(n.code);
          } else {
            collectAllLeaves(n).forEach((l) => result.add(l.code));
          }
        }
        walk(n.children);
      });
    };
    walk(tree);
    return result;
  };

  const collectAllLeaves = (node: ProductNode): ProductNode[] => {
    if (node.children.length === 0) return [node];
    return node.children.flatMap(collectAllLeaves);
  };

  // 每次打开时，从 initialProductCodes 还原选择状态
  useEffect(() => {
    if (!isOpen) return;
    const codes = (initialProductCodes ?? "").trim();
    if (codes === "" || codes === ALL_PRODUCTS_PRODUCT_CODE) {
      setIsAllSelected(true);
      setSelectedCodes(new Set());
    } else {
      setIsAllSelected(false);
      const rawCodes = new Set(codes.split(",").map((c) => c.trim()).filter(Boolean));
      // 将父级产品代码（如Z0101）展开为其所有叶子后代
      setSelectedCodes(expandToLeaves(rawCodes));
    }
    // 默认展开第1层
    const nextExpanded: Record<string, boolean> = {};
    tree.forEach((n) => {
      nextExpanded[n.id] = true;
    });
    setExpanded(nextExpanded);
    setSearchText("");
  }, [isOpen, initialProductCodes, tree]);

  const toggleAllProducts = () => {
    if (isAllSelected) {
      setIsAllSelected(false);
    } else {
      setIsAllSelected(true);
      setSelectedCodes(new Set());
    }
  };

  const selectAllVisibleProducts = () => {
    const visible = getVisibleProductNodes();
    setIsAllSelected(false);
    setSelectedCodes(new Set(visible.map((n) => n.code)));
  };

  const clearAll = () => {
    setIsAllSelected(false);
    setSelectedCodes(new Set());
  };

  const toggleDept = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const nodeDepthMap = useMemo(() => {
    const map: Record<string, number> = {};
    const walk = (nodes: ProductNode[], depth: number) => {
      nodes.forEach((n) => {
        map[n.id] = depth;
        if (n.children.length > 0) walk(n.children, depth + 1);
      });
    };
    walk(tree, 1);
    return map;
  }, [tree]);

  const collectAllNodeIds = (): string[] => Object.keys(nodeDepthMap);

  const setExpandedForIds = (ids: string[], value: boolean) => {
    setExpanded((prev) => {
      const next = { ...prev };
      ids.forEach((id) => {
        next[id] = value;
      });
      return next;
    });
  };

  const expandAll = () => setExpandedForIds(collectAllNodeIds(), true);
  const collapseAll = () => {
    setExpandedForIds(collectAllNodeIds(), false);
    setSearchText("");
  };

  const getVisibleProductNodes = (): ProductNode[] => {
    const result: ProductNode[] = [];
    const walk = (nodes: ProductNode[]) => {
      nodes.forEach((n) => {
        result.push(n);
        if (n.children.length > 0) walk(n.children);
      });
    };
    walk(filterTree(tree));
    return result;
  };

  const selectedCount = isAllSelected ? flatProducts.length : selectedCodes.size;

  const filterTree = (nodes: ProductNode[]): ProductNode[] => {
    const s = searchText.trim().toLowerCase();
    if (!s) return nodes;
    return nodes
      .map((n) => {
        const children = filterTree(n.children);
        const match = n.code.toLowerCase().includes(s) || n.name.toLowerCase().includes(s);
        if (match || children.length > 0) return { ...n, children };
        return null;
      })
      .filter((n): n is ProductNode => Boolean(n));
  };

  const renderNode = (node: ProductNode, depth = 0): JSX.Element => {
    const hasChildren = node.children.length > 0;
    const isOpen = Boolean(expanded[node.id]);
    const isChecked = isAllSelected || selectedCodes.has(node.code);

    // 收集所有后代叶子节点
    const collectDescendantLeaves = (n: ProductNode): ProductNode[] => {
      if (n.children.length === 0) return [n];
      return n.children.flatMap(collectDescendantLeaves);
    };

    // 计算子树的全选/半选状态
    const getSubtreeCheckState = (): boolean | "indeterminate" => {
      if (isChecked) return true;
      const leaves = collectDescendantLeaves(node);
      const checkedCount = leaves.filter((l) => selectedCodes.has(l.code)).length;
      if (checkedCount === 0) return false;
      if (checkedCount === leaves.length) return true;
      return "indeterminate";
    };

    const subtreeState = hasChildren ? getSubtreeCheckState() : isChecked;

    // 切换节点（包含所有子孙叶子）
    const toggleNode = () => {
      if (isAllSelected) return;
      const leaves = hasChildren ? collectDescendantLeaves(node) : [node];
      setSelectedCodes((prev) => {
        const next = new Set(prev);
        // 同时检查节点自身代码和所有叶子后代
        const selfChecked = prev.has(node.code);
        const allLeavesChecked = leaves.every((l) => next.has(l.code));
        // 如果节点自身被选中或所有叶子都被选中，则取消选择
        if (selfChecked || allLeavesChecked) {
          next.delete(node.code);
          leaves.forEach((l) => next.delete(l.code));
        } else {
          leaves.forEach((l) => next.add(l.code));
        }
        return next;
      });
    };

    const levelLabel = node.level ? `L${node.level}` : "";

    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-1 px-2 py-1.5 text-xs ${
            hasChildren ? "font-medium text-gray-800 hover:bg-gray-100" : "text-gray-700 cursor-pointer hover:bg-blue-50"
          }`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          {/* 展开/收起箭头 */}
          {hasChildren ? (
            <button
              onClick={() => toggleDept(node.id)}
              className="p-0 m-0 border-0 bg-transparent cursor-pointer"
            >
              {isOpen ? (
                <ChevronDown className="w-3 h-3 text-gray-500" />
              ) : (
                <ChevronRight className="w-3 h-3 text-gray-500" />
              )}
            </button>
          ) : (
            <span className="w-3" />
          )}
          {/* 复选框 */}
          <input
            type="checkbox"
            className="w-3 h-3 accent-blue-600"
            checked={subtreeState === true}
            ref={(el) => {
              if (el) el.indeterminate = subtreeState === "indeterminate";
            }}
            onChange={toggleNode}
            onClick={(e) => e.stopPropagation()}
            disabled={isAllSelected}
          />
          {/* 代码 + 名称 */}
          <span
            className={`font-mono ${hasChildren ? "text-gray-600" : "text-gray-500"}`}
            onClick={toggleNode}
            style={{ cursor: isAllSelected ? "not-allowed" : "pointer" }}
          >
            {node.code}
          </span>
          <span onClick={hasChildren ? () => toggleDept(node.id) : toggleNode} style={{ cursor: "pointer" }}>
            {node.name}
          </span>
          {levelLabel && <span className="ml-1 text-[10px] text-gray-400">({levelLabel})</span>}
          {hasChildren && (
            <span className="ml-1 text-[10px] text-gray-400">
              ({collectDescendantLeaves(node).length}个叶子)
            </span>
          )}
        </div>
        {hasChildren && isOpen && node.children.map((c) => renderNode(c, depth + 1))}
      </div>
    );
  };

  if (!isOpen) return null;

  const selectedProducts = flatProducts.filter((p) => selectedCodes.has(p.code));

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[820px] h-[75vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-medium text-gray-800">选择产品科目（多选）</h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-200 rounded transition-colors">
            <X className="w-4 h-4 text-gray-600" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="px-3 py-2 bg-gray-100 border-b border-gray-200">
          <div className="flex items-center justify-between gap-2 mb-1">
            <h4 className="text-xs font-medium text-gray-700">产品科目层级树（勾选产品节点）</h4>
            <div className="flex flex-wrap items-center gap-1">
              <button type="button" onClick={collapseAll} className={treeToolbarButtonCompactClass}>
                全部收起
              </button>
              <button type="button" onClick={expandAll} className={treeToolbarButtonCompactClass}>
                全部展开
              </button>
              <button type="button" onClick={selectAllVisibleProducts} className={treeToolbarButtonCompactClass}>
                全选可见
              </button>
              <button type="button" onClick={clearAll} className={treeToolbarButtonCompactClass}>
                清除
              </button>
            </div>
          </div>
          <p className="text-[10px] text-gray-500 mb-2">
            勾选产品节点可多选；选择「适用所有产品科目」则数据对所有产品可见（与具体产品互斥）。
            {selectedCount > 0 && !isAllSelected && (
              <span className="ml-2 text-blue-600 font-medium">已选 {selectedCount} 个产品</span>
            )}
          </p>
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索产品代码或名称..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-full pl-8 pr-8 py-1 text-[10px] border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {searchText && (
              <button
                onClick={() => setSearchText("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded"
              >
                <X className="w-3 h-3 text-gray-500" />
              </button>
            )}
          </div>
        </div>

        {/* Tree */}
        <div className="flex-1 overflow-auto">
          {/* 全行选项 */}
          <div
            className={`flex items-center gap-1 px-2 py-1.5 text-xs border-b border-gray-100 cursor-pointer ${
              isAllSelected ? "bg-blue-100" : "hover:bg-blue-50"
            }`}
            style={{ paddingLeft: 8 }}
            onClick={toggleAllProducts}
          >
            <input
              type="checkbox"
              className="w-3 h-3 accent-blue-600"
              checked={isAllSelected}
              onChange={toggleAllProducts}
              onClick={(e) => e.stopPropagation()}
            />
            <Database className="w-3 h-3 text-purple-600" />
            <span className="font-mono text-gray-600">{ALL_PRODUCTS_PRODUCT_CODE}</span>
            <span>适用所有产品科目</span>
            <span className="ml-1 text-[10px] text-gray-400">（所有产品可见）</span>
          </div>

          {/* 产品树 */}
          {filterTree(tree).map((n) => renderNode(n))}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50">
          <div className="text-xs text-gray-600 mb-2 min-h-[20px]">
            {isAllSelected ? (
              <span className="text-blue-600">已选择：适用所有产品科目（数据对所有产品可见）</span>
            ) : selectedCodes.size === 0 ? (
              <span className="text-gray-400">未选择任何产品（效果等同于「适用所有产品」）</span>
            ) : (
              <span>
                已选择 {selectedCodes.size} 个产品：
                {selectedProducts
                  .slice(0, 5)
                  .map((p) => `${p.code} ${p.name}`)
                  .join("、")}
                {selectedProducts.length > 5 && `...等${selectedProducts.length}个`}
              </span>
            )}
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100"
            >
              取消
            </button>
            <button
              onClick={() => {
                onConfirm(selectedProducts, isAllSelected);
                onClose();
              }}
              className="px-4 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              确认
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
