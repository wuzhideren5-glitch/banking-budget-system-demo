import { useState } from "react";
import { ChevronRight, ChevronDown, Database, FileInput, BarChart3, Settings, HelpCircle } from "lucide-react";

interface TreeNode {
  id: string;
  label: string;
  icon: React.ReactNode;
  children?: TreeNode[];
}

const DISABLED_NODE_IDS = new Set(["analysis-report", "analysis-ppt"]);

function hasPermission(permissionType: number, required: number): boolean {
  if (permissionType === 1) return true;
  if (permissionType === 2) return required <= 2;
  return required <= 1;
}

function requiredPermissionByNodeId(id: string): number {
  if (id.startsWith("analysis") || id.startsWith("help")) return 1;
  if (id.startsWith("input")) return 2;
  return 3;
}

function filterTreeByPermission(nodes: TreeNode[], permissionType: number): TreeNode[] {
  const result: TreeNode[] = [];
  for (const node of nodes) {
    const required = requiredPermissionByNodeId(node.id);
    if (!hasPermission(permissionType, required)) {
      continue;
    }
    const filteredChildren = node.children
      ? node.children.filter((child) => hasPermission(permissionType, requiredPermissionByNodeId(child.id)))
      : undefined;
    result.push({
      ...node,
      children: filteredChildren,
    });
  }
  return result;
}

const treeData: TreeNode[] = [
  {
    id: "data",
    label: "基础数据维护",
    icon: <Database className="w-3.5 h-3.5" />,
    children: [
      { id: "data-account", label: "数据科目维护", icon: null },
      { id: "data-budget-subject", label: "部门预算科目维护", icon: null },
      { id: "data-report", label: "报告科目维护", icon: null },
      { id: "data-product", label: "产品科目维护", icon: null },
      { id: "data-department", label: "部门科目维护", icon: null },
    ],
  },
  {
    id: "input",
    label: "部门费用输入",
    icon: <FileInput className="w-3.5 h-3.5" />,
    children: [
      { id: "input-basic", label: "部门费用数据维护", icon: null },
      { id: "input-expense-actual-import", label: "费用执行明细导入", icon: null },
      { id: "input-expense-forecast", label: "费用预测表", icon: null },
    ],
  },
  {
    id: "analysis",
    label: "多维分析工具",
    icon: <BarChart3 className="w-3.5 h-3.5" />,
    children: [
      { id: "analysis-pivot-table-current", label: "当前可编辑年度多版本透视报表", icon: null },
      { id: "analysis-pivot-table-compare", label: "多年度对比透视报表", icon: null },
      { id: "analysis-expense-budget-execution", label: "费用预算执行报表", icon: null },
      { id: "analysis-pivot-chart", label: "多年度数据透视图", icon: null },
      { id: "analysis-report", label: "智能分析报告", icon: null },
      { id: "analysis-ppt", label: "智能演示PPT", icon: null },
    ],
  },
  {
    id: "config",
    label: "系统配置中心",
    icon: <Settings className="w-3.5 h-3.5" />,
    children: [
      { id: "config-user", label: "用户和权限管理", icon: null },
      { id: "config-system", label: "系统设定控制", icon: null },
      { id: "config-data-sync", label: "数据同步管理", icon: null },
      { id: "config-agent-debug", label: "Agent对话测试**", icon: null },
    ],
  },
  {
    id: "help",
    label: "帮助与使用说明",
    icon: <HelpCircle className="w-3.5 h-3.5" />,
    children: [
      { id: "help-guide", label: "使用说明", icon: null },
      { id: "help-faq", label: "常见问题", icon: null },
      { id: "help-contact", label: "联系管理员", icon: null },
    ],
  },
];

function TreeItem({ node, level = 0, onItemClick }: { node: TreeNode; level?: number; onItemClick?: (id: string, label: string) => void }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = node.children && node.children.length > 0;
  const isDisabledLeaf = !hasChildren && DISABLED_NODE_IDS.has(node.id);
  const isAgentDebugTest = node.id === "config-agent-debug";

  const handleClick = () => {
    if (hasChildren) {
      setIsExpanded(!isExpanded);
    } else {
      onItemClick?.(node.id, node.label);
    }
  };

  return (
    <div>
      <div
        className={`flex items-center gap-1.5 px-2 py-1.5 text-xs cursor-pointer hover:bg-gray-100 ${
          isDisabledLeaf ? "text-gray-400" : ""
        }`}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
        onClick={handleClick}
      >
        {hasChildren ? (
          isExpanded ? (
            <ChevronDown className="w-3 h-3 text-gray-500 flex-shrink-0" />
          ) : (
            <ChevronRight className="w-3 h-3 text-gray-500 flex-shrink-0" />
          )
        ) : (
          <span className="w-3" />
        )}
        {node.icon && <span className={isDisabledLeaf ? "text-gray-400" : "text-gray-600"}>{node.icon}</span>}
        <span className={isDisabledLeaf ? "text-gray-400" : isAgentDebugTest ? "text-amber-700 font-medium" : "text-gray-700"}>
          {node.label}
        </span>
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child) => (
            <TreeItem key={child.id} node={child} level={level + 1} onItemClick={onItemClick} />
          ))}
        </div>
      )}
    </div>
  );
}

export function NavigationTree({
  onItemClick,
  permissionType,
}: {
  onItemClick?: (id: string, label: string) => void;
  permissionType: number;
}) {
  const visibleTree = filterTreeByPermission(treeData, permissionType);
  return (
    <div className="h-full bg-[#f5f6fa] border-r border-gray-300 overflow-y-auto">
      <div className="py-2">
        {visibleTree.map((node) => (
          <TreeItem key={node.id} node={node} onItemClick={onItemClick} />
        ))}
      </div>
    </div>
  );
}
