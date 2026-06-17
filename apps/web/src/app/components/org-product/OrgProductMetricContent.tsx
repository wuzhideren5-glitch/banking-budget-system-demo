import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  BadgePlus,
  Building,
  Building2,
  Calculator,
  ChevronDown,
  ChevronRight,
  Download,
  Edit3,
  Upload,
  Package2,
  Save,
  Search,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import {
  buildOrgExpandedState,
  cloneDefaultOrgProductTree,
  collectOrgNodes,
  findOrgNodeByCode,
  findOrgNodeById,
  AA_BANK_METRIC_TABLE_NAMES,
  activeCatalogTableNamesForScope,
  appendInactiveCatalogMetricTables,
  isAaBankNode,
  metricTableEntityScopeForNode,
  metricTableNamesForOrgNode,
  migrateMetricEntityIdMap,
  buildMetricSheetMatchCandidates,
  canonicalMetricTableNameInList,
  normalizeMetricTableNameKey,
  pruneMetricTablesToCatalog,
  supportsMetricDefinition,
  prepareOrgProductTreeFromStorage,
  type MetricTableCatalogItem,
  type OrgProductNode,
} from "@/lib/org-product/orgProductTree";
// API calls migrated to @/lib/org-product/orgProductMetricApi
import {
  getOrgProductMetricBootstrap,
  getMetricTableCatalog,
  getOrgProductMetricDbSnapshot,
  saveMetricTable,
  saveRefreshOrgProductMetrics,
  importMetricReport,
  exportMetricReport,
  saveMetricTableCatalog,
  patchMetricTableCatalogItem,
} from "@/lib/org-product/orgProductMetricApi";
import {
  buildFormulaInsertText as buildFormulaInsertTextShared,
  canonicalizeFormulaForStorage as canonicalizeFormulaForStorageShared,
  decorateFormulaTextForDisplay as decorateFormulaTextForDisplayShared,
  normalizeFormulaRefText,
  parseFormulaRefs,
  resolveFormulaRefDependency,
  validateFormulaText,
} from "@/lib/org-product/orgProductFormulaRefs";

type FormulaScopeKind = "actual" | "forecast" | "budgetAnnual" | "forecastAnnual";

const FORMULA_NOTE_OPTIONS = [
  "",
  "率年化指标",
  "率年化指标（仅实际月）",
  "收支月化指标",
] as const;

type MetricNature = "收入" | "支出" | "利润" | "其他";
type MetricViewMode = "metric" | "formula";
type MetricLevelLabel = "一级" | "二级" | "三级" | "四级" | "五级" | "六级";

type MetricNode = {
  id: string;
  levelLabel: string;
  nature: string;
  code: string;
  name: string;
  value_type?: string;
  allow_manual_entry?: number;
  note: string;
  formula?: string;
  formula_budget_annual?: string;
  formula_forecast_annual?: string;
  formula_actual?: string;
  formula_forecast?: string;
  formula_note?: string;
  entry_granularity?: "monthly" | "annual";
  horizontal_rollup?: number;
  vertical_rollup?: number;
  logic_code?: string;
  children: MetricNode[];
};

type EntryGranularity = "monthly" | "annual";

type MetricTable = {
  id: string;
  name: string;
  metrics: MetricNode[];
};

type MetricEditDraft = {
  levelLabel: string;
  nature: string;
  code: string;
  name: string;
  note: string;
  formula: string;
  formula_budget_annual: string;
  formula_forecast_annual: string;
  horizontal_rollup: boolean;
  vertical_rollup: boolean;
  logic_code: string;
  value_type: string;
  allow_manual_entry: boolean;
  entry_granularity: EntryGranularity;
};

type BootstrapResponse = {
  items: Record<string, MetricNode[]>;
  table_items?: Record<string, MetricTable[]>;
  entities?: Array<{
    entity_code: string;
    entity_name: string;
    tables: { id: string; name: string; metrics: MetricNode[] }[];
  }>;
  sources: {
    org_metric_file: string;
    product_metric_file: string;
  };
};

type MetricReportImportResponse = {
  imported_entities: Array<{
    sheet_name: string;
    entity_code: string;
    entity_name: string;
    table_name: string;
    row_count: number;
    has_formula_column?: boolean;
    metrics: MetricNode[];
  }>;
  ignored_sheets: string[];
  ignored_details?: Array<{ sheet_name: string; reason: string }>;
  formula_convert_errors?: Array<{ sheet_name: string; row: number; excel_formula: string; reason: string }>;
};

type MetricSaveRefreshResponse = {
  saved_entities: number;
  saved_tables: number;
};

type MetricTableCatalogResponse = {
  items: MetricTableCatalogItem[];
};


type OrgProductMetricDbSnapshotDto = {
  entities: {
    entity_code: string;
    entity_name: string;
    tables: Array<{ id: string; name: string; metrics: MetricNode[] }>;
  }[];
};

const ORG_PRODUCT_STORAGE_KEY_SUFFIX = "::org-product-tree-v3";
const ORG_PRODUCT_TREE_SAVED_EVENT = "org-product-tree-saved";
const DEFAULT_AA_ENTITY_ID = "node-aa";
const ORG_PRODUCT_METRIC_STORAGE_KEY_SUFFIX = "::org-product-metrics-v2";
const ORG_PRODUCT_METRIC_LEGACY_STORAGE_KEY_SUFFIX = "::org-product-metrics-v1";
const METRIC_TABLE_LOCAL_STORAGE_MAX_CHARS = 1_000_000;
const LEVEL_OPTIONS: MetricLevelLabel[] = ["一级", "二级", "三级", "四级", "五级", "六级"];
const NATURE_OPTIONS: MetricNature[] = ["收入", "支出", "利润", "其他"];
const VALUE_TYPE_OPTIONS = ["金额", "百分比", "户数"] as const;
const ENTRY_GRANULARITY_OPTIONS: Array<{ value: EntryGranularity; label: string }> = [
  { value: "monthly", label: "按月录入" },
  { value: "annual", label: "按年录入" },
];
const PROFIT_METRIC_NAMES = new Set(["分摊前利润", "税前利润", "净利润"]);

function normalizeEntryGranularity(value?: string): EntryGranularity {
  const text = String(value ?? "").trim();
  if (!text) return "monthly";
  if (
    text === "annual" ||
    text.includes("按年录入") ||
    text.includes("仅年度") ||
    text.includes("仅全年") ||
    text === "年度" ||
    text === "全年" ||
    text === "按年"
  ) {
    return "annual";
  }
  return "monthly";
}

function normalizeMetricNameText(name?: string): string {
  return String(name ?? "").replace(/\s+/g, "").trim();
}

function defaultValueTypeForNature(nature?: string): string {
  const text = normalizeMetricNatureText(nature);
  return text.includes("率") || text.includes("比") ? "百分比" : "金额";
}

function normalizeValueType(value?: string, nature?: string): string {
  const text = String(value ?? "").trim();
  if (VALUE_TYPE_OPTIONS.includes(text as (typeof VALUE_TYPE_OPTIONS)[number])) return text;
  return defaultValueTypeForNature(nature);
}

function normalizeAllowManualEntry(value: unknown, fallback = true): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  const text = String(value ?? "").trim().toLowerCase();
  if (!text) return fallback;
  if (["0", "false", "否", "不允许", "no", "n"].includes(text)) return false;
  if (["1", "true", "是", "允许", "yes", "y"].includes(text)) return true;
  return fallback;
}

function normalizeRollupFlag(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  const text = String(value ?? "").trim().toLowerCase();
  if (!text) return false;
  if (["0", "false", "否", "不", "不汇总", "no", "n"].includes(text)) return false;
  if (["1", "true", "是", "汇总", "需要汇总", "yes", "y"].includes(text)) return true;
  return true;
}
const DEFAULT_METRIC_TABLE_NAME = "业务状况表";
const PROFIT_LOSS_TABLE_NAME = "损益表";
const CLEANUP_METRIC_CODES = ["AA01N04", "AA01N05", "AA01N05N01"] as const;
const CODE_TO_NODE_ID: Record<string, string> = {
  AAA: "node-root",
  AA: "node-aa",
  AB: "node-ab",
  A: "node-a",
  A01: "node-a01",
  A02: "node-a02",
  A03: "node-a03",
  A04: "node-a04",
  A05: "node-a05",
  B: "node-b",
  B01: "node-b01",
  B02: "node-b02",
  C: "node-c",
  C01: "node-c01",
  C02: "node-c02",
  D: "node-d",
  D01: "node-d01",
  E: "node-e",
  E01: "node-e01",
  F: "node-f",
  F01: "node-f01",
};

const primaryActionClass =
  "inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-sky-500 to-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:from-sky-600 hover:to-blue-700";
const secondaryActionClass =
  "inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-emerald-500 to-teal-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:from-emerald-600 hover:to-teal-700";
const neutralActionClass =
  "inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm transition hover:bg-gray-50";
const dangerActionClass =
  "inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-rose-500 to-red-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:from-rose-600 hover:to-red-700";

function cloneMetricForest(nodes?: MetricNode[]): MetricNode[] {
  return JSON.parse(JSON.stringify(Array.isArray(nodes) ? nodes : [])) as MetricNode[];
}

function cloneMetricTables(tables?: MetricTable[]): MetricTable[] {
  return JSON.parse(JSON.stringify(Array.isArray(tables) ? tables : [])) as MetricTable[];
}

function cloneOrgProductTree(tree: OrgProductNode): OrgProductNode {
  return JSON.parse(JSON.stringify(tree)) as OrgProductNode;
}

function mergeOrgProductTreeMissingNodes(base: OrgProductNode, fallback: OrgProductNode): OrgProductNode {
  const byCode = new Map(collectOrgNodes(base).map((node) => [node.code.trim().toUpperCase(), node]));
  const mergeInto = (target: OrgProductNode, source: OrgProductNode) => {
    source.children.forEach((sourceChild) => {
      const code = sourceChild.code.trim().toUpperCase();
      const existing = byCode.get(code);
      if (existing) {
        mergeInto(existing, sourceChild);
        return;
      }
      const cloned = cloneOrgProductTree(sourceChild);
      target.children.push(cloned);
      collectOrgNodes(cloned).forEach((node) => byCode.set(node.code.trim().toUpperCase(), node));
    });
  };
  mergeInto(base, fallback);
  return base;
}

