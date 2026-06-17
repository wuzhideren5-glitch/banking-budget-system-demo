/** 机构及产品树 · 共享类型、默认树、迁移与工具函数 */

export type OrgProductNodeType = "level0" | "level1" | "level2" | "level3";

export type OrgProductNode = {
  id: string;
  code: string;
  name: string;
  type: OrgProductNodeType;
  children: OrgProductNode[];
};

/** 与 D:\预算预测AI开发\基础数据\机构及产品.xlsx 一致（2026-05） */
export const DEFAULT_ORG_PRODUCT_TREE: OrgProductNode = {
  id: "node-root",
  code: "AAA",
  name: "微众集团",
  type: "level0",
  children: [
    {
      id: "node-aa",
      code: "AA",
      name: "微众银行",
      type: "level1",
      children: [
        {
          id: "node-a",
          code: "A",
          name: "个金群",
          type: "level2",
          children: [
            { id: "node-a01", code: "A01", name: "泛微粒贷", type: "level3", children: [] },
            { id: "node-a02", code: "A02", name: "微账户", type: "level3", children: [] },
            { id: "node-a03", code: "A03", name: "汽车金融", type: "level3", children: [] },
            { id: "node-a04", code: "A04", name: "财富", type: "level3", children: [] },
            { id: "node-a05", code: "A05", name: "小鹅", type: "level3", children: [] },
          ],
        },
        {
          id: "node-b",
          code: "B",
          name: "企金群",
          type: "level2",
          children: [
            { id: "node-b01", code: "B01", name: "企业金融", type: "level3", children: [] },
            { id: "node-b02", code: "B02", name: "金融市场", type: "level3", children: [] },
          ],
        },
        {
          id: "node-c",
          code: "C",
          name: "数字金融",
          type: "level2",
          children: [
            { id: "node-c01", code: "C01", name: "国内业务", type: "level3", children: [] },
            { id: "node-c02", code: "C02", name: "国内研发", type: "level3", children: [] },
          ],
        },
        {
          id: "node-d",
          code: "D",
          name: "国际业务",
          type: "level2",
          children: [{ id: "node-d01", code: "D01", name: "国际业务", type: "level3", children: [] }],
        },
        {
          id: "node-e",
          code: "E",
          name: "小鹅导流",
          type: "level2",
          children: [{ id: "node-e01", code: "E01", name: "小鹅导流", type: "level3", children: [] }],
        },
        {
          id: "node-f",
          code: "F",
          name: "司库及其他",
          type: "level2",
          children: [{ id: "node-f01", code: "F01", name: "司库及其他", type: "level3", children: [] }],
        },
      ],
    },
    {
      id: "node-ab",
      code: "AB",
      name: "微众科技",
      type: "level1",
      children: [],
    },
  ],
};

export function cloneDefaultOrgProductTree(): OrgProductNode {
  return JSON.parse(JSON.stringify(DEFAULT_ORG_PRODUCT_TREE)) as OrgProductNode;
}

export function normalizeOrgProductNodeType(raw: unknown): OrgProductNodeType {
  const t = String(raw || "").trim();
  if (t === "level0" || t === "level1" || t === "level2" || t === "level3") return t;
  return "level3";
}

export function normalizeOrgProductTree(raw: unknown): OrgProductNode | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Partial<OrgProductNode>;
  if (typeof obj.id !== "string" || typeof obj.code !== "string" || typeof obj.name !== "string") return null;
  const children = Array.isArray((obj as OrgProductNode).children)
    ? ((obj as OrgProductNode).children as unknown[])
        .map((c) => normalizeOrgProductTree(c))
        .filter((c): c is OrgProductNode => Boolean(c))
    : [];
  return {
    id: obj.id,
    code: obj.code.trim().toUpperCase(),
    name: String(obj.name || "").trim(),
    type: normalizeOrgProductNodeType(obj.type),
    children,
  };
}

/** 旧版 AA 为根 (level1) → 包裹为 AAA 集团根 */
export function migrateLegacyOrgProductTree(raw: OrgProductNode): OrgProductNode {
  if (raw.type === "level0" && raw.code === "AAA") {
    return raw;
  }
  if (raw.type === "level1" && raw.code === "AA") {
    return {
      id: "node-root",
      code: "AAA",
      name: "微众集团",
      type: "level0",
      children: [{ ...raw, id: raw.id === "node-root" ? "node-aa" : raw.id, type: "level1" }],
    };
  }
  return raw;
}

