import { useState } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import {
  filterWorkspaceTreeByPermission,
  workspaceTree,
  type WorkspaceNode,
} from "@/app/workspaceCatalog";

function TreeItem({ node, level = 0, onItemClick }: { node: WorkspaceNode; level?: number; onItemClick?: (id: string, label: string) => void }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = node.children && node.children.length > 0;

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
        className="bb-tree-item"
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
        {node.icon && <span className="text-slate-600">{node.icon}</span>}
        <span className={node.diagnostic ? "text-amber-700 font-medium" : "text-gray-700"}>
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
  const visibleTree = filterWorkspaceTreeByPermission(workspaceTree, permissionType);
  return (
    <div className="bb-tree-pane h-full">
      <div className="py-2">
        {visibleTree.map((node) => (
          <TreeItem key={node.id} node={node} onItemClick={onItemClick} />
        ))}
      </div>
    </div>
  );
}