function orgProductNodeIdFromCode(code: string): string {
  const normalized = code.trim().toUpperCase();
  return CODE_TO_NODE_ID[normalized] ?? `node-${normalized.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

function inferOrgProductNodeType(code: string): OrgProductNode["type"] {
  const normalized = code.trim().toUpperCase();
  if (normalized === "AAA") return "level0";
  if (normalized === "AA" || normalized === "AB") return "level1";
  if (/^[A-Z]$/.test(normalized)) return "level2";
  if (/^[A-Z]\d+/.test(normalized)) return "level3";
  return "level1";
}

function upsertOrgProductEntityNode(tree: OrgProductNode, entityCode: string, entityName: string): void {
  const code = entityCode.trim().toUpperCase();
  if (!code || findOrgNodeByCode(tree, code)) return;
  const node: OrgProductNode = {
    id: orgProductNodeIdFromCode(code),
    code,
    name: entityName.trim() || code,
    type: inferOrgProductNodeType(code),
    children: [],
  };
  if (node.type === "level3") {
    const parentCode = code.match(/^[A-Z]+/)?.[0]?.slice(0, 1) ?? "";
    const parent = parentCode ? findOrgNodeByCode(tree, parentCode) : null;
    if (parent) {
      parent.children.push(node);
      return;
    }
  }
  if (node.type === "level2") {
    const aa = findOrgNodeByCode(tree, "AA");
    if (aa) {
      aa.children.push(node);
      return;
    }
  }
  tree.children.push(node);
}

function ensureOrgTreeIncludesDbSnapshotEntities(tree: OrgProductNode, snapshot: OrgProductMetricDbSnapshotDto): OrgProductNode {
  const next = mergeOrgProductTreeMissingNodes(cloneOrgProductTree(tree), cloneDefaultOrgProductTree());
  const entities = [...(snapshot.entities ?? [])].sort((a, b) => a.entity_code.length - b.entity_code.length || a.entity_code.localeCompare(b.entity_code));
  entities.forEach((ent) => upsertOrgProductEntityNode(next, ent.entity_code, ent.entity_name));
  return next;
}

function defaultSelectableEntityId(tree: OrgProductNode, snapshot?: OrgProductMetricDbSnapshotDto): string {
  const aa = findOrgNodeByCode(tree, "AA")?.id;
  if (aa) return aa;
  const firstSnapshotEntity = (snapshot?.entities ?? [])
    .filter((ent) => (ent.tables ?? []).some((table) => (table.metrics ?? []).length > 0))
    .map((ent) => findOrgNodeByCode(tree, ent.entity_code)?.id)
    .find((id): id is string => Boolean(id));
  return firstSnapshotEntity ?? DEFAULT_AA_ENTITY_ID;
}

function collectMetricNodes(nodes: MetricNode[]): MetricNode[] {
  return (Array.isArray(nodes) ? nodes : []).flatMap((node) => [node, ...collectMetricNodes(Array.isArray(node.children) ? node.children : [])]);
}

function normalizeMetricNatureText(nature?: string): string {
  const trimmed = String(nature ?? "").trim();
  if (trimmed === "住处") return "支出";
  return trimmed || "其他";
}

function normalizeMetricForest(nodes?: MetricNode[]): MetricNode[] {
  if (!Array.isArray(nodes)) return [];
  return nodes.map((node, index) => {
    const name = String(node?.name ?? "").trim();
    const normalizedName = normalizeMetricNameText(name);
    const nextNature = PROFIT_METRIC_NAMES.has(normalizedName) ? "利润" : (normalizeMetricNatureText(node?.nature) as MetricNature);
    return {
      id: String(node?.id ?? `metric-auto-${index}`),
      levelLabel: String(node?.levelLabel ?? "一级"),
      nature: nextNature,
      code: String(node?.code ?? "").trim(),
      name,
      value_type: normalizeValueType((node as any)?.value_type, nextNature),
      allow_manual_entry: normalizeAllowManualEntry((node as any)?.allow_manual_entry, true) ? 1 : 0,
      note: String(node?.note ?? "").trim(),
      formula: String((node as any)?.formula ?? "").trim(),
      formula_budget_annual: String((node as any)?.formula_budget_annual ?? "").trim(),
      formula_forecast_annual: String((node as any)?.formula_forecast_annual ?? "").trim(),
      formula_actual: String((node as any)?.formula_actual ?? "").trim(),
      formula_forecast: String((node as any)?.formula_forecast ?? "").trim(),
      formula_note: String((node as any)?.formula_note ?? "").trim(),
      entry_granularity: normalizeEntryGranularity((node as any)?.entry_granularity),
      horizontal_rollup: normalizeRollupFlag((node as any)?.horizontal_rollup) ? 1 : 0,
      vertical_rollup: normalizeRollupFlag((node as any)?.vertical_rollup) ? 1 : 0,
      logic_code: String((node as any)?.logic_code ?? "").trim().toUpperCase(),
      children: normalizeMetricForest(Array.isArray(node?.children) ? node.children : []),
    };
  });
}

function normalizeMetricTables(tables?: MetricTable[]): MetricTable[] {
  if (!Array.isArray(tables)) return [];
  return tables.map((table, index) => ({
    id: String(table?.id ?? `table-auto-${index}`),
    name: String(table?.name ?? DEFAULT_METRIC_TABLE_NAME),
    metrics: normalizeMetricForest(Array.isArray(table?.metrics) ? table.metrics : []),
  }));
}

function findMetricNodeById(nodes: MetricNode[], id: string): MetricNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const found = findMetricNodeById(node.children, id);
    if (found) return found;
  }
  return null;
}

function filterOrgTree(node: OrgProductNode, term: string): OrgProductNode | null {
  const keyword = term.trim().toLowerCase();
  if (!keyword) return node;
  const matchedChildren = node.children
    .map((child) => filterOrgTree(child, keyword))
    .filter((child): child is OrgProductNode => Boolean(child));
  const selfMatched = node.code.toLowerCase().includes(keyword) || node.name.toLowerCase().includes(keyword);
  if (selfMatched || matchedChildren.length > 0) {
    return { ...node, children: matchedChildren };
  }
  return null;
}

function filterMetricTree(nodes: MetricNode[], term: string): MetricNode[] {
  const keyword = term.trim().toLowerCase();
  if (!keyword) return nodes;
  return nodes
    .map((node) => {
      const children = filterMetricTree(node.children, keyword);
      const matched =
        node.code.toLowerCase().includes(keyword) ||
        node.name.toLowerCase().includes(keyword) ||
        (node.note || "").toLowerCase().includes(keyword);
      if (matched || children.length > 0) return { ...node, children };
      return null;
    })
    .filter((node): node is MetricNode => Boolean(node));
}

function updateMetricNodeById(nodes: MetricNode[], id: string, updater: (node: MetricNode) => MetricNode): MetricNode[] {
  return nodes.map((node) => {
    if (node.id === id) return updater(node);
    return {
      ...node,
      children: updateMetricNodeById(node.children, id, updater),
    };
  });
}

function addMetricChild(nodes: MetricNode[], parentId: string, child: MetricNode): MetricNode[] {
  return nodes.map((node) => {
    if (node.id === parentId) {
      return { ...node, children: [...node.children, child] };
    }
    return {
      ...node,
      children: addMetricChild(node.children, parentId, child),
    };
  });
}

function deleteMetricNodeById(nodes: MetricNode[], id: string): MetricNode[] {
  return nodes
    .filter((node) => node.id !== id)
    .map((node) => ({ ...node, children: deleteMetricNodeById(node.children, id) }));
}

function pruneMetricTreeByCode(nodes: MetricNode[], blockedCodes: Set<string>): MetricNode[] {
  return (Array.isArray(nodes) ? nodes : [])
    .filter((node) => !blockedCodes.has(String(node.code || "").trim().toUpperCase()))
    .map((node) => ({
      ...node,
      children: pruneMetricTreeByCode(Array.isArray(node.children) ? node.children : [], blockedCodes),
    }));
}

function cleanupMetricTablesMap(map: Record<string, MetricTable[]>): Record<string, MetricTable[]> {
  const blocked = new Set<string>(CLEANUP_METRIC_CODES.map((code) => code.toUpperCase()));
  const result: Record<string, MetricTable[]> = {};
  Object.entries(map).forEach(([entityId, tables]) => {
    result[entityId] = (Array.isArray(tables) ? tables : []).map((table) => ({
      ...table,
      metrics: pruneMetricTreeByCode(table.metrics, blocked),
    }));
  });
  return result;
}

function nextMetricLevelLabel(parent?: MetricNode | null): MetricLevelLabel {
  if (!parent) return "一级";
  const index = Math.min(LEVEL_OPTIONS.indexOf(parent.levelLabel as MetricLevelLabel) + 1, LEVEL_OPTIONS.length - 1);
  return LEVEL_OPTIONS[index];
}

function newMetricCode(parent?: MetricNode | null, currentRoots?: MetricNode[]): string {
  if (!parent) return `NEW${String((currentRoots?.length ?? 0) + 1).padStart(2, "0")}`;
  return `${parent.code}N${String(parent.children.length + 1).padStart(2, "0")}`;
}

function formatMetricCodeForDisplay(entityCode: string, rawCode: string): string {
  const owner = String(entityCode || "").trim().toUpperCase();
  const code = String(rawCode || "").trim().toUpperCase();
  if (!owner || !code) return code;
  if (!code.startsWith(owner)) return code;
  const remainder = code.slice(owner.length);
  if (!remainder) return owner;
  if (!/^[0-9A-Z]+$/.test(remainder)) return code;
  const chunks = remainder.match(/.{1,2}/g) ?? [remainder];
  return `${owner}.${chunks.join(".")}`;
}

function formatMetricHeaderText(entity: OrgProductNode, metric: MetricNode): string {
  const entityName = String(entity?.name ?? "").trim();
  const metricCode = formatMetricCodeForDisplay(String(entity?.code ?? "").trim().toUpperCase(), String(metric?.code ?? ""));
  const metricName = String(metric?.name ?? "").trim();
  return [entityName, metricCode, metricName].filter(Boolean).join(" · ");
}

function normalizeMetricCodeForStorage(entityCode: string, inputCode: string): string {
  const owner = String(entityCode || "").trim().toUpperCase();
  const cleaned = String(inputCode || "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "")
    .replace(/\./g, "");
  if (!cleaned) return "";
  if (!owner) return cleaned;
  if (cleaned.startsWith(owner)) return cleaned;
  if (/^[0-9]+$/.test(cleaned)) return `${owner}${cleaned}`;
  return cleaned;
}

function buildDefaultMetricDraft(metric: MetricNode): MetricEditDraft {
  return {
    levelLabel: metric.levelLabel,
    nature: normalizeMetricNatureText(metric.nature),
    code: metric.code,
    name: metric.name,
    note: metric.note || "",
    formula: String(metric.formula ?? ""),
    formula_budget_annual: String(metric.formula_budget_annual ?? ""),
    formula_forecast_annual: String(metric.formula_forecast_annual ?? ""),
    horizontal_rollup: normalizeRollupFlag(metric.horizontal_rollup),
    vertical_rollup: normalizeRollupFlag(metric.vertical_rollup),
    logic_code: String(metric.logic_code ?? "").trim().toUpperCase(),
    value_type: normalizeValueType(metric.value_type, metric.nature),
    allow_manual_entry: normalizeAllowManualEntry(metric.allow_manual_entry, true),
    entry_granularity: normalizeEntryGranularity(metric.entry_granularity),
  };
}

function mergeMetricForestPreservingFormula(existing: MetricNode[], incoming: MetricNode[]): MetricNode[] {
  const existingByCode = new Map(existing.map((n) => [String(n.code || "").trim().toUpperCase(), n]));
  const pickFormula = (incomingVal: string | undefined, oldVal: string | undefined) =>
    String(incomingVal ?? "").trim() ? incomingVal : oldVal;
  return incoming.map((node) => {
    const key = String(node.code || "").trim().toUpperCase();
    const old = key ? existingByCode.get(key) : undefined;
    return {
      ...node,
      formula: pickFormula(node.formula, old?.formula),
      formula_budget_annual: pickFormula(node.formula_budget_annual, old?.formula_budget_annual),
      formula_forecast_annual: pickFormula(node.formula_forecast_annual, old?.formula_forecast_annual),
      formula_actual: pickFormula(node.formula_actual, old?.formula_actual),
      formula_forecast: pickFormula(node.formula_forecast, old?.formula_forecast),
      formula_note: String(node.formula_note ?? "").trim() ? node.formula_note : old?.formula_note,
      value_type: normalizeValueType(node.value_type || old?.value_type, node.nature || old?.nature),
      allow_manual_entry: normalizeAllowManualEntry(node.allow_manual_entry ?? old?.allow_manual_entry, true) ? 1 : 0,
      entry_granularity: node.entry_granularity ?? old?.entry_granularity ?? "monthly",
      horizontal_rollup: normalizeRollupFlag(node.horizontal_rollup ?? old?.horizontal_rollup) ? 1 : 0,
      vertical_rollup: normalizeRollupFlag(node.vertical_rollup ?? old?.vertical_rollup) ? 1 : 0,
      logic_code: String(node.logic_code || old?.logic_code || "").trim().toUpperCase(),
      children: mergeMetricForestPreservingFormula(old?.children ?? [], node.children ?? []),
    };
  });
}

type FlatMetricRow = {
  id: string;
  pathKey: string;
  levelLabel: string;
  nature: string;
  code: string;
  name: string;
  depth: number;
  formula?: string;
  formula_budget_annual?: string;
  formula_forecast_annual?: string;
  formula_actual?: string;
  formula_forecast?: string;
  formula_note?: string;
  horizontal_rollup?: number;
  vertical_rollup?: number;
  logic_code?: string;
};

function metricHasActualFormula(node: Pick<MetricNode, "formula" | "formula_actual" | "formula_forecast">): boolean {
  if (String(node.formula_actual ?? "").trim()) return true;
  if (String(node.formula_forecast ?? "").trim()) return false;
  return Boolean(String(node.formula ?? "").trim());
}

function metricHasForecastFormula(node: Pick<MetricNode, "formula_forecast">): boolean {
  return Boolean(String(node.formula_forecast ?? "").trim());
}

function metricHasBudgetAnnualFormula(node: Pick<MetricNode, "formula_budget_annual">): boolean {
  return Boolean(String(node.formula_budget_annual ?? "").trim());
}

function metricHasForecastAnnualFormula(node: Pick<MetricNode, "formula_forecast_annual">): boolean {
  return Boolean(String(node.formula_forecast_annual ?? "").trim());
}

const FORMULA_SCOPE_LABEL: Record<FormulaScopeKind, string> = {
  actual: "实际月公式",
  forecast: "预测月公式",
  budgetAnnual: "年预算公式",
  forecastAnnual: "年预测公式",
};

const FORMULA_METRIC_LIST_GRID = "grid-cols-[44px_92px_minmax(80px,132px)_36px_36px_36px_36px_minmax(64px,1fr)]";
const FORMULA_METRIC_LEVEL_CELL = "pt-0.5 text-[10px] leading-4 text-gray-600";
const FORMULA_METRIC_CODE_CELL = "pt-0.5 min-w-0 truncate text-[10px] text-gray-700";
const FORMULA_METRIC_NAME_CELL = "block min-w-0 w-full truncate whitespace-nowrap pt-0.5 text-[11px] leading-4 text-gray-800";
const FORMULA_METRIC_NAME_INDENT_PX = 8;
/** 公式配置区输入/预览：与顶部工具栏一致，使用系统 sans（text-xs），不用等宽字体 */
const FORMULA_UI_INPUT_CLASS = "text-xs text-gray-800";

type MetricRefInfo = {
  displayCode: string;
  name: string;
};

type AiExprCandidate = {
  entityId: string;
  entityCode: string;
  tableName: string;
  normalizedCode: string;
  displayCode: string;
  name: string;
  formulaPiece: string;
};

type AiExprToken = {
  kind: "metric" | "op" | "literal";
  value: string;
  candidates?: AiExprCandidate[];
  selectedNormalizedCode?: string;
};

type AiPreviewRow = {
  entityId: string;
  entityCode: string;
  entityName: string;
  tableName: string;
  targetMetricId: string;
  targetMetricName: string;
  targetMetricCodeDisplay: string;
  oldFormula: string;
  newFormula: string;
  ok: boolean;
  reason?: string;
  aiExprTokens?: AiExprToken[];
};

function collectFlatMetricRows(nodes: MetricNode[], depth = 0, parentPath = ""): FlatMetricRow[] {
  return nodes.flatMap((node, index) => {
    const pathKey = parentPath ? `${parentPath}.${index}` : `${index}`;
    return [
      {
        id: node.id,
        pathKey,
        levelLabel: node.levelLabel,
        nature: node.nature,
        code: node.code,
        name: node.name,
        depth,
        formula: node.formula,
        formula_budget_annual: node.formula_budget_annual,
        formula_forecast_annual: node.formula_forecast_annual,
        formula_actual: node.formula_actual,
        formula_forecast: node.formula_forecast,
        formula_note: node.formula_note,
        horizontal_rollup: node.horizontal_rollup,
        vertical_rollup: node.vertical_rollup,
        logic_code: node.logic_code,
      },
      ...collectFlatMetricRows(Array.isArray(node.children) ? node.children : [], depth + 1, pathKey),
    ];
  });
}

function formatFormulaText(raw: string): string {
  const text = String(raw ?? "");
  if (!text.trim()) return "";
  const refs = parseFormulaRefs(text);
  let protectedText = text;
  const placeholders: string[] = [];
  refs.forEach((r, idx) => {
    const placeholder = `__REF_${idx}__`;
    placeholders.push(r.raw);
    protectedText = protectedText.split(r.raw).join(placeholder);
  });

  let out = protectedText
    .replace(/[\u00A0\t]/g, " ")
    .replace(/[，]/g, ",")
    .replace(/[＋]/g, "+")
    .replace(/[－]/g, "-")
    .replace(/[×]/g, "*")
    .replace(/[÷]/g, "/")
    .replace(/\s+/g, " ")
    .trim();

  out = out
    .replace(/\s*(<=|>=|<>|=|<|>)\s*/g, " $1 ")
    .replace(/\s*([+\-*/^%(),])\s*/g, " $1 ")
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")")
    .replace(/,\s+/g, ", ")
    .trim();

  placeholders.forEach((rawRef, idx) => {
    out = out.split(`__REF_${idx}__`).join(rawRef);
  });
  return out;
}

type MetricKey = string;

function metricKey(entityId: string, tableName: string, metricId: string): MetricKey {
  return `${entityId}::${tableName}::${metricId}`;
}

function detectCycleFrom(start: MetricKey, edges: Map<MetricKey, MetricKey[]>): MetricKey[] | null {
  const visited = new Set<MetricKey>();
  const stack = new Set<MetricKey>();
  const parent = new Map<MetricKey, MetricKey>();

  const dfs = (node: MetricKey): MetricKey[] | null => {
    visited.add(node);
    stack.add(node);
    const next = edges.get(node) ?? [];
    for (const dep of next) {
      if (!visited.has(dep)) {
        parent.set(dep, node);
        const found = dfs(dep);
        if (found) return found;
      } else if (stack.has(dep)) {
        const path: MetricKey[] = [dep];
        let cur: MetricKey | undefined = node;
        while (cur && cur !== dep) {
          path.push(cur);
          cur = parent.get(cur);
        }
        path.push(dep);
        path.reverse();
        return path;
      }
    }
    stack.delete(node);
    return null;
  };

  return dfs(start);
}

function normalizeBootstrapSeed(items: Record<string, MetricNode[]>): Record<string, MetricNode[]> {
  const result: Record<string, MetricNode[]> = {};
  Object.entries(items).forEach(([ownerCode, nodes]) => {
    const nodeId = CODE_TO_NODE_ID[ownerCode];
    if (!nodeId) return;
    result[nodeId] = cloneMetricForest(nodes);
  });
  return result;
}

function normalizeBootstrapMetricTables(items?: Record<string, MetricTable[]>): Record<string, MetricTable[]> {
  const result: Record<string, MetricTable[]> = {};
  Object.entries(items ?? {}).forEach(([ownerCode, tables]) => {
    const nodeId = CODE_TO_NODE_ID[ownerCode];
    if (!nodeId) return;
    result[nodeId] = normalizeMetricTables(tables ?? []);
  });
  return result;
}

function metricTableNamesForEntity(
  entityId: string,
  tree?: OrgProductNode | null,
  catalog?: MetricTableCatalogItem[] | null
): string[] {
  const node = tree ? findOrgNodeById(tree, entityId) : null;
  if (node) return [...metricTableNamesForOrgNode(node, catalog)];
  if (!tree && entityId === DEFAULT_AA_ENTITY_ID) {
    const aaNames = activeCatalogTableNamesForScope(catalog, "AA");
    return aaNames.length > 0 ? aaNames : [...AA_BANK_METRIC_TABLE_NAMES];
  }
  return [DEFAULT_METRIC_TABLE_NAME];
}

function defaultActiveTableNameForEntity(
  entityId: string,
  tree: OrgProductNode,
  catalog?: MetricTableCatalogItem[] | null
): string {
  const node = findOrgNodeById(tree, entityId);
  const names = metricTableNamesForOrgNode(node, catalog);
  if (isAaBankNode(node)) return PROFIT_LOSS_TABLE_NAME;
  return names[0] ?? DEFAULT_METRIC_TABLE_NAME;
}

function buildMetricTableId(tableName: string): string {
  return `table-${tableName}`;
}

function buildMetricScopeKey(entityId: string, tableId: string): string {
  return `${entityId}::${tableId}`;
}

function migrateLegacyMetricMap(legacy?: Record<string, MetricNode[]>): Record<string, MetricTable[]> | undefined {
  if (!legacy) return undefined;
  const result: Record<string, MetricTable[]> = {};
  Object.entries(legacy).forEach(([entityId, metrics]) => {
    result[entityId] = [
      {
        id: buildMetricTableId(DEFAULT_METRIC_TABLE_NAME),
        name: DEFAULT_METRIC_TABLE_NAME,
        metrics: cloneMetricForest(metrics),
      },
    ];
  });
  return result;
}

function shouldKeepExtraMetricTableName(name: string): boolean {
  const trimmed = name.trim();
  if (!trimmed) return false;
  return trimmed.endsWith("表");
}

function migrateV2ButActuallyMetricNodesByEntityId(raw: unknown): Record<string, MetricTable[]> | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const result: Record<string, MetricTable[]> = {};
  Object.entries(raw as Record<string, unknown>).forEach(([entityId, value]) => {
    if (!Array.isArray(value)) return;
    const first = value[0] as any;
    const looksLikeMetricNode = Boolean(first && typeof first === "object" && "levelLabel" in first && "code" in first && "children" in first);
    if (!looksLikeMetricNode) return;
    result[entityId] = [
      {
        id: buildMetricTableId(DEFAULT_METRIC_TABLE_NAME),
        name: DEFAULT_METRIC_TABLE_NAME,
        metrics: normalizeMetricForest(value as any),
      },
    ];
  });
  return Object.keys(result).length > 0 ? result : undefined;
}

function sanitizeStoredMetricTablesByEntityId(
  raw: unknown,
  tree?: OrgProductNode | null,
  catalog?: MetricTableCatalogItem[] | null
): Record<string, MetricTable[]> | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const migrated = migrateV2ButActuallyMetricNodesByEntityId(raw);
  if (migrated) return migrated;

  const result: Record<string, MetricTable[]> = {};
  Object.entries(raw as Record<string, unknown>).forEach(([entityId, value]) => {
    if (!Array.isArray(value)) return;
    const node = tree ? findOrgNodeById(tree, entityId) : null;
    const normalized = normalizeMetricTables(value as any);
    const allowed = metricTableNamesForOrgNode(node ?? null, catalog);
    const allowedNames = allowed.length ? [...allowed] : [...metricTableNamesForEntity(entityId, tree, catalog)];
    let filtered: MetricTable[];
    if (allowedNames.length > 0) {
      filtered = pruneMetricTablesToCatalog(
        normalized,
        allowedNames,
        buildMetricTableId,
        (name) => canonicalMetricTableNameInList(name, allowedNames)
      );
      filtered = appendInactiveCatalogMetricTables(
        filtered,
        normalized,
        metricTableEntityScopeForNode(node),
        catalog,
        buildMetricTableId
      );
      if (!isAaBankNode(node)) {
        const kept = new Set(filtered.map((t) => t.name));
        normalized.forEach((table) => {
          if (!kept.has(table.name) && shouldKeepExtraMetricTableName(table.name)) {
            filtered.push({ ...table, id: buildMetricTableId(table.name), name: table.name.trim() });
          }
        });
      }
    } else {
      filtered = normalized
        .filter((table) => {
          if (allowedNames.includes(table.name)) return true;
          return shouldKeepExtraMetricTableName(table.name);
        })
        .map((table) => ({
          ...table,
          id: buildMetricTableId(table.name),
          name: table.name.trim(),
        }));
    }

    if (filtered.length > 0) result[entityId] = filtered;
  });
  return Object.keys(result).length > 0 ? result : undefined;
}

function reconcileMetricTableMap(
  seed: Record<string, MetricNode[]>,
  tree: OrgProductNode,
  existing?: Record<string, MetricTable[]>,
  catalog?: MetricTableCatalogItem[] | null
): Record<string, MetricTable[]> {
  const result: Record<string, MetricTable[]> = {};
  collectOrgNodes(tree).forEach((node) => {
    if (!supportsMetricDefinition(node)) return;
    const defaultNames = metricTableNamesForEntity(node.id, tree, catalog);
    const activeNames = [...metricTableNamesForOrgNode(node, catalog)];
    const scope = metricTableEntityScopeForNode(node);
    const rawExisting = normalizeMetricTables(cloneMetricTables(existing?.[node.id] ?? []));
    const existingByName = new Map<string, MetricTable>();
    for (const table of rawExisting) {
      const canonical = isAaBankNode(node)
        ? canonicalMetricTableNameInList(table.name, activeNames)
        : canonicalMetricTableNameInList(table.name, activeNames) ?? table.name.trim();
      if (!canonical) continue;
      const metrics = Array.isArray(table.metrics) ? table.metrics : [];
      const prev = existingByName.get(canonical);
      if (!prev) {
        existingByName.set(canonical, {
          ...table,
          name: canonical,
          id: buildMetricTableId(canonical),
          metrics,
        });
        continue;
      }
      const prevMetrics = Array.isArray(prev.metrics) ? prev.metrics : [];
      if (prevMetrics.length === 0 && metrics.length > 0) {
        existingByName.set(canonical, { ...prev, metrics });
      }
    }
    const seedMetrics = normalizeMetricForest(cloneMetricForest(seed[node.id] ?? []));

    let tables: MetricTable[] = defaultNames.map((tableName) => {
      const existingTable = existingByName.get(tableName);
      if (existingTable) {
        const shouldSeed = isAaBankNode(node)
          ? tableName === PROFIT_LOSS_TABLE_NAME
          : tableName === DEFAULT_METRIC_TABLE_NAME;
        if (shouldSeed && existingTable.metrics.length === 0 && seedMetrics.length > 0) return { ...existingTable, metrics: seedMetrics };
        return existingTable;
      }
      return {
        id: buildMetricTableId(tableName),
        name: tableName,
        metrics: isAaBankNode(node)
          ? tableName === PROFIT_LOSS_TABLE_NAME
            ? seedMetrics
            : []
          : tableName === DEFAULT_METRIC_TABLE_NAME
            ? seedMetrics
            : [],
      };
    });

    tables = appendInactiveCatalogMetricTables(tables, rawExisting, scope, catalog, buildMetricTableId);

    if (!isAaBankNode(node)) {
      rawExisting.forEach((table) => {
        if (!defaultNames.includes(table.name) && shouldKeepExtraMetricTableName(table.name)) {
          const key = normalizeMetricTableNameKey(table.name);
          if (tables.some((t) => normalizeMetricTableNameKey(t.name) === key)) return;
          tables.push({ ...table, id: buildMetricTableId(table.name), name: table.name.trim() });
        }
      });
    }

    if (activeNames.length > 0) {
      tables.sort((a, b) => {
        const order = (name: string) => {
          const idx = activeNames.indexOf(name);
          if (idx >= 0) return idx;
          const inactiveIdx = catalog?.findIndex(
            (r) => r.entity_scope === scope && normalizeMetricTableNameKey(r.table_name) === normalizeMetricTableNameKey(name)
          );
          return inactiveIdx !== undefined && inactiveIdx >= 0 ? 200 + inactiveIdx : 300;
        };
        return order(a.name) - order(b.name);
      });
    }

    result[node.id] = tables;
  });
  return result;
}

function metricNodeCount(nodes: MetricNode[]): number {
  return collectMetricNodes(nodes).filter((n) => (n.code || "").trim() && (n.name || "").trim()).length;
}

function dbSnapshotToMetricTablesByEntityId(
  snapshot: OrgProductMetricDbSnapshotDto,
  tree: OrgProductNode
): Record<string, MetricTable[]> {
  const result: Record<string, MetricTable[]> = {};
  for (const ent of snapshot.entities ?? []) {
    const node = findOrgNodeByCode(tree, ent.entity_code);
    if (!node) continue;
    result[node.id] = normalizeMetricTables(
      (ent.tables ?? []).map((t) => ({
        id: t.id || buildMetricTableId(t.name),
        name: t.name,
        metrics: normalizeMetricForest(t.metrics ?? []),
      }))
    );
  }
  return result;
}

function mergeMetricTablesByEntityIdPreferRicher(
  primary: Record<string, MetricTable[]>,
  secondary: Record<string, MetricTable[]>,
  options?: { preferSecondaryOnTie?: boolean }
): Record<string, MetricTable[]> {
  const result: Record<string, MetricTable[]> = {};
  const entityIds = new Set([...Object.keys(primary), ...Object.keys(secondary)]);
  entityIds.forEach((entityId) => {
    const byKey = new Map<string, MetricTable>();
    for (const table of primary[entityId] ?? []) {
      byKey.set(normalizeMetricTableNameKey(table.name), table);
    }
    for (const table of secondary[entityId] ?? []) {
      const key = normalizeMetricTableNameKey(table.name);
      const prev = byKey.get(key);
      const secondaryCount = metricNodeCount(table.metrics);
      const primaryCount = prev ? metricNodeCount(prev.metrics) : -1;
      if (!prev || secondaryCount > primaryCount || (options?.preferSecondaryOnTie && secondaryCount === primaryCount)) {
        byKey.set(key, table);
      }
    }
    if (byKey.size > 0) result[entityId] = Array.from(byKey.values());
  });
  return result;
}

function mergeMetricTablesByEntityIdFillMissing(
  primary: Record<string, MetricTable[]>,
  fallback: Record<string, MetricTable[]>
): Record<string, MetricTable[]> {
  const result: Record<string, MetricTable[]> = {};
  const entityIds = new Set([...Object.keys(primary), ...Object.keys(fallback)]);
  entityIds.forEach((entityId) => {
    const byKey = new Map<string, MetricTable>();
    for (const table of primary[entityId] ?? []) {
      byKey.set(normalizeMetricTableNameKey(table.name), table);
    }
    for (const table of fallback[entityId] ?? []) {
      const key = normalizeMetricTableNameKey(table.name);
      if (!byKey.has(key)) byKey.set(key, table);
    }
    if (byKey.size > 0) result[entityId] = Array.from(byKey.values());
  });
  return result;
}

function hasMetricTables(map: Record<string, MetricTable[]>): boolean {
  return Object.values(map).some((tables) => (tables ?? []).length > 0);
}

function persistMetricTablesCache(storageKey: string, tablesByEntityId: Record<string, MetricTable[]>): void {
  try {
    const payload = JSON.stringify(tablesByEntityId);
    if (payload.length > METRIC_TABLE_LOCAL_STORAGE_MAX_CHARS) {
      window.localStorage.removeItem(storageKey);
      return;
    }
    window.localStorage.setItem(storageKey, payload);
  } catch {
    try {
      window.localStorage.removeItem(storageKey);
    } catch {
      // Ignore browser storage quota and privacy-mode errors; DB snapshot is the source of truth.
    }
  }
}

function loadOrgTree(storageKey: string, storagePrefix: string): OrgProductNode {
  const read = (key: string): OrgProductNode | null => {
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) return null;
      return prepareOrgProductTreeFromStorage(JSON.parse(raw));
    } catch {
      return null;
    }
  };
  return (
    mergeOrgProductTreeMissingNodes(
      read(storageKey) ??
        read(`${storagePrefix}::org-product-tree-v2`) ??
        cloneDefaultOrgProductTree(),
      cloneDefaultOrgProductTree()
    )
  );
}

export function OrgProductMetricContent({ initialView = "metric" as MetricViewMode }: { initialView?: MetricViewMode } = {}) {
  const userStorageKeyPrefix = useUserStorageKeyPrefix();
  const orgTreeStorageKey = `${userStorageKeyPrefix}${ORG_PRODUCT_STORAGE_KEY_SUFFIX}`;
  const metricStorageKey = `${userStorageKeyPrefix}${ORG_PRODUCT_METRIC_STORAGE_KEY_SUFFIX}`;

  const [viewMode, setViewMode] = useState<MetricViewMode>(initialView);
  const [orgTree, setOrgTree] = useState<OrgProductNode>(() => loadOrgTree(orgTreeStorageKey, userStorageKeyPrefix));
  const [entityExpanded, setEntityExpanded] = useState<Record<string, boolean>>(() =>
    buildOrgExpandedState(loadOrgTree(orgTreeStorageKey, userStorageKeyPrefix))
  );
  const [entitySearchInput, setEntitySearchInput] = useState("");
  const [entitySearch, setEntitySearch] = useState("");
  const [entityDropdownOpen, setEntityDropdownOpen] = useState(false);
  const [selectedEntityIds, setSelectedEntityIds] = useState<string[]>([DEFAULT_AA_ENTITY_ID]);
  const [activeEntityId, setActiveEntityId] = useState<string>(DEFAULT_AA_ENTITY_ID);
  const [metricSearchInput, setMetricSearchInput] = useState("");
  const [metricSearch, setMetricSearch] = useState("");
  const [metricTablesByEntityId, setMetricTablesByEntityId] = useState<Record<string, MetricTable[]>>({});
  const [activeTableIdByEntityId, setActiveTableIdByEntityId] = useState<Record<string, string>>({});
  const [selectedMetricIdByScope, setSelectedMetricIdByScope] = useState<Record<string, string | null>>({});
  const [metricDraft, setMetricDraft] = useState<MetricEditDraft>({
    levelLabel: "一级",
    nature: "其他",
    code: "",
    name: "",
    note: "",
    formula: "",
    formula_budget_annual: "",
    formula_forecast_annual: "",
    horizontal_rollup: false,
    vertical_rollup: false,
    logic_code: "",
    value_type: "金额",
    allow_manual_entry: true,
    entry_granularity: "monthly",
  });
  const [bootstrapSeedByEntityId, setBootstrapSeedByEntityId] = useState<Record<string, MetricNode[]>>({});
  const [bootstrapTableSeedByEntityId, setBootstrapTableSeedByEntityId] = useState<Record<string, MetricTable[]>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [savingRefresh, setSavingRefresh] = useState(false);
  const [metricEditorOpen, setMetricEditorOpen] = useState(false);
  const [metricEditorSaving, setMetricEditorSaving] = useState(false);
  const metricEditorRef = useRef<HTMLDivElement | null>(null);
  const metricEditorDragRef = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);
  const [metricEditorPos, setMetricEditorPos] = useState<{ x: number; y: number } | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const formulaInputRef = useRef<HTMLTextAreaElement | null>(null);
  const [formulaScope, setFormulaScope] = useState<FormulaScopeKind>("actual");
  const [formulaActualText, setFormulaActualText] = useState("");
  const [formulaForecastText, setFormulaForecastText] = useState("");
  const [formulaBudgetAnnualText, setFormulaBudgetAnnualText] = useState("");
  const [formulaForecastAnnualText, setFormulaForecastAnnualText] = useState("");
  const [formulaNoteText, setFormulaNoteText] = useState("");
  const [formulaDirty, setFormulaDirty] = useState(false);
  const [formulaFullscreenOpen, setFormulaFullscreenOpen] = useState(false);
  const formulaFullscreenRef = useRef<HTMLTextAreaElement | null>(null);
  const [refEntityId, setRefEntityId] = useState<string | null>(null);
  const [refTableName, setRefTableName] = useState<string>("");
  const [refMetricSearch, setRefMetricSearch] = useState("");
  const [refMetricSearchInput, setRefMetricSearchInput] = useState("");
  const [aiDescription, setAiDescription] = useState("");
  const [aiDescriptionFullscreenOpen, setAiDescriptionFullscreenOpen] = useState(false);
  const aiDescriptionFullscreenRef = useRef<HTMLTextAreaElement | null>(null);
  const [aiScope, setAiScope] = useState<"active" | "selected" | "all-products">("active");
  const [aiTargetTableName, setAiTargetTableName] = useState<string>("");
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [aiPreviewOpen, setAiPreviewOpen] = useState(false);
  const [aiPreviewRows, setAiPreviewRows] = useState<AiPreviewRow[]>([]);
  const [aiPreviewDetailOpen, setAiPreviewDetailOpen] = useState(false);
  const [aiPreviewDetailRow, setAiPreviewDetailRow] = useState<AiPreviewRow | null>(null);
  const [aiAddSourceQuery, setAiAddSourceQuery] = useState("");
  const [aiAddSourceSelectedKey, setAiAddSourceSelectedKey] = useState("");
  const [aiAddSourceDropdownOpen, setAiAddSourceDropdownOpen] = useState(false);
  const [aiAddSourceEntityId, setAiAddSourceEntityId] = useState<string>("");
  const [aiAddSourceTableName, setAiAddSourceTableName] = useState<string>("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiApplying, setAiApplying] = useState(false);
  const [metricTableCatalog, setMetricTableCatalog] = useState<MetricTableCatalogItem[]>([]);
  const [catalogManagerOpen, setCatalogManagerOpen] = useState(false);
  const [catalogDraftName, setCatalogDraftName] = useState("");
  const [catalogBusy, setCatalogBusy] = useState(false);

  const activeEntity = useMemo(() => findOrgNodeById(orgTree, activeEntityId) ?? orgTree, [orgTree, activeEntityId]);
  const activeCatalogScope = useMemo(() => metricTableEntityScopeForNode(activeEntity), [activeEntity]);
  const activeScopeCatalogRows = useMemo(() => {
    if (!activeCatalogScope) return [];
    return metricTableCatalog
      .filter((row) => row.entity_scope === activeCatalogScope)
      .sort(
        (a, b) =>
          a.sort_order - b.sort_order ||
          a.table_name.localeCompare(b.table_name, "zh-CN")
      );
  }, [activeCatalogScope, metricTableCatalog]);
  const selectedEntities = useMemo(
    () => selectedEntityIds.map((id) => findOrgNodeById(orgTree, id)).filter((node): node is OrgProductNode => Boolean(node)),
    [orgTree, selectedEntityIds]
  );
  const visibleEntityTree = useMemo(() => filterOrgTree(orgTree, entitySearch), [orgTree, entitySearch]);
  const activeEntityNode = useMemo(
    () => findOrgNodeById(orgTree, activeEntityId),
    [orgTree, activeEntityId]
  );
  const activeMetricTables = useMemo(() => {
    const all = metricTablesByEntityId[activeEntityId] ?? [];
    const activeNames = metricTableNamesForOrgNode(activeEntityNode, metricTableCatalog);
    const byKey = new Map(all.map((t) => [normalizeMetricTableNameKey(t.name), t]));
    return activeNames.map((name) => {
      const hit = byKey.get(normalizeMetricTableNameKey(name));
      return hit ?? { id: buildMetricTableId(name), name, metrics: [] };
    });
  }, [metricTablesByEntityId, activeEntityId, activeEntityNode, metricTableCatalog]);
  const fallbackTableId = buildMetricTableId(
    defaultActiveTableNameForEntity(activeEntityId, orgTree, metricTableCatalog)
  );
  const activeTableId =
    activeTableIdByEntityId[activeEntityId] ??
    activeMetricTables.find((t) => t.id === fallbackTableId)?.id ??
    activeMetricTables[0]?.id ??
    fallbackTableId;
  const activeMetricTable = activeMetricTables.find((table) => table.id === activeTableId) ?? activeMetricTables[0] ?? null;

  useEffect(() => {
    if (!metricEditorOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMetricEditorOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    const raf = window.requestAnimationFrame(() => {
      const el = metricEditorRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const margin = 12;
      const x = Math.max(margin, Math.round((window.innerWidth - rect.width) / 2));
      const y = Math.max(margin, Math.round((window.innerHeight - rect.height) / 2));
      setMetricEditorPos({ x, y });
    });
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.cancelAnimationFrame(raf);
    };
  }, [metricEditorOpen]);
  const activeMetricTree = activeMetricTable?.metrics ?? [];
  const filteredMetricTree = useMemo(
    () => filterMetricTree(activeMetricTree, metricSearch),
    [activeMetricTree, metricSearch]
  );
  const hasMetricSearch = metricSearch.trim().length > 0;
  const activeMetricScopeKey = buildMetricScopeKey(activeEntityId, activeTableId);
  const activeMetricId = selectedMetricIdByScope[activeMetricScopeKey] ?? null;
  const activeMetric = useMemo(() => (activeMetricId ? findMetricNodeById(activeMetricTree, activeMetricId) : null), [activeMetricId, activeMetricTree]);
  const metricCount = useMemo(() => activeMetricTree.length > 0 ? collectMetricNodes(activeMetricTree).length : 0, [activeMetricTree]);
  const entityIdByCode = useMemo(() => {
    const m = new Map<string, string>();
    collectOrgNodes(orgTree).forEach((node) => {
      const code = String(node.code || "").trim().toUpperCase();
      if (code) m.set(code, node.id);
    });
    return m;
  }, [orgTree]);

  const knownCodesByEntityTableKey = useMemo(() => {
    const m = new Map<string, Set<string>>();
    Object.entries(metricTablesByEntityId).forEach(([entityId, tables]) => {
      const node = findOrgNodeById(orgTree, entityId);
      const entityCode = node?.code ?? "";
      (Array.isArray(tables) ? tables : []).forEach((table) => {
        const codes = new Set<string>();
        collectMetricNodes(table.metrics ?? []).forEach((n) => {
          const display = formatMetricCodeForDisplay(entityCode, n.code);
          const normalized = normalizeFormulaRefText(display);
          if (normalized) codes.add(normalized);
        });
        m.set(`${entityId}::${String(table.name || "").trim()}`, codes);
      });
    });
    return m;
  }, [metricTablesByEntityId, orgTree]);

  const codeToMetricIdByEntityTableKey = useMemo(() => {
    const m = new Map<string, Map<string, string>>();
    Object.entries(metricTablesByEntityId).forEach(([entityId, tables]) => {
      const node = findOrgNodeById(orgTree, entityId);
      const entityCode = node?.code ?? "";
      (Array.isArray(tables) ? tables : []).forEach((table) => {
        const inner = new Map<string, string>();
        collectMetricNodes(table.metrics ?? []).forEach((n) => {
          const display = formatMetricCodeForDisplay(entityCode, n.code);
          const normalized = normalizeFormulaRefText(display);
          if (normalized) inner.set(normalized, n.id);
        });
        m.set(`${entityId}::${String(table.name || "").trim()}`, inner);
      });
    });
    return m;
  }, [metricTablesByEntityId, orgTree]);

  const metricRefInfoByEntityTableKey = useMemo(() => {
    const m = new Map<string, Map<string, MetricRefInfo>>();
    Object.entries(metricTablesByEntityId).forEach(([entityId, tables]) => {
      const node = findOrgNodeById(orgTree, entityId);
      const entityCode = node?.code ?? "";
      (Array.isArray(tables) ? tables : []).forEach((table) => {
        const inner = new Map<string, MetricRefInfo>();
        collectMetricNodes(table.metrics ?? []).forEach((n) => {
          const displayCode = formatMetricCodeForDisplay(entityCode, n.code);
          const normalized = normalizeFormulaRefText(displayCode);
          if (!normalized) return;
          inner.set(normalized, { displayCode, name: String(n.name || "").trim() });
        });
        m.set(`${entityId}::${String(table.name || "").trim()}`, inner);
      });
    });
    return m;
  }, [metricTablesByEntityId, orgTree]);

  const formulaKnownCodeSet = useMemo(() => {
    const codes = new Set<string>();
    collectMetricNodes(activeMetricTree).forEach((n) => {
      const display = formatMetricCodeForDisplay(activeEntity.code, n.code);
      const normalized = normalizeFormulaRefText(display);
      if (normalized) codes.add(normalized);
    });
    return codes;
  }, [activeEntity.code, activeMetricTree]);

  const selfCodeNormalized = useMemo(() => {
    const display = activeMetric ? formatMetricCodeForDisplay(activeEntity.code, activeMetric.code) : "";
    return normalizeFormulaRefText(display);
  }, [activeEntity.code, activeMetric]);

  const flatMetricRowsForFormula = useMemo(() => collectFlatMetricRows(filteredMetricTree), [filteredMetricTree]);
  const currentTableName = String(activeMetricTable?.name ?? "").trim();
  const allProducts = useMemo(
    () => collectOrgNodes(orgTree).filter((n) => n.type === "level3"),
    [orgTree]
  );
  const metricConfigurableOrgNodes = useMemo(
    () => collectOrgNodes(orgTree).filter((n) => supportsMetricDefinition(n)),
    [orgTree]
  );
  const allMetricTableNames = useMemo(() => {
    const names = new Set<string>();
    Object.values(metricTablesByEntityId).forEach((tables) => {
      (tables ?? []).forEach((t) => {
        const name = String(t.name || "").trim();
        if (name) names.add(name);
      });
    });
    const list = [...names];
    list.sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
    return list;
  }, [metricTablesByEntityId]);

  useEffect(() => {
    if (!aiTargetTableName) setAiTargetTableName(currentTableName);
  }, [aiTargetTableName, currentTableName]);

  useEffect(() => {
    if (viewMode !== "formula") return;
    if (!refEntityId) setRefEntityId(activeEntityId);
    if (!refTableName) setRefTableName(currentTableName);
  }, [activeEntityId, currentTableName, refEntityId, refTableName, viewMode]);

  const refEntity = useMemo(() => {
    if (!refEntityId) return activeEntity;
    return findOrgNodeById(orgTree, refEntityId) ?? activeEntity;
  }, [activeEntity, orgTree, refEntityId]);

  const refTables = useMemo(() => metricTablesByEntityId[refEntity.id] ?? [], [metricTablesByEntityId, refEntity.id]);
  const refTable = useMemo(() => {
    const name = String(refTableName || "").trim();
    const found = refTables.find((t) => String(t.name || "").trim() === name);
    return found ?? refTables[0] ?? null;
  }, [refTableName, refTables]);
  const refFilteredTree = useMemo(() => filterMetricTree(refTable?.metrics ?? [], refMetricSearch), [refMetricSearch, refTable]);
  const refFlatRows = useMemo(() => collectFlatMetricRows(refFilteredTree), [refFilteredTree]);

  const buildFormulaInsertText = (
    sourceEntity: OrgProductNode,
    sourceTableName: string,
    sourceMetricDisplayCode: string,
    sourceMetricName: string
  ): string =>
    buildFormulaInsertTextShared(
      activeEntity.code,
      currentTableName,
      sourceEntity.code,
      sourceEntity.name,
      sourceTableName,
      sourceMetricDisplayCode,
      sourceMetricName
    );

  const decorateFormulaTextForDisplayWithContext = (formula: string, baseEntityId: string, baseTableName: string): string =>
    decorateFormulaTextForDisplayShared(
      formula,
      baseEntityId,
      baseTableName,
      entityIdByCode,
      metricRefInfoByEntityTableKey,
      (entityId, fallbackCode) => {
        const node = findOrgNodeById(orgTree, entityId);
        return String(node?.name || fallbackCode).trim();
      }
    );

  const metricFormulaForScope = (node: MetricNode, scope: FormulaScopeKind = formulaScope): string => {
    const legacy = String(node.formula ?? "").trim();
    if (scope === "actual") return String(node.formula_actual ?? legacy).trim();
    if (scope === "forecast") return String(node.formula_forecast ?? legacy).trim();
    if (scope === "budgetAnnual") return String(node.formula_budget_annual ?? "").trim();
    return String(node.formula_forecast_annual ?? "").trim();
  };

  const formulaText =
    formulaScope === "actual"
      ? formulaActualText
      : formulaScope === "forecast"
        ? formulaForecastText
        : formulaScope === "budgetAnnual"
          ? formulaBudgetAnnualText
          : formulaForecastAnnualText;
  const setFormulaText = (value: string) => {
    if (formulaScope === "actual") setFormulaActualText(value);
    else if (formulaScope === "forecast") setFormulaForecastText(value);
    else if (formulaScope === "budgetAnnual") setFormulaBudgetAnnualText(value);
    else setFormulaForecastAnnualText(value);
  };

  const formulaScopeLabel = FORMULA_SCOPE_LABEL[formulaScope];

  const loadFormulaDraftsForMetric = (metric: MetricNode | null) => {
    const legacy = String(metric?.formula ?? "").trim();
    const decorate = (raw: string) => decorateFormulaTextForDisplayWithContext(raw, activeEntityId, currentTableName);
    setFormulaActualText(decorate(String(metric?.formula_actual ?? legacy)));
    setFormulaForecastText(decorate(String(metric?.formula_forecast ?? legacy)));
    setFormulaBudgetAnnualText(decorate(String(metric?.formula_budget_annual ?? "")));
    setFormulaForecastAnnualText(decorate(String(metric?.formula_forecast_annual ?? "")));
    setFormulaNoteText(String(metric?.formula_note ?? "").trim());
  };

  const canonicalizeFormulaForStorage = (displayText: string): string =>
    canonicalizeFormulaForStorageShared(
      displayText,
      activeEntityId,
      activeEntity.code,
      activeEntity.name,
      currentTableName,
      metricRefInfoByEntityTableKey,
      entityIdByCode,
      (entityId) => {
        const node = findOrgNodeById(orgTree, entityId);
        return String(node?.name || "").trim();
      }
    );

  useEffect(() => {
    if (viewMode !== "formula") return;
    if (formulaDirty) return;
    loadFormulaDraftsForMetric(activeMetric);
    setFormulaDirty(false);
  }, [activeEntity.name, activeEntityId, activeMetric, activeMetricId, currentTableName, entityIdByCode, formulaDirty, metricRefInfoByEntityTableKey, orgTree, viewMode]);

  const formulaValidationMessage = useMemo(() => {
    if (!activeMetric) return "请选择一个指标后再编辑公式。";
    const validationOptions = {
      currentKnownCodes: formulaKnownCodeSet,
      selfCodeNormalized,
      entityIdByCode,
      knownCodesByEntityTableKey,
      currentEntityId: activeEntityId,
      currentEntityCode: activeEntity.code,
      currentTableName,
    };
    const validateDraft = (displayText: string, label: string): string | null => {
      const formatted = formatFormulaText(canonicalizeFormulaForStorage(displayText));
      const err = validateFormulaText(formatted, validationOptions);
      return err ? `校验失败（${label}）：${err}` : null;
    };
    const actualErr = validateDraft(formulaActualText, "实际月");
    if (actualErr) return actualErr;
    const forecastErr = validateDraft(formulaForecastText, "预测月");
    if (forecastErr) return forecastErr;
    const budgetAnnualErr = validateDraft(formulaBudgetAnnualText, "年预算");
    if (budgetAnnualErr) return budgetAnnualErr;
    const forecastAnnualErr = validateDraft(formulaForecastAnnualText, "年预测");
    if (forecastAnnualErr) return forecastAnnualErr;
    return "校验通过";
  }, [
    activeEntity.code,
    activeEntityId,
    activeMetric,
    currentTableName,
    entityIdByCode,
    formulaActualText,
    formulaBudgetAnnualText,
    formulaForecastText,
    formulaForecastAnnualText,
    formulaKnownCodeSet,
    knownCodesByEntityTableKey,
    selfCodeNormalized,
  ]);

  const formulaResolvedRefs = useMemo(() => {
    if (!activeMetric) return [];
    const refs = parseFormulaRefs(formulaText);
    const out: Array<{ key: string; label: string; missing: boolean }> = [];
    const seen = new Set<string>();
    refs.forEach((ref) => {
      if (ref.kind === "local") {
        const tableKey = `${activeEntityId}::${currentTableName}`;
        const info = metricRefInfoByEntityTableKey.get(tableKey)?.get(ref.metricCodeNormalized) ?? null;
        const label = info?.name ? `${info.displayCode} ${info.name}` : `${ref.metricCodeRaw}（未找到）`;
        const key = `local:${tableKey}:${ref.metricCodeNormalized}`;
        if (seen.has(key)) return;
        seen.add(key);
        out.push({ key, label, missing: !info?.name });
        return;
      }
      if (ref.kind === "cross_table") {
        const tableKey = `${activeEntityId}::${ref.tableName}`;
        const info = metricRefInfoByEntityTableKey.get(tableKey)?.get(ref.metricCodeNormalized) ?? null;
        const labelBase = `${ref.tableName}/${ref.metricCodeRaw}`;
        const label = info?.name ? `${labelBase} ${info.name}` : `${labelBase}（未找到）`;
        const key = `table:${ref.tableName}:${ref.metricCodeNormalized}`;
        if (seen.has(key)) return;
        seen.add(key);
        out.push({ key, label, missing: !info?.name });
        return;
      }
      const entityId = entityIdByCode.get(ref.entityCode) ?? "";
      const tableName = String(ref.tableName || "").trim();
      const tableKey = entityId ? `${entityId}::${tableName}` : "";
      const info = tableKey ? metricRefInfoByEntityTableKey.get(tableKey)?.get(ref.metricCodeNormalized) ?? null : null;
      const labelBase = `${ref.entityCode}/${tableName}/${ref.metricCodeRaw}`;
      const label = info?.name ? `${labelBase} ${info.name}` : `${labelBase}（未找到）`;
      const key = `entity:${ref.entityCode}:${tableName}:${ref.metricCodeNormalized}`;
      if (seen.has(key)) return;
      seen.add(key);
      out.push({ key, label, missing: !info?.name });
    });
    return out;
  }, [activeEntityId, activeMetric, currentTableName, entityIdByCode, formulaText, metricRefInfoByEntityTableKey]);

  const insertIntoFormula = (text: string, cursorShift: number) => {
    const el = formulaFullscreenOpen
      ? formulaFullscreenRef.current ?? formulaInputRef.current
      : formulaInputRef.current;
    if (!el) return;
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? start;
    const current = formulaText;
    const next = current.slice(0, start) + text + current.slice(end);
    setFormulaText(next);
    setFormulaDirty(true);
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + cursorShift;
      el.setSelectionRange(pos, pos);
    });
  };

  const selectFormulaMetric = (metricId: string) => {
    if (metricId === activeMetricId) return;
    if (formulaDirty && !confirm("当前公式还未保存，切换指标会丢失未保存内容，确认继续吗？")) return;
    setSelectedMetricIdByScope((prev) => ({ ...prev, [activeMetricScopeKey]: metricId }));
  };

  const openFormulaFromListRow = (metricId: string, presetScope?: FormulaScopeKind) => {
    if (metricId !== activeMetricId) {
      if (formulaDirty && !confirm("当前公式还未保存，切换指标会丢失未保存内容，确认继续吗？")) return;
      setSelectedMetricIdByScope((prev) => ({ ...prev, [activeMetricScopeKey]: metricId }));
    }
    const node = findMetricNodeById(activeMetricTree, metricId);
    if (node) {
      if (presetScope) {
        setFormulaScope(presetScope);
      } else if (metricHasForecastFormula(node)) {
        setFormulaScope("forecast");
      } else {
        setFormulaScope("actual");
      }
      loadFormulaDraftsForMetric(node);
    }
    setFormulaDirty(false);
    requestAnimationFrame(() => formulaInputRef.current?.focus());
  };

  const normalizeAiName = (text: string) => normalizeMetricNameText(String(text || "").trim());

  const parseAiTemplate = (raw: string): { targetName: string; tokens: Array<{ kind: "metric" | "op" | "literal"; value: string }> } | null => {
    let text = String(raw || "").trim();
    if (!text) return null;
    text = text.replace(/[＝]/g, "=").replace(/[＋]/g, "+").replace(/[－]/g, "-").replace(/[×]/g, "*").replace(/[÷]/g, "/").replace(/[，]/g, ",");
    const eqIndex = text.indexOf("=");
    const altIndex = eqIndex >= 0 ? eqIndex : text.indexOf("等于");
    if (altIndex < 0) return null;
    const left = eqIndex >= 0 ? text.slice(0, eqIndex) : text.slice(0, altIndex);
    const right = eqIndex >= 0 ? text.slice(eqIndex + 1) : text.slice(altIndex + 2);
    const targetName = left.trim();
    const rhs = right.trim().replace(/^由/, "").trim();
    if (!targetName || !rhs) return null;
    const parts = rhs.split(/(\+|\-|\*|\/|\(|\))/).filter((p) => p !== "");
    const tokens: Array<{ kind: "metric" | "op" | "literal"; value: string }> = [];
    parts.forEach((p) => {
      const t = p.trim();
      if (!t) return;
      if (["+", "-", "*", "/", "(", ")"].includes(t)) {
        tokens.push({ kind: "op", value: t });
        return;
      }
      if (/^\d+(\.\d+)?$/.test(t)) {
        tokens.push({ kind: "literal", value: t });
        return;
      }
      tokens.push({ kind: "metric", value: t });
    });
    if (tokens.length === 0) return null;
    return { targetName, tokens };
  };

  const AI_METRIC_CODE_RE = /[A-Za-z]{1,6}\d{0,2}(?:\.\d+){1,6}/g;

  const getMetricLevelByDisplayCode = (displayCode: string): number => {
    const dots = String(displayCode || "").match(/\./g);
    return dots ? dots.length : 0;
  };

  const parseAiLevelRestriction = (raw: string): number | null => {
    const text = String(raw || "");
    if (!text.trim()) return null;
    const hasL1 = /一级科目/.test(text);
    const hasL2 = /二级科目/.test(text);
    const hasL3 = /三级科目/.test(text);
    if (/不要取.*(非一级|一级科目之外|除一级)/.test(text) || /(只|仅|只能|必须).{0,6}一级科目/.test(text) || (/注意.{0,10}一级科目/.test(text) && !hasL2 && !hasL3)) return 1;
    if (/不要取.*(非二级|二级科目之外|除二级)/.test(text) || /(只|仅|只能|必须).{0,6}二级科目/.test(text) || (/注意.{0,10}二级科目/.test(text) && !hasL1 && !hasL3)) return 2;
    if (/不要取.*(非三级|三级科目之外|除三级)/.test(text) || /(只|仅|只能|必须).{0,6}三级科目/.test(text) || (/注意.{0,10}三级科目/.test(text) && !hasL1 && !hasL2)) return 3;
    if (hasL1 && !hasL2 && !hasL3) return 1;
    if (hasL2 && !hasL1 && !hasL3) return 2;
    if (hasL3 && !hasL1 && !hasL2) return 3;
    return null;
  };

  const buildAiCandidates = (
    phrase: string,
    entityId: string,
    entityCode: string,
    tableName: string,
    nodes: MetricNode[],
    excludeMetricId: string,
    levelRestriction: number | null
  ): AiExprCandidate[] => {
    const rawPhrase = String(phrase || "").trim();
    const phraseNorm = normalizeAiName(rawPhrase);
    const codeMatch = rawPhrase.match(AI_METRIC_CODE_RE)?.[0] ?? "";
    const wantedCode = codeMatch ? normalizeFormulaRefText(codeMatch) : "";
    const out: Array<{ score: number; item: AiExprCandidate }> = [];
    nodes.forEach((n) => {
      if (n.id === excludeMetricId) return;
      const displayCode = formatMetricCodeForDisplay(entityCode, n.code);
      if (levelRestriction !== null && getMetricLevelByDisplayCode(displayCode) !== levelRestriction) return;
      const normalizedCode = normalizeFormulaRefText(displayCode);
      if (!normalizedCode) return;
      const name = String(n.name || "").trim();
      const nameNorm = normalizeAiName(name);
      if (!nameNorm && !wantedCode) return;
      let score = 0;
      if (wantedCode && normalizedCode === wantedCode) score = Math.max(score, 300);
      if (phraseNorm && nameNorm && phraseNorm === nameNorm) score = Math.max(score, 240);
      if (phraseNorm && nameNorm && phraseNorm.includes(nameNorm)) score = Math.max(score, 160 + Math.min(60, nameNorm.length));
      if (phraseNorm && nameNorm && nameNorm.includes(phraseNorm)) score = Math.max(score, 140 + Math.min(40, phraseNorm.length));
      if (score <= 0) return;
      out.push({ score, item: { entityId, entityCode, tableName, normalizedCode, displayCode, name, formulaPiece: displayCode } });
    });
    out.sort((a, b) => b.score - a.score);
    const seen = new Set<string>();
    const result: AiExprCandidate[] = [];
    out.forEach((x) => {
      if (seen.has(x.item.normalizedCode)) return;
      seen.add(x.item.normalizedCode);
      result.push(x.item);
    });
    return result.slice(0, 8);
  };

  const parseAiExpression = (raw: string): { tokens: Array<{ kind: "metric" | "op" | "literal"; value: string }> } | null => {
    let text = String(raw || "").trim();
    if (!text) return null;
    text = text.replace(/[＝]/g, "=").replace(/[＋]/g, "+").replace(/[－]/g, "-").replace(/[×]/g, "*").replace(/[÷]/g, "/").replace(/[，]/g, ",");
    if (text.includes("=") || text.includes("等于")) return null;
    const parts = text.split(/(\+|\-|\*|\/|\(|\))/).filter((p) => p !== "");
    const tokens: Array<{ kind: "metric" | "op" | "literal"; value: string }> = [];
    parts.forEach((p) => {
      const t = p.trim();
      if (!t) return;
      if (["+", "-", "*", "/", "(", ")"].includes(t)) {
        tokens.push({ kind: "op", value: t });
        return;
      }
      if (/^\d+(\.\d+)?$/.test(t)) {
        tokens.push({ kind: "literal", value: t });
        return;
      }
      tokens.push({ kind: "metric", value: t });
    });
    if (tokens.length === 0) return null;
    return { tokens };
  };

  const parseAiActiveTargetTemplate = (raw: string): { tokens: Array<{ kind: "metric" | "op" | "literal"; value: string }> } | null => {
    let text = String(raw || "").trim();
    if (!text) return null;
    text = text.replace(/[＝]/g, "=").replace(/[＋]/g, "+").replace(/[－]/g, "-").replace(/[×]/g, "*").replace(/[÷]/g, "/").replace(/[，]/g, ",");
    const eqIndex = text.indexOf("=");
    const altIndex = eqIndex >= 0 ? eqIndex : text.indexOf("等于");
    if (altIndex < 0) return null;
    const left = eqIndex >= 0 ? text.slice(0, eqIndex) : text.slice(0, altIndex);
    const right = eqIndex >= 0 ? text.slice(eqIndex + 1) : text.slice(altIndex + 2);
    if (left.trim()) return null;
    const rhs = right.trim().replace(/^由/, "").trim();
    if (!rhs) return null;
    const parts = rhs.split(/(\+|\-|\*|\/|\(|\))/).filter((p) => p !== "");
    const tokens: Array<{ kind: "metric" | "op" | "literal"; value: string }> = [];
    parts.forEach((p) => {
      const t = p.trim();
      if (!t) return;
      if (["+", "-", "*", "/", "(", ")"].includes(t)) {
        tokens.push({ kind: "op", value: t });
        return;
      }
      if (/^\d+(\.\d+)?$/.test(t)) {
        tokens.push({ kind: "literal", value: t });
        return;
      }
      tokens.push({ kind: "metric", value: t });
    });
    if (tokens.length === 0) return null;
    return { tokens };
  };

  const parseAiSumLevel3ByCodeTemplate = (
    raw: string
  ): { targetEntityCode: string | null; code1: string; code2: string } | null => {
    const text = String(raw || "").trim();
    if (!text) return null;
    if (!text.includes("所有") || !text.includes("三级产品") || !text.includes("相加") || !text.includes("等于")) return null;
    const codeMatches = [...text.matchAll(/一级科目代码[^0-9A-Za-z]*[“"']?([0-9A-Za-z]{1,10})[”"']?/g)].map((m) => String(m[1] || ""));
    if (codeMatches.length === 0) return null;
    const code1 = codeMatches[0] || "";
    const code2 = codeMatches[1] || code1;
    const afterEq = text.split("等于")[1] ?? "";
    const entityMatch = /([A-Za-z0-9]{1,6})\s*机构/.exec(afterEq);
    const targetEntityCode = entityMatch?.[1] ? String(entityMatch[1]).trim().toUpperCase() : null;
    if (!code1) return null;
    return { targetEntityCode, code1, code2 };
  };

  const generateAiPreview = async () => {
    setAiGenerating(true);
    try {
      const template = parseAiTemplate(aiDescription);
      const sumTpl = template ? null : parseAiSumLevel3ByCodeTemplate(aiDescription);
      const activeTargetTpl = template || sumTpl ? null : parseAiActiveTargetTemplate(aiDescription);
      const exprTpl = template || sumTpl || activeTargetTpl ? null : parseAiExpression(aiDescription);
      if (!template && !sumTpl && !activeTargetTpl && !exprTpl) {
        alert(
          "支持四种输入：\n1）“利息净收入 = 资产业务利息净收入 + 负债业务利息净收入”\n2）“所有三级产品一级科目代码为“01”的相加等于AA机构一级科目代码“01””\n3）在当前选中指标下，直接写表达式，例如：A01.14 + A01.15（也可以写：贷款利息收入 + 金融机构往来利息收入）\n4）在当前选中指标下，写“等于...”类话术（不写左边指标名），例如：等于本表中一级科目贷款利息收入和一级科目金融机构往来利息收入的和"
        );
        return;
      }
      const scopeEntities =
        aiScope === "active" ? [activeEntity] : aiScope === "all-products" ? allProducts : selectedEntities.length > 0 ? selectedEntities : [activeEntity];
      const targetTableName = String(aiTargetTableName || currentTableName).trim();
      const preview: AiPreviewRow[] = [];
      if (template) {
        for (const entity of scopeEntities) {
          const tables = metricTablesByEntityId[entity.id] ?? [];
          const table = tables.find((t) => String(t.name || "").trim() === targetTableName) ?? null;
          if (!table) {
            preview.push({
              entityId: entity.id,
              entityCode: entity.code,
              entityName: entity.name,
              tableName: targetTableName,
              targetMetricId: "",
              targetMetricName: template.targetName,
              targetMetricCodeDisplay: "",
              oldFormula: "",
              newFormula: "",
              ok: false,
              reason: "未找到对应指标表",
            });
            continue;
          }
          const nodes = collectMetricNodes(table.metrics ?? []);
          const target = nodes.find((n) => normalizeAiName(n.name) === normalizeAiName(template.targetName)) ?? null;
          if (!target) {
            preview.push({
              entityId: entity.id,
              entityCode: entity.code,
              entityName: entity.name,
              tableName: targetTableName,
              targetMetricId: "",
              targetMetricName: template.targetName,
              targetMetricCodeDisplay: "",
              oldFormula: "",
              newFormula: "",
              ok: false,
              reason: "未找到目标指标",
            });
            continue;
          }
          const missingNames: string[] = [];
          const exprPieces: string[] = [];
          for (const token of template.tokens) {
            if (token.kind === "op") {
              exprPieces.push(token.value);
              continue;
            }
            if (token.kind === "literal") {
              exprPieces.push(token.value);
              continue;
            }
            const source = nodes.find((n) => normalizeAiName(n.name) === normalizeAiName(token.value)) ?? null;
            if (!source) {
              missingNames.push(token.value);
              continue;
            }
            exprPieces.push(formatMetricCodeForDisplay(entity.code, source.code));
          }
          if (missingNames.length > 0) {
            preview.push({
              entityId: entity.id,
              entityCode: entity.code,
              entityName: entity.name,
              tableName: targetTableName,
              targetMetricId: target.id,
              targetMetricName: target.name,
              targetMetricCodeDisplay: formatMetricCodeForDisplay(entity.code, target.code),
              oldFormula: metricFormulaForScope(target),
              newFormula: "",
              ok: false,
              reason: `缺少来源指标：${[...new Set(missingNames)].slice(0, 4).join("、")}`,
            });
            continue;
          }
          const next = formatFormulaText(exprPieces.join(" "));
          preview.push({
            entityId: entity.id,
            entityCode: entity.code,
            entityName: entity.name,
            tableName: targetTableName,
            targetMetricId: target.id,
            targetMetricName: target.name,
            targetMetricCodeDisplay: formatMetricCodeForDisplay(entity.code, target.code),
            oldFormula: metricFormulaForScope(target),
            newFormula: next,
            ok: true,
          });
        }
      } else if (sumTpl) {
        const targetEntity =
          (sumTpl.targetEntityCode ? findOrgNodeByCode(orgTree, sumTpl.targetEntityCode) : null) ??
          (aiScope === "active" ? activeEntity : null) ??
          activeEntity;

        const targetTables = metricTablesByEntityId[targetEntity.id] ?? [];
        const targetTable = targetTables.find((t) => String(t.name || "").trim() === targetTableName) ?? null;
        if (!targetTable) {
          preview.push({
            entityId: targetEntity.id,
            entityCode: targetEntity.code,
            entityName: targetEntity.name,
            tableName: targetTableName,
            targetMetricId: "",
            targetMetricName: `一级科目代码${sumTpl.code2}`,
            targetMetricCodeDisplay: "",
            oldFormula: "",
            newFormula: "",
            ok: false,
            reason: "未找到目标指标表",
          });
        } else {
          const targetNodes = collectMetricNodes(targetTable.metrics ?? []);
          const targetWanted = normalizeFormulaRefText(normalizeMetricCodeForStorage(targetEntity.code, sumTpl.code2));
          const target = targetNodes.find((n) => String(n.levelLabel) === "一级" && normalizeFormulaRefText(n.code) === targetWanted) ?? null;
          if (!target) {
            preview.push({
              entityId: targetEntity.id,
              entityCode: targetEntity.code,
              entityName: targetEntity.name,
              tableName: targetTableName,
              targetMetricId: "",
              targetMetricName: `一级科目代码${sumTpl.code2}`,
              targetMetricCodeDisplay: "",
              oldFormula: "",
              newFormula: "",
              ok: false,
              reason: "未找到目标一级科目",
            });
          } else {
            const products = collectOrgNodes(targetEntity).filter((n) => n.type === "level3");
            const sourcePieces: string[] = [];
            const missingSources: string[] = [];
            const srcWantedByProductCode = new Map<string, string>();
            products.forEach((p) => srcWantedByProductCode.set(p.id, normalizeFormulaRefText(normalizeMetricCodeForStorage(p.code, sumTpl.code1))));
            products.forEach((p) => {
              const tables = metricTablesByEntityId[p.id] ?? [];
              const table = tables.find((t) => String(t.name || "").trim() === targetTableName) ?? null;
              if (!table) {
                missingSources.push(`${p.code}未找到指标表`);
                return;
              }
              const nodes = collectMetricNodes(table.metrics ?? []);
              const wanted = srcWantedByProductCode.get(p.id) ?? "";
              const source = nodes.find((n) => String(n.levelLabel) === "一级" && normalizeFormulaRefText(n.code) === wanted) ?? null;
              if (!source) {
                missingSources.push(`${p.code}缺少一级科目${sumTpl.code1}`);
                return;
              }
              const displayCode = formatMetricCodeForDisplay(p.code, source.code);
              sourcePieces.push(buildFormulaInsertText(p, targetTableName, displayCode, source.name));
            });
            if (sourcePieces.length === 0) {
              preview.push({
                entityId: targetEntity.id,
                entityCode: targetEntity.code,
                entityName: targetEntity.name,
                tableName: targetTableName,
                targetMetricId: target.id,
                targetMetricName: target.name,
                targetMetricCodeDisplay: formatMetricCodeForDisplay(targetEntity.code, target.code),
                oldFormula: metricFormulaForScope(target),
                newFormula: "",
                ok: false,
                reason: missingSources.length > 0 ? missingSources.slice(0, 6).join("；") : "未找到可汇总的三级产品来源指标",
              });
            } else if (missingSources.length > 0) {
              preview.push({
                entityId: targetEntity.id,
                entityCode: targetEntity.code,
                entityName: targetEntity.name,
                tableName: targetTableName,
                targetMetricId: target.id,
                targetMetricName: target.name,
                targetMetricCodeDisplay: formatMetricCodeForDisplay(targetEntity.code, target.code),
                oldFormula: metricFormulaForScope(target),
                newFormula: "",
                ok: false,
                reason: missingSources.slice(0, 6).join("；"),
              });
            } else {
              const next = formatFormulaText(`SUM(${sourcePieces.join(",")})`);
              preview.push({
                entityId: targetEntity.id,
                entityCode: targetEntity.code,
                entityName: targetEntity.name,
                tableName: targetTableName,
                targetMetricId: target.id,
                targetMetricName: target.name,
                targetMetricCodeDisplay: formatMetricCodeForDisplay(targetEntity.code, target.code),
                oldFormula: metricFormulaForScope(target),
                newFormula: next,
                ok: true,
              });
            }
          }
        }
      }
      const activeTargetOrExprTpl = activeTargetTpl ?? exprTpl;
      if (activeTargetOrExprTpl) {
        const entity = activeEntity;
        const tables = metricTablesByEntityId[entity.id] ?? [];
        const table = tables.find((t) => String(t.name || "").trim() === targetTableName) ?? null;
        if (!table) {
          preview.push({
            entityId: entity.id,
            entityCode: entity.code,
            entityName: entity.name,
            tableName: targetTableName,
            targetMetricId: "",
            targetMetricName: activeMetric?.name ?? "",
            targetMetricCodeDisplay: "",
            oldFormula: "",
            newFormula: "",
            ok: false,
            reason: "未找到对应指标表",
          });
        } else if (!activeMetric) {
          preview.push({
            entityId: entity.id,
            entityCode: entity.code,
            entityName: entity.name,
            tableName: targetTableName,
            targetMetricId: "",
            targetMetricName: "",
            targetMetricCodeDisplay: "",
            oldFormula: "",
            newFormula: "",
            ok: false,
            reason: "请先在左侧选择一个目标指标",
          });
        } else {
          const nodes = collectMetricNodes(table.metrics ?? []);
          const target =
            nodes.find((n) => n.id === activeMetric.id) ??
            nodes.find((n) => normalizeAiName(n.name) === normalizeAiName(activeMetric.name)) ??
            null;
          if (!target) {
            preview.push({
              entityId: entity.id,
              entityCode: entity.code,
              entityName: entity.name,
              tableName: targetTableName,
              targetMetricId: "",
              targetMetricName: activeMetric.name,
              targetMetricCodeDisplay: "",
              oldFormula: "",
              newFormula: "",
              ok: false,
              reason: "未找到目标指标",
            });
          } else {
            const missingNames: string[] = [];
            const hasExplicitOps = activeTargetOrExprTpl.tokens.some((t) => t.kind === "op");
            const whole = String(aiDescription || "").trim().replace(/[＝]/g, "=").replace(/[＋]/g, "+").replace(/[－]/g, "-").replace(/[×]/g, "*").replace(/[÷]/g, "/");
            const wholeNorm = normalizeAiName(whole);
            const levelRestriction = parseAiLevelRestriction(whole);
            const targetDisplayCode = formatMetricCodeForDisplay(entity.code, target.code);
            const targetDisplayCodeNormalized = normalizeFormulaRefText(targetDisplayCode);
            let aiExprTokens: AiExprToken[] = [];

            const pickCandidateDisplayCode = (token: AiExprToken): string => {
              const selected = token.selectedNormalizedCode || token.candidates?.[0]?.normalizedCode || "";
              const picked = (token.candidates ?? []).find((c) => c.normalizedCode === selected) ?? token.candidates?.[0] ?? null;
              return picked?.formulaPiece || picked?.displayCode || "";
            };

            let next = "";
            if (!hasExplicitOps) {
              const codes = [...whole.matchAll(AI_METRIC_CODE_RE)]
                .map((m) => String(m[0] || ""))
                .filter((c) => normalizeFormulaRefText(c) !== targetDisplayCodeNormalized)
                .filter((c) => (levelRestriction !== null ? getMetricLevelByDisplayCode(c) === levelRestriction : true));
              if (codes.length >= 2) {
                aiExprTokens = codes.slice(0, 8).map((c) => {
                  const candidates = buildAiCandidates(c, entity.id, entity.code, targetTableName, nodes, target.id, levelRestriction);
                  const selectedNormalizedCode = candidates[0]?.normalizedCode;
                  if (!selectedNormalizedCode) missingNames.push(c);
                  return { kind: "metric", value: c, candidates, selectedNormalizedCode };
                });
                if (missingNames.length === 0) {
                  next = formatFormulaText(aiExprTokens.map((t) => pickCandidateDisplayCode(t)).filter(Boolean).join(" + "));
                }
              } else if (wholeNorm) {
                const hits = nodes
                  .filter((n) => {
                    if (n.id === target.id) return false;
                    if (levelRestriction === null) return true;
                    const dc = formatMetricCodeForDisplay(entity.code, n.code);
                    return getMetricLevelByDisplayCode(dc) === levelRestriction;
                  })
                  .map((n) => ({ node: n, nameNorm: normalizeAiName(n.name), idx: wholeNorm.indexOf(normalizeAiName(n.name)) }))
                  .filter((x) => x.nameNorm && x.idx >= 0)
                  .sort((a, b) => a.idx - b.idx || b.nameNorm.length - a.nameNorm.length);
                const unique: MetricNode[] = [];
                const seen = new Set<string>();
                hits.forEach((h) => {
                  if (seen.has(h.node.id)) return;
                  seen.add(h.node.id);
                  unique.push(h.node);
                });
                if (unique.length >= 2) {
                  aiExprTokens = unique.slice(0, 8).map((n) => {
                    const phrase = String(n.name || "").trim();
                    const candidates = buildAiCandidates(phrase, entity.id, entity.code, targetTableName, nodes, target.id, levelRestriction);
                    const selectedNormalizedCode = candidates[0]?.normalizedCode;
                    if (!selectedNormalizedCode) missingNames.push(phrase);
                    return { kind: "metric", value: phrase, candidates, selectedNormalizedCode };
                  });
                  if (missingNames.length === 0) {
                    next = formatFormulaText(aiExprTokens.map((t) => pickCandidateDisplayCode(t)).filter(Boolean).join(" + "));
                  }
                }
              }
            }

            if (!next.trim()) {
              aiExprTokens = [];
              const exprPieces: string[] = [];
              for (const token of activeTargetOrExprTpl.tokens) {
                if (token.kind === "op" || token.kind === "literal") {
                  aiExprTokens.push({ kind: token.kind, value: token.value });
                  exprPieces.push(token.value);
                  continue;
                }
                const phrase = String(token.value || "").trim();
                const candidates = buildAiCandidates(phrase, entity.id, entity.code, targetTableName, nodes, target.id, levelRestriction);
                const selectedNormalizedCode = candidates[0]?.normalizedCode;
                if (!selectedNormalizedCode) {
                  missingNames.push(phrase);
                  aiExprTokens.push({ kind: "metric", value: phrase, candidates, selectedNormalizedCode: "" });
                  continue;
                }
                aiExprTokens.push({ kind: "metric", value: phrase, candidates, selectedNormalizedCode });
                exprPieces.push(pickCandidateDisplayCode({ kind: "metric", value: phrase, candidates, selectedNormalizedCode }));
              }
              if (missingNames.length === 0) next = formatFormulaText(exprPieces.join(" "));
            }

            if (missingNames.length > 0) {
              preview.push({
                entityId: entity.id,
                entityCode: entity.code,
                entityName: entity.name,
                tableName: targetTableName,
                targetMetricId: target.id,
                targetMetricName: target.name,
                targetMetricCodeDisplay: formatMetricCodeForDisplay(entity.code, target.code),
                oldFormula: metricFormulaForScope(target),
                newFormula: "",
                ok: false,
                reason: `无法识别：${[...new Set(missingNames)].slice(0, 4).join("、")}`,
                aiExprTokens: aiExprTokens.length > 0 ? aiExprTokens : undefined,
              });
            } else if (!next.trim()) {
              preview.push({
                entityId: entity.id,
                entityCode: entity.code,
                entityName: entity.name,
                tableName: targetTableName,
                targetMetricId: target.id,
                targetMetricName: target.name,
                targetMetricCodeDisplay: formatMetricCodeForDisplay(entity.code, target.code),
                oldFormula: metricFormulaForScope(target),
                newFormula: "",
                ok: false,
                reason: "未能从描述中解析出可用的公式表达式",
                aiExprTokens: aiExprTokens.length > 0 ? aiExprTokens : undefined,
              });
            } else {
              const currentKnownCodes = knownCodesByEntityTableKey.get(`${entity.id}::${targetTableName}`) ?? formulaKnownCodeSet;
              const err = validateFormulaText(next, {
                currentKnownCodes,
                selfCodeNormalized: normalizeFormulaRefText(formatMetricCodeForDisplay(entity.code, target.code)),
                entityIdByCode,
                knownCodesByEntityTableKey,
                currentEntityId: entity.id,
                currentEntityCode: entity.code,
                currentTableName: targetTableName,
              });
              const reasonText = err
                ? err.includes("引用自身")
                  ? "解析结果包含目标指标自身（通常是“指标名被包含匹配”导致）。请在描述中明确两个来源指标的完整名称或代码。"
                  : `公式校验失败：${err}`
                : undefined;
              preview.push({
                entityId: entity.id,
                entityCode: entity.code,
                entityName: entity.name,
                tableName: targetTableName,
                targetMetricId: target.id,
                targetMetricName: target.name,
                targetMetricCodeDisplay: formatMetricCodeForDisplay(entity.code, target.code),
                oldFormula: metricFormulaForScope(target),
                newFormula: err ? "" : next,
                ok: !err,
                reason: reasonText,
                aiExprTokens: aiExprTokens.length > 0 ? aiExprTokens : undefined,
              });
            }
          }
        }
      }
      setAiPreviewRows(preview);
      setAiPreviewOpen(true);
    } finally {
      setAiGenerating(false);
    }
  };

  const formatValidateFormulaDraft = (displayText: string, label: string): string | null => {
    const formatted = formatFormulaText(canonicalizeFormulaForStorage(displayText));
    const err = validateFormulaText(formatted, {
      currentKnownCodes: formulaKnownCodeSet,
      selfCodeNormalized,
      entityIdByCode,
      knownCodesByEntityTableKey,
      currentEntityId: activeEntityId,
      currentEntityCode: activeEntity.code,
      currentTableName,
    });
    if (err) {
      alert(`公式校验失败（${label}）：${err}`);
      return null;
    }
    return formatted.trim();
  };

  const collectStoredFormulaTexts = (node: MetricNode, scope: FormulaScopeKind): string[] => {
    const scoped = String(
      scope === "actual"
        ? node.formula_actual ?? ""
        : scope === "forecast"
          ? node.formula_forecast ?? ""
          : scope === "budgetAnnual"
            ? node.formula_budget_annual ?? ""
            : node.formula_forecast_annual ?? ""
    ).trim();
    if (scope === "budgetAnnual" || scope === "forecastAnnual") return scoped ? [scoped] : [];
    if (scoped) return [scoped];
    const hasSplitFormula = Boolean(String(node.formula_actual ?? "").trim() || String(node.formula_forecast ?? "").trim());
    if (hasSplitFormula) return [];
    const legacy = String(node.formula ?? "").trim();
    return legacy ? [legacy] : [];
  };

  const buildFormulaDependencyEdges = (
    tablesByEntityIdSnapshot: Record<string, MetricTable[]>,
    scope: FormulaScopeKind
  ): Map<MetricKey, MetricKey[]> => {
    const edges = new Map<MetricKey, MetricKey[]>();
    Object.entries(tablesByEntityIdSnapshot).forEach(([entityId, tables]) => {
      (tables ?? []).forEach((table) => {
        const tableName = String(table.name || "").trim();
        collectMetricNodes(table.metrics ?? []).forEach((node) => {
          const fromKey = metricKey(entityId, tableName, node.id);
          const deps: MetricKey[] = [];
          collectStoredFormulaTexts(node, scope).forEach((f) => {
            parseFormulaRefs(f).forEach((ref) => {
              const dep = resolveFormulaRefDependency(ref, entityId, tableName, entityIdByCode, codeToMetricIdByEntityTableKey);
              if (dep) deps.push(metricKey(dep.entityId, dep.tableName, dep.metricId));
            });
          });
          if (deps.length > 0) edges.set(fromKey, deps);
        });
      });
    });
    return edges;
  };

  const formulaFullValidationMessage = useMemo(() => {
    if (formulaValidationMessage !== "校验通过") return formulaValidationMessage;
    if (!activeMetric) return formulaValidationMessage;
    const actualFormatted = formatFormulaText(canonicalizeFormulaForStorage(formulaActualText)).trim();
    const forecastFormatted = formatFormulaText(canonicalizeFormulaForStorage(formulaForecastText)).trim();
    const budgetAnnualFormatted = formatFormulaText(canonicalizeFormulaForStorage(formulaBudgetAnnualText)).trim();
    const forecastAnnualFormatted = formatFormulaText(canonicalizeFormulaForStorage(formulaForecastAnnualText)).trim();
    const tempTablesByEntityId = { ...metricTablesByEntityId };
    const curTables = tempTablesByEntityId[activeEntityId] ?? [];
    tempTablesByEntityId[activeEntityId] = curTables.map((t) =>
      String(t.name || "").trim() === currentTableName
        ? {
            ...t,
            metrics: updateMetricNodeById(t.metrics ?? [], activeMetric.id, (n) => ({
              ...n,
              formula: forecastFormatted || actualFormatted,
              formula_actual: actualFormatted,
              formula_forecast: forecastFormatted,
              formula_budget_annual: budgetAnnualFormatted,
              formula_forecast_annual: forecastAnnualFormatted,
            })),
          }
        : t
    );
    const start = metricKey(activeEntityId, currentTableName, activeMetric.id);
    const actualCycle = detectCycleFrom(start, buildFormulaDependencyEdges(tempTablesByEntityId, "actual"));
    const forecastCycle = detectCycleFrom(start, buildFormulaDependencyEdges(tempTablesByEntityId, "forecast"));
    const budgetAnnualCycle = detectCycleFrom(start, buildFormulaDependencyEdges(tempTablesByEntityId, "budgetAnnual"));
    const forecastAnnualCycle = detectCycleFrom(start, buildFormulaDependencyEdges(tempTablesByEntityId, "forecastAnnual"));
    const cycle = actualCycle ?? forecastCycle ?? budgetAnnualCycle ?? forecastAnnualCycle;
    return cycle ? "校验失败：检测到循环依赖" : "校验通过";
  }, [
    activeEntityId,
    activeMetric,
    currentTableName,
    formulaActualText,
    formulaBudgetAnnualText,
    formulaForecastText,
    formulaForecastAnnualText,
    formulaValidationMessage,
    metricTablesByEntityId,
  ]);

  const applyAiPreview = async () => {
    const okRows = aiPreviewRows.filter((r) => r.ok);
    if (okRows.length === 0) {
      alert("没有可应用的公式变更。");
      return;
    }
    if (!confirm(`将应用 ${okRows.length} 条公式变更，并写入数据库。确认继续吗？`)) return;
    setAiApplying(true);
    try {
      const grouped = new Map<string, AiPreviewRow[]>();
      okRows.forEach((r) => {
        const key = `${r.entityId}::${r.tableName}`;
        grouped.set(key, [...(grouped.get(key) ?? []), r]);
      });
      let anyFailed = false;
      const nextTablesByEntityId: Record<string, MetricTable[]> = JSON.parse(JSON.stringify(metricTablesByEntityId));
      grouped.forEach((rows, key) => {
        const [entityId, tableName] = key.split("::");
        const tables = nextTablesByEntityId[entityId] ?? [];
        nextTablesByEntityId[entityId] = tables.map((t) => {
          if (String(t.name || "").trim() !== String(tableName || "").trim()) return t;
          let metrics = t.metrics ?? [];
          rows.forEach((row) => {
            metrics = updateMetricNodeById(metrics, row.targetMetricId, (n) => {
              const patch =
                formulaScope === "actual"
                  ? { formula_actual: row.newFormula }
                  : formulaScope === "forecast"
                    ? { formula_forecast: row.newFormula }
                    : formulaScope === "budgetAnnual"
                      ? { formula_budget_annual: row.newFormula }
                      : { formula_forecast_annual: row.newFormula };
              const legacy =
                formulaScope === "actual" || formulaScope === "forecast"
                  ? String(row.newFormula ?? "").trim() || String(n.formula ?? "").trim()
                  : String(n.formula ?? "").trim();
              return { ...n, ...patch, formula: legacy };
            });
          });
          return { ...t, metrics };
        });
      });

      const edges = buildFormulaDependencyEdges(nextTablesByEntityId, formulaScope);
      for (const row of okRows) {
        const start = metricKey(row.entityId, row.tableName, row.targetMetricId);
        const cycle = detectCycleFrom(start, edges);
        if (cycle) {
          alert("检测到循环依赖，已取消批量应用。请检查预览公式是否互相引用形成闭环。");
          return;
        }
      }

      setMetricTablesByEntityId(nextTablesByEntityId);
      if (viewMode === "formula" && activeMetricId) {
        const hit = okRows.find(
          (r) =>
            r.targetMetricId === activeMetricId &&
            r.entityId === activeEntityId &&
            String(r.tableName || "").trim() === String(currentTableName || "").trim()
        );
        if (hit) {
          const tables = nextTablesByEntityId[hit.entityId] ?? [];
          const table = tables.find((t) => String(t.name || "").trim() === String(hit.tableName || "").trim());
          const node = table ? findMetricNodeById(table.metrics ?? [], hit.targetMetricId) : null;
          if (node) {
            loadFormulaDraftsForMetric(node);
            setFormulaDirty(false);
          }
        }
      }

      for (const [key] of grouped.entries()) {
        const [entityId, tableName] = key.split("::");
        const tables = nextTablesByEntityId[entityId] ?? [];
        const table = tables.find((t) => String(t.name || "").trim() === String(tableName || "").trim());
        const updatedMetrics = table?.metrics ?? [];
        const ok = await persistMetricTableByEntityAndName(entityId, tableName, updatedMetrics);
        if (!ok) anyFailed = true;
      }
      window.dispatchEvent(new Event("org-product-metrics-saved"));
      alert(anyFailed ? "已应用，但部分表保存失败（请重试保存刷新）。" : "已成功应用并保存到数据库。");
    } finally {
      setAiApplying(false);
    }
  };

  const openAiPreviewDetail = (row: AiPreviewRow) => {
    setAiPreviewDetailRow(row);
    setAiPreviewDetailOpen(true);
    setAiAddSourceQuery("");
    setAiAddSourceSelectedKey("");
    setAiAddSourceDropdownOpen(false);
    setAiAddSourceEntityId(row.entityId);
    setAiAddSourceTableName(String(row.tableName || "").trim());
  };

  const aiPreviewRowKey = (row: AiPreviewRow): string => `${row.entityId}::${String(row.tableName || "").trim()}::${row.targetMetricId}`;

  const rebuildAiPreviewRowFromTokens = (row: AiPreviewRow, tokens: AiExprToken[]): AiPreviewRow => {
    const hasOps = tokens.some((t) => t.kind === "op");
    const pieces: string[] = [];
    if (hasOps) {
      tokens.forEach((t) => {
        if (t.kind !== "metric") {
          pieces.push(t.value);
          return;
        }
        const selected = t.selectedNormalizedCode || t.candidates?.[0]?.normalizedCode || "";
        const picked = (t.candidates ?? []).find((c) => c.normalizedCode === selected) ?? t.candidates?.[0] ?? null;
        pieces.push(picked?.formulaPiece || picked?.displayCode || "");
      });
    } else {
      tokens
        .filter((t) => t.kind === "metric")
        .forEach((t) => {
          const selected = t.selectedNormalizedCode || t.candidates?.[0]?.normalizedCode || "";
          const picked = (t.candidates ?? []).find((c) => c.normalizedCode === selected) ?? t.candidates?.[0] ?? null;
          const piece = picked?.formulaPiece || picked?.displayCode || "";
          if (piece) pieces.push(piece);
        });
    }
    const rawFormula = hasOps ? pieces.join(" ") : pieces.join(" + ");
    const next = formatFormulaText(rawFormula);
    const currentKnownCodes = knownCodesByEntityTableKey.get(`${row.entityId}::${String(row.tableName || "").trim()}`) ?? formulaKnownCodeSet;
    const selfCodeNormalized = normalizeFormulaRefText(row.targetMetricCodeDisplay || "");
    const err = validateFormulaText(next, {
      currentKnownCodes,
      selfCodeNormalized,
      entityIdByCode,
      knownCodesByEntityTableKey,
      currentEntityId: row.entityId,
      currentEntityCode: row.entityCode,
      currentTableName: row.tableName,
    });
    return {
      ...row,
      aiExprTokens: tokens,
      newFormula: err ? "" : next,
      ok: !err,
      reason: err ? `公式校验失败：${err}` : undefined,
    };
  };

  const updateAiPreviewDetailTokenSelection = (tokenIndex: number, nextSelected: string) => {
    const row = aiPreviewDetailRow;
    if (!row?.aiExprTokens || tokenIndex < 0 || tokenIndex >= row.aiExprTokens.length) return;
    const nextTokens = row.aiExprTokens.map((t, idx) => (idx === tokenIndex ? { ...t, selectedNormalizedCode: nextSelected } : t));
    const nextRow = rebuildAiPreviewRowFromTokens(row, nextTokens);
    setAiPreviewDetailRow(nextRow);
    setAiPreviewRows((prev) => prev.map((r) => (aiPreviewRowKey(r) === aiPreviewRowKey(nextRow) ? nextRow : r)));
  };

  const removeAiPreviewDetailToken = (tokenIndex: number) => {
    const row = aiPreviewDetailRow;
    if (!row?.aiExprTokens || tokenIndex < 0 || tokenIndex >= row.aiExprTokens.length) return;
    const nextTokens = row.aiExprTokens.filter((_, idx) => idx !== tokenIndex);
    const nextRow = rebuildAiPreviewRowFromTokens(row, nextTokens);
    setAiPreviewDetailRow(nextRow);
    setAiPreviewRows((prev) => prev.map((r) => (aiPreviewRowKey(r) === aiPreviewRowKey(nextRow) ? nextRow : r)));
  };

  const addAiPreviewDetailMetric = () => {
    const row = aiPreviewDetailRow;
    if (!row) return;
    const srcEntityId = String(aiAddSourceEntityId || row.entityId).trim();
    const srcTableName = String(aiAddSourceTableName || row.tableName || "").trim();
    const key = `${srcEntityId}::${srcTableName}`;
    const infoMap = metricRefInfoByEntityTableKey.get(key) ?? null;
    const parseKey = (rawKey: string): { entityId: string; tableName: string; normalizedCode: string } | null => {
      const parts = String(rawKey || "").split("::");
      if (parts.length !== 3) return null;
      return { entityId: parts[0], tableName: parts[1], normalizedCode: parts[2] };
    };
    const selectedParsed = parseKey(aiAddSourceSelectedKey);
    let normalizedCode = selectedParsed?.normalizedCode ? String(selectedParsed.normalizedCode).trim() : "";
    if (!normalizedCode && infoMap) {
      const q = String(aiAddSourceQuery || "").trim().toUpperCase();
      const list = [...infoMap.entries()].map(([n, info]) => ({ normalizedCode: n, info }));
      const filtered = q
        ? list.filter((x) => `${x.info.displayCode} ${x.info.name}`.toUpperCase().includes(q) || String(x.normalizedCode).includes(q))
        : list;
      normalizedCode = filtered[0]?.normalizedCode || "";
    }
    const info = infoMap?.get(normalizedCode) ?? null;
    if (!info?.name) return;
    const srcEntity = findOrgNodeById(orgTree, srcEntityId) ?? null;
    const srcEntityCode = String(srcEntity?.code ?? row.entityCode ?? "").trim();
    const formulaPiece =
      srcEntityId === row.entityId && srcTableName === String(row.tableName || "").trim()
        ? info.displayCode
        : `${srcEntityCode}/${srcTableName}/${info.displayCode}`;
    const selectionKey = `${srcEntityId}::${srcTableName}::${normalizedCode}`;
    const token: AiExprToken = {
      kind: "metric",
      value: info.name,
      candidates: [{ entityId: srcEntityId, entityCode: srcEntityCode, tableName: srcTableName, normalizedCode: selectionKey, displayCode: info.displayCode, name: info.name, formulaPiece }],
      selectedNormalizedCode: selectionKey,
    };
    const current = row.aiExprTokens ? [...row.aiExprTokens] : [];
    const hasOps = current.some((t) => t.kind === "op");
    if (hasOps) {
      if (current.length > 0 && current[current.length - 1].kind !== "op") current.push({ kind: "op", value: "+" });
      current.push(token);
    } else {
      current.push(token);
    }
    const nextRow = rebuildAiPreviewRowFromTokens(row, current);
    setAiPreviewDetailRow(nextRow);
    setAiPreviewRows((prev) => prev.map((r) => (aiPreviewRowKey(r) === aiPreviewRowKey(nextRow) ? nextRow : r)));
    setAiAddSourceQuery("");
    setAiAddSourceSelectedKey("");
    setAiAddSourceDropdownOpen(false);
  };

  const copyText = async (text: string) => {
    const value = String(text || "");
    try {
      await navigator.clipboard.writeText(value);
      alert("已复制到剪贴板。");
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = value;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        ta.style.top = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        ta.remove();
        alert("已复制到剪贴板。");
      } catch {
        alert("复制失败，请手动复制。");
      }
    }
  };

  const saveFormulaForActiveMetric = async () => {
    if (!activeMetric) {
      alert("请先在左侧选择一个指标。");
      return;
    }
    const actualFormatted = formatValidateFormulaDraft(formulaActualText, "实际月");
    if (actualFormatted === null) return;
    const forecastFormatted = formatValidateFormulaDraft(formulaForecastText, "预测月");
    if (forecastFormatted === null) return;
    const budgetAnnualFormatted = formatValidateFormulaDraft(formulaBudgetAnnualText, "年预算");
    if (budgetAnnualFormatted === null) return;
    const forecastAnnualFormatted = formatValidateFormulaDraft(formulaForecastAnnualText, "年预测");
    if (forecastAnnualFormatted === null) return;
    const legacyFormula = forecastFormatted || actualFormatted;
    const formulaNote = formulaNoteText.trim();

    const tempTablesByEntityId = { ...metricTablesByEntityId };
    const curTables = tempTablesByEntityId[activeEntityId] ?? [];
    tempTablesByEntityId[activeEntityId] = curTables.map((t) =>
      String(t.name || "").trim() === currentTableName
        ? {
            ...t,
            metrics: updateMetricNodeById(t.metrics ?? [], activeMetric.id, (n) => ({
              ...n,
              formula: legacyFormula,
              formula_actual: actualFormatted,
              formula_forecast: forecastFormatted,
              formula_budget_annual: budgetAnnualFormatted,
              formula_forecast_annual: forecastAnnualFormatted,
              formula_note: formulaNote,
            })),
          }
        : t
    );

    const start = metricKey(activeEntityId, currentTableName, activeMetric.id);
    const actualCycle = detectCycleFrom(start, buildFormulaDependencyEdges(tempTablesByEntityId, "actual"));
    const forecastCycle = detectCycleFrom(start, buildFormulaDependencyEdges(tempTablesByEntityId, "forecast"));
    const budgetAnnualCycle = detectCycleFrom(start, buildFormulaDependencyEdges(tempTablesByEntityId, "budgetAnnual"));
    const forecastAnnualCycle = detectCycleFrom(start, buildFormulaDependencyEdges(tempTablesByEntityId, "forecastAnnual"));
    const cycle = actualCycle ?? forecastCycle ?? budgetAnnualCycle ?? forecastAnnualCycle;
    if (cycle) {
      alert("检测到循环依赖，无法保存。请检查公式引用关系。");
      return;
    }

    const nextMetrics = updateMetricNodeById(activeMetricTree, activeMetric.id, (node) => ({
      ...node,
      formula: legacyFormula,
      formula_actual: actualFormatted,
      formula_forecast: forecastFormatted,
      formula_budget_annual: budgetAnnualFormatted,
      formula_forecast_annual: forecastAnnualFormatted,
      formula_note: formulaNote,
    }));
    setActiveMetricTree(nextMetrics);
    const ok = await persistActiveMetricTable(nextMetrics);
    if (ok) setFormulaDirty(false);
  };

  useEffect(() => {
    let currentTree = loadOrgTree(orgTreeStorageKey, userStorageKeyPrefix);
    setOrgTree(currentTree);
    setEntityExpanded(buildOrgExpandedState(currentTree));
    let cancelled = false;

    const init = async () => {
      setLoading(true);
      setLoadError("");
      try {
        const [response, catalogResp] = await Promise.all([
          (getOrgProductMetricBootstrap() as unknown as Promise<BootstrapResponse>),
          (getMetricTableCatalog() as unknown as Promise<MetricTableCatalogResponse>),
        ]);
        const snapResp = { entities: ((response as any).entities ?? []) } as OrgProductMetricDbSnapshotDto;
        if (cancelled) return;
        currentTree = ensureOrgTreeIncludesDbSnapshotEntities(currentTree, snapResp);
        setOrgTree(currentTree);
        setEntityExpanded(buildOrgExpandedState(currentTree));
        const fallbackEntityId = defaultSelectableEntityId(currentTree, snapResp);
        setSelectedEntityIds((current) => {
          const kept = current.find((id) => findOrgNodeById(currentTree, id));
          return [kept ?? fallbackEntityId];
        });
        setActiveEntityId((current) => (findOrgNodeById(currentTree, current) ? current : fallbackEntityId));
        const catalog = catalogResp.items ?? [];
        setMetricTableCatalog(catalog);
        const seedByNodeId = normalizeBootstrapSeed(response.items);
        const seedTablesByNodeId = normalizeBootstrapMetricTables(response.table_items);
        setBootstrapSeedByEntityId(seedByNodeId);
        setBootstrapTableSeedByEntityId(seedTablesByNodeId);
        let parsedStored: Record<string, MetricTable[]> | undefined;
        try {
          const raw = window.localStorage.getItem(metricStorageKey);
          if (raw) {
            parsedStored = sanitizeStoredMetricTablesByEntityId(JSON.parse(raw), currentTree, catalog);
          } else {
            const legacyRaw = window.localStorage.getItem(`${userStorageKeyPrefix}${ORG_PRODUCT_METRIC_LEGACY_STORAGE_KEY_SUFFIX}`);
            if (legacyRaw) {
              parsedStored = migrateLegacyMetricMap(JSON.parse(legacyRaw) as Record<string, MetricNode[]>);
            }
          }
        } catch {
          parsedStored = undefined;
        }

        const migratedStored = parsedStored
          ? (migrateMetricEntityIdMap(currentTree, parsedStored) as Record<string, MetricTable[]>)
          : undefined;
        const fromDb = dbSnapshotToMetricTablesByEntityId(snapResp, currentTree);
        const storageFallback = hasMetricTables(fromDb) ? {} : migratedStored ?? {};
        const mergedStored = mergeMetricTablesByEntityIdPreferRicher(storageFallback, fromDb, {
          preferSecondaryOnTie: true,
        });
        const mergedWithSeedTables = mergeMetricTablesByEntityIdFillMissing(mergedStored, seedTablesByNodeId);
        const reconciled = cleanupMetricTablesMap(
          reconcileMetricTableMap(seedByNodeId, currentTree, mergedWithSeedTables, catalog)
        );
        setMetricTablesByEntityId(reconciled);

        const selectedMetricState: Record<string, string | null> = {};
        const activeTableState: Record<string, string> = {};
        Object.entries(reconciled).forEach(([entityId, tables]) => {
          const firstTable = tables[0];
          if (firstTable) {
            activeTableState[entityId] = firstTable.id;
            selectedMetricState[buildMetricScopeKey(entityId, firstTable.id)] = firstTable.metrics[0]?.id ?? null;
          }
        });
        setActiveTableIdByEntityId(activeTableState);
        setSelectedMetricIdByScope(selectedMetricState);
      } catch (e) {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : "加载指标失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void init();
    return () => {
      cancelled = true;
    };
  }, [metricStorageKey, orgTreeStorageKey, userStorageKeyPrefix]);

  useEffect(() => {
    const onTreeSaved = () => {
      const tree = loadOrgTree(orgTreeStorageKey, userStorageKeyPrefix);
      setOrgTree(tree);
      setEntityExpanded(buildOrgExpandedState(tree));
      setMetricTablesByEntityId((prev) =>
        migrateMetricEntityIdMap(tree, prev) as Record<string, MetricTable[]>
      );
      setActiveEntityId((id) => {
        if (findOrgNodeById(tree, id)) return id;
        return findOrgNodeByCode(tree, "AA")?.id ?? DEFAULT_AA_ENTITY_ID;
      });
      setSelectedEntityIds((ids) => {
        const kept = ids.filter((id) => findOrgNodeById(tree, id));
        return kept.length > 0 ? kept : [findOrgNodeByCode(tree, "AA")?.id ?? DEFAULT_AA_ENTITY_ID];
      });
    };
    window.addEventListener(ORG_PRODUCT_TREE_SAVED_EVENT, onTreeSaved);
    return () => window.removeEventListener(ORG_PRODUCT_TREE_SAVED_EVENT, onTreeSaved);
  }, [orgTreeStorageKey, userStorageKeyPrefix]);

  useEffect(() => {
    if (!loading && Object.keys(metricTablesByEntityId).length > 0) {
      persistMetricTablesCache(metricStorageKey, metricTablesByEntityId);
    }
  }, [loading, metricStorageKey, metricTablesByEntityId]);

  useEffect(() => {
    if (!selectedEntityIds.includes(activeEntityId)) {
      setActiveEntityId(selectedEntityIds[0] ?? DEFAULT_AA_ENTITY_ID);
    }
  }, [activeEntityId, orgTree.id, selectedEntityIds]);

  useEffect(() => {
    if (activeMetricTables.length === 0) return;
    if (!activeMetricTables.some((table) => table.id === activeTableIdByEntityId[activeEntityId])) {
      setActiveTableIdByEntityId((prev) => ({ ...prev, [activeEntityId]: activeMetricTables[0].id }));
    }
  }, [activeEntityId, activeTableIdByEntityId, activeMetricTables]);

  useEffect(() => {
    if (!activeMetricTable) return;
    const scopeKey = buildMetricScopeKey(activeEntityId, activeMetricTable.id);
    if (!(scopeKey in selectedMetricIdByScope)) {
      setSelectedMetricIdByScope((prev) => ({
        ...prev,
        [scopeKey]: activeMetricTable.metrics[0]?.id ?? null,
      }));
    }
  }, [activeEntityId, activeMetricTable, selectedMetricIdByScope]);

  useEffect(() => {
    if (activeMetric) {
      const base = buildDefaultMetricDraft(activeMetric);
      setMetricDraft({ ...base, code: formatMetricCodeForDisplay(activeEntity.code, base.code) });
      return;
    }
    setMetricDraft({
      levelLabel: "一级",
      nature: "其他",
      code: "",
      name: "",
      note: "",
      formula: "",
      formula_budget_annual: "",
      formula_forecast_annual: "",
      horizontal_rollup: false,
      vertical_rollup: false,
      logic_code: "",
      value_type: "金额",
      allow_manual_entry: true,
      entry_granularity: "monthly",
    });
  }, [activeMetric]);

  const setActiveMetricTree = (metrics: MetricNode[]) => {
    setMetricTablesByEntityId((prev) => {
      const tables = prev[activeEntityId] ?? [];
      return {
        ...prev,
        [activeEntityId]: tables.map((table) => (table.id === activeTableId ? { ...table, metrics } : table)),
      };
    });
  };

  const persistActiveMetricTable = async (metrics: MetricNode[]): Promise<boolean> => {
    if (!activeMetricTable) {
      alert("当前对象暂无指标表，无法保存。");
      return false;
    }
    if (metricEditorSaving) return false;
    setMetricEditorSaving(true);
    try {
      await saveMetricTable({
        entity_code: activeEntity.code,
        entity_name: activeEntity.name,
        table_id: activeMetricTable.id,
        table_name: activeMetricTable.name,
        metrics,
      });
      window.dispatchEvent(new Event("org-product-metrics-saved"));
      return true;
    } catch (e) {
      alert(e instanceof Error ? `保存失败：${e.message}` : "保存失败");
      return false;
    } finally {
      setMetricEditorSaving(false);
    }
  };

  const persistMetricTableByEntityAndName = async (entityId: string, tableName: string, metrics: MetricNode[]): Promise<boolean> => {
    const entity = findOrgNodeById(orgTree, entityId);
    if (!entity) return false;
    const tables = metricTablesByEntityId[entityId] ?? [];
    const table = tables.find((t) => String(t.name || "").trim() === String(tableName || "").trim());
    if (!table) return false;
    try {
      await saveMetricTable({
        entity_code: entity.code,
        entity_name: entity.name,
        table_id: table.id,
        table_name: table.name,
        metrics,
      });
      return true;
    } catch {
      return false;
    }
  };

  const toggleEntityChecked = (entityId: string) => {
    setSelectedEntityIds([entityId]);
    setActiveEntityId(entityId);
    setEntityDropdownOpen(false);
  };

  const selectMetricTable = (tableId: string) => {
    if (viewMode === "formula" && tableId !== activeTableId && formulaDirty) {
      if (!confirm("当前公式还未保存，切换指标表会丢失未保存内容，确认继续吗？")) return;
    }
    setActiveTableIdByEntityId((prev) => ({ ...prev, [activeEntityId]: tableId }));
    const table = activeMetricTables.find((item) => item.id === tableId);
    if (!table) return;
    const scopeKey = buildMetricScopeKey(activeEntityId, tableId);
    setSelectedMetricIdByScope((prev) => ({
      ...prev,
      [scopeKey]: prev[scopeKey] ?? table.metrics[0]?.id ?? null,
    }));
  };

  const addRootMetric = async () => {
    const nextNode: MetricNode = {
      id: `metric-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      levelLabel: "一级",
      nature: "其他",
      code: newMetricCode(undefined, activeMetricTree),
      name: "新一级指标",
      value_type: "金额",
      allow_manual_entry: 1,
      formula_budget_annual: "",
      formula_forecast_annual: "",
      horizontal_rollup: 0,
      vertical_rollup: 0,
      logic_code: "",
      note: "",
      children: [],
    };
    const nextMetrics = [...activeMetricTree, nextNode];
    setActiveMetricTree(nextMetrics);
    setSelectedMetricIdByScope((prev) => ({ ...prev, [activeMetricScopeKey]: nextNode.id }));
    await persistActiveMetricTable(nextMetrics);
  };

  const addChildMetric = async () => {
    if (!activeMetric) {
      await addRootMetric();
      return;
    }
    const nextNode: MetricNode = {
      id: `metric-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      levelLabel: nextMetricLevelLabel(activeMetric),
      nature: "其他",
      code: newMetricCode(activeMetric),
      name: `新${nextMetricLevelLabel(activeMetric)}指标`,
      value_type: "金额",
      allow_manual_entry: 1,
      formula_budget_annual: "",
      formula_forecast_annual: "",
      horizontal_rollup: 0,
      vertical_rollup: 0,
      logic_code: "",
      note: "",
      children: [],
    };
    const nextMetrics = addMetricChild(activeMetricTree, activeMetric.id, nextNode);
    setActiveMetricTree(nextMetrics);
    setSelectedMetricIdByScope((prev) => ({ ...prev, [activeMetricScopeKey]: nextNode.id }));
    await persistActiveMetricTable(nextMetrics);
  };

  const saveMetric = async () => {
    if (!activeMetric) return;
    const code = normalizeMetricCodeForStorage(activeEntity.code, metricDraft.code);
    const name = metricDraft.name.trim();
    if (!code) {
      alert("指标代码不能为空。");
      return;
    }
    if (!name) {
      alert("指标名称不能为空。");
      return;
    }
    const nextMetrics = updateMetricNodeById(activeMetricTree, activeMetric.id, (node) => ({
      ...node,
      levelLabel: metricDraft.levelLabel.trim() || "一级",
      nature: normalizeMetricNatureText(metricDraft.nature),
      code,
      name,
      note: metricDraft.note.trim(),
      formula: metricDraft.formula.trim(),
      formula_budget_annual: metricDraft.formula_budget_annual.trim(),
      formula_forecast_annual: metricDraft.formula_forecast_annual.trim(),
      horizontal_rollup: metricDraft.horizontal_rollup ? 1 : 0,
      vertical_rollup: metricDraft.vertical_rollup ? 1 : 0,
      logic_code: metricDraft.logic_code.trim().toUpperCase(),
      value_type: normalizeValueType(metricDraft.value_type, metricDraft.nature),
      allow_manual_entry: metricDraft.allow_manual_entry ? 1 : 0,
      entry_granularity: metricDraft.entry_granularity,
    }));
    setActiveMetricTree(nextMetrics);
    await persistActiveMetricTable(nextMetrics);
  };

  const refreshMetricTableCatalog = async () => {
    const [catalogResp, snapResp] = await Promise.all([
      (getMetricTableCatalog() as unknown as Promise<MetricTableCatalogResponse>),
      (getOrgProductMetricDbSnapshot() as unknown as Promise<OrgProductMetricDbSnapshotDto>).catch(() => ({
        entities: [],
      })),
    ]);
    const catalog = catalogResp.items ?? [];
    setMetricTableCatalog(catalog);
    const fromDb = dbSnapshotToMetricTablesByEntityId(snapResp, orgTree);
    setMetricTablesByEntityId((prev) => {
      const merged = mergeMetricTablesByEntityIdPreferRicher(
        mergeMetricTablesByEntityIdPreferRicher(prev, fromDb, { preferSecondaryOnTie: true }),
        bootstrapTableSeedByEntityId
      );
      return cleanupMetricTablesMap(reconcileMetricTableMap(bootstrapSeedByEntityId, orgTree, merged, catalog));
    });
    return catalog;
  };

  const handleAddCatalogTable = async () => {
    if (!activeCatalogScope) return;
    const table_name = catalogDraftName.trim();
    if (!table_name) {
      alert("请输入指标表名称。");
      return;
    }
    if (!table_name.endsWith("表")) {
      alert("指标表名称须以「表」结尾。");
      return;
    }
    setCatalogBusy(true);
    try {
      await saveMetricTableCatalog({
        entity_scope: activeCatalogScope,
        table_name,
      });
      setCatalogDraftName("");
      await refreshMetricTableCatalog();
    } catch (e) {
      alert(e instanceof Error ? e.message : "新增指标表失败");
    } finally {
      setCatalogBusy(false);
    }
  };

  const handleToggleCatalogStatus = async (row: MetricTableCatalogItem) => {
    const nextStatus = row.status === "active" ? "inactive" : "active";
    const actionLabel = nextStatus === "inactive" ? "停用" : "启用";
    if (
      nextStatus === "inactive" &&
      !confirm(`确认${actionLabel}「${row.table_name}」吗？\n\n停用后页签与导入匹配将隐藏该表，已保存的科目数据仍保留。`)
    ) {
      return;
    }
    setCatalogBusy(true);
    try {
      await patchMetricTableCatalogItem(row.id, {
        status: nextStatus,
      });
      await refreshMetricTableCatalog();
    } catch (e) {
      alert(e instanceof Error ? e.message : `${actionLabel}失败`);
    } finally {
      setCatalogBusy(false);
    }
  };

  const handleUpdateCatalogSortOrder = async (row: MetricTableCatalogItem, sortOrder: number) => {
    if (!Number.isFinite(sortOrder)) return;
    setCatalogBusy(true);
    try {
      await patchMetricTableCatalogItem(row.id, {
        sort_order: Math.round(sortOrder),
      });
      await refreshMetricTableCatalog();
    } catch (e) {
      alert(e instanceof Error ? e.message : "更新排序失败");
    } finally {
      setCatalogBusy(false);
    }
  };

  const triggerImportReportFilePicker = () => {
    importInputRef.current?.click();
  };

  const handleImportReport = async (file: File) => {
    const formulaImport = viewMode === "formula";
    if (!confirm(
      formulaImport
        ? "确认从 Excel 导入取数公式吗？\n\n· 工作表名：机构及产品代码 + 指标表名称（如 AA业务状况表）\n· 表头须含：科目层级、科目性质、科目代码、科目名称\n· 公式列：「实际月公式」「预测月公式」「年预算公式」「年预测公式」（或兼容旧列「取数公式」）\n· 可选列：「公式说明」「录入粒度」「数值类型」「允许手工录入」「横向汇总」「纵向汇总」「逻辑码」\n· 支持 Excel 原生公式（如 =E3+E10），将自动转换为系统公式\n· 未出现在 Excel 中的指标表不会被修改\n\n导入后请点击「保存刷新」写入数据库。"
        : "确认导入 Excel 吗？\n\n· 工作表名：机构及产品代码 + 指标表名称（如 AA业务状况表）\n· 表头须含：科目层级、科目性质、科目代码、科目名称（可选：取数公式）\n· 可选列：「数值类型」「允许手工录入」「录入粒度」「横向汇总」「纵向汇总」「逻辑码」\n· 取数公式列可写系统文本，或 Excel 原生公式（=E3+E10 等）\n· 将覆盖对应机构/产品下该指标表的科目树\n\n导入后请点击「保存刷新」写入数据库。"
    )) {
      return;
    }
    setImporting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append(
        "candidates_json",
        JSON.stringify(buildMetricSheetMatchCandidates(orgTree, metricTableCatalog))
      );
      formData.append("strict_import", "true");
      const result = await importMetricReport(formData) as MetricReportImportResponse;

      const updates: Array<{
        entityId: string;
        entityLabel: string;
        sheetName: string;
        tableName: string;
        rowCount: number;
        hasFormulaColumn: boolean;
        metrics: MetricNode[];
      }> = [];
      const normalizeTableKey = normalizeMetricTableNameKey;
      const unmatchedSheets: string[] = [];
      (result.imported_entities ?? []).forEach((item) => {
        const node = findOrgNodeByCode(orgTree, item.entity_code);
        const rawTableName = String(item.table_name || "").trim();
        const allowedNames = node ? [...metricTableNamesForOrgNode(node, metricTableCatalog)] : [];
        const tableName =
          canonicalMetricTableNameInList(rawTableName, allowedNames) ??
          rawTableName;
        if (!node || !tableName) {
          unmatchedSheets.push(item.sheet_name);
          return;
        }
        updates.push({
          entityId: node.id,
          entityLabel: `${node.code} ${node.name}`,
          sheetName: item.sheet_name,
          tableName,
          rowCount: item.row_count,
          hasFormulaColumn: Boolean(item.has_formula_column),
          metrics: item.metrics,
        });
      });

      const normalizedUpdates = updates.map((u) => ({
        ...u,
        normalizedMetrics: normalizeMetricForest(u.metrics),
        hasFormulaColumn: u.hasFormulaColumn,
      }));

      if (normalizedUpdates.length === 0) {
        const ignored = [...new Set([...(result.ignored_sheets ?? []), ...unmatchedSheets])];
        const ignoredTxt = ignored.length > 0 ? `\n\n未处理工作表：${ignored.join("、")}` : "";
        alert(`未匹配到可导入的工作表。请检查工作表命名（如 AA业务状况表）。${ignoredTxt}`);
        return;
      }

      if (formulaImport && !normalizedUpdates.some((u) => u.hasFormulaColumn)) {
        alert("未识别到公式列。请在 Excel 表头增加「年预算公式」「年预测公式」「实际月公式」「预测月公式」或「取数公式」列后再导入。");
        return;
      }

      setMetricTablesByEntityId((prev) => {
        const next: Record<string, MetricTable[]> = { ...prev };
        normalizedUpdates.forEach((u) => {
          let tables = [...(next[u.entityId] ?? [])];
          const targetKey = normalizeTableKey(u.tableName);
          const idx = tables.findIndex((table) => normalizeTableKey(table.name) === targetKey);
          if (idx >= 0) {
            const current = tables[idx];
            const nextMetrics = u.hasFormulaColumn
              ? u.normalizedMetrics
              : mergeMetricForestPreservingFormula(current.metrics ?? [], u.normalizedMetrics);
            tables[idx] = {
              ...current,
              name: u.tableName,
              id: buildMetricTableId(u.tableName),
              metrics: nextMetrics,
            };
          } else {
            tables.push({
              id: buildMetricTableId(u.tableName),
              name: u.tableName,
              metrics: u.normalizedMetrics,
            });
          }
          const entityNode = findOrgNodeById(orgTree, u.entityId);
          const allowed = entityNode ? [...metricTableNamesForOrgNode(entityNode, metricTableCatalog)] : [];
          if (allowed.length > 0) {
            tables = pruneMetricTablesToCatalog(
              tables,
              allowed,
              buildMetricTableId,
              (name) => canonicalMetricTableNameInList(name, allowed)
            );
          }
          next[u.entityId] = tables;
        });
        return next;
      });

      setSelectedMetricIdByScope((prev) => {
        const next = { ...prev };
        normalizedUpdates.forEach((u) => {
          const scopeKey = buildMetricScopeKey(u.entityId, buildMetricTableId(u.tableName));
          next[scopeKey] = u.normalizedMetrics[0]?.id ?? null;
        });
        return next;
      });

      const updatedCount = normalizedUpdates.length;
      const totalRows = normalizedUpdates.reduce((sum, u) => sum + (u.rowCount || 0), 0);
      const mappingTxt = normalizedUpdates
        .map((u) => `· ${u.sheetName} → ${u.tableName}（${u.rowCount} 行）`)
        .join("\n");

      const lastUpdate = normalizedUpdates[normalizedUpdates.length - 1];
      if (lastUpdate && lastUpdate.entityId === activeEntityId) {
        setActiveTableIdByEntityId((prev) => ({
          ...prev,
          [lastUpdate.entityId]: buildMetricTableId(lastUpdate.tableName),
        }));
      }
      const detailMap = new Map<string, string>();
      (result.ignored_details ?? []).forEach((d) => {
        if (d?.sheet_name) detailMap.set(d.sheet_name, String(d.reason || "").trim());
      });
      const ignored = [...new Set([...(result.ignored_sheets ?? []), ...unmatchedSheets])];
      const ignoredTxt =
        ignored.length > 0
          ? `\n\n未处理工作表：\n${ignored
              .map((name) => {
                const reason = detailMap.get(name);
                return reason ? `· ${name}（${reason}）` : `· ${name}`;
              })
              .join("\n")}`
          : "";
      const formulaTxt = normalizedUpdates.some((u) => u.hasFormulaColumn) ? "（含取数公式）" : "";
      const convertErrs = result.formula_convert_errors ?? [];
      const convertErrTxt =
        convertErrs.length > 0
          ? `\n\n公式转换警告（${convertErrs.length} 处，对应行公式未写入）：\n${convertErrs
              .slice(0, 8)
              .map((e) => `· ${e.sheet_name} 第${e.row}行：${e.reason}`)
              .join("\n")}${convertErrs.length > 8 ? `\n…等 ${convertErrs.length} 处` : ""}`
          : "";
      alert(
        `导入完成${formulaTxt}：已更新 ${updatedCount} 张指标表，共 ${totalRows} 行科目。\n\n写入明细：\n${mappingTxt}${ignoredTxt}${convertErrTxt}\n\n未出现在 Excel 中的指标表不会被修改。\n\n请在左侧点击对应指标表标签查看，确认无误后点击「保存刷新」写入数据库。`
      );
    } catch (e) {
      alert(e instanceof Error ? `导入失败：${e.message}` : "导入失败");
    } finally {
      setImporting(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };

  const handleExportReport = async () => {
    if (selectedEntities.length === 0) {
      alert("请先勾选至少一个机构或产品。");
      return;
    }
    setExporting(true);
    try {
      const sheets: Array<{ entity_code: string; table_name: string; metrics: MetricNode[] }> = [];
      selectedEntities.forEach((entity) => {
        const tables = metricTablesByEntityId[entity.id] ?? [];
        const tableByKey = new Map(tables.map((t) => [normalizeMetricTableNameKey(t.name), t]));
        const names = [...metricTableNamesForOrgNode(entity, metricTableCatalog)];
        const exportNames = names.length > 0 ? names : tables.map((t) => t.name);
        exportNames.forEach((tableName) => {
          const table = tableByKey.get(normalizeMetricTableNameKey(tableName));
          sheets.push({
            entity_code: entity.code,
            table_name: tableName,
            metrics: table?.metrics ?? [],
          });
        });
      });
      if (sheets.length === 0) {
        alert("所选对象没有可导出的指标表。");
        return;
      }
      const { blob, filename } = await exportMetricReport({ sheets });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || "机构及产品指标.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? `导出失败：${e.message}` : "导出失败");
    } finally {
      setExporting(false);
    }
  };

  const handleSaveRefresh = async () => {
    if (savingRefresh) return;
    setSavingRefresh(true);
    try {
      const entities = Object.entries(metricTablesByEntityId)
        .map(([entityId, tables]) => {
          const node = findOrgNodeById(orgTree, entityId);
          if (!node) return null;
          const safeTables = Array.isArray(tables) ? tables : [];
          return {
            entity_code: node.code,
            entity_name: node.name,
            tables: safeTables.map((t) => ({
              id: t.id,
              name: t.name,
              metrics: t.metrics,
            })),
          };
        })
        .filter((x): x is { entity_code: string; entity_name: string; tables: Array<{ id: string; name: string; metrics: MetricNode[] }> } => Boolean(x));

      const resp = await (saveRefreshOrgProductMetrics(entities) as unknown as Promise<MetricSaveRefreshResponse>);
      window.dispatchEvent(new Event("org-product-metrics-saved"));
      alert(
        `保存成功：${resp.saved_entities} 个对象，${resp.saved_tables} 张指标表。机构及产品指标体系已作为唯一主键体系保存。`
      );
    } catch (e) {
      alert(e instanceof Error ? `保存失败：${e.message}` : "保存失败");
    } finally {
      setSavingRefresh(false);
    }
  };

  const deleteMetric = async () => {
    if (!activeMetric) return;
    if (!confirm(`确认删除指标 ${activeMetric.code} 吗？其下级指标也会一起删除。`)) return;
    const nextMetrics = deleteMetricNodeById(activeMetricTree, activeMetric.id);
    setActiveMetricTree(nextMetrics);
    setSelectedMetricIdByScope((prev) => ({ ...prev, [activeMetricScopeKey]: null }));
    setMetricEditorOpen(false);
    await persistActiveMetricTable(nextMetrics);
  };

  const renderEntityNode = (node: OrgProductNode, level = 0): JSX.Element => {
    const isOpen = entityExpanded[node.id] ?? false;
    const hasChildren = node.children.length > 0;
    const isChecked = activeEntityId === node.id;
    const isActive = activeEntityId === node.id;
    const Icon =
      node.type === "level0" || node.type === "level1"
        ? Building2
        : node.type === "level2"
          ? Building
          : Package2;
    const shouldShowChildren = entitySearch.trim() ? true : isOpen;

    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-2 border-b border-gray-100 px-3 py-2 text-xs ${
            isActive ? "bg-blue-50 ring-1 ring-inset ring-blue-200" : "hover:bg-gray-50"
          }`}
          style={{ paddingLeft: `${level * 18 + 10}px` }}
          onClick={() => toggleEntityChecked(node.id)}
        >
          {hasChildren ? (
            <button
              type="button"
              className="rounded p-0.5 hover:bg-gray-200"
              onClick={(e) => {
                e.stopPropagation();
                setEntityExpanded((prev) => ({ ...prev, [node.id]: !isOpen }));
              }}
            >
              {shouldShowChildren ? <ChevronDown className="h-3 w-3 text-gray-600" /> : <ChevronRight className="h-3 w-3 text-gray-600" />}
            </button>
          ) : (
            <span className="w-4" />
          )}
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="org-product-active-entity"
              checked={isChecked}
              onChange={() => toggleEntityChecked(node.id)}
              onClick={(e) => e.stopPropagation()}
              className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <Icon className={`h-3.5 w-3.5 ${node.type === "level3" ? "text-amber-600" : "text-blue-600"}`} />
          </label>
          <span className="w-14 shrink-0 text-gray-700">{node.code}</span>
          <span className="min-w-0 flex-1 truncate text-gray-800">{node.name}</span>
        </div>
        {hasChildren && shouldShowChildren ? node.children.map((child) => renderEntityNode(child, level + 1)) : null}
      </div>
    );
  };

  const buildIndentedMetricName = (node: MetricNode): string => {
    const levelIndex = Math.max(0, LEVEL_OPTIONS.indexOf(node.levelLabel as MetricLevelLabel));
    return `${" ".repeat(levelIndex * 2)}${node.name}`;
  };

  const metricLevelIndex = (node: MetricNode): number =>
    Math.max(0, LEVEL_OPTIONS.indexOf(node.levelLabel as MetricLevelLabel));

  const metricRowToneClass = (node: MetricNode): string => {
    if (node.levelLabel === "一级") return "border-b border-slate-300 bg-slate-100/90";
    if (node.levelLabel === "二级") return "border-b border-blue-100 bg-blue-50/70";
    return "border-b border-gray-100";
  };

  const metricRowAccentClass = (node: MetricNode): string => {
    if (node.levelLabel === "一级") return "bg-slate-500";
    if (node.levelLabel === "二级") return "bg-blue-400";
    return "";
  };

  const isPrimaryMetricLevel = (node: MetricNode): boolean => node.levelLabel === "一级" || node.levelLabel === "二级";

  const renderMetricNameCell = (node: MetricNode, emphasizeRow: boolean, rowKey: string): JSX.Element => {
    const levelIndex = metricLevelIndex(node);
    return (
      <div className={`flex min-w-0 items-center text-left text-gray-800 ${emphasizeRow ? "font-semibold" : ""}`}>
        {Array.from({ length: levelIndex }).map((_, index) => (
          <span
            key={`${rowKey}-indent-${index}`}
            className="mr-2 h-4 w-3 shrink-0 border-l border-slate-300/90"
            aria-hidden="true"
          />
        ))}
        <span className="min-w-0 flex-1 truncate">{buildIndentedMetricName(node).trimStart()}</span>
        {String(node.formula ?? "").trim() ? (
          <span className="ml-2 shrink-0 rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700">
            公式
          </span>
        ) : null}
        <button
          type="button"
          className="ml-2 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded border border-gray-200 bg-white text-gray-600 shadow-sm transition hover:bg-gray-50"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedMetricIdByScope((prev) => ({ ...prev, [activeMetricScopeKey]: node.id }));
            setMetricEditorOpen(true);
          }}
          aria-label="编辑指标"
          title="编辑指标"
        >
          <Edit3 className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  };

  const renderMetricRows = (nodes: MetricNode[], parentPath = ""): JSX.Element[] =>
    nodes.flatMap((node, index) => {
      const rowKey = parentPath ? `${parentPath}.${index}-${node.id}` : `${index}-${node.id}`;
      const isSelected = activeMetricId === node.id;
      const emphasizeRow = isPrimaryMetricLevel(node);
      return [
        <div
          key={`${activeMetricScopeKey}-${rowKey}`}
          className={`group relative grid grid-cols-[86px_86px_150px_minmax(240px,1fr)_130px_92px] items-center gap-2 px-3 py-2 text-xs ${
            isSelected
              ? "border-b border-emerald-200 bg-emerald-50 ring-1 ring-inset ring-emerald-200"
              : `${metricRowToneClass(node)} hover:bg-gray-50`
          }`}
          onClick={() => setSelectedMetricIdByScope((prev) => ({ ...prev, [activeMetricScopeKey]: node.id }))}
        >
          {!isSelected && metricRowAccentClass(node) ? (
            <span className={`absolute inset-y-0 left-0 w-1 ${metricRowAccentClass(node)}`} aria-hidden="true" />
          ) : null}
          <div className={`text-left text-gray-700 ${emphasizeRow ? "font-semibold" : ""}`}>{node.levelLabel}</div>
          <div className={`text-left text-gray-700 ${emphasizeRow ? "font-semibold" : ""}`}>
            <div>{normalizeMetricNatureText(node.nature)}</div>
            {node.entry_granularity === "annual" ? (
              <div className="mt-0.5 text-[10px] font-normal text-amber-700">按年录入</div>
            ) : null}
          </div>
          <div className={`text-left font-mono text-gray-700 ${emphasizeRow ? "font-semibold" : ""}`}>
            {formatMetricCodeForDisplay(activeEntity.code, node.code)}
          </div>
          {renderMetricNameCell(node, emphasizeRow, rowKey)}
          <div className="truncate font-mono text-[11px] text-gray-600" title={node.logic_code || ""}>
            {node.logic_code || "-"}
          </div>
          <div className="flex flex-wrap gap-1 text-[10px]">
            {normalizeRollupFlag(node.horizontal_rollup) ? <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">横</span> : null}
            {normalizeRollupFlag(node.vertical_rollup) ? <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">纵</span> : null}
          </div>
        </div>,
        ...renderMetricRows(node.children, rowKey),
      ];
    });

  const renderFormulaReferencePicker = (variant: "inline" | "modal" = "inline"): JSX.Element => {
    const isModal = variant === "modal";
    const rowGrid = isModal
      ? "grid-cols-[42px_56px_minmax(102px,132px)_minmax(0,1fr)_44px]"
      : "grid-cols-[36px_minmax(72px,92px)_minmax(0,1fr)_42px]";
    return (
      <div className={`min-h-0 w-full overflow-hidden rounded-md border border-gray-200 bg-slate-50/70 ${isModal ? "flex h-full flex-col p-3" : "p-2.5"}`}>
        <div className="space-y-1.5">
          <div className={isModal ? "space-y-1.5" : "grid grid-cols-[52px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-1.5"}>
            <div className="text-[11px] font-medium text-gray-700 whitespace-nowrap">
              {isModal ? "引用指标" : "引用来源"}
            </div>
            <select
              value={refEntity.id}
              onChange={(e) => {
                const nextId = e.target.value;
                setRefEntityId(nextId);
                const tables = metricTablesByEntityId[nextId] ?? [];
                const currentName = String(currentTableName || "").trim();
                const matched = tables.find((t) => String(t.name || "").trim() === currentName);
                const nextName = String(matched?.name ?? tables[0]?.name ?? "");
                setRefTableName(nextName);
                setRefMetricSearch("");
                setRefMetricSearchInput("");
              }}
              className="h-7 w-full min-w-0 rounded border border-gray-300 bg-white px-2 text-[11px]"
              disabled={!activeMetric}
              title={`${refEntity.code} ${refEntity.name}`}
            >
              {metricConfigurableOrgNodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.code} {node.name}
                </option>
              ))}
            </select>
            <select
              value={String(refTable?.name ?? "")}
              onChange={(e) => setRefTableName(e.target.value)}
              className="h-7 w-full min-w-0 rounded border border-gray-300 bg-white px-2 text-[11px]"
              disabled={!activeMetric || refTables.length === 0}
              title={String(refTable?.name ?? "")}
            >
              {refTables.map((t) => (
                <option key={t.id} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div className={isModal ? "flex items-center gap-1.5" : "grid grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-1.5"}>
            {isModal ? null : <div />}
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
              <input
                value={refMetricSearchInput}
                onChange={(e) => {
                  setRefMetricSearchInput(e.target.value);
                  setRefMetricSearch(e.target.value);
                }}
                placeholder="搜索指标代码或名称..."
                className="h-7 w-full rounded border border-gray-300 bg-white pl-8 pr-2 text-[11px] focus:outline-none focus:ring-1 focus:ring-blue-500"
                disabled={!activeMetric}
              />
            </div>
            <div className="shrink-0 whitespace-nowrap px-1 text-[10px] text-gray-500">{refFlatRows.length} 项</div>
          </div>
        </div>

        <div className={`${isModal ? "mt-2 min-h-0 flex-1" : "mt-2 max-h-52"} overflow-auto rounded border border-gray-200 bg-white`}>
          {refTable == null ? (
            <div className="px-3 py-3 text-xs text-gray-500">当前来源对象暂无指标表。</div>
          ) : refFlatRows.length === 0 ? (
            <div className="px-3 py-3 text-xs text-gray-500">未找到匹配的来源指标。</div>
          ) : (
            <div className="min-w-full">
              <div className={`sticky top-0 z-10 grid ${rowGrid} gap-1 border-b border-gray-200 bg-slate-50 px-2 py-1.5 text-[10px] font-medium text-gray-700`}>
                <div className="whitespace-nowrap">层级</div>
                {isModal ? <div className="whitespace-nowrap">性质</div> : null}
                <div className="whitespace-nowrap">代码</div>
                <div className="whitespace-nowrap">科目名称</div>
                <div />
              </div>
              {refFlatRows.map((row) => {
                const displayCode = formatMetricCodeForDisplay(refEntity.code, row.code);
                const insertText = buildFormulaInsertText(refEntity, String(refTable.name || ""), displayCode, row.name);
                const isSummaryLevel = row.levelLabel === "一级" || row.levelLabel === "二级";
                return (
                  <div
                    key={`ref-${variant}-${refEntity.id}-${refTable.id}-${row.pathKey}-${row.id}`}
                    className={`grid ${rowGrid} items-start gap-1 border-b border-gray-100 px-2 py-1.5 text-[11px] hover:bg-gray-50/80 ${isSummaryLevel ? "bg-slate-50/70 font-medium text-gray-900" : "text-gray-700"}`}
                    draggable={Boolean(activeMetric)}
                    onDragStart={(e) => {
                      e.dataTransfer.setData("text/plain", insertText);
                      e.dataTransfer.effectAllowed = "copy";
                    }}
                  >
                    <span className={FORMULA_METRIC_LEVEL_CELL}>{row.levelLabel}</span>
                    {isModal ? <span className="pt-0.5 text-[10px] leading-4 text-gray-600">{normalizeMetricNatureText(row.nature)}</span> : null}
                    <span className={FORMULA_METRIC_CODE_CELL} title={displayCode}>
                      {displayCode}
                    </span>
                    <span
                      className={FORMULA_METRIC_NAME_CELL}
                      style={{ paddingLeft: `${Math.min(row.depth, 5) * FORMULA_METRIC_NAME_INDENT_PX}px` }}
                      title={row.name}
                    >
                      {row.name}
                    </span>
                    <button
                      type="button"
                      className="justify-self-end rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-normal text-gray-700 hover:bg-gray-50"
                      onClick={() => insertIntoFormula(insertText, insertText.length)}
                      disabled={!activeMetric}
                    >
                      插入
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="relative z-10 flex h-full flex-col p-3">
      <input
        ref={importInputRef}
        type="file"
        accept=".xlsx,.xlsm,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleImportReport(file);
        }}
      />

      <div className="mb-2 flex items-center gap-2">
        <button
          type="button"
          className={`rounded-full border px-3 py-1 text-xs transition ${
            viewMode === "metric" ? "border-blue-300 bg-blue-50 text-blue-700 shadow-sm" : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
          }`}
          onClick={() => setViewMode("metric")}
        >
          指标维护
        </button>
        <button
          type="button"
          className={`rounded-full border px-3 py-1 text-xs transition ${
            viewMode === "formula" ? "border-blue-300 bg-blue-50 text-blue-700 shadow-sm" : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
          }`}
          onClick={() => setViewMode("formula")}
        >
          公式配置
        </button>
        <div className="ml-auto text-[11px] text-gray-500">
          {viewMode === "formula"
            ? "在左侧选择指标并编辑公式"
            : `当前对象指标数：${metricCount}`}
        </div>
      </div>

      <div className="mb-2 rounded border border-gray-300 bg-white">
        <div className="border-b border-gray-300 bg-gray-100 px-3 py-1.5">
          <div className="flex min-w-0 items-center gap-2">
            <div className="shrink-0 pt-0.5 text-[11px] font-medium text-gray-700">机构及产品</div>
            <div className="relative min-w-0 flex-1">
              <div
                className="flex min-h-[30px] w-full cursor-pointer items-center gap-2 rounded border border-gray-300 bg-white px-2 py-1 text-left text-xs shadow-sm transition hover:border-blue-300"
                onClick={() => setEntityDropdownOpen((prev) => !prev)}
              >
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <span className="shrink-0 rounded bg-blue-50 px-2 py-0.5 font-mono text-[11px] text-blue-700">
                    {activeEntity.code}
                  </span>
                  <span className="min-w-0 truncate text-gray-800">{activeEntity.name || "请选择机构或产品"}</span>
                </div>
                <div className="ml-auto flex shrink-0 items-center gap-1.5 text-gray-500">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setEntityDropdownOpen((prev) => !prev);
                    }}
                    className="rounded border border-gray-200 bg-gray-50 p-0.5 hover:bg-gray-100"
                    title="展开或收起选择框"
                  >
                    <ChevronDown className={`h-4 w-4 transition ${entityDropdownOpen ? "rotate-180" : ""}`} />
                  </button>
                </div>
              </div>

              {entityDropdownOpen ? (
                <div className="absolute left-0 right-0 top-[calc(100%+8px)] z-20 rounded-lg border border-gray-300 bg-white shadow-xl">
                  <div className="border-b border-gray-200 p-3">
                    <div className="relative">
                      <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
                      <input
                        value={entitySearchInput}
                        onChange={(e) => {
                          setEntitySearchInput(e.target.value);
                          setEntitySearch(e.target.value);
                        }}
                        placeholder="按机构或产品搜索..."
                        className="w-full rounded border border-gray-300 py-1.5 pl-8 pr-8 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                      {entitySearchInput ? (
                        <button
                          type="button"
                          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-gray-200"
                          onClick={() => {
                            setEntitySearchInput("");
                            setEntitySearch("");
                          }}
                        >
                          <X className="h-3.5 w-3.5 text-gray-500" />
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <div className="max-h-72 overflow-auto">
                    {visibleEntityTree ? (
                      renderEntityNode(visibleEntityTree)
                    ) : (
                      <div className="px-4 py-6 text-xs text-gray-500">未找到匹配的机构或产品。</div>
                    )}
                  </div>
                  <div className="flex justify-end border-t border-gray-200 bg-gray-50 px-3 py-2">
                    <button
                      type="button"
                      onClick={() => setEntityDropdownOpen(false)}
                      className={`${neutralActionClass} shrink-0 whitespace-nowrap`}
                      title="已勾选项显示在上方；点击标签可切换当前对象"
                    >
                      <span>确定</span>
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
            {viewMode === "metric" ? (
              <div className="flex shrink-0 flex-nowrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={triggerImportReportFilePicker}
                  className={`${neutralActionClass} whitespace-nowrap px-2.5 py-1`}
                  disabled={importing}
                >
                  <Upload className="h-3.5 w-3.5 shrink-0" />
                  <span>{importing ? "导入中..." : "Excel导入"}</span>
                </button>
                <button
                  type="button"
                  onClick={handleExportReport}
                  className={`${neutralActionClass} whitespace-nowrap px-2.5 py-1`}
                  disabled={exporting}
                >
                  <Download className="h-3.5 w-3.5 shrink-0" />
                  <span>{exporting ? "导出中..." : "Excel导出"}</span>
                </button>
                {supportsMetricDefinition(activeEntity) && activeCatalogScope ? (
                  <button
                    type="button"
                    onClick={() => setCatalogManagerOpen(true)}
                    className={`${neutralActionClass} whitespace-nowrap px-2.5 py-1`}
                    title="管理当前主体范围的指标表（新增、停用、排序）"
                  >
                    <Settings2 className="h-3.5 w-3.5 shrink-0" />
                    <span>管理指标表</span>
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={handleSaveRefresh}
                  className={`${neutralActionClass} whitespace-nowrap px-2.5 py-1`}
                  disabled={savingRefresh}
                >
                  <Save className="h-3.5 w-3.5 shrink-0" />
                  <span>{savingRefresh ? "保存中..." : "保存刷新"}</span>
                </button>
              </div>
            ) : (
              <div className="flex shrink-0 flex-nowrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={triggerImportReportFilePicker}
                  className={`${neutralActionClass} whitespace-nowrap px-2.5 py-1`}
                  disabled={importing}
                  title="从 Excel 导入取数公式（工作表名如 AA业务状况表）"
                >
                  <Upload className="h-3.5 w-3.5 shrink-0" />
                  <span>{importing ? "导入中..." : "Excel导入"}</span>
                </button>
                <button
                  type="button"
                  onClick={handleExportReport}
                  className={`${neutralActionClass} whitespace-nowrap px-2.5 py-1`}
                  disabled={exporting}
                  title="导出带取数公式的 Excel，便于批量检查与编辑"
                >
                  <Download className="h-3.5 w-3.5 shrink-0" />
                  <span>{exporting ? "导出中..." : "Excel导出"}</span>
                </button>
                <button
                  type="button"
                  onClick={handleSaveRefresh}
                  className={`${neutralActionClass} whitespace-nowrap px-2.5 py-1`}
                  disabled={savingRefresh}
                >
                  <Save className="h-3.5 w-3.5 shrink-0" />
                  <span>{savingRefresh ? "保存中..." : "保存刷新"}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mb-2 rounded border border-gray-300 bg-white px-3 py-1.5">
        <div className="flex flex-nowrap items-center gap-2 overflow-x-auto">
          <div className="text-[11px] font-medium text-gray-700">指标表</div>
          {activeMetricTables.map((table) => (
            <button
              key={table.id}
              type="button"
              onClick={() => selectMetricTable(table.id)}
              className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[11px] transition ${
                table.id === activeTableId
                  ? "border-blue-300 bg-blue-50 text-blue-700 shadow-sm"
                  : "border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100"
              }`}
            >
              {table.name}
            </button>
          ))}
          {activeMetricTables.length === 0 ? (
            <span className="text-xs text-gray-500">
              {supportsMetricDefinition(activeEntity)
                ? "当前对象暂无指标表。"
                : "集团层（AAA）无单机构指标表；集团汇总见「预测输出 · 矩阵报表」。请选择 AA、AB 或下级机构/产品。"}
            </span>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {viewMode === "metric" ? (
        <div className="flex min-h-0 max-h-[calc(100vh-260px)] flex-col overflow-hidden rounded border border-gray-300 bg-white">
          <div className="border-b border-gray-300 bg-gray-100 px-3 py-2">
            <div className="flex flex-nowrap items-center gap-2 overflow-x-auto">
              <div className="relative min-w-[260px] max-w-[420px] flex-1">
                <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
                <input
                  value={metricSearchInput}
                  onChange={(e) => {
                    setMetricSearchInput(e.target.value);
                    setMetricSearch(e.target.value);
                  }}
                  placeholder="搜索指标代码、名称或备注..."
                  className="w-full rounded border border-gray-300 py-1 pl-8 pr-8 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                {metricSearchInput ? (
                  <button
                    type="button"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-gray-200"
                    onClick={() => {
                      setMetricSearchInput("");
                      setMetricSearch("");
                    }}
                  >
                    <X className="h-3.5 w-3.5 text-gray-500" />
                  </button>
                ) : null}
              </div>
              <div className="shrink-0 text-[11px] text-gray-500">共 {metricCount} 个指标</div>
              <div className="ml-auto flex shrink-0 flex-nowrap items-center gap-2">
                <button type="button" onClick={addRootMetric} className={secondaryActionClass}>
                  <BadgePlus className="h-3.5 w-3.5" />
                  <span>新增一级指标</span>
                </button>
                <button type="button" onClick={addChildMetric} className={primaryActionClass}>
                  <BadgePlus className="h-3.5 w-3.5" />
                  <span>{activeMetric ? "新增当前下级指标" : "新增一级指标"}</span>
                </button>
                <button type="button" onClick={deleteMetric} className={dangerActionClass} disabled={!activeMetric}>
                  <Trash2 className="h-3.5 w-3.5" />
                  <span>删除当前指标</span>
                </button>
              </div>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {!loading && !loadError && filteredMetricTree.length > 0 ? (
                <div className="sticky top-0 z-10 grid grid-cols-[86px_86px_150px_minmax(240px,1fr)_130px_92px] gap-2 border-b border-gray-300 bg-slate-50 px-3 py-2 text-xs font-medium text-gray-700">
                  <div className="text-left">科目层级</div>
                  <div className="text-left">科目性质</div>
                  <div className="text-left">科目代码</div>
                  <div className="text-left">科目名称</div>
                  <div className="text-left">逻辑码</div>
                  <div className="text-left">汇总</div>
                </div>
            ) : null}
            {loading ? <div className="px-4 py-8 text-xs text-gray-500">正在加载指标...</div> : null}
            {!loading && loadError ? <div className="px-4 py-8 text-xs text-red-600">{loadError}</div> : null}
            {!loading && !loadError && filteredMetricTree.length === 0 ? (
              <div className="px-4 py-10">
                {hasMetricSearch && activeMetricTree.length > 0 ? (
                  <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-xs text-gray-600">
                    <div className="font-medium text-gray-800">未找到匹配的指标</div>
                    <div className="mt-1">请检查搜索关键字，清空条件后查看全部指标。</div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className={neutralActionClass}
                        onClick={() => {
                          setMetricSearchInput("");
                          setMetricSearch("");
                        }}
                      >
                        <span>清空条件</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50 px-4 py-6 text-xs text-gray-700">
                    <div className="font-medium text-blue-800">当前指标表暂无指标</div>
                    <div className="mt-1">可点击「新增一级指标」维护；或使用顶部工具栏「Excel导入」（工作表名如 AA业务状况表）。</div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button type="button" onClick={addRootMetric} className={secondaryActionClass}>
                        <BadgePlus className="h-3.5 w-3.5" />
                        <span>新增一级指标</span>
                      </button>
                    </div>
                    <div className="mt-3 text-[11px] text-gray-600">
                      批量导入后请点击「保存刷新」写入数据库。
                    </div>
                  </div>
                )}
              </div>
            ) : null}
            {!loading && !loadError ? renderMetricRows(filteredMetricTree) : null}
          </div>
        </div>
        ) : (
          <div className="grid min-h-0 grid-cols-2 gap-0 font-sans">
            <div className="min-h-0 overflow-hidden rounded-l border border-gray-300 border-r-0 bg-white">
              <div className="border-b border-gray-200 bg-gray-100 px-3 py-2">
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
                    <input
                      value={metricSearchInput}
                      onChange={(e) => {
                        setMetricSearchInput(e.target.value);
                        setMetricSearch(e.target.value);
                      }}
                      placeholder="搜索指标代码、名称或备注..."
                      className="w-full rounded border border-gray-300 py-1 pl-8 pr-8 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    {metricSearchInput ? (
                      <button
                        type="button"
                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-gray-200"
                        onClick={() => {
                          setMetricSearchInput("");
                          setMetricSearch("");
                        }}
                      >
                        <X className="h-3.5 w-3.5 text-gray-500" />
                      </button>
                    ) : null}
                  </div>
                  <span className="shrink-0 text-[11px] text-gray-500">{flatMetricRowsForFormula.length} 项</span>
                </div>
              </div>
              <div className="min-h-0 max-h-[calc(100vh-320px)] overflow-y-auto overflow-x-auto">
                {flatMetricRowsForFormula.length === 0 ? (
                  <div className="px-4 py-6 text-xs text-gray-500">当前条件下没有可配置公式的指标。</div>
                ) : (
                  <div className="min-w-0">
                    <div className={`sticky top-0 z-10 grid ${FORMULA_METRIC_LIST_GRID} gap-1.5 border-b border-gray-200 bg-slate-50 px-2.5 py-2 text-[10px] font-medium text-gray-700`}>
                      <div className="whitespace-nowrap">科目层级</div>
                      <div className="whitespace-nowrap">科目代码</div>
                      <div className="whitespace-nowrap">科目名称</div>
                      <div className="text-center whitespace-nowrap" title="实际月公式">实际月</div>
                      <div className="text-center whitespace-nowrap" title="预测月公式">预测月</div>
                      <div className="text-center whitespace-nowrap" title="年预算公式">年预算</div>
                      <div className="text-center whitespace-nowrap" title="年预测公式">年预测</div>
                      <div className="text-center whitespace-nowrap">公式说明</div>
                    </div>
                    {flatMetricRowsForFormula.map((row) => {
                      const isSelected = row.id === activeMetricId;
                      const displayCode = formatMetricCodeForDisplay(activeEntity.code, row.code);
                      const dragText = buildFormulaInsertText(activeEntity, currentTableName, displayCode, row.name);
                      const hasActual = metricHasActualFormula(row);
                      const hasForecast = metricHasForecastFormula(row);
                      const hasBudgetAnnual = metricHasBudgetAnnualFormula(row);
                      const hasForecastAnnual = metricHasForecastAnnualFormula(row);
                      const formulaNote = String(row.formula_note ?? "").trim();
                      return (
                        <div
                          key={`${activeMetricScopeKey}-${row.pathKey}-${row.id}`}
                          className={`grid ${FORMULA_METRIC_LIST_GRID} items-start gap-1.5 border-b border-gray-100 px-2.5 py-1.5 text-[11px] ${
                            isSelected ? "bg-blue-50/80 ring-1 ring-inset ring-blue-200" : "hover:bg-gray-50/80"
                          }`}
                          onClick={() => selectFormulaMetric(row.id)}
                          draggable
                          onDragStart={(e) => {
                            e.dataTransfer.setData("text/plain", dragText);
                            e.dataTransfer.effectAllowed = "copy";
                          }}
                        >
                          <span className={FORMULA_METRIC_LEVEL_CELL}>{row.levelLabel}</span>
                          <span className={FORMULA_METRIC_CODE_CELL} title={displayCode}>
                            {displayCode}
                          </span>
                          <span
                            className={FORMULA_METRIC_NAME_CELL}
                            style={{ paddingLeft: `${Math.min(row.depth, 4) * FORMULA_METRIC_NAME_INDENT_PX}px` }}
                            title={row.name}
                          >
                            {row.name}
                          </span>
                          <div className="flex justify-center pt-0.5">
                            {hasActual ? (
                              <button
                                type="button"
                                className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-blue-50 text-blue-600 hover:bg-blue-100"
                                title="有实际月公式，点击查看"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openFormulaFromListRow(row.id, "actual");
                                }}
                                aria-label="实际月公式"
                              >
                                <Calculator className="h-3 w-3" />
                              </button>
                            ) : (
                              <span className="inline-flex h-5 w-5 items-center justify-center text-[10px] text-gray-300">—</span>
                            )}
                          </div>
                          <div className="flex justify-center pt-0.5">
                            {hasForecast ? (
                              <button
                                type="button"
                                className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 hover:bg-emerald-100"
                                title="有预测月公式，点击查看"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openFormulaFromListRow(row.id, "forecast");
                                }}
                                aria-label="预测月公式"
                              >
                                <Calculator className="h-3 w-3" />
                              </button>
                            ) : (
                              <span className="inline-flex h-5 w-5 items-center justify-center text-[10px] text-gray-300">—</span>
                            )}
                          </div>
                          <div className="flex justify-center pt-0.5">
                            {hasBudgetAnnual ? (
                              <button
                                type="button"
                                className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-amber-50 text-amber-600 hover:bg-amber-100"
                                title="有年预算公式，点击查看"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openFormulaFromListRow(row.id, "budgetAnnual");
                                }}
                                aria-label="年预算公式"
                              >
                                <Calculator className="h-3 w-3" />
                              </button>
                            ) : (
                              <span className="inline-flex h-5 w-5 items-center justify-center text-[10px] text-gray-300">—</span>
                            )}
                          </div>
                          <div className="flex justify-center pt-0.5">
                            {hasForecastAnnual ? (
                              <button
                                type="button"
                                className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-violet-50 text-violet-600 hover:bg-violet-100"
                                title="有年预测公式，点击查看"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openFormulaFromListRow(row.id, "forecastAnnual");
                                }}
                                aria-label="年预测公式"
                              >
                                <Calculator className="h-3 w-3" />
                              </button>
                            ) : (
                              <span className="inline-flex h-5 w-5 items-center justify-center text-[10px] text-gray-300">—</span>
                            )}
                          </div>
                          <span
                            className="pt-0.5 min-w-0 truncate text-center text-[10px] leading-4 text-gray-600"
                            title={formulaNote || "无公式说明"}
                          >
                            {formulaNote || "—"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            <div className="min-h-0 overflow-hidden rounded-r border border-gray-300 border-l-0 bg-white">
              <div className="border-b border-gray-200 bg-gradient-to-r from-white to-slate-50 px-3 py-2">
                <div className="flex flex-col gap-1.5">
                  <div
                    className="min-w-0 text-[10px] font-medium text-gray-700"
                    title={activeMetric ? formatMetricHeaderText(activeEntity, activeMetric) : ""}
                  >
                    {activeMetric ? (
                      <div className="min-w-0 truncate">{formatMetricHeaderText(activeEntity, activeMetric)}</div>
                    ) : (
                      <span className="font-normal text-gray-500">请选择一个指标</span>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <div className="inline-flex overflow-hidden rounded border border-gray-200 bg-white text-[10px] shadow-sm">
                      <button
                        type="button"
                        className={`h-6 px-2.5 ${formulaScope === "actual" ? "bg-indigo-50 font-medium text-indigo-700" : "text-gray-600 hover:bg-gray-50"}`}
                        onClick={() => setFormulaScope("actual")}
                        disabled={!activeMetric}
                      >
                        实际月公式
                      </button>
                      <div className="w-px bg-gray-200" />
                      <button
                        type="button"
                        className={`h-6 px-2.5 ${formulaScope === "forecast" ? "bg-indigo-50 font-medium text-indigo-700" : "text-gray-600 hover:bg-gray-50"}`}
                        onClick={() => setFormulaScope("forecast")}
                        disabled={!activeMetric}
                      >
                        预测月公式
                      </button>
                      <div className="w-px bg-gray-200" />
                      <button
                        type="button"
                        className={`h-6 px-2.5 ${formulaScope === "budgetAnnual" ? "bg-indigo-50 font-medium text-indigo-700" : "text-gray-600 hover:bg-gray-50"}`}
                        onClick={() => setFormulaScope("budgetAnnual")}
                        disabled={!activeMetric}
                      >
                        年预算公式
                      </button>
                      <div className="w-px bg-gray-200" />
                      <button
                        type="button"
                        className={`h-6 px-2.5 ${formulaScope === "forecastAnnual" ? "bg-indigo-50 font-medium text-indigo-700" : "text-gray-600 hover:bg-gray-50"}`}
                        onClick={() => setFormulaScope("forecastAnnual")}
                        disabled={!activeMetric}
                      >
                        年预测公式
                      </button>
                    </div>
                    <label className="inline-flex items-center gap-1.5 text-[10px] text-gray-600">
                      <span>公式说明</span>
                      <select
                        value={formulaNoteText}
                        onChange={(e) => {
                          setFormulaNoteText(e.target.value);
                          setFormulaDirty(true);
                        }}
                        className="h-6 rounded border border-gray-200 bg-white px-1.5 text-[10px] text-gray-700"
                        disabled={!activeMetric}
                      >
                        {FORMULA_NOTE_OPTIONS.map((opt) => (
                          <option key={opt || "__empty"} value={opt}>
                            {opt || "无"}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span className="text-[10px] text-gray-500">月度公式用于实际/预测月；年度公式用于全年预算/全年预测口径。</span>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="inline-flex overflow-hidden rounded border border-gray-200 bg-white shadow-sm">
                      <button
                        type="button"
                        className="h-6 px-2 text-[10px] text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        onClick={() => {
                          const next = formatFormulaText(formulaText);
                          setFormulaText(next);
                          setFormulaDirty(true);
                        }}
                        disabled={!activeMetric}
                      >
                        格式化
                      </button>
                      <div className="w-px bg-gray-200" />
                      <button
                        type="button"
                        className="h-6 px-2 text-[10px] text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        onClick={() => {
                          setFormulaText("");
                          setFormulaDirty(true);
                        }}
                        disabled={!activeMetric}
                      >
                        清空
                      </button>
                    </div>

                    <button
                      type="button"
                      className="h-6 rounded border border-gray-200 bg-white px-2 text-[10px] text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
                      onClick={() => {
                        setRefEntityId(activeEntityId);
                        setRefTableName(currentTableName);
                        setRefMetricSearch("");
                        setRefMetricSearchInput("");
                        setFormulaFullscreenOpen(true);
                        requestAnimationFrame(() => formulaFullscreenRef.current?.focus());
                      }}
                      disabled={!activeMetric}
                      title="弹出编辑"
                      aria-label="弹出编辑"
                    >
                      弹出编辑
                    </button>

                    <div className="flex-1" />

                    <button
                      type="button"
                      className={`${primaryActionClass} h-6 justify-center px-3 py-1 text-[10px]`}
                      onClick={() => void saveFormulaForActiveMetric()}
                      disabled={!activeMetric || metricEditorSaving}
                    >
                      <Save className="h-2.5 w-2.5" />
                      <span>{metricEditorSaving ? "保存中..." : "保存公式"}</span>
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex min-h-0 flex-col gap-2.5 p-3">
                <div className="min-h-0 w-full flex flex-col gap-1.5">
                  <div className="rounded-md border border-gray-200 bg-white shadow-sm">
                    <textarea
                      ref={formulaInputRef}
                      value={formulaText}
                      onChange={(e) => {
                        setFormulaText(e.target.value);
                        setFormulaDirty(true);
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        const text = e.dataTransfer.getData("text/plain");
                        if (text) insertIntoFormula(text, text.length);
                      }}
                      onDragOver={(e) => e.preventDefault()}
                      placeholder=""
                      wrap="soft"
                      spellCheck={false}
                      className={`h-[88px] w-full resize-y overflow-x-hidden break-all bg-white p-2.5 leading-6 focus:outline-none focus:ring-1 focus:ring-blue-500 ${FORMULA_UI_INPUT_CLASS}`}
                      disabled={!activeMetric}
                    />
                  </div>
                  <div className={`text-[11px] ${formulaFullValidationMessage.startsWith("校验通过") ? "text-green-700" : "text-red-600"}`}>
                    {formulaFullValidationMessage}
                    {activeMetric && formulaDirty ? "（未保存）" : ""}
                  </div>
                  {formulaResolvedRefs.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5 text-[10px]">
                      <span className="text-gray-500">引用解析：</span>
                      {formulaResolvedRefs.map((ref) => (
                        <span
                          key={ref.key}
                          className={`rounded border px-1.5 py-0.5 ${ref.missing ? "border-red-200 bg-red-50 text-red-700" : "border-gray-200 bg-gray-50 text-gray-700"}`}
                          title={ref.label}
                        >
                          {ref.label}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>

                {renderFormulaReferencePicker("inline")}

                <div className="min-h-0 w-full overflow-hidden rounded-md border border-gray-200 bg-slate-50/70 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="shrink-0 text-[11px] font-medium text-gray-700 whitespace-nowrap">AI 批量生成</div>
                      <span
                        className={`shrink-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          formulaScope === "actual" ? "bg-blue-50 text-blue-700" : "bg-emerald-50 text-emerald-700"
                        }`}
                      >
                        {formulaScopeLabel}
                      </span>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <button
                        type="button"
                        className="h-7 rounded border border-gray-200 bg-white px-2.5 text-[11px] text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
                        onClick={() => setAiPanelOpen((v) => !v)}
                        disabled={!activeMetric}
                      >
                        {aiPanelOpen ? "收起" : "展开"}
                      </button>
                      <button
                        type="button"
                        className="h-7 rounded border border-gray-200 bg-white px-2.5 text-[11px] text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
                        onClick={() => {
                          setAiPanelOpen(true);
                          setAiDescriptionFullscreenOpen(true);
                          requestAnimationFrame(() => aiDescriptionFullscreenRef.current?.focus());
                        }}
                        disabled={!activeMetric}
                      >
                        弹出编辑
                      </button>
                      <button
                        type="button"
                        className="h-7 rounded border border-gray-200 bg-white px-2.5 text-[11px] text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
                        onClick={() => setAiPreviewOpen((v) => !v)}
                        disabled={!activeMetric}
                      >
                        {aiPreviewOpen ? "收起预览" : "展开预览"}
                      </button>
                    </div>
                  </div>

                  {aiPanelOpen ? (
                    <div className="mt-2 grid gap-2">
                      <textarea
                        value={aiDescription}
                        onChange={(e) => setAiDescription(e.target.value)}
                        placeholder=""
                        wrap="soft"
                        spellCheck={false}
                        className="h-24 w-full resize-y rounded border border-gray-300 bg-white px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                        <div className="flex items-center gap-2 rounded border border-gray-300 bg-white px-2">
                          <div className="shrink-0 text-[11px] text-gray-500">应用范围</div>
                          <select
                            value={aiScope}
                            onChange={(e) => setAiScope(e.target.value as any)}
                            className="h-8 min-w-0 flex-1 bg-transparent text-xs outline-none"
                          >
                            <option value="active">当前对象</option>
                            <option value="selected">已勾选对象</option>
                            <option value="all-products">全部三级产品</option>
                          </select>
                        </div>
                        <div className="flex items-center gap-2 rounded border border-gray-300 bg-white px-2">
                          <div className="shrink-0 text-[11px] text-gray-500">指标表</div>
                          <select
                            value={String(aiTargetTableName || currentTableName)}
                            onChange={(e) => setAiTargetTableName(e.target.value)}
                            className="h-8 min-w-0 flex-1 bg-transparent text-xs outline-none"
                          >
                            {(allMetricTableNames.length > 0 ? allMetricTableNames : [currentTableName]).map((name) => (
                              <option key={name} value={name}>
                                {name}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          className="inline-flex items-center justify-center gap-1.5 rounded-md border border-sky-300 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-800 shadow-sm transition hover:bg-sky-100 disabled:opacity-50"
                          onClick={() => void generateAiPreview()}
                          disabled={aiGenerating}
                        >
                          <span>{aiGenerating ? "生成中..." : "生成预览"}</span>
                        </button>
                        <button
                          type="button"
                          className="inline-flex items-center justify-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50"
                          onClick={() => void applyAiPreview()}
                          disabled={aiApplying}
                        >
                          <span>{aiApplying ? "应用中..." : "一键应用"}</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2 text-[11px] leading-5 text-gray-500">按描述批量生成公式，先预览再一键应用。</div>
                  )}

                  {aiPreviewOpen ? (
                    <div className="mt-2 max-h-56 overflow-auto rounded border border-gray-200 bg-white">
                      {aiPreviewRows.length === 0 ? (
                        <div className="px-3 py-3 text-xs text-gray-500">暂无预览结果。</div>
                      ) : (
                        <table className="w-full table-fixed text-xs">
                          <thead className="sticky top-0 bg-gray-50">
                            <tr className="border-b border-gray-200 text-[11px] text-gray-600">
                              <th className="w-36 px-3 py-2 text-left font-medium">对象</th>
                              <th className="w-44 px-3 py-2 text-left font-medium">目标指标</th>
                              <th className="px-3 py-2 text-left font-medium whitespace-nowrap">预览结果</th>
                            </tr>
                          </thead>
                          <tbody>
                            {aiPreviewRows.map((row, idx) => (
                              <tr key={`${row.entityId}-${row.tableName}-${row.targetMetricId}-${idx}`} className="border-b border-gray-100">
                                <td className="px-3 py-2">
                                  <div className="truncate">
                                    {row.entityCode} {row.entityName}
                                  </div>
                                  <div className="text-[11px] text-gray-500 truncate">{row.tableName}</div>
                                </td>
                                <td className="px-3 py-2">
                                  <div className="truncate text-gray-700">{row.targetMetricCodeDisplay || "-"}</div>
                                  <div className="truncate">{row.targetMetricName}</div>
                                </td>
                                <td className="px-3 py-2">
                                  <div className="flex items-start gap-2">
                                    <div
                                      className={`min-w-0 flex-1 truncate ${row.ok ? "text-gray-800" : "text-red-600"}`}
                                      title={row.ok ? row.newFormula : row.reason || "生成失败"}
                                    >
                                      {row.ok ? row.newFormula : row.reason || "生成失败"}
                                    </div>
                                    <button
                                      type="button"
                                      className="shrink-0 rounded border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50"
                                      onClick={() => openAiPreviewDetail(row)}
                                    >
                                      详情
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {aiPreviewDetailOpen && typeof document !== "undefined"
        ? createPortal(
            <div className="fixed inset-0 z-[1000] bg-black/40 p-4">
              <div className="mx-auto flex max-h-full w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white shadow-xl ring-1 ring-black/10">
                <div className="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-3">
                  <div className="min-w-0 flex-1 text-sm font-medium text-gray-800">预览详情</div>
                  {aiPreviewDetailRow?.ok ? (
                    <button
                      type="button"
                      className="inline-flex items-center justify-center rounded border border-gray-200 bg-white px-2.5 py-1 text-[11px] text-gray-700 hover:bg-gray-50"
                      onClick={() => void copyText(aiPreviewDetailRow?.newFormula ?? "")}
                    >
                      复制公式
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 items-center justify-center rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                    onClick={() => setAiPreviewDetailOpen(false)}
                    aria-label="关闭"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-auto p-4 text-xs">
                  <div className="grid gap-2 text-gray-700">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="text-gray-500">对象：</span>
                      <span className="font-medium">
                        {aiPreviewDetailRow ? `${aiPreviewDetailRow.entityCode} ${aiPreviewDetailRow.entityName}` : "-"}
                      </span>
                      <span className="text-gray-500">指标表：</span>
                      <span className="font-medium">{aiPreviewDetailRow?.tableName || "-"}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="text-gray-500">目标指标：</span>
                      <span className="font-medium text-gray-800">{aiPreviewDetailRow?.targetMetricCodeDisplay || "-"}</span>
                      <span className="font-medium">{aiPreviewDetailRow?.targetMetricName || "-"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">结果：</span>
                      {aiPreviewDetailRow?.ok ? (
                        <span className="rounded bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">可应用</span>
                      ) : (
                        <span className="rounded bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700">需修正</span>
                      )}
                    </div>
                  </div>
                  {aiPreviewDetailRow?.aiExprTokens?.some((t) => t.kind === "metric" && (t.candidates?.length ?? 0) > 0) ? (
                    <div className="mt-3 rounded border border-gray-200 bg-white p-3">
                      <div className="mb-2 text-[11px] font-medium text-gray-600">来源指标确认</div>
                      <div className="grid gap-2">
                        {aiPreviewDetailRow.aiExprTokens.map((t, idx) =>
                          t.kind === "metric" && (t.candidates?.length ?? 0) > 0 ? (
                            <div key={`src-${idx}-${t.value}`} className="grid grid-cols-[140px_minmax(0,1fr)_28px] items-center gap-2">
                              <div className="truncate text-gray-600" title={t.value}>
                                {t.value || "来源指标"}
                              </div>
                              <select
                                value={t.selectedNormalizedCode || t.candidates?.[0]?.normalizedCode || ""}
                                onChange={(e) => updateAiPreviewDetailTokenSelection(idx, e.target.value)}
                                className="h-8 min-w-0 rounded border border-gray-300 bg-white px-2 text-xs outline-none"
                              >
                                {(t.candidates ?? []).map((c) => (
                                  <option key={`${c.normalizedCode}`} value={c.normalizedCode}>
                                    {c.displayCode} {c.name}
                                  </option>
                                ))}
                              </select>
                              <button
                                type="button"
                                className="inline-flex h-7 w-7 items-center justify-center rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                                onClick={() => removeAiPreviewDetailToken(idx)}
                                title="移除该来源指标"
                                aria-label="移除"
                              >
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ) : null
                        )}
                      </div>
                      <div className="mt-3 grid gap-2">
                        <div className="text-[11px] font-medium text-gray-600">新增来源指标</div>
                        <div className="grid gap-2">
                          <div className="grid grid-cols-[120px_minmax(0,1fr)_120px_minmax(0,1fr)] items-center gap-2">
                            <div className="text-xs text-gray-600">来源对象</div>
                            <select
                              value={aiAddSourceEntityId || aiPreviewDetailRow?.entityId || ""}
                              onChange={(e) => {
                                const nextId = e.target.value;
                                setAiAddSourceEntityId(nextId);
                                const tables = metricTablesByEntityId[nextId] ?? [];
                                setAiAddSourceTableName(String(tables[0]?.name ?? ""));
                                setAiAddSourceSelectedKey("");
                                setAiAddSourceDropdownOpen(false);
                              }}
                              className="h-8 min-w-0 rounded border border-gray-300 bg-white px-2 text-xs outline-none"
                            >
                              {collectOrgNodes(orgTree)
                                .filter((n) => (metricTablesByEntityId[n.id] ?? []).length > 0)
                                .map((n) => (
                                  <option key={n.id} value={n.id}>
                                    {String(n.code || "").trim()} {String(n.name || "").trim()}
                                  </option>
                                ))}
                            </select>
                            <div className="text-xs text-gray-600">指标表</div>
                            <select
                              value={aiAddSourceTableName || aiPreviewDetailRow?.tableName || ""}
                              onChange={(e) => {
                                setAiAddSourceTableName(e.target.value);
                                setAiAddSourceSelectedKey("");
                                setAiAddSourceDropdownOpen(false);
                              }}
                              className="h-8 min-w-0 rounded border border-gray-300 bg-white px-2 text-xs outline-none"
                            >
                              {(metricTablesByEntityId[aiAddSourceEntityId || aiPreviewDetailRow?.entityId || ""] ?? []).map((t) => (
                                <option key={t.id} value={t.name}>
                                  {t.name}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="grid grid-cols-[minmax(0,1fr)_72px] items-start gap-2">
                            <div className="relative">
                              <input
                                value={aiAddSourceQuery}
                                onChange={(e) => {
                                  setAiAddSourceQuery(e.target.value);
                                  setAiAddSourceSelectedKey("");
                                  setAiAddSourceDropdownOpen(true);
                                }}
                                onFocus={() => setAiAddSourceDropdownOpen(true)}
                                onBlur={() => {
                                  window.setTimeout(() => setAiAddSourceDropdownOpen(false), 100);
                                }}
                                placeholder="搜索科目代码/名称..."
                                className="h-8 w-full min-w-0 rounded border border-gray-300 bg-white px-2 text-xs outline-none"
                              />
                              {(() => {
                                const row = aiPreviewDetailRow;
                                const srcEntityId = String(aiAddSourceEntityId || row?.entityId || "").trim();
                                const srcTableName = String(aiAddSourceTableName || row?.tableName || "").trim();
                                const key = srcEntityId && srcTableName ? `${srcEntityId}::${srcTableName}` : "";
                                const infoMap = key ? metricRefInfoByEntityTableKey.get(key) ?? null : null;
                                const q = String(aiAddSourceQuery || "").trim().toUpperCase();
                                const list = infoMap ? [...infoMap.entries()].map(([normalizedCode, info]) => ({ normalizedCode, info })) : [];
                                const filtered = q
                                  ? list.filter((x) => `${x.info.displayCode} ${x.info.name}`.toUpperCase().includes(q) || String(x.normalizedCode).includes(q))
                                  : list;
                                const items = filtered.slice(0, 8);
                                if (!aiAddSourceDropdownOpen || !q || items.length === 0) return null;
                                return (
                                  <div className="absolute left-0 right-0 top-9 z-20 max-h-48 overflow-auto rounded border border-gray-200 bg-white shadow">
                                    {items.map((x) => {
                                      const k = `${srcEntityId}::${srcTableName}::${x.normalizedCode}`;
                                      const active = aiAddSourceSelectedKey === k;
                                      return (
                                        <button
                                          key={k}
                                          type="button"
                                          className={`flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs hover:bg-gray-50 ${active ? "bg-gray-50" : ""}`}
                                          onMouseDown={(e) => {
                                            e.preventDefault();
                                            setAiAddSourceSelectedKey(k);
                                            setAiAddSourceQuery(`${x.info.displayCode} ${x.info.name}`.trim());
                                            setAiAddSourceDropdownOpen(false);
                                          }}
                                        >
                                          <span className="text-gray-700">{x.info.displayCode}</span>
                                          <span className="truncate text-gray-700">{x.info.name}</span>
                                        </button>
                                      );
                                    })}
                                  </div>
                                );
                              })()}
                            </div>
                            <button
                              type="button"
                              className="h-8 rounded bg-blue-600 px-3 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                              onClick={addAiPreviewDetailMetric}
                              disabled={!aiPreviewDetailRow}
                            >
                              添加
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}
                  <div className="mt-3 rounded border border-gray-200 bg-gray-50 p-3">
                    <div className="mb-2 text-[11px] font-medium text-gray-600">{aiPreviewDetailRow?.ok ? "新公式" : "原因"}</div>
                    <div className={`whitespace-pre-wrap break-all ${FORMULA_UI_INPUT_CLASS} ${aiPreviewDetailRow?.ok ? "" : "text-rose-700"}`}>
                      {aiPreviewDetailRow
                        ? aiPreviewDetailRow.ok
                          ? decorateFormulaTextForDisplayWithContext(aiPreviewDetailRow.newFormula, aiPreviewDetailRow.entityId, aiPreviewDetailRow.tableName)
                          : aiPreviewDetailRow.reason || "生成失败"
                        : ""}
                    </div>
                  </div>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}

      {aiDescriptionFullscreenOpen && typeof document !== "undefined"
        ? createPortal(
            <div className="fixed inset-0 z-[1000] bg-black/40 p-4">
              <div className="mx-auto flex h-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white shadow-xl ring-1 ring-black/10">
                <div className="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-3">
                  <div className="min-w-0 flex-1 text-sm font-medium text-gray-800">AI 批量生成（文本输入）</div>
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 items-center justify-center rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                    onClick={() => setAiDescriptionFullscreenOpen(false)}
                    aria-label="关闭"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="min-h-0 flex-1 p-4">
                  <div className="h-full overflow-hidden rounded border border-gray-200 bg-white">
                    <textarea
                      ref={aiDescriptionFullscreenRef}
                      value={aiDescription}
                      onChange={(e) => setAiDescription(e.target.value)}
                      placeholder=""
                      wrap="soft"
                      spellCheck={false}
                      className="h-full w-full resize-none bg-white p-3 text-xs leading-6 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      type="button"
                      className="inline-flex items-center justify-center gap-1.5 rounded-md border border-sky-300 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-800 shadow-sm transition hover:bg-sky-100 disabled:opacity-50"
                      onClick={() => void generateAiPreview()}
                      disabled={aiGenerating}
                    >
                      <span>{aiGenerating ? "生成中..." : "生成预览"}</span>
                    </button>
                    <button
                      type="button"
                      className="inline-flex items-center justify-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50"
                      onClick={() => void applyAiPreview()}
                      disabled={aiApplying}
                    >
                      <span>{aiApplying ? "应用中..." : "一键应用"}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}

      {formulaFullscreenOpen && typeof document !== "undefined"
        ? createPortal(
            <div className="fixed inset-0 z-[1000] bg-black/40 p-4">
              <div className="mx-auto flex h-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white shadow-xl ring-1 ring-black/10">
                <div className="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-gray-800">
                      {activeMetric ? formatMetricHeaderText(activeEntity, activeMetric) : "公式编辑"}
                    </div>
                    <div className="mt-1 inline-flex overflow-hidden rounded border border-gray-200 bg-white text-[11px]">
                      <button
                        type="button"
                        className={`px-2.5 py-1 ${formulaScope === "actual" ? "bg-indigo-50 font-medium text-indigo-700" : "text-gray-600 hover:bg-gray-50"}`}
                        onClick={() => setFormulaScope("actual")}
                        disabled={!activeMetric}
                      >
                        实际月公式
                      </button>
                      <div className="w-px bg-gray-200" />
                      <button
                        type="button"
                        className={`px-2.5 py-1 ${formulaScope === "forecast" ? "bg-indigo-50 font-medium text-indigo-700" : "text-gray-600 hover:bg-gray-50"}`}
                        onClick={() => setFormulaScope("forecast")}
                        disabled={!activeMetric}
                      >
                        预测月公式
                      </button>
                      <div className="w-px bg-gray-200" />
                      <button
                        type="button"
                        className={`px-2.5 py-1 ${formulaScope === "budgetAnnual" ? "bg-indigo-50 font-medium text-indigo-700" : "text-gray-600 hover:bg-gray-50"}`}
                        onClick={() => setFormulaScope("budgetAnnual")}
                        disabled={!activeMetric}
                      >
                        年预算公式
                      </button>
                      <div className="w-px bg-gray-200" />
                      <button
                        type="button"
                        className={`px-2.5 py-1 ${formulaScope === "forecastAnnual" ? "bg-indigo-50 font-medium text-indigo-700" : "text-gray-600 hover:bg-gray-50"}`}
                        onClick={() => setFormulaScope("forecastAnnual")}
                        disabled={!activeMetric}
                      >
                        年预测公式
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="inline-flex overflow-hidden rounded border border-gray-200 bg-white">
                      <button
                        type="button"
                        className="px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        onClick={() => {
                          const next = formatFormulaText(formulaText);
                          setFormulaText(next);
                          setFormulaDirty(true);
                        }}
                        disabled={!activeMetric}
                      >
                        格式化
                      </button>
                      <div className="w-px bg-gray-200" />
                      <button
                        type="button"
                        className="px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        onClick={() => {
                          setFormulaText("");
                          setFormulaDirty(true);
                          requestAnimationFrame(() => formulaFullscreenRef.current?.focus());
                        }}
                        disabled={!activeMetric}
                      >
                        清空
                      </button>
                    </div>
                    <div className="flex-1" />
                    <button
                      type="button"
                      className={primaryActionClass}
                      onClick={() => void saveFormulaForActiveMetric()}
                      disabled={!activeMetric || metricEditorSaving}
                    >
                      <Save className="h-3.5 w-3.5" />
                      <span>{metricEditorSaving ? "保存中..." : "保存公式"}</span>
                    </button>
                    <button
                      type="button"
                      className="inline-flex h-8 w-8 items-center justify-center rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                      onClick={() => setFormulaFullscreenOpen(false)}
                      aria-label="关闭"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </div>
                <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_420px] gap-3 p-4">
                  <div className="flex min-h-0 flex-col">
                    <div className="min-h-0 flex-1 overflow-hidden rounded border border-gray-200 bg-white">
                      <textarea
                        ref={formulaFullscreenRef}
                        value={formulaText}
                        onChange={(e) => {
                          setFormulaText(e.target.value);
                          setFormulaDirty(true);
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          const text = e.dataTransfer.getData("text/plain");
                          if (text) insertIntoFormula(text, text.length);
                        }}
                        onDragOver={(e) => e.preventDefault()}
                        wrap="soft"
                        spellCheck={false}
                        className={`h-full w-full resize-none overflow-x-hidden break-all bg-white p-3 leading-6 focus:outline-none focus:ring-1 focus:ring-blue-500 ${FORMULA_UI_INPUT_CLASS}`}
                        disabled={!activeMetric}
                      />
                    </div>
                    <div className={`mt-2 text-[11px] ${formulaFullValidationMessage.startsWith("校验通过") ? "text-green-700" : "text-red-600"}`}>
                      {formulaFullValidationMessage}
                      {activeMetric && formulaDirty ? "（未保存）" : ""}
                    </div>
                    {formulaResolvedRefs.length > 0 ? (
                      <div className="mt-1 flex flex-wrap gap-1.5 text-[10px]">
                        <span className="text-gray-500">引用解析：</span>
                        {formulaResolvedRefs.map((ref) => (
                          <span
                            key={`fullscreen-${ref.key}`}
                            className={`rounded border px-1.5 py-0.5 ${ref.missing ? "border-red-200 bg-red-50 text-red-700" : "border-gray-200 bg-gray-50 text-gray-700"}`}
                            title={ref.label}
                          >
                            {ref.label}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="min-h-0">
                    {renderFormulaReferencePicker("modal")}
                  </div>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}

      {metricEditorOpen ? (
        <div
          className="fixed inset-0 z-50 bg-black/40 p-4"
        >
          <div
            ref={metricEditorRef}
            className="fixed w-full max-w-xl overflow-hidden rounded-xl bg-white shadow-xl ring-1 ring-black/10"
            style={
              metricEditorPos
                ? { left: `${metricEditorPos.x}px`, top: `${metricEditorPos.y}px` }
                : { left: "50%", top: "50%", transform: "translate(-50%, -50%)" }
            }
          >
            <div
              className="flex cursor-move select-none items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-3"
              onPointerDown={(e) => {
                if (e.button !== 0) return;
                const target = e.target as HTMLElement | null;
                if (target && target.closest("button, a, input, textarea, select")) return;
                const el = metricEditorRef.current;
                if (!el) return;
                const rect = el.getBoundingClientRect();
                metricEditorDragRef.current = {
                  pointerId: e.pointerId,
                  offsetX: e.clientX - rect.left,
                  offsetY: e.clientY - rect.top,
                };
                (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
              }}
              onPointerMove={(e) => {
                const drag = metricEditorDragRef.current;
                if (!drag || drag.pointerId !== e.pointerId) return;
                const el = metricEditorRef.current;
                if (!el) return;
                const rect = el.getBoundingClientRect();
                const margin = 12;
                const nextX = e.clientX - drag.offsetX;
                const nextY = e.clientY - drag.offsetY;
                const maxX = Math.max(margin, window.innerWidth - rect.width - margin);
                const maxY = Math.max(margin, window.innerHeight - rect.height - margin);
                setMetricEditorPos({
                  x: Math.min(maxX, Math.max(margin, Math.round(nextX))),
                  y: Math.min(maxY, Math.max(margin, Math.round(nextY))),
                });
              }}
              onPointerUp={(e) => {
                const drag = metricEditorDragRef.current;
                if (drag && drag.pointerId === e.pointerId) metricEditorDragRef.current = null;
              }}
            >
              <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-gray-800">
                <Edit3 className="h-4 w-4 text-gray-600" />
                <span className="truncate">指标维护</span>
              </div>
              <button
                type="button"
                className="inline-flex h-8 w-8 items-center justify-center rounded border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => setMetricEditorOpen(false)}
                aria-label="关闭"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="max-h-[72vh] overflow-auto px-4 py-4">
              <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-gray-700">
                <div className="font-medium text-blue-700">{activeEntity.code} {activeEntity.name}</div>
                <div className="mt-1 text-[11px] text-gray-600">指标表：{activeMetricTable?.name ?? DEFAULT_METRIC_TABLE_NAME}</div>
              </div>

              {activeMetric ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="mb-1 text-[11px] text-gray-500">科目层级</div>
                      <select
                        value={metricDraft.levelLabel}
                        onChange={(e) => setMetricDraft((prev) => ({ ...prev, levelLabel: e.target.value }))}
                        className="w-full rounded border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        disabled={metricEditorSaving}
                      >
                        {LEVEL_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] text-gray-500">性质</div>
                      <select
                        value={metricDraft.nature}
                        onChange={(e) => setMetricDraft((prev) => ({ ...prev, nature: e.target.value }))}
                        className="w-full rounded border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        disabled={metricEditorSaving}
                      >
                        {NATURE_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] text-gray-500">录入粒度</div>
                      <select
                        value={metricDraft.entry_granularity}
                        onChange={(e) =>
                          setMetricDraft((prev) => ({
                            ...prev,
                            entry_granularity: normalizeEntryGranularity(e.target.value),
                          }))
                        }
                        className="w-full rounded border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        disabled={metricEditorSaving}
                      >
                        {ENTRY_GRANULARITY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                      <div className="mt-1 text-[10px] leading-4 text-gray-500">
                        「按年录入」表示该指标无月度明细；年度取值由数据录入与预测规则处理。
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] text-gray-500">数值类型</div>
                      <select
                        value={metricDraft.value_type}
                        onChange={(e) =>
                          setMetricDraft((prev) => ({
                            ...prev,
                            value_type: normalizeValueType(e.target.value, prev.nature),
                          }))
                        }
                        className="w-full rounded border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        disabled={metricEditorSaving}
                      >
                        {VALUE_TYPE_OPTIONS.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <label className="flex items-center gap-2 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700">
                      <input
                        type="checkbox"
                        checked={metricDraft.allow_manual_entry}
                        onChange={(e) =>
                          setMetricDraft((prev) => ({
                            ...prev,
                            allow_manual_entry: e.target.checked,
                          }))
                        }
                        className="h-4 w-4 rounded border-gray-300 text-blue-600"
                        disabled={metricEditorSaving}
                      />
                      <span>允许在机构及产品数据录入中手工录入</span>
                    </label>
                    <label className="flex items-center gap-2 rounded border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-800">
                      <input
                        type="checkbox"
                        checked={metricDraft.horizontal_rollup}
                        onChange={(e) =>
                          setMetricDraft((prev) => ({
                            ...prev,
                            horizontal_rollup: e.target.checked,
                          }))
                        }
                        className="h-4 w-4 rounded border-blue-300 text-blue-600"
                        disabled={metricEditorSaving}
                      />
                      <span>横向汇总</span>
                    </label>
                    <label className="flex items-center gap-2 rounded border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                      <input
                        type="checkbox"
                        checked={metricDraft.vertical_rollup}
                        onChange={(e) =>
                          setMetricDraft((prev) => ({
                            ...prev,
                            vertical_rollup: e.target.checked,
                          }))
                        }
                        className="h-4 w-4 rounded border-emerald-300 text-emerald-600"
                        disabled={metricEditorSaving}
                      />
                      <span>纵向汇总</span>
                    </label>
                  </div>

                  <div>
                    <div className="mb-1 text-[11px] text-gray-500">代码</div>
                    <input
                      value={metricDraft.code}
                      onChange={(e) => setMetricDraft((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))}
                      className="w-full rounded border border-gray-300 px-3 py-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                      disabled={metricEditorSaving}
                    />
                  </div>

                  <div>
                    <div className="mb-1 text-[11px] text-gray-500">逻辑码</div>
                    <input
                      value={metricDraft.logic_code}
                      onChange={(e) => setMetricDraft((prev) => ({ ...prev, logic_code: e.target.value.toUpperCase() }))}
                      className="w-full rounded border border-gray-300 px-3 py-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                      disabled={metricEditorSaving}
                    />
                  </div>

                  <div>
                    <div className="mb-1 text-[11px] text-gray-500">名称</div>
                    <input
                      value={metricDraft.name}
                      onChange={(e) => setMetricDraft((prev) => ({ ...prev, name: e.target.value }))}
                      className="w-full rounded border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      disabled={metricEditorSaving}
                    />
                  </div>

                  <div>
                    <div className="mb-1 text-[11px] text-gray-500">解释 / 备注</div>
                    <textarea
                      value={metricDraft.note}
                      onChange={(e) => setMetricDraft((prev) => ({ ...prev, note: e.target.value }))}
                      rows={5}
                      placeholder="预留用于记录该指标的口径解释、业务说明或补充备注"
                      className="w-full rounded border border-gray-300 px-3 py-2 text-xs leading-6 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      disabled={metricEditorSaving}
                    />
                  </div>

                  <div>
                    <div className="mb-1 text-[11px] text-gray-500">取数公式（可选）</div>
                    <textarea
                      value={metricDraft.formula}
                      onChange={(e) => setMetricDraft((prev) => ({ ...prev, formula: e.target.value }))}
                      rows={4}
                      placeholder="例如：AA.01 + AA.02 - AA.03（支持后续扩展）"
                      className="w-full rounded border border-gray-300 px-3 py-2 text-xs font-mono leading-6 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      disabled={metricEditorSaving}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="mb-1 text-[11px] text-gray-500">年预算公式</div>
                      <textarea
                        value={metricDraft.formula_budget_annual}
                        onChange={(e) => setMetricDraft((prev) => ({ ...prev, formula_budget_annual: e.target.value }))}
                        rows={3}
                        className="w-full rounded border border-gray-300 px-3 py-2 text-xs font-mono leading-6 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        disabled={metricEditorSaving}
                      />
                    </div>
                    <div>
                      <div className="mb-1 text-[11px] text-gray-500">年预测公式</div>
                      <textarea
                        value={metricDraft.formula_forecast_annual}
                        onChange={(e) => setMetricDraft((prev) => ({ ...prev, formula_forecast_annual: e.target.value }))}
                        rows={3}
                        className="w-full rounded border border-gray-300 px-3 py-2 text-xs font-mono leading-6 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        disabled={metricEditorSaving}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="rounded border border-dashed border-gray-300 bg-gray-50 px-3 py-4 text-xs text-gray-500">
                  请先在指标表中选择一个指标，然后点击指标名称右侧的小按钮打开维护窗口。
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-gray-200 bg-gray-50 px-4 py-3">
              <button
                type="button"
                className={neutralActionClass}
                onClick={() => setMetricEditorOpen(false)}
                disabled={metricEditorSaving}
              >
                <span>取消</span>
              </button>
              <button type="button" onClick={saveMetric} className={primaryActionClass} disabled={!activeMetric || metricEditorSaving}>
                <Save className="h-3.5 w-3.5" />
                <span>{metricEditorSaving ? "保存中..." : "保存当前指标"}</span>
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {catalogManagerOpen && activeCatalogScope
        ? createPortal(
            <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 p-4">
              <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-lg border border-gray-300 bg-white shadow-xl">
                <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
                  <div>
                    <div className="text-sm font-semibold text-gray-800">管理指标表</div>
                    <div className="mt-0.5 text-[11px] text-gray-500">
                      范围：{activeCatalogScope}
                      {activeCatalogScope === "AA"
                        ? "（微众银行及 AA 级配置）"
                        : activeCatalogScope === "AB"
                          ? "（微众科技）"
                          : "（各机构/产品共用）"}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 items-center justify-center rounded border border-gray-200 text-gray-600 hover:bg-gray-50"
                    onClick={() => setCatalogManagerOpen(false)}
                    aria-label="关闭"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="overflow-auto px-4 py-3">
                  <div className="mb-3 flex gap-2">
                    <input
                      value={catalogDraftName}
                      onChange={(e) => setCatalogDraftName(e.target.value)}
                      placeholder="新指标表名称，如 流动性表"
                      className="min-w-0 flex-1 rounded border border-gray-300 px-2 py-1.5 text-xs"
                      disabled={catalogBusy}
                    />
                    <button
                      type="button"
                      className={primaryActionClass}
                      onClick={() => void handleAddCatalogTable()}
                      disabled={catalogBusy}
                    >
                      新增
                    </button>
                  </div>
                  <div className="space-y-2">
                    {activeScopeCatalogRows.length === 0 ? (
                      <div className="rounded border border-dashed border-gray-300 px-3 py-4 text-xs text-gray-500">
                        暂无目录项，可上方新增。
                      </div>
                    ) : (
                      activeScopeCatalogRows.map((row) => (
                        <div
                          key={row.id}
                          className="flex flex-wrap items-center gap-2 rounded border border-gray-200 bg-gray-50 px-2 py-2 text-xs"
                        >
                          <span
                            className={`min-w-0 flex-1 font-medium ${
                              row.status === "inactive" ? "text-gray-400 line-through" : "text-gray-800"
                            }`}
                          >
                            {row.table_name}
                          </span>
                          <label className="inline-flex items-center gap-1 text-[11px] text-gray-600">
                            排序
                            <input
                              type="number"
                              defaultValue={row.sort_order}
                              className="w-14 rounded border border-gray-300 px-1 py-0.5 text-right"
                              disabled={catalogBusy}
                              onBlur={(e) => {
                                const next = Number(e.target.value);
                                if (Number.isFinite(next) && next !== row.sort_order) {
                                  void handleUpdateCatalogSortOrder(row, next);
                                }
                              }}
                            />
                          </label>
                          <button
                            type="button"
                            className={`rounded border px-2 py-0.5 text-[11px] ${
                              row.status === "active"
                                ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100"
                                : "border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                            }`}
                            disabled={catalogBusy}
                            onClick={() => void handleToggleCatalogStatus(row)}
                          >
                            {row.status === "active" ? "停用" : "启用"}
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                  <p className="mt-3 text-[11px] leading-relaxed text-gray-500">
                    停用后页签与 Excel 导入匹配将隐藏该表；已保存科目数据保留，重新启用后可继续编辑。
                  </p>
                </div>
                <div className="flex justify-end border-t border-gray-200 px-4 py-3">
                  <button
                    type="button"
                    className={neutralActionClass}
                    onClick={() => setCatalogManagerOpen(false)}
                  >
                    关闭
                  </button>
                </div>
              </div>
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
