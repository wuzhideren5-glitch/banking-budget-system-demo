import { useState, useRef, useEffect } from "react";
import { X, ChevronRight, ChevronDown, Building2, Database, ChevronsRight, ChevronsDown, ChevronUp, ChevronsUp, Search } from "lucide-react";

interface ProductNode {
  id: string;
  code: string;
  name: string;
  type: 'department' | 'team' | 'product';
  children?: ProductNode[];
  isExpanded?: boolean;
}

interface ProductSelectorDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (product: { code: string; name: string }) => void;
  initialProduct?: string;
}

export function ProductSelectorDialog({
  isOpen,
  onClose,
  onConfirm,
  initialProduct = ""
}: ProductSelectorDialogProps) {
  const [selectedProduct, setSelectedProduct] = useState<{ code: string; name: string } | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string } | null>(null);
  const [searchText, setSearchText] = useState("");
  const contextMenuRef = useRef<HTMLDivElement>(null);

  const [treeData, setTreeData] = useState<ProductNode[]>([
    {
      id: "dept1",
      code: "Y11",
      name: "零售银行部",
      type: "department",
      isExpanded: true,
      children: [
        {
          id: "team1-1",
          code: "Y111",
          name: "个人信贷团队",
          type: "team",
          isExpanded: true,
          children: [
            { id: "prod1", code: "Z0001", name: "个人住房贷款", type: "product" },
            { id: "prod2", code: "Z0005", name: "汽车消费贷款", type: "product" },
          ]
        },
        {
          id: "team1-2",
          code: "Y112",
          name: "零售存款团队",
          type: "team",
          isExpanded: false,
          children: [
            { id: "prod3", code: "Z0017", name: "零售存款", type: "product" },
          ]
        },
        {
          id: "team1-3",
          code: "Y113",
          name: "信用卡中心",
          type: "team",
          isExpanded: false,
          children: [
            { id: "prod4", code: "Z0006", name: "信用卡产品", type: "product" },
          ]
        }
      ]
    },
    {
      id: "dept2",
      code: "Y12",
      name: "公司银行部",
      type: "department",
      isExpanded: true,
      children: [
        {
          id: "team2-1",
          code: "Y121",
          name: "公司贷款团队",
          type: "team",
          isExpanded: false,
          children: [
            { id: "prod5", code: "Z0002", name: "企业流动资金贷款", type: "product" },
            { id: "prod6", code: "Z0011", name: "项目贷款", type: "product" },
          ]
        },
        {
          id: "team2-2",
          code: "Y122",
          name: "对公存款团队",
          type: "team",
          isExpanded: false,
          children: [
            { id: "prod7", code: "Z0018", name: "对公存款", type: "product" },
          ]
        }
      ]
    },
    {
      id: "dept3",
      code: "Y13",
      name: "金融市场部",
      type: "department",
      isExpanded: false,
      children: [
        {
          id: "team3-1",
          code: "Y131",
          name: "理财业务团队",
          type: "team",
          isExpanded: false,
          children: [
            { id: "prod8", code: "Z0003", name: "结构性存款", type: "product" },
            { id: "prod9", code: "Z0004", name: "理财产品A", type: "product" },
          ]
        },
        {
          id: "team3-2",
          code: "Y132",
          name: "同业业务团队",
          type: "team",
          isExpanded: false,
          children: [
            { id: "prod10", code: "Z0019", name: "同业存款", type: "product" },
          ]
        }
      ]
    }
  ]);

  // 当对话框打开时，重置搜索文本
  useEffect(() => {
    if (isOpen) {
      setSearchText("");
    }
  }, [isOpen]);

  // 关闭右键菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };

    if (contextMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [contextMenu]);

  if (!isOpen) return null;

  const toggleNode = (nodeId: string) => {
    const toggleInTree = (nodes: ProductNode[]): ProductNode[] => {
      return nodes.map(node => {
        if (node.id === nodeId) {
          return { ...node, isExpanded: !node.isExpanded };
        }
        if (node.children) {
          return { ...node, children: toggleInTree(node.children) };
        }
        return node;
      });
    };
    setTreeData(toggleInTree(treeData));
  };

  // 展开到指定层级
  const expandToLevel = (level: number) => {
    const expandNodes = (nodes: ProductNode[], currentLevel: number = 1): ProductNode[] => {
      return nodes.map(node => {
        if (node.children) {
          return {
            ...node,
            isExpanded: currentLevel < level,
            children: expandNodes(node.children, currentLevel + 1)
          };
        }
        return node;
      });
    };
    setTreeData(expandNodes(treeData));
    setContextMenu(null);
  };

  // 展开指定节点的所有子节点
  const expandNodeChildren = (nodeId: string) => {
    const expandChildren = (nodes: ProductNode[]): ProductNode[] => {
      return nodes.map(node => {
        if (node.id === nodeId && node.children) {
          const expandAllChildren = (children: ProductNode[]): ProductNode[] => {
            return children.map(child => ({
              ...child,
              isExpanded: true,
              children: child.children ? expandAllChildren(child.children) : undefined
            }));
          };
          return { ...node, isExpanded: true, children: expandAllChildren(node.children) };
        }
        if (node.children) {
          return { ...node, children: expandChildren(node.children) };
        }
        return node;
      });
    };
    setTreeData(expandChildren(treeData));
    setContextMenu(null);
  };

  // 全部展开
  const expandAll = () => {
    const expandAllNodes = (nodes: ProductNode[]): ProductNode[] => {
      return nodes.map(node => ({
        ...node,
        isExpanded: true,
        children: node.children ? expandAllNodes(node.children) : undefined
      }));
    };
    setTreeData(expandAllNodes(treeData));
    setContextMenu(null);
  };

  // 收起指定节点
  const collapseNode = (nodeId: string) => {
    const collapseInTree = (nodes: ProductNode[]): ProductNode[] => {
      return nodes.map(node => {
        if (node.id === nodeId) {
          return { ...node, isExpanded: false };
        }
        if (node.children) {
          return { ...node, children: collapseInTree(node.children) };
        }
        return node;
      });
    };
    setTreeData(collapseInTree(treeData));
    setContextMenu(null);
  };

  // 全部收起
  const collapseAll = () => {
    const collapseAllNodes = (nodes: ProductNode[]): ProductNode[] => {
      return nodes.map(node => ({
        ...node,
        isExpanded: false,
        children: node.children ? collapseAllNodes(node.children) : undefined
      }));
    };
    setTreeData(collapseAllNodes(treeData));
    setContextMenu(null);
  };

  // 右键菜单
  const handleContextMenu = (e: React.MouseEvent, nodeId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, nodeId });
  };

  const handleProductClick = (product: { code: string; name: string }) => {
    setSelectedProduct(product);
  };

  const handleDoubleClick = (product: { code: string; name: string }) => {
    onConfirm(product);
    onClose();
  };

  const handleConfirm = () => {
    if (selectedProduct) {
      onConfirm(selectedProduct);
      onClose();
    } else {
      alert('请先选择一个产品科目');
    }
  };

  // 搜索过滤函数
  const filterTree = (nodes: ProductNode[], searchTerm: string): ProductNode[] => {
    if (!searchTerm) return nodes;

    const searchLower = searchTerm.toLowerCase();

    return nodes.filter(node => {
      const matchesCurrent =
        node.code.toLowerCase().includes(searchLower) ||
        node.name.toLowerCase().includes(searchLower);

      if (node.children && node.children.length > 0) {
        const filteredChildren = filterTree(node.children, searchTerm);
        if (filteredChildren.length > 0) {
          return true;
        }
      }

      return matchesCurrent;
    }).map(node => {
      if (node.children && node.children.length > 0) {
        return {
          ...node,
          isExpanded: true, // 搜索时自动展开
          children: filterTree(node.children, searchTerm)
        };
      }
      return node;
    });
  };

  const renderTreeNode = (node: ProductNode, level: number = 0) => {
    const hasChildren = node.children && node.children.length > 0;
    const paddingLeft = level * 16;
    const isProduct = node.type === 'product';
    const isSelected = selectedProduct?.code === node.code && isProduct;

    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-1 px-2 py-1.5 cursor-pointer text-xs ${
            isSelected ? 'bg-blue-100' : 'hover:bg-blue-50'
          } ${
            node.type === 'department' ? 'font-medium text-gray-800' :
            node.type === 'team' ? 'font-medium text-gray-700' :
            'text-gray-700'
          }`}
          style={{ paddingLeft: `${paddingLeft + 8}px` }}
          onClick={() => {
            if (hasChildren) {
              toggleNode(node.id);
            } else if (isProduct) {
              handleProductClick({ code: node.code, name: node.name });
            }
          }}
          onDoubleClick={() => isProduct && handleDoubleClick({ code: node.code, name: node.name })}
          onContextMenu={(e) => handleContextMenu(e, node.id)}
        >
          {hasChildren ? (
            node.isExpanded ? (
              <ChevronDown className="w-3 h-3 text-gray-500 flex-shrink-0" />
            ) : (
              <ChevronRight className="w-3 h-3 text-gray-500 flex-shrink-0" />
            )
          ) : (
            <span className="w-3" />
          )}

          {node.type === 'department' ? (
            <Building2 className="w-3 h-3 text-blue-600 flex-shrink-0" />
          ) : node.type === 'team' ? (
            <Building2 className="w-3 h-3 text-green-600 flex-shrink-0" />
          ) : (
            <Database className="w-3 h-3 text-purple-600 flex-shrink-0" />
          )}

          <span className="font-mono text-gray-600">{node.code}</span>
          <span>{node.name}</span>

          {isProduct && (
            <span className="ml-auto text-[10px] text-gray-400">双击选择</span>
          )}
        </div>

        {hasChildren && node.isExpanded && (
          <div>
            {node.children?.map(child => renderTreeNode(child, level + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[600px] h-[70vh] flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-medium text-gray-800">选择产品科目</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
          >
            <X className="w-4 h-4 text-gray-600" />
          </button>
        </div>

        {/* 主体内容 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="px-3 py-2 bg-gray-100 border-b border-gray-200">
            <div className="flex items-center justify-between mb-1">
              <h4 className="text-xs font-medium text-gray-700">部门与产品列表</h4>
              <div className="flex flex-wrap gap-1">
                <button
                  onClick={() => expandToLevel(2)}
                  className="px-2 py-0.5 text-[10px] bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-100 transition-colors"
                  title="展开1级"
                >
                  展开1级
                </button>
                <button
                  onClick={() => expandToLevel(3)}
                  className="px-2 py-0.5 text-[10px] bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-100 transition-colors"
                  title="展开2级"
                >
                  展开2级
                </button>
                <button
                  onClick={() => expandAll()}
                  className="px-2 py-0.5 text-[10px] bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-100 transition-colors"
                  title="全部展开"
                >
                  全部展开
                </button>
                <button
                  onClick={() => collapseAll()}
                  className="px-2 py-0.5 text-[10px] bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-100 transition-colors"
                  title="全部收起"
                >
                  全部收起
                </button>
              </div>
            </div>
            <p className="text-[10px] text-gray-500 mb-2">单击选择，双击确认</p>
            <div className="relative">
              <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="搜索产品..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="w-full pl-8 pr-8 py-1 text-[10px] border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {searchText && (
                <button
                  onClick={() => setSearchText("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded transition-colors"
                  title="清除搜索"
                >
                  <X className="w-3 h-3 text-gray-500" />
                </button>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-auto">
            {filterTree(treeData, searchText).map(node => renderTreeNode(node))}
          </div>
        </div>

        {/* 底部状态栏 */}
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center justify-between">
            <div className="flex-1 text-xs text-gray-600">
              {selectedProduct ? (
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-700">已选择:</span>
                  <span className="font-mono bg-white px-3 py-1 rounded border border-gray-300 text-gray-800">
                    {selectedProduct.code} - {selectedProduct.name}
                  </span>
                </div>
              ) : (
                <span className="text-gray-400">未选择产品</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="px-4 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleConfirm}
                className="px-4 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                确认
              </button>
            </div>
          </div>
        </div>

        {/* 右键菜单 */}
        {contextMenu && (
          <div
            ref={contextMenuRef}
            className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[140px]"
            style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
          >
            <button
              onClick={() => expandToLevel(2)}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-blue-50 flex items-center gap-2"
            >
              <ChevronsRight className="w-3 h-3" />
              展开1级
            </button>
            <button
              onClick={() => expandToLevel(3)}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-blue-50 flex items-center gap-2"
            >
              <ChevronsRight className="w-3 h-3" />
              展开2级
            </button>
            <button
              onClick={() => expandNodeChildren(contextMenu.nodeId)}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-blue-50 flex items-center gap-2"
            >
              <ChevronsDown className="w-3 h-3" />
              展开下级
            </button>
            <button
              onClick={() => expandAll()}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-green-50 flex items-center gap-2"
            >
              <ChevronsDown className="w-3 h-3" />
              全部展开
            </button>
            <div className="border-t border-gray-200 my-1"></div>
            <button
              onClick={() => collapseNode(contextMenu.nodeId)}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-orange-50 flex items-center gap-2"
            >
              <ChevronUp className="w-3 h-3" />
              收起本级
            </button>
            <button
              onClick={() => collapseAll()}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-red-50 flex items-center gap-2"
            >
              <ChevronsUp className="w-3 h-3" />
              全部收起
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