export function prepareOrgProductTreeFromStorage(raw: unknown): OrgProductNode {
  const normalized = normalizeOrgProductTree(raw);
  if (!normalized) return cloneDefaultOrgProductTree();
  return migrateLegacyOrgProductTree(normalized);
}

export function orgLevelLabel(type: OrgProductNodeType): string {
  if (type === "level0") return "集团";
  if (type === "level1") return "主体";
  if (type === "level2") return "机构";
  return "产品";
}

export function orgLevelBadgeClass(type: OrgProductNodeType): string {
  if (type === "level0") return "bg-violet-100 text-violet-800";
  if (type === "level1") return "bg-blue-100 text-blue-700";
  if (type === "level2") return "bg-emerald-100 text-emerald-700";
  return "bg-amber-100 text-amber-700";
}

export function orgLevelExcelLabel(type: OrgProductNodeType): string {
  if (type === "level0") return "一级";
  if (type === "level1") return "二级";
  if (type === "level2") return "三级";
  return "四级";
}

export function childTypeForParent(parentType: OrgProductNodeType): OrgProductNodeType | null {
  if (parentType === "level0") return "level1";
  if (parentType === "level1") return "level2";
  if (parentType === "level2") return "level3";
  return null;
}

export function collectOrgNodes(node: OrgProductNode): OrgProductNode[] {
  return [node, ...node.children.flatMap(collectOrgNodes)];
}

export function findOrgNodeById(root: OrgProductNode | null, id: string): OrgProductNode | null {
  if (!root) return null;
  if (root.id === id) return root;
  for (const child of root.children) {
    const hit = findOrgNodeById(child, id);
    if (hit) return hit;
  }
  return null;
}

export function findOrgNodeByCode(root: OrgProductNode | null, code: string): OrgProductNode | null {
  const c = code.trim().toUpperCase();
  return collectOrgNodes(root ?? DEFAULT_ORG_PRODUCT_TREE).find((n) => n.code === c) ?? null;
}

export function findOrgNodePath(root: OrgProductNode | null, id: string): OrgProductNode[] {
  if (!root) return [];
  const walk = (node: OrgProductNode, trail: OrgProductNode[]): OrgProductNode[] | null => {
    const next = [...trail, node];
    if (node.id === id) return next;
    for (const c of node.children) {
      const hit = walk(c, next);
      if (hit) return hit;
    }
    return null;
  };
  return walk(root, []) ?? [];
}

export function findOrgNodePathByCode(root: OrgProductNode | null, code: string): OrgProductNode[] {
  const node = findOrgNodeByCode(root, code);
  if (!node) return [];
  return findOrgNodePath(root, node.id);
}

export function buildOrgExpandedState(node: OrgProductNode): Record<string, boolean> {
  const expanded: Record<string, boolean> = {};
  const walk = (current: OrgProductNode) => {
    if (current.children.length > 0) expanded[current.id] = true;
    current.children.forEach(walk);
  };
  walk(node);
  return expanded;
}

/** 微众银行 AA：原 node-root 对应的全套指标表 */
export function isAaBankNode(node: OrgProductNode | null | undefined): boolean {
  return Boolean(node && node.type === "level1" && node.code === "AA");
}

/** 集团根 AAA（导航用；无单机构指标表，集团视图走矩阵报表） */
export function isGroupRootNode(node: OrgProductNode | null | undefined): boolean {
  return Boolean(node && node.type === "level0");
}

/**
 * AA 微众银行 · 单机构指标表清单（仅维护入口，不含矩阵专用表）。
 * 产品利润表、风险驱动表、净利息驱动表等 → 预测输出 · 矩阵报表。
 */
export const AA_BANK_METRIC_TABLE_NAMES = [
  "业务状况表",
  "损益表",
  "资产负债表（余额）",
  "资产负债表（日均）",
  "资产质量表",
  "利息净收入表",
] as const;

export type MetricTableCatalogScope = "AA" | "AB" | "PRODUCT";
export type MetricTableCatalogStatus = "active" | "inactive";

