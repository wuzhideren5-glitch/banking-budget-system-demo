import type { DeptAccountDto } from "@/lib/expense/masterDataApi";

export type DeptTreeNode = DeptAccountDto & { children: DeptTreeNode[] };
export type DeptTreeEntityGroup = { entityName: string; nodes: DeptTreeNode[] };

export const MAX_DEPT_LEVEL = 2;
export const DEPT_ENTITY_ORDER = ["微众银行", "科技子", "科技孙"];
export const DEPT_GROUP_ORDER = [
  "个人金融事业群",
  "企业及机构金融事业群",
  "科技及智能事业群",
  "国际发展部",
  "国际业务",
  "资源管理及管控职能群",
  "其他",
  "历史架构",
  "科技子",
  "科技孙",
  "虚拟架构",
];

export function buildDeptTree(rows: DeptAccountDto[]): DeptTreeNode[] {
  const map = new Map<string, DeptTreeNode>();
  rows.forEach((row) => map.set(row.dept_code, { ...row, children: [] }));
  const roots: DeptTreeNode[] = [];
  map.forEach((node) => {
    if (node.parent_code && map.has(node.parent_code)) {
      map.get(node.parent_code)!.children.push(node);
    } else {
      roots.push(node);
    }
  });
  const sortRecursively = (nodes: DeptTreeNode[]) => {
    nodes.sort((a, b) => {
      const aGroupIndex = DEPT_GROUP_ORDER.indexOf(a.dept_name);
      const bGroupIndex = DEPT_GROUP_ORDER.indexOf(b.dept_name);
      const aGroupRank = aGroupIndex === -1 ? Number.MAX_SAFE_INTEGER : aGroupIndex;
      const bGroupRank = bGroupIndex === -1 ? Number.MAX_SAFE_INTEGER : bGroupIndex;
      if (a.level === 1 && b.level === 1) {
        const groupCompare = aGroupRank - bGroupRank;
        if (groupCompare !== 0) return groupCompare;
      }
      if (a.level === 2 && b.level === 2) {
        const lengthCompare = a.dept_name.length - b.dept_name.length;
        if (lengthCompare !== 0) return lengthCompare;
      }
      return a.dept_code.localeCompare(b.dept_code, "zh-CN");
    });
    nodes.forEach((node) => sortRecursively(node.children));
  };
  sortRecursively(roots);
  return roots;
}

export function filterDeptTree(nodes: DeptTreeNode[], term: string): DeptTreeNode[] {
  const keyword = term.trim().toLowerCase();
  if (!keyword) return nodes;
  return nodes
    .map((node) => {
      const children = filterDeptTree(node.children, keyword);
      const matched =
        node.dept_code.toLowerCase().includes(keyword) ||
        node.dept_name.toLowerCase().includes(keyword) ||
        node.entity_name.toLowerCase().includes(keyword);
      if (matched || children.length > 0) return { ...node, children };
      return null;
    })
    .filter((node): node is DeptTreeNode => Boolean(node));
}

export function sortDeptEntityNames(entityNames: Iterable<string>): string[] {
  return Array.from(new Set(entityNames))
    .map((name) => name || "微众银行")
    .sort((a, b) => {
      const leftIndex = DEPT_ENTITY_ORDER.indexOf(a);
      const rightIndex = DEPT_ENTITY_ORDER.indexOf(b);
      const leftRank = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
      const rightRank = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
      return leftRank - rightRank || a.localeCompare(b, "zh-CN");
    });
}

export function groupDeptTreeByEntity(nodes: DeptTreeNode[]): DeptTreeEntityGroup[] {
  const groups = new Map<string, DeptTreeNode[]>();
  for (const node of nodes) {
    const entityName = node.entity_name || "微众银行";
    if (!groups.has(entityName)) groups.set(entityName, []);
    groups.get(entityName)!.push(node);
  }
  return sortDeptEntityNames(groups.keys()).map((entityName) => ({
    entityName,
    nodes: groups.get(entityName) ?? [],
  }));
}

export function validateDeptCode(codeRaw: string, level: number, parentCode?: string): string | null {
  const code = codeRaw.trim().toUpperCase();
  if (!code) return "部门科目代码不能为空";
  if (level < 1 || level > MAX_DEPT_LEVEL) return `部门科目层级必须在 1-${MAX_DEPT_LEVEL} 级`;
  if (level === 1) {
    if (!/^Y\d{1,2}$/.test(code)) return "事业群代码格式错误，应为 Y + 1-2位数字（例如 Y1 或 Y01）";
    return null;
  }
  if (!parentCode) return "缺少上级部门代码，无法校验";
  const escapedParent = parentCode.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`^${escapedParent}\\d{1,2}$`);
  if (!pattern.test(code)) {
    return `费用归属部门代码格式错误，应为“上级代码 + 1-2位数字”（例如 ${parentCode}01）`;
  }
  return null;
}

export function nextChildDeptCode(parentCode: string, children: DeptTreeNode[]): string | null {
  const suffixNumbers = children
    .map((child) => child.dept_code)
    .filter((code) => code.startsWith(parentCode))
    .map((code) => code.slice(parentCode.length))
    .filter((suffix) => /^\d{1,2}$/.test(suffix))
    .map((suffix) => Number.parseInt(suffix, 10))
    .filter((value) => Number.isFinite(value));
  const max = suffixNumbers.length > 0 ? Math.max(...suffixNumbers) : -1;
  if (max >= 99) return null;
  return `${parentCode}${String(max + 1).padStart(2, "0")}`;
}

export function findDeptTreeNodeByCode(nodes: DeptTreeNode[], code: string): DeptTreeNode | null {
  for (const node of nodes) {
    if (node.dept_code === code) return node;
    const child = findDeptTreeNodeByCode(node.children, code);
    if (child) return child;
  }
  return null;
}
