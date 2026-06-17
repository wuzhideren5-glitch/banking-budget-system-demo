import type { BudgetSubjectCatalogDto } from "@/lib/expense/masterDataApi";

export type BudgetSubjectTreeNode = BudgetSubjectCatalogDto & { children: BudgetSubjectTreeNode[] };

export const MAX_BUDGET_SUBJECT_LEVEL = 5;

export function buildBudgetSubjectTree(rows: BudgetSubjectCatalogDto[]): BudgetSubjectTreeNode[] {
  const map = new Map<number, BudgetSubjectTreeNode>();
  rows.forEach((row) => map.set(row.id, { ...row, children: [] }));
  const roots: BudgetSubjectTreeNode[] = [];
  map.forEach((node) => {
    if (node.parent_id != null && map.has(node.parent_id)) {
      map.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  });
  const sortRecursively = (nodes: BudgetSubjectTreeNode[]) => {
    nodes.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
    nodes.forEach((node) => sortRecursively(node.children));
  };
  sortRecursively(roots);
  return roots;
}

export function filterBudgetSubjectTree(nodes: BudgetSubjectTreeNode[], term: string): BudgetSubjectTreeNode[] {
  const keyword = term.trim().toLowerCase();
  if (!keyword) return nodes;
  return nodes
    .map((node) => {
      const children = filterBudgetSubjectTree(node.children, keyword);
      const matched =
        node.subject_name.toLowerCase().includes(keyword) ||
        node.level_label.toLowerCase().includes(keyword) ||
        (node.manage_department ?? "").toLowerCase().includes(keyword) ||
        (node.formula_text ?? "").toLowerCase().includes(keyword);
      if (matched || children.length > 0) return { ...node, children };
      return null;
    })
    .filter((node): node is BudgetSubjectTreeNode => Boolean(node));
}

export function findBudgetSubjectTreeNodeById(
  nodes: BudgetSubjectTreeNode[],
  id: number,
): BudgetSubjectTreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = findBudgetSubjectTreeNodeById(node.children, id);
    if (child) return child;
  }
  return null;
}
