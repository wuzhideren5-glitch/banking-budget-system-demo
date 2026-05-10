import { useEffect, useMemo, useState } from "react";
import { X, ChevronRight, ChevronDown, Building2, Database, Search } from "lucide-react";
import type { DeptAccountDto, DeptProductMappingDto } from "@/lib/api";
import { treeToolbarButtonCompactClass } from "@/lib/treeToolbarStyles";

type ProductNode = {
  id: string;
  code: string;
  name: string;
  type: "department" | "product";
  deptCode?: string;
  children: ProductNode[];
};

/** 数据科目「适用所有产品」选项码，与具体产品互斥 */
export const ALL_PRODUCTS_PRODUCT_CODE = "__ALL__";

interface ProductSelectorDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (product: { code: string; name: string }) => void;
  initialProduct?: string;
  /** 为 true 时在树上方显示「适用所有产品科目」首选项（数据科目维护用） */
  showAllProductsOption?: boolean;
  flatProducts: { code: string; name: string }[];
  deptAccounts: DeptAccountDto[];
  deptProductMappings: DeptProductMappingDto[];
}

function buildDeptProductTree(
  deptAccounts: DeptAccountDto[],
  deptProductMappings: DeptProductMappingDto[],
  flatProducts: { code: string; name: string }[]
): ProductNode[] {
  const productMap = new Map(flatProducts.map((p) => [p.code, p.name]));
  const deptNodes = new Map<string, ProductNode>();
  deptAccounts.forEach((d) => {
    deptNodes.set(d.dept_code, {
      id: `dept-${d.dept_code}`,
      code: d.dept_code,
      name: d.dept_name,
      type: "department",
      deptCode: d.dept_code,
      children: [],
    });
  });

  const roots: ProductNode[] = [];
  deptAccounts.forEach((d) => {
    const node = deptNodes.get(d.dept_code)!;
    if (d.parent_code && deptNodes.has(d.parent_code)) {
      deptNodes.get(d.parent_code)!.children.push(node);
    } else {
      roots.push(node);
    }
  });

  const mappedCodes = new Set<string>();
  deptProductMappings.forEach((m) => {
    const parent = deptNodes.get(m.dept_code);
    if (!parent) return;
    mappedCodes.add(m.product_code);
    parent.children.push({
      id: `prod-${m.product_code}-${m.dept_code}`,
      code: m.product_code,
      name: productMap.get(m.product_code) ?? "（未知产品）",
      type: "product",
      children: [],
    });
  });

  const unmapped = flatProducts.filter((p) => !mappedCodes.has(p.code));
  if (unmapped.length > 0) {
    roots.push({
      id: "dept-unmapped",
      code: "UNMAPPED",
      name: "未映射部门产品",
      type: "department",
      deptCode: "UNMAPPED",
      children: unmapped.map((p) => ({
        id: `prod-${p.code}-unmapped`,
        code: p.code,
        name: p.name,
        type: "product",
        children: [],
      })),
    });
  }

  const sortRec = (nodes: ProductNode[]) => {
    nodes.sort((a, b) => a.code.localeCompare(b.code, "zh-CN"));
    nodes.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}

export function ProductSelectorDialog({
  isOpen,
  onClose,
  onConfirm,
  initialProduct = "",
  showAllProductsOption = false,
  flatProducts,
  deptAccounts,
  deptProductMappings,
}: ProductSelectorDialogProps) {
  const [selectedProduct, setSelectedProduct] = useState<{ code: string; name: string } | null>(null);
  const [selectedDeptId, setSelectedDeptId] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const tree = useMemo(
    () => buildDeptProductTree(deptAccounts, deptProductMappings, flatProducts),
    [deptAccounts, deptProductMappings, flatProducts]
  );

  useEffect(() => {
    if (!isOpen) return;
    const nextExpanded: Record<string, boolean> = {};
    tree.forEach((n) => {
      if (n.type === "department") nextExpanded[n.id] = true;
    });
    setExpanded(nextExpanded);
    setSearchText("");
    setSelectedDeptId(null);
  }, [isOpen, tree]);

  useEffect(() => {
    if (!isOpen) return;
    const t = initialProduct.trim();
    if (showAllProductsOption && (t.includes("适用所有产品") || t.startsWith(ALL_PRODUCTS_PRODUCT_CODE))) {
      setSelectedProduct({ code: ALL_PRODUCTS_PRODUCT_CODE, name: "适用所有产品科目" });
      return;
    }
    const m = t.match(/^([A-Z]\d{4})\s*-\s*(.+)$/) || t.match(/^([A-Z]\d{4})$/);
    if (!m) {
      setSelectedProduct(null);
      return;
    }
    const code = m[1];
    const name = flatProducts.find((p) => p.code === code)?.name ?? (m[2] ?? "");
    setSelectedProduct({ code, name });
  }, [isOpen, initialProduct, flatProducts, showAllProductsOption]);

  const toggleDept = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const deptDepthMap = useMemo(() => {
    const map: Record<string, number> = {};
    const walk = (nodes: ProductNode[], depth: number) => {
      nodes.forEach((n) => {
        if (n.type === "department") map[n.id] = depth;
        if (n.children.length > 0) walk(n.children, depth + 1);
      });
    };
    walk(tree, 1);
    return map;
  }, [tree]);

  const collectDeptIdsAtDepth = (depth: number): string[] => {
    return Object.entries(deptDepthMap)
      .filter(([, d]) => d === depth)
      .map(([id]) => id);
  };

  const collectDeptSubtreeIds = (rootId: string): string[] => {
    const ids: string[] = [];
    const walk = (nodes: ProductNode[]) => {
      nodes.forEach((n) => {
        if (n.id === rootId && n.type === "department") {
          const collect = (node: ProductNode) => {
            if (node.type === "department") ids.push(node.id);
            node.children.forEach(collect);
          };
          collect(n);
          return;
        }
        if (n.children.length > 0) walk(n.children);
      });
    };
    walk(tree);
    return ids;
  };

  const setExpandedForIds = (ids: string[], value: boolean) => {
    setExpanded((prev) => {
      const next = { ...prev };
      ids.forEach((id) => {
        next[id] = value;
      });
      return next;
    });
  };

  const collapseCurrentLevelOnly = () => {
    if (selectedDeptId) {
      setExpandedForIds([selectedDeptId], false);
      return;
    }
    setExpandedForIds(collectDeptIdsAtDepth(1), false);
  };

  const expandNextLevelOnly = () => {
    if (selectedDeptId) {
      setExpandedForIds([selectedDeptId], true);
      return;
    }
    setExpandedForIds(collectDeptIdsAtDepth(1), true);
  };

  const collapseAllCurrentLevel = () => {
    const level = selectedDeptId ? (deptDepthMap[selectedDeptId] ?? 1) : 1;
    setExpandedForIds(collectDeptIdsAtDepth(level), false);
  };

  const expandAllChildren = () => {
    if (selectedDeptId) {
      setExpandedForIds(collectDeptSubtreeIds(selectedDeptId), true);
      return;
    }
    const allDeptIds = Object.keys(deptDepthMap);
    setExpandedForIds(allDeptIds, true);
  };

  const collapseAll = () => {
    setSearchText("");
    const allDeptIds = Object.keys(deptDepthMap);
    setExpandedForIds(allDeptIds, false);
  };

  const expandAll = () => {
    const allDeptIds = Object.keys(deptDepthMap);
    setExpandedForIds(allDeptIds, true);
  };

  if (!isOpen) return null;

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
    const isDept = node.type === "department";
    const isSelected = node.type === "product" && selectedProduct?.code === node.code;
    const isSelectedDept = isDept && selectedDeptId === node.id;
    const forceOpenBySearch = searchText.trim().length > 0;
    const isOpen = forceOpenBySearch || Boolean(expanded[node.id]);

    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-1 px-2 py-1.5 text-xs ${
            isSelected || isSelectedDept ? "bg-blue-100" : "hover:bg-blue-50"
          } ${
            isDept ? "font-medium text-gray-800" : "text-gray-700 cursor-pointer"
          }`}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => {
            if (isDept) {
              setSelectedDeptId(node.id);
              toggleDept(node.id);
            } else {
              setSelectedProduct({ code: node.code, name: node.name });
            }
          }}
          onDoubleClick={() => {
            if (!isDept) {
              onConfirm({ code: node.code, name: node.name });
              onClose();
            }
          }}
        >
          {hasChildren ? (
            isOpen ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />
          ) : (
            <span className="w-3" />
          )}
          {isDept ? <Building2 className="w-3 h-3 text-blue-600" /> : <Database className="w-3 h-3 text-purple-600" />}
          <span className="font-mono text-gray-600">{node.code}</span>
          <span>{node.name}</span>
        </div>
        {hasChildren && isOpen && node.children.map((c) => renderNode(c, depth + 1))}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[760px] h-[72vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-medium text-gray-800">选择产品科目</h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-200 rounded transition-colors">
            <X className="w-4 h-4 text-gray-600" />
          </button>
        </div>
        <div className="px-3 py-2 bg-gray-100 border-b border-gray-200">
          <div className="flex items-center justify-between gap-2 mb-1">
            <h4 className="text-xs font-medium text-gray-700">部门科目与产品科目树（仅可选择产品叶子）</h4>
            <div className="flex flex-wrap items-center gap-1">
              <button type="button" onClick={collapseCurrentLevelOnly} className={treeToolbarButtonCompactClass}>
                收起本级
              </button>
              <button type="button" onClick={expandNextLevelOnly} className={treeToolbarButtonCompactClass}>
                展开下级
              </button>
              <button type="button" onClick={collapseAllCurrentLevel} className={treeToolbarButtonCompactClass}>
                收起全部本级
              </button>
              <button type="button" onClick={expandAllChildren} className={treeToolbarButtonCompactClass}>
                展开全部下级
              </button>
              <button type="button" onClick={collapseAll} className={treeToolbarButtonCompactClass}>
                全部收起
              </button>
              <button type="button" onClick={expandAll} className={treeToolbarButtonCompactClass}>
                全部展开
              </button>
            </div>
          </div>
          <p className="text-[10px] text-gray-500 mb-2">
            {showAllProductsOption
              ? "首行可选「适用所有产品科目」（与具体产品互斥）；单击选择产品，双击确认；搜索时会自动展开匹配路径。"
              : "单击选择产品，双击确认；搜索时会自动展开匹配路径。"}
          </p>
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索部门或产品..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-full pl-8 pr-8 py-1 text-[10px] border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            {searchText && (
              <button onClick={() => setSearchText("")} className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded">
                <X className="w-3 h-3 text-gray-500" />
              </button>
            )}
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          {showAllProductsOption && (
            <div
              className={`flex items-center gap-1 px-2 py-1.5 text-xs border-b border-gray-100 ${
                selectedProduct?.code === ALL_PRODUCTS_PRODUCT_CODE
                  ? "bg-blue-100"
                  : "hover:bg-blue-50 text-gray-700 cursor-pointer"
              }`}
              style={{ paddingLeft: 8 }}
              onClick={() =>
                setSelectedProduct({ code: ALL_PRODUCTS_PRODUCT_CODE, name: "适用所有产品科目" })
              }
              onDoubleClick={() => {
                onConfirm({ code: ALL_PRODUCTS_PRODUCT_CODE, name: "适用所有产品科目" });
                onClose();
              }}
            >
              <span className="w-3" />
              <Database className="w-3 h-3 text-purple-600" />
              <span className="font-mono text-gray-600">{ALL_PRODUCTS_PRODUCT_CODE}</span>
              <span>适用所有产品科目</span>
            </div>
          )}
          {filterTree(tree).map((n) => renderNode(n))}
        </div>
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
          <div className="text-xs text-gray-600">
            {selectedProduct
              ? selectedProduct.code === ALL_PRODUCTS_PRODUCT_CODE
                ? "已选择：适用所有产品科目"
                : `已选择：${selectedProduct.code} - ${selectedProduct.name}`
              : "未选择产品"}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="px-4 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100">
              取消
            </button>
            <button
              onClick={() => {
                if (!selectedProduct) {
                  alert("请先选择一个产品科目");
                  return;
                }
                onConfirm(selectedProduct);
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