export type MetricTableCatalogItem = {
  id: number;
  entity_scope: MetricTableCatalogScope;
  table_name: string;
  sort_order: number;
  status: MetricTableCatalogStatus;
  remark: string;
  updated_at?: string;
};

const AB_DEFAULT_METRIC_TABLE_NAMES = ["业务状况表", "损益表"] as const;
const PRODUCT_DEFAULT_METRIC_TABLE_NAMES = ["业务状况表"] as const;

export function metricTableEntityScopeForNode(
  node: OrgProductNode | null | undefined
): MetricTableCatalogScope | null {
  if (!node || isGroupRootNode(node)) return null;
  if (isAaBankNode(node)) return "AA";
  if (node.type === "level1" && node.code === "AB") return "AB";
  return "PRODUCT";
}

export function activeCatalogTableNamesForScope(
  catalog: MetricTableCatalogItem[] | null | undefined,
  scope: MetricTableCatalogScope
): string[] {
  if (!catalog?.length) return [];
  return catalog
    .filter((row) => row.entity_scope === scope && row.status === "active")
    .sort(
      (a, b) =>
        a.sort_order - b.sort_order ||
        a.table_name.localeCompare(b.table_name, "zh-CN")
    )
    .map((row) => row.table_name);
}

export function fallbackMetricTableNamesForScope(scope: MetricTableCatalogScope): readonly string[] {
  if (scope === "AA") return AA_BANK_METRIC_TABLE_NAMES;
  if (scope === "AB") return AB_DEFAULT_METRIC_TABLE_NAMES;
  return PRODUCT_DEFAULT_METRIC_TABLE_NAMES;
}

/** AA 已下线指标表（矩阵专用等），加载时删除 */
export const AA_REMOVED_METRIC_TABLE_NAMES = [
  "产品利润表",
  "风险驱动表",
  "净利息驱动表",
] as const;

const AA_REMOVED_METRIC_TABLE_NAME_SET = new Set<string>(AA_REMOVED_METRIC_TABLE_NAMES);

/** AA 旧表名 → 现行表名（合并科目数据） */
export const AA_METRIC_TABLE_RENAME_MAP: Record<string, string> = {
  资产负债表: "资产负债表（余额）",
  净利息收入表: "利息净收入表",
};

/** 指标表名比较键（全角/半角括号等价） */
export function normalizeMetricTableNameKey(name: string): string {
  return String(name || "")
    .trim()
    .replace(/（/g, "(")
    .replace(/）/g, ")");
}

export function canonicalMetricTableNameInList(
  name: string,
  allowedNames: readonly string[]
): string | null {
  const trimmed = String(name || "").trim();
  if (!trimmed || AA_REMOVED_METRIC_TABLE_NAME_SET.has(trimmed)) return null;
  const renamed =
    AA_METRIC_TABLE_RENAME_MAP[trimmed] ??
    AA_METRIC_TABLE_RENAME_MAP[normalizeMetricTableNameKey(trimmed)] ??
    trimmed;
  const key = normalizeMetricTableNameKey(renamed);
  const hit = allowedNames.find((tableName) => normalizeMetricTableNameKey(tableName) === key);
  return hit ?? null;
}

export function canonicalAaMetricTableName(name: string): string | null {
  return canonicalMetricTableNameInList(name, AA_BANK_METRIC_TABLE_NAMES);
}

