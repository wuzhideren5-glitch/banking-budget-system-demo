import type {
  BusinessCostIncomeIndicatorFormat,
  BusinessCostIncomeItemDto,
  BusinessCostIncomeItemSection,
} from "@/lib/business/businessCostIncomeApi";

export type BusinessCostIncomeTreeItemNode = BusinessCostIncomeItemDto & {
  depth: number;
  children: BusinessCostIncomeTreeItemNode[];
};

export type BusinessCostIncomeTreeItemRow = BusinessCostIncomeTreeItemNode & {
  hasChildren: boolean;
  isExpanded: boolean;
};

export type BusinessCostIncomeLeafOption = {
  id: number;
  name: string;
  depth: number;
};

export const BUSINESS_COST_INCOME_SECTION_LABELS: Record<BusinessCostIncomeItemSection, string> = {
  input: "业务投入",
  output: "业务产出",
};

export const BUSINESS_COST_INCOME_FORMAT_LABELS: Record<BusinessCostIncomeIndicatorFormat, string> = {
  ratio: "比率",
  percent: "百分比(×100)",
  number: "数值",
};

export function buildBusinessCostIncomeTreeRows(
  items: BusinessCostIncomeItemDto[],
  section: BusinessCostIncomeItemSection
): Array<BusinessCostIncomeItemDto & { depth: number }> {
  const sectionItems = items.filter((it) => it.section === section);
  const childrenMap = new Map<number | null, BusinessCostIncomeItemDto[]>();
  for (const item of sectionItems) {
    const siblings = childrenMap.get(item.parent_id) ?? [];
    siblings.push(item);
    childrenMap.set(item.parent_id, siblings);
  }
  for (const siblings of childrenMap.values()) {
    siblings.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  }

  const rows: Array<BusinessCostIncomeItemDto & { depth: number }> = [];
  const walk = (parentId: number | null, depth: number) => {
    for (const child of childrenMap.get(parentId) ?? []) {
      rows.push({ ...child, depth });
      walk(child.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

export function buildBusinessCostIncomeItemTree(
  items: BusinessCostIncomeItemDto[],
  section: BusinessCostIncomeItemSection
): BusinessCostIncomeTreeItemNode[] {
  const treeRows = buildBusinessCostIncomeTreeRows(items, section);
  const nodeMap = new Map<number, BusinessCostIncomeTreeItemNode>();
  const roots: BusinessCostIncomeTreeItemNode[] = [];
  for (const row of treeRows) {
    nodeMap.set(row.id, { ...row, children: [] });
  }
  for (const row of treeRows) {
    const node = nodeMap.get(row.id);
    if (!node) continue;
    if (row.parent_id != null && nodeMap.has(row.parent_id)) {
      nodeMap.get(row.parent_id)?.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

export function businessCostIncomeItemExpandKey(
  section: BusinessCostIncomeItemSection,
  id: number
): string {
  return `${section}:${id}`;
}

export function flattenVisibleBusinessCostIncomeTree(
  nodes: BusinessCostIncomeTreeItemNode[],
  expanded: Record<string, boolean>,
  section: BusinessCostIncomeItemSection
): BusinessCostIncomeTreeItemRow[] {
  const rows: BusinessCostIncomeTreeItemRow[] = [];
  const walk = (list: BusinessCostIncomeTreeItemNode[]) => {
    for (const node of list) {
      const hasChildren = node.children.length > 0;
      const isExpanded = expanded[businessCostIncomeItemExpandKey(section, node.id)] ?? true;
      rows.push({ ...node, hasChildren, isExpanded });
      if (hasChildren && isExpanded) walk(node.children);
    }
  };
  walk(nodes);
  return rows;
}

export function buildBusinessCostIncomeLeafOptions(
  items: BusinessCostIncomeItemDto[],
  section: BusinessCostIncomeItemSection
): BusinessCostIncomeLeafOption[] {
  const sectionItems = items.filter((it) => it.section === section);
  const hasChildren = new Set<number>();
  for (const it of sectionItems) {
    if (it.parent_id != null) hasChildren.add(it.parent_id);
  }
  const leaves = sectionItems.filter((it) => !hasChildren.has(it.id));
  const treeRows = buildBusinessCostIncomeTreeRows(items, section);
  const depthMap = new Map(treeRows.map((r) => [r.id, r.depth]));
  return leaves.map((it) => ({
    id: it.id,
    name: it.name,
    depth: depthMap.get(it.id) ?? 0,
  }));
}