/** 清理 AA 本地/缓存中的废弃指标表，并按现行清单排序 */
/** Excel 工作表名匹配候选：机构及产品代码 + 指标表名称 */
export function buildMetricSheetMatchCandidates(
  tree: OrgProductNode,
  catalog?: MetricTableCatalogItem[] | null
): Array<{
  entity_code: string;
  entity_name: string;
  table_name: string;
}> {
  const out: Array<{ entity_code: string; entity_name: string; table_name: string }> = [];
  const seen = new Set<string>();
  const push = (entity_code: string, entity_name: string, table_name: string) => {
    const key = `${entity_code}::${normalizeMetricTableNameKey(table_name)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ entity_code, entity_name, table_name });
  };
  collectOrgNodes(tree).forEach((node) => {
    if (!supportsMetricDefinition(node)) return;
    const code = String(node.code || "").trim();
    if (!code) return;
    const entity_name = String(node.name || "").trim();
    for (const tableName of metricTableNamesForOrgNode(node, catalog)) {
      push(code, entity_name, tableName);
    }
    if (isAaBankNode(node)) {
      push(code, entity_name, "净利息收入表");
    }
  });
  return out;
}

export function pruneMetricTablesToCatalog<T extends { id: string; name: string; metrics: unknown[] }>(
  tables: T[],
  allowedNames: readonly string[],
  buildTableId: (name: string) => string,
  canonicalize: (name: string) => string | null = (name) => canonicalMetricTableNameInList(name, allowedNames)
): T[] {
  const merged = new Map<string, T>();
  for (const table of tables) {
    const canonical = canonicalize(table.name);
    if (!canonical) continue;
    const prev = merged.get(canonical);
    const metrics = Array.isArray(table.metrics) ? table.metrics : [];
    if (!prev) {
      merged.set(canonical, { ...table, name: canonical, id: buildTableId(canonical), metrics });
      continue;
    }
    const prevMetrics = Array.isArray(prev.metrics) ? prev.metrics : [];
    if (prevMetrics.length === 0 && metrics.length > 0) {
      merged.set(canonical, { ...prev, metrics });
    }
  }
  return allowedNames.map((name) => {
    const found = merged.get(name);
    if (found) return found;
    return { id: buildTableId(name), name, metrics: [] } as unknown as T;
  });
}

/** @deprecated 使用 pruneMetricTablesToCatalog */
export function pruneAaLegacyMetricTables<T extends { id: string; name: string; metrics: unknown[] }>(
  tables: T[],
  buildTableId: (name: string) => string
): T[] {
  return pruneMetricTablesToCatalog(tables, AA_BANK_METRIC_TABLE_NAMES, buildTableId, canonicalAaMetricTableName);
}

/** 停用中的指标表：保留在内存/本地存储，仅 UI 与导入候选隐藏 */
export function appendInactiveCatalogMetricTables<T extends { id: string; name: string; metrics: unknown[] }>(
  tables: T[],
  rawExisting: T[],
  scope: MetricTableCatalogScope | null,
  catalog: MetricTableCatalogItem[] | null | undefined,
  buildTableId: (name: string) => string
): T[] {
  if (!scope || !catalog?.length) return tables;
  const out = [...tables];
  for (const row of catalog) {
    if (row.entity_scope !== scope || row.status !== "inactive") continue;
    const key = normalizeMetricTableNameKey(row.table_name);
    if (out.some((t) => normalizeMetricTableNameKey(t.name) === key)) continue;
    const preserved = rawExisting.find((t) => normalizeMetricTableNameKey(t.name) === key);
    if (preserved) {
      out.push({
        ...preserved,
        id: buildTableId(row.table_name),
        name: row.table_name,
      });
    }
  }
  return out;
}

/** 是否可在「机构及产品指标 / 数据录入」维护指标表 */
export function supportsMetricDefinition(node: OrgProductNode | null | undefined): boolean {
  if (!node) return false;
  return !isGroupRootNode(node);
}

/** 某主体可用的指标表名称列表（优先指标表目录，否则内置默认） */
export function metricTableNamesForOrgNode(
  node: OrgProductNode | null | undefined,
  catalog?: MetricTableCatalogItem[] | null
): readonly string[] {
  if (!node || isGroupRootNode(node)) return [];
  const scope = metricTableEntityScopeForNode(node);
  if (!scope) return [];
  const fromCatalog = activeCatalogTableNamesForScope(catalog, scope);
  if (fromCatalog.length > 0) return fromCatalog;
  return fallbackMetricTableNamesForScope(scope);
}

/** @deprecated 使用 isAaBankNode；AAA 不再视为「全表主体」 */
export function isFullTableEntity(node: OrgProductNode | null | undefined): boolean {
  return isAaBankNode(node);
}

export function migrateMetricEntityIdMap(
  tree: OrgProductNode,
  tablesByEntityId: Record<string, unknown>
): Record<string, unknown> {
  if (tree.type !== "level0" || tree.code !== "AAA") return tablesByEntityId;
  const aa = tree.children.find((c) => c.code === "AA");
  if (!aa) return tablesByEntityId;
  const legacy = tablesByEntityId["node-root"];
  if (!legacy || tablesByEntityId[aa.id]) return tablesByEntityId;
  return { ...tablesByEntityId, [aa.id]: legacy };
}
