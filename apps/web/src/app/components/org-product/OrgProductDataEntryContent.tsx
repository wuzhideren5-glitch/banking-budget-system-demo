import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ChevronDown, ChevronRight, Database, Download, RefreshCw, Search, Upload, X } from "lucide-react";
import {
  getOrgProductDataEntrySnapshot,
  saveRefreshOrgProductDataEntry,
  exportOrgProductDataEntry,
  exportOrgProductDataEntryBatch,
  previewDataEntryBudgetSync,
  applyDataEntryBudgetSync,
  importDataEntryWorkbook,
  applyDataEntryWorkbookImport,
  type DataEntryBatchExportItem,
} from "@/lib/org-product/orgProductDataEntryApi";
import { getOrgProductTreeSnapshot } from "@/lib/org-product/orgProductTreeApi";
import { getOrgProductMetricSnapshot, getMetricTableCatalog } from "@/lib/org-product/orgProductMetricApi";
import { PILOT_ENTITY_CODE, PILOT_TABLE_NAME, pickPilotEntityCode, pickPilotTableName } from "@/lib/org-product/orgProductPilot";
import {
  cloneDefaultOrgProductTree,
  findOrgNodeByCode,
  findOrgNodePathByCode,
  metricTableNamesForOrgNode,
  prepareOrgProductTreeFromStorage,
  type MetricTableCatalogItem,
  type OrgProductNode,
} from "@/lib/org-product/orgProductTree";

function cloneDefaultOrgTree(): OrgProductNode {
  return cloneDefaultOrgProductTree();
}

function buildInitialExpanded(node: OrgProductNode): Record<string, boolean> {
  const expanded: Record<string, boolean> = {};
  const walk = (current: OrgProductNode) => {
    if (current.children.length > 0) expanded[current.id] = true;
    current.children.forEach(walk);
  };
  walk(node);
  return expanded;
}

type OrgProductTreeSnapshotDto =
  | { found: false }
  | { found: true; tree: OrgProductNode; updated_at: string };

type MetricNodePayload = {
  id: string;
  levelLabel: string;
  nature: string;
  code: string;
  name: string;
  children?: MetricNodePayload[];
};

type MetricTablePayload = {
  id: string;
  name: string;
  metrics: MetricNodePayload[];
};

type OrgProductMetricSnapshotDto = {
  entities: { entity_code: string; entity_name: string; tables: MetricTablePayload[] }[];
};

type DataEntryValues = {
  prev_actual: string;
  prev_budget: string;
  prev_forecast: string;
  year_forecast: string;
  months: Record<string, string>;
};

type DataEntryRow = {
  metric_id: string;
  metric_code: string;
  metric_name: string;
  displayCode: string;
  displayName: string;
  levelLabel: string;
  nature: string;
  depth: number;
  values: DataEntryValues;
};

const METRIC_LEVEL_OPTIONS = ["一级", "二级", "三级", "四级", "五级", "六级"] as const;

type DataEntrySnapshotDto =
  | { found: false }
  | {
      found: true;
      payload: {
        metrics?: DataEntryRow[];
        entry_status?: string;
        version_name?: string;
      };
      updated_at: string;
    };

type ImportWorkbookSheetDto = {
  sheet_name: string;
  entity_code: string;
  table_name: string;
  matched: boolean;
  row_count: number;
  metrics: Array<{
    metric_code: string;
    metric_name: string;
    levelLabel: string;
    nature: string;
    values: DataEntryValues;
  }>;
};

type ImportWorkbookResponseDto = {
  sheets: ImportWorkbookSheetDto[];
  sheet_count: number;
};

type OrgProductBudgetSyncResponseDto = {
  candidate_rows: number;
  writable_cells: number;
  legacy_confirmed_rows?: number;
  unbound_rows: number;
  non_confirmed_rows: number;
  empty_rows: number;
  skipped_cells: number;
  warnings?: string[];
  ok?: boolean;
  saved_cells?: number;
  affected_products?: string[];
  written_data_accts?: string[];
  summary_rows?: number;
  budget_aggregate_rows?: number;
  errors?: string[];
};

type DataColumn = {
  key: string;
  label: string;
  /** 全年预测列：由 1-M 月实际 + (M+1)-12 月预测汇总，只读 */
  computed?: boolean;
};

const BASE_YEAR = 2026;
const YEAR_RANGE = 5;
const VERSION_SLOTS = 10;
const ORG_PRODUCT_TREE_SAVED_EVENT = "org-product-tree-saved";
const ORG_PRODUCT_METRICS_SAVED_EVENT = "org-product-metrics-saved";

const DEFAULT_METRIC_TABLE_NAME = "业务状况表";

/** 与「机构及产品」「机构及产品指标」一致的工具栏样式 */
const primaryActionClass =
  "inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-sky-500 to-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:from-sky-600 hover:to-blue-700 disabled:opacity-50";
const secondaryActionClass =
  "inline-flex items-center gap-1.5 rounded-md bg-gradient-to-r from-emerald-500 to-teal-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:from-emerald-600 hover:to-teal-700 disabled:opacity-50";
const neutralActionClass =
  "inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm transition hover:bg-gray-50 disabled:opacity-50";
const entryToolbarBtn = "px-2.5 py-1";
const entryLabelClass = "shrink-0 pt-1 text-[11px] font-medium text-gray-700";
const entryControlClass =
  "min-h-[30px] rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-800 shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-500";
const entrySelectClass = `${entryControlClass} cursor-pointer`;
const entryInputClass = `${entryControlClass} placeholder:text-gray-400`;
const entryEntityPickerClass =
  "flex min-h-[30px] w-full items-center justify-between gap-2 rounded border border-gray-300 bg-white px-2 py-1 text-left text-xs shadow-sm transition hover:border-blue-300";

function emptyValues(): DataEntryValues {
  return { prev_actual: "", prev_budget: "", prev_forecast: "", year_forecast: "", months: {} };
}

function cloneValues(v: DataEntryValues): DataEntryValues {
  return { ...v, months: { ...v.months } };
}

function buildVersionOptions(year: number, month: number): string[] {
  const prefix = `${year}${String(month).padStart(2, "0")}`;
  return Array.from({ length: VERSION_SLOTS }, (_, i) => `${prefix}v${i + 1}`);
}

function versionNameToId(name: string): number {
  const m = /v(\d+)$/i.exec(name.trim());
  if (m) {
    const n = Number.parseInt(m[1], 10);
    if (Number.isFinite(n) && n >= 1 && n <= VERSION_SLOTS) return n;
  }
  return 1;
}

/**
 * 滚动预测列：选 Y 年 M 月时，展示 Y 年 1..M 月实际、(M+1)..12 月预测，及 Y 年全年预测（汇总列）。
 */
function buildDataColumns(year: number, forecastMonth: number): DataColumn[] {
  const prevYy = (year - 1) % 100;
  const yy = year % 100;
  const m = Math.min(12, Math.max(1, forecastMonth));
  const cols: DataColumn[] = [
    { key: "prev_actual", label: `${prevYy}年实际` },
    { key: "prev_budget", label: `${yy}年预算` },
    { key: "prev_forecast", label: `${yy}年预测`, computed: true },
  ];
  for (let month = 1; month <= m; month++) {
    cols.push({ key: `a${month}`, label: `${yy}年${month}月实际` });
  }
  for (let month = m + 1; month <= 12; month++) {
    cols.push({ key: `f${month}`, label: `${yy}年${month}月预测` });
  }
  return cols;
}

/** 列宽：至少容纳表头；单元格内容更长时再自动加宽 */
const DATA_CELL_WIDTH_MAX = 168;
const HEADER_CHAR_PX = 11;
const HEADER_PAD_PX = 20;
const CELL_CHAR_PX = 7.5;
const CELL_PAD_PX = 14;

function estimateHeaderWidthPx(label: string): number {
  const len = String(label ?? "").length;
  return Math.ceil(len * HEADER_CHAR_PX + HEADER_PAD_PX);
}

function estimateCellContentWidthPx(cellTexts: string[]): number {
  let maxLen = 0;
  for (const raw of cellTexts) {
    const t = String(raw ?? "").trim();
    if (t) maxLen = Math.max(maxLen, t.length);
  }
  if (!maxLen) return 0;
  return Math.ceil(maxLen * CELL_CHAR_PX + CELL_PAD_PX);
}

function measureDataColumnWidth(label: string, cellTexts: string[]): number {
  const headerW = estimateHeaderWidthPx(label);
  const contentW = estimateCellContentWidthPx(cellTexts);
  if (contentW <= headerW) return headerW;
  return Math.min(DATA_CELL_WIDTH_MAX, Math.max(headerW, contentW));
}

function buildDataColumnWidths(columns: DataColumn[], tableRows: DataEntryRow[]): Record<string, number> {
  const widths: Record<string, number> = {};
  for (const col of columns) {
    const texts = tableRows.map((r) => getCellValue(r.values, col.key));
    widths[col.key] = measureDataColumnWidth(col.label, texts);
  }
  return widths;
}

function dataColWidthStyle(width: number): CSSProperties {
  return { width, minWidth: width, maxWidth: width };
}

function parseAmountText(raw: string): number | null {
  const text = String(raw ?? "").trim();
  if (!text) return null;
  const normalized = text.replace(/,/g, "").replace(/，/g, "").replace(/%/g, "").replace(/％/g, "");
  const n = Number(normalized);
  if (!Number.isFinite(n)) return null;
  if (/%|％/.test(text)) return n / 100;
  return n;
}

/** 全年预测 = 当年 1..M 月实际之和 + (M+1)..12 月预测之和 */
function computeYearForecastValue(values: DataEntryValues, forecastMonth: number): string {
  const m = Math.min(12, Math.max(1, forecastMonth));
  let sum = 0;
  let hasAny = false;
  for (let month = 1; month <= m; month++) {
    const v = parseAmountText(values.months[`a${month}`] ?? "");
    if (v !== null) {
      sum += v;
      hasAny = true;
    }
  }
  for (let month = m + 1; month <= 12; month++) {
    const v = parseAmountText(values.months[`f${month}`] ?? "");
    if (v !== null) {
      sum += v;
      hasAny = true;
    }
  }
  if (!hasAny) return "";
  const rounded = Math.round(sum * 1e6) / 1e6;
  return String(rounded);
}

/** 滚动窗口外月份清空：不展示 M+1..12 实际、1..M 月预测 */
function sanitizeRollingMonthValues(values: DataEntryValues, forecastMonth: number): DataEntryValues {
  const m = Math.min(12, Math.max(1, forecastMonth));
  const next = cloneValues(values);
  const months = { ...next.months };
  for (let month = 1; month <= 12; month++) {
    if (month > m) delete months[`a${month}`];
    if (month <= m) delete months[`f${month}`];
  }
  next.months = months;
  return next;
}

function applyRollingForecastLogic(values: DataEntryValues, forecastMonth: number): DataEntryValues {
  const sanitized = sanitizeRollingMonthValues(values, forecastMonth);
  return { ...sanitized, prev_forecast: computeYearForecastValue(sanitized, forecastMonth) };
}

function isRollingDataColumnEditable(key: string, forecastMonth: number): boolean {
  if (key === "prev_forecast") return false;
  const m = Math.min(12, Math.max(1, forecastMonth));
  const ma = /^a(\d+)$/.exec(key);
  if (ma) {
    const month = Number(ma[1]);
    return month >= 1 && month <= m;
  }
  const mf = /^f(\d+)$/.exec(key);
  if (mf) {
    const month = Number(mf[1]);
    return month > m && month <= 12;
  }
  return true;
}

function normalizeImportMetricCode(entityCode: string, rawCode: string): string {
  const owner = String(entityCode || "").trim().toUpperCase();
  const cleaned = String(rawCode || "")
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

function buildImportMetricLookup(
  imported: ImportWorkbookSheetDto["metrics"],
  entityCode: string
): Map<string, ImportWorkbookSheetDto["metrics"][number]> {
  const map = new Map<string, ImportWorkbookSheetDto["metrics"][number]>();
  for (const item of imported) {
    const raw = String(item.metric_code || "").trim().toUpperCase();
    const canon = normalizeImportMetricCode(entityCode, item.metric_code);
    if (raw) map.set(raw, item);
    if (raw.replace(/\./g, "")) map.set(raw.replace(/\./g, ""), item);
    if (canon) map.set(canon, item);
  }
  return map;
}

function resolveImportMetricRow(
  row: DataEntryRow,
  lookup: Map<string, ImportWorkbookSheetDto["metrics"][number]>,
  entityCode: string
): ImportWorkbookSheetDto["metrics"][number] | undefined {
  const keys = [
    row.metric_code,
    normalizeImportMetricCode(entityCode, row.metric_code),
    row.metric_code.replace(/\./g, ""),
  ];
  for (const k of keys) {
    const hit = lookup.get(String(k || "").trim().toUpperCase());
    if (hit) return hit;
  }
  return undefined;
}

function getCellValue(values: DataEntryValues, key: string): string {
  if (key === "prev_actual") return values.prev_actual;
  if (key === "prev_budget") return values.prev_budget;
  if (key === "prev_forecast") return values.prev_forecast;
  if (key === "year_forecast") return values.year_forecast;
  return values.months[key] ?? "";
}

function setCellValue(values: DataEntryValues, key: string, raw: string): DataEntryValues {
  const next = cloneValues(values);
  if (key === "prev_actual") next.prev_actual = raw;
  else if (key === "prev_budget") next.prev_budget = raw;
  else if (key === "prev_forecast") next.prev_forecast = raw;
  else if (key === "year_forecast") next.year_forecast = raw;
  else next.months[key] = raw;
  return next;
}

function flattenMetricForest(nodes: MetricNodePayload[]): MetricNodePayload[] {
  const out: MetricNodePayload[] = [];
  const walk = (n: MetricNodePayload) => {
    out.push(n);
    (n.children ?? []).forEach(walk);
  };
  nodes.forEach(walk);
  return out;
}

/** 与 OrgProductMetricContent.formatMetricCodeForDisplay 一致：AA0101 → AA.01.01 */
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

function metricLevelIndex(levelLabel: string): number {
  const idx = METRIC_LEVEL_OPTIONS.indexOf(levelLabel as (typeof METRIC_LEVEL_OPTIONS)[number]);
  return idx >= 0 ? idx : 0;
}

function buildIndentedMetricName(levelLabel: string, name: string): string {
  const levelIndex = metricLevelIndex(levelLabel);
  return `${" ".repeat(levelIndex * 2)}${name}`;
}

function collectFlatMetricRows(
  nodes: MetricNodePayload[],
  depth = 0
): Array<MetricNodePayload & { depth: number }> {
  return nodes.flatMap((node) => [
    { ...node, depth },
    ...collectFlatMetricRows(node.children ?? [], depth + 1),
  ]);
}

function metricRowToneClass(levelLabel: string): string {
  if (levelLabel === "一级") return "bg-slate-50/80";
  if (levelLabel === "二级") return "bg-blue-50/50";
  return "";
}

function isPrimaryMetricLevel(levelLabel: string): boolean {
  return levelLabel === "一级" || levelLabel === "二级";
}

/** 左侧冻结列（类似 Excel 冻结窗格）：层级 / 性质 / 代码 / 名称 */
const ENTRY_FROZEN_COLUMN_WIDTHS = [
  { label: "科目层级", width: 60 },
  { label: "科目性质", width: 56 },
  { label: "科目代码", width: 108 },
  { label: "科目名称", width: 188 },
] as const;

const ENTRY_FROZEN_COLUMNS = ENTRY_FROZEN_COLUMN_WIDTHS.map((col, idx) => ({
  ...col,
  left: ENTRY_FROZEN_COLUMN_WIDTHS.slice(0, idx).reduce((sum, c) => sum + c.width, 0),
}));

function frozenColBoxStyle(left: number, width: number): CSSProperties {
  return { left, width, minWidth: width, maxWidth: width };
}

function frozenHeaderThClass(isLastFrozen: boolean): string {
  return [
    "sticky top-0 z-40 border border-gray-200 bg-slate-100 px-1.5 py-1.5 text-left text-[11px] font-semibold text-slate-700 whitespace-nowrap",
    isLastFrozen ? "shadow-[4px_0_10px_-4px_rgba(15,23,42,0.2)]" : "",
  ].join(" ");
}

function frozenBodyTdClass(levelLabel: string, isLastFrozen: boolean): string {
  const rowBg =
    levelLabel === "一级"
      ? "bg-slate-50 group-hover:bg-slate-100"
      : levelLabel === "二级"
        ? "bg-blue-50/90 group-hover:bg-blue-100/80"
        : "bg-white group-hover:bg-gray-50";
  return [
    "sticky left-0 z-20 border border-gray-200 px-1.5 py-1",
    rowBg,
    isLastFrozen ? "shadow-[4px_0_10px_-4px_rgba(15,23,42,0.14)]" : "",
  ].join(" ");
}

function scrollableHeaderThClass(): string {
  return "sticky top-0 z-30 border border-gray-200 bg-slate-100 px-2 py-2 text-right text-[11px] font-semibold text-slate-700 whitespace-nowrap shadow-[0_3px_6px_-2px_rgba(15,23,42,0.12)]";
}

function canonicalTableNamesForEntity(
  tree: OrgProductNode | null,
  entityCode: string,
  catalog?: MetricTableCatalogItem[] | null
): string[] {
  const code = entityCode.trim();
  if (!code) return [];
  const node = findOrgNodeByCode(tree, entityCode);
  const names = metricTableNamesForOrgNode(node, catalog);
  if (names.length) return [...names];
  if (code === PILOT_ENTITY_CODE) return [PILOT_TABLE_NAME, DEFAULT_METRIC_TABLE_NAME];
  if (node?.type === "level1" && code === "AB") return [DEFAULT_METRIC_TABLE_NAME, "损益表"];
  return [DEFAULT_METRIC_TABLE_NAME];
}

function getMetricTableForEntity(
  snapshot: OrgProductMetricSnapshotDto | null,
  entityCode: string,
  tableName: string
): MetricTablePayload {
  const tn = tableName.trim();
  const hit = snapshot?.entities.find((e) => e.entity_code === entityCode.trim());
  const table = (hit?.tables ?? []).find((t) => (t.name || "").trim() === tn);
  if (table) return table;
  return { id: `table-${tn}`, name: tn, metrics: [] };
}

function tableNamesForEntity(
  tree: OrgProductNode | null,
  snapshot: OrgProductMetricSnapshotDto | null,
  entityCode: string,
  catalog?: MetricTableCatalogItem[] | null
): string[] {
  const canonical = canonicalTableNamesForEntity(tree, entityCode, catalog);
  const code = entityCode.trim();
  if (!code) return [];
  const hit = snapshot?.entities.find((e) => e.entity_code === code);
  const canonicalSet = new Set<string>(canonical);
  const extra = (hit?.tables ?? [])
    .map((t) => (t.name || "").trim())
    .filter((name) => name && !canonicalSet.has(name) && name.endsWith("表"));
  return [...canonical, ...extra];
}

function entityHasMetricConfig(tree: OrgProductNode | null, snapshot: OrgProductMetricSnapshotDto | null, entityCode: string): boolean {
  const node = findOrgNodeByCode(tree, entityCode);
  if (!node) return false;
  if (node.type === "level0") return false;
  if (node.type === "level1") return true;
  return (snapshot?.entities ?? []).some((e) => e.entity_code === entityCode.trim());
}

function pickDefaultTableName(
  tree: OrgProductNode | null,
  snapshot: OrgProductMetricSnapshotDto | null,
  entityCode: string,
  prior: string,
  catalog?: MetricTableCatalogItem[] | null
): string {
  const all = tableNamesForEntity(tree, snapshot, entityCode, catalog);
  if (!all.length) return entityCode === PILOT_ENTITY_CODE ? PILOT_TABLE_NAME : "";
  if (entityCode === PILOT_ENTITY_CODE) return pickPilotTableName(all, prior);
  const trimmed = prior.trim();
  if (trimmed && all.includes(trimmed)) return trimmed;
  return all[0];
}

function resolveEntityName(
  tree: OrgProductNode | null,
  snapshot: OrgProductMetricSnapshotDto | null,
  entityCode: string
): string {
  const node = findOrgNodeByCode(tree, entityCode);
  if (node?.name) return node.name;
  const hit = snapshot?.entities.find((e) => e.entity_code === entityCode);
  return hit?.entity_name ?? "";
}

function buildBatchExportItems(
  tree: OrgProductNode | null,
  snapshot: OrgProductMetricSnapshotDto | null,
  catalog: MetricTableCatalogItem[],
  selectedEntityCodes: string[],
  selectedTableNames: string[]
): DataEntryBatchExportItem[] {
  const items: DataEntryBatchExportItem[] = [];
  const seen = new Set<string>();
  for (const code of selectedEntityCodes) {
    const entityCode = code.trim();
    if (!entityCode) continue;
    const tables = tableNamesForEntity(tree, snapshot, entityCode, catalog);
    for (const tableName of selectedTableNames) {
      const tn = tableName.trim();
      if (!tn || !tables.includes(tn)) continue;
      const key = `${entityCode}::${tn}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({
        entity_code: entityCode,
        entity_name: resolveEntityName(tree, snapshot, entityCode),
        table_name: tn,
      });
    }
  }
  return items;
}

function getMetricForestForEntity(
  snapshot: OrgProductMetricSnapshotDto | null,
  entityCode: string,
  tableName: string
): MetricNodePayload[] {
  const code = entityCode.trim();
  const tn = tableName.trim();
  if (!code || !tn) return [];
  return getMetricTableForEntity(snapshot, code, tn).metrics ?? [];
}

function formatOrgNodeSegment(node: OrgProductNode): string {
  return `${node.code} ${node.name}`.trim();
}

/** 选择框展示：三级产品不显示一级主体，仅上级机构 + 产品，如 A 个金群 / A01 泛微粒贷 */
function formatEntityDisplayLabel(root: OrgProductNode | null, code: string): string {
  const path = findOrgNodePathByCode(root, code);
  if (!path.length) return code || "请选择机构或产品";
  const node = path[path.length - 1];
  if (node.type === "level3") {
    const displayPath = path.filter((n) => n.type !== "level0");
    return displayPath.map(formatOrgNodeSegment).join(" / ");
  }
  if (node.type === "level2") {
    return formatOrgNodeSegment(node);
  }
  return formatOrgNodeSegment(node);
}

function findFirstEntityCodeWithConfig(root: OrgProductNode, tree: OrgProductNode, snapshot: OrgProductMetricSnapshotDto | null): string {
  if (entityHasMetricConfig(tree, snapshot, root.code.trim())) return root.code;
  for (const child of root.children) {
    const hit = findFirstEntityCodeWithConfig(child, tree, snapshot);
    if (hit) return hit;
  }
  return "";
}

function pickDefaultEntityCode(
  tree: OrgProductNode,
  snapshot: OrgProductMetricSnapshotDto | null,
  prior: string
): string {
  const configured = (snapshot?.entities ?? [])
    .map((e) => e.entity_code)
    .filter((code) => entityHasMetricConfig(tree, snapshot, code));
  const fromTree = findFirstEntityCodeWithConfig(tree, tree, snapshot);
  const fallback = configured[0] ?? fromTree ?? tree.code;
  return pickPilotEntityCode(configured, prior, fallback);
}

function splitSearchKeywords(raw: string): string[] {
  return raw
    .toLowerCase()
    .split(/[\s,，;；/\\]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function filterOrgProductTree(root: OrgProductNode, query: string): OrgProductNode | null {
  const keywords = splitSearchKeywords(query);
  if (!keywords.length) return root;
  const nodeText = `${root.code} ${root.name}`.toLowerCase();
  const selfHit = keywords.some((kw) => nodeText.includes(kw));
  const kids = root.children
    .map((c) => filterOrgProductTree(c, query))
    .filter((x): x is OrgProductNode => Boolean(x));
  if (selfHit || kids.length) return { ...root, children: kids };
  return null;
}

function buildRowsFromMetrics(
  metrics: MetricNodePayload[],
  saved: DataEntryRow[],
  entityCode: string,
  forecastMonth: number
): DataEntryRow[] {
  const savedByCode = new Map(saved.map((r) => [r.metric_code || r.metric_id, r]));
  return collectFlatMetricRows(metrics).map((m) => {
    const hit = savedByCode.get(m.code) ?? savedByCode.get(m.id);
    const base = hit?.values ? cloneValues(hit.values) : emptyValues();
    return {
      metric_id: m.id,
      metric_code: m.code,
      metric_name: m.name,
      displayCode: formatMetricCodeForDisplay(entityCode, m.code),
      displayName: buildIndentedMetricName(m.levelLabel, m.name),
      levelLabel: m.levelLabel,
      nature: m.nature,
      depth: m.depth,
      values: applyRollingForecastLogic(base, forecastMonth),
    };
  });
}

function mergeImportedMetrics(
  rows: DataEntryRow[],
  imported: ImportWorkbookSheetDto["metrics"],
  entityCode: string,
  forecastMonth: number
): DataEntryRow[] {
  const lookup = buildImportMetricLookup(imported, entityCode);
  return rows.map((row) => {
    const hit = resolveImportMetricRow(row, lookup, entityCode);
    if (!hit?.values) return { ...row, values: applyRollingForecastLogic(row.values, forecastMonth) };
    const merged = cloneValues(row.values);
    const iv = hit.values;
    if (iv.prev_actual) merged.prev_actual = iv.prev_actual;
    if (iv.prev_budget) merged.prev_budget = iv.prev_budget;
    for (const [k, v] of Object.entries(iv.months ?? {})) {
      if (v && isRollingDataColumnEditable(k, forecastMonth)) merged.months[k] = v;
    }
    return { ...row, values: applyRollingForecastLogic(merged, forecastMonth) };
  });
}

export function OrgProductDataEntryContent() {
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [batchExporting, setBatchExporting] = useState(false);
  const [batchImporting, setBatchImporting] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [batchSelectedEntities, setBatchSelectedEntities] = useState<string[]>([]);
  const [batchSelectedTables, setBatchSelectedTables] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [tree, setTree] = useState<OrgProductNode | null>(null);
  const [metricSnapshot, setMetricSnapshot] = useState<OrgProductMetricSnapshotDto | null>(null);
  const [metricTableCatalog, setMetricTableCatalog] = useState<MetricTableCatalogItem[]>([]);

  const [selectedYear, setSelectedYear] = useState(BASE_YEAR);
  const [selectedMonth, setSelectedMonth] = useState(3);
  const [selectedVersionName, setSelectedVersionName] = useState("");
  const [versionConfirmed, setVersionConfirmed] = useState(false);

  const [selectedEntityCode, setSelectedEntityCode] = useState("");
  const [selectedTableName, setSelectedTableName] = useState("");
  const [subjectSearch, setSubjectSearch] = useState("");
  const [rows, setRows] = useState<DataEntryRow[]>([]);

  const [orgDropdownOpen, setOrgDropdownOpen] = useState(false);
  const [orgExpanded, setOrgExpanded] = useState<Record<string, boolean>>({});
  const [orgSearchInput, setOrgSearchInput] = useState("");
  const orgDialogRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const skipSnapshotLoadRef = useRef(false);
  const selectionRef = useRef({ entityCode: "", tableName: "" });

  useEffect(() => {
    selectionRef.current = { entityCode: selectedEntityCode, tableName: selectedTableName };
  }, [selectedEntityCode, selectedTableName]);

  const yearOptions = useMemo(
    () => Array.from({ length: YEAR_RANGE * 2 + 1 }, (_, i) => BASE_YEAR - YEAR_RANGE + i),
    []
  );
  const versionOptions = useMemo(
    () => buildVersionOptions(selectedYear, selectedMonth),
    [selectedYear, selectedMonth]
  );
  const dataColumns = useMemo(
    () => buildDataColumns(selectedYear, selectedMonth),
    [selectedYear, selectedMonth]
  );

  const selectedEntityLabel = useMemo(
    () => formatEntityDisplayLabel(tree, selectedEntityCode),
    [tree, selectedEntityCode]
  );

  const entityCodesWithMetrics = useMemo(() => {
    const set = new Set<string>();
    for (const e of metricSnapshot?.entities ?? []) {
      const code = (e.entity_code || "").trim();
      if (code && entityHasMetricConfig(tree, metricSnapshot, code)) set.add(code);
    }
    return set;
  }, [metricSnapshot, tree]);

  const visibleOrgTree = useMemo(() => {
    if (!tree) return null;
    if (!orgSearchInput.trim()) return tree;
    return filterOrgProductTree(tree, orgSearchInput);
  }, [tree, orgSearchInput]);

  const tablesForEntity = useMemo(
    () => tableNamesForEntity(tree, metricSnapshot, selectedEntityCode, metricTableCatalog),
    [tree, metricSnapshot, selectedEntityCode, metricTableCatalog]
  );

  const batchTableOptions = useMemo(() => {
    const names = new Set<string>();
    for (const code of batchSelectedEntities) {
      for (const tn of tableNamesForEntity(tree, metricSnapshot, code, metricTableCatalog)) {
        if (tn) names.add(tn);
      }
    }
    return [...names];
  }, [batchSelectedEntities, tree, metricSnapshot, metricTableCatalog]);

  const batchExportItems = useMemo(
    () =>
      buildBatchExportItems(
        tree,
        metricSnapshot,
        metricTableCatalog,
        batchSelectedEntities,
        batchSelectedTables
      ),
    [tree, metricSnapshot, metricTableCatalog, batchSelectedEntities, batchSelectedTables]
  );

  const metricForest = useMemo(
    () => getMetricForestForEntity(metricSnapshot, selectedEntityCode, selectedTableName),
    [metricSnapshot, selectedEntityCode, selectedTableName]
  );

  const metricForestSignature = useMemo(
    () => flattenMetricForest(metricForest).map((m) => `${m.code}|${m.name}|${m.levelLabel}|${m.nature}`).join("\n"),
    [metricForest]
  );

  const filteredRows = useMemo(() => {
    const keywords = splitSearchKeywords(subjectSearch);
    if (!keywords.length) return rows;
    return rows.filter((r) => {
      const text = `${r.metric_code} ${r.displayCode} ${r.metric_name} ${r.displayName}`.toLowerCase();
      return keywords.some((kw) => text.includes(kw));
    });
  }, [rows, subjectSearch]);

  const dataColumnWidths = useMemo(
    () => buildDataColumnWidths(dataColumns, filteredRows),
    [dataColumns, filteredRows]
  );

  useEffect(() => {
    if (!batchMode) return;
    setBatchSelectedEntities((prev) => {
      if (prev.length) return prev;
      const code = selectedEntityCode.trim();
      return code ? [code] : [];
    });
    setBatchSelectedTables((prev) => {
      if (prev.length) return prev;
      const tn = selectedTableName.trim();
      return tn ? [tn] : [];
    });
  }, [batchMode, selectedEntityCode, selectedTableName]);

  useEffect(() => {
    if (!batchMode) return;
    setBatchSelectedTables((prev) => prev.filter((tn) => batchTableOptions.includes(tn)));
  }, [batchMode, batchTableOptions]);

  const toggleBatchEntity = (entityCode: string) => {
    const code = entityCode.trim();
    if (!code) return;
    setBatchSelectedEntities((prev) =>
      prev.includes(code) ? prev.filter((item) => item !== code) : [...prev, code]
    );
  };

  const toggleBatchTable = (tableName: string) => {
    const tn = tableName.trim();
    if (!tn) return;
    setBatchSelectedTables((prev) =>
      prev.includes(tn) ? prev.filter((item) => item !== tn) : [...prev, tn]
    );
  };

  const loadSnapshot = async (
    entityCode: string,
    year: number,
    versionId: number,
    tableName: string,
    metrics: MetricNodePayload[]
  ) => {
    try {
      const resp = await getOrgProductDataEntrySnapshot(
        entityCode,
        year,
        versionId,
        tableName
      ) as DataEntrySnapshotDto;
      if (resp.found && resp.payload) {
        const saved = (resp.payload.metrics ?? []) as DataEntryRow[];
        setRows(buildRowsFromMetrics(metrics, saved, entityCode, selectedMonth));
        setVersionConfirmed((resp.payload.entry_status ?? "") === "confirmed");
        return;
      }
    } catch {
      // ignore and init empty
    }
    setRows(buildRowsFromMetrics(metrics, [], entityCode, selectedMonth));
    setVersionConfirmed(false);
  };

  const applyCatalog = (
    resolvedTree: OrgProductNode,
    ms: OrgProductMetricSnapshotDto,
    catalog: MetricTableCatalogItem[],
    prior?: { entityCode?: string; tableName?: string }
  ) => {
    setTree(resolvedTree);
    setOrgExpanded(buildInitialExpanded(resolvedTree));
    setMetricSnapshot(ms);
    setMetricTableCatalog(catalog);
    const code = pickDefaultEntityCode(resolvedTree, ms, prior?.entityCode ?? "");
    const table = pickDefaultTableName(resolvedTree, ms, code, prior?.tableName ?? "", catalog);
    setSelectedEntityCode(code);
    setSelectedTableName(table);
  };

  const syncCatalog = async (opts?: { showFullLoading?: boolean; notifyMessage?: string }) => {
    if (opts?.showFullLoading) setLoading(true);
    else setSyncing(true);
    setError("");
    try {
      const [t, ms, catalogResp] = await Promise.all([
        (getOrgProductTreeSnapshot() as Promise<OrgProductTreeSnapshotDto>),
        (getOrgProductMetricSnapshot() as Promise<OrgProductMetricSnapshotDto>),
        (getMetricTableCatalog() as unknown as Promise<{ items: MetricTableCatalogItem[] }>),
      ]);
      let resolvedTree: OrgProductNode = cloneDefaultOrgTree();
      if ("found" in t && t.found && t.tree) {
        resolvedTree = prepareOrgProductTreeFromStorage(t.tree);
      }
      applyCatalog(resolvedTree, ms, catalogResp.items ?? [], selectionRef.current);
      if (opts?.notifyMessage) setMessage(opts.notifyMessage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "同步失败");
    } finally {
      if (opts?.showFullLoading) setLoading(false);
      else setSyncing(false);
    }
  };

  useEffect(() => {
    void syncCatalog({ showFullLoading: true });
  }, []);

  useEffect(() => {
    const onTreeSaved = () => {
      void syncCatalog({ notifyMessage: "已自动同步「机构及产品」最新机构树。" });
    };
    const onMetricsSaved = () => {
      void syncCatalog({ notifyMessage: "已自动同步「机构及产品指标」最新指标表与科目。" });
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void syncCatalog();
      }
    };
    window.addEventListener(ORG_PRODUCT_TREE_SAVED_EVENT, onTreeSaved);
    window.addEventListener(ORG_PRODUCT_METRICS_SAVED_EVENT, onMetricsSaved);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener(ORG_PRODUCT_TREE_SAVED_EVENT, onTreeSaved);
      window.removeEventListener(ORG_PRODUCT_METRICS_SAVED_EVENT, onMetricsSaved);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  useEffect(() => {
    const onDocMouseDown = (e: MouseEvent) => {
      const el = orgDialogRef.current;
      if (!el?.contains(e.target as Node)) setOrgDropdownOpen(false);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, []);

  useEffect(() => {
    const versions = buildVersionOptions(selectedYear, selectedMonth);
    if (!versions.includes(selectedVersionName)) {
      setSelectedVersionName(versions[0]);
    }
  }, [selectedYear, selectedMonth, selectedVersionName]);

  useEffect(() => {
    const code = selectedEntityCode.trim();
    if (!code || !metricSnapshot) return;
    const names = tableNamesForEntity(tree, metricSnapshot, code);
    if (!names.length) return;
    setSelectedTableName((prev) => (names.includes(prev) ? prev : pickDefaultTableName(tree, metricSnapshot, code, prev)));
  }, [selectedEntityCode, metricSnapshot, tablesForEntity, tree]);

  useEffect(() => {
    if (skipSnapshotLoadRef.current) {
      skipSnapshotLoadRef.current = false;
      return;
    }
    const code = selectedEntityCode.trim();
    const tn = selectedTableName.trim();
    if (!code || !tn) {
      setRows([]);
      return;
    }
    const versionId = versionNameToId(selectedVersionName);
    const forest = getMetricForestForEntity(metricSnapshot, code, tn);
    void loadSnapshot(code, selectedYear, versionId, tn, forest);
  }, [
    selectedEntityCode,
    selectedTableName,
    selectedYear,
    selectedVersionName,
    metricForestSignature,
    metricSnapshot,
  ]);

  const buildSavePayload = (status: "draft" | "confirmed") => {
    const code = selectedEntityCode.trim();
    return {
      entity_code: code,
      entity_name: resolveEntityName(tree, metricSnapshot, code),
      year: selectedYear,
      month_index: selectedMonth,
      version_id: versionNameToId(selectedVersionName),
      version_name: selectedVersionName,
      table_name: selectedTableName,
      entry_status: status,
      metrics: rows.map((r) => ({
        metric_id: r.metric_id,
        metric_code: r.metric_code,
        metric_name: r.metric_name,
        levelLabel: r.levelLabel,
        nature: r.nature,
        values: r.values,
      })),
    };
  };

  const saveRefresh = async (status: "draft" | "confirmed" = "draft"): Promise<boolean> => {
    const code = selectedEntityCode.trim();
    const tn = selectedTableName.trim();
    if (!code) {
      setError("请选择机构或产品");
      return false;
    }
    if (!tn) {
      setError("请选择指标表");
      return false;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await saveRefreshOrgProductDataEntry(buildSavePayload(status));
      setMessage(status === "confirmed" ? "版本已确认，正在准备写入预算事实。" : "数据已保存。");
      if (status === "confirmed") setVersionConfirmed(true);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
      return false;
    } finally {
      setSaving(false);
    }
  };

  const syncBudgetFacts = async (opts?: { requireConfirmed?: boolean; afterConfirm?: boolean }) => {
    const code = selectedEntityCode.trim();
    const tn = selectedTableName.trim();
    const requireConfirmed = opts?.requireConfirmed ?? true;
    if (!code) {
      setError("请选择机构或产品");
      return;
    }
    if (!tn) {
      setError("请选择指标表");
      return;
    }
    if (requireConfirmed && !versionConfirmed) {
      setError("请先完成版本确认");
      return;
    }
    const request = {
      entity_code: code,
      year: selectedYear,
      table_name: tn,
      entry_version_id: versionNameToId(selectedVersionName),
      budget_version_id: versionNameToId(selectedVersionName),
      budget_actuals: [1, 0],
    };
    setSyncing(true);
    setError("");
    setMessage("");
    try {
      const preview = await (previewDataEntryBudgetSync(
        request
      ) as unknown as Promise<OrgProductBudgetSyncResponseDto>);
      if (!preview.writable_cells) {
        setMessage(
          `无可写入预算事实单元格；已确认但未写入 ${preview.legacy_confirmed_rows ?? 0} 行，未绑定 ${preview.unbound_rows} 行，未确认 ${preview.non_confirmed_rows} 行，已跳过 ${preview.skipped_cells} 个单元格。`
        );
        return;
      }
      const ok = window.confirm(
        `${opts?.afterConfirm ? "版本已确认。" : ""}将把当前机构产品录入版本写入预算事实：可写 ${preview.writable_cells} 个单元格，已跳过 ${preview.skipped_cells} 个单元格。是否继续？`
      );
      if (!ok) return;
      const resp = await (applyDataEntryBudgetSync(
        request
      ) as unknown as Promise<OrgProductBudgetSyncResponseDto>);
      setMessage(
        `已写入预算事实：写入 ${resp.saved_cells ?? 0} 个单元格，刷新汇总 ${resp.summary_rows ?? 0} 行、透视聚合 ${resp.budget_aggregate_rows ?? 0} 行；已确认但未写入 ${resp.legacy_confirmed_rows ?? 0} 行，未绑定 ${resp.unbound_rows} 行，未确认 ${resp.non_confirmed_rows} 行，跳过 ${resp.skipped_cells} 个单元格。`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "写入预算事实失败");
    } finally {
      setSyncing(false);
    }
  };

  const exportBatchTemplate = async () => {
    if (!batchExportItems.length) {
      setError("请先在批量模式下选择至少一个机构/产品和一个指标表。");
      return;
    }
    setBatchExporting(true);
    setError("");
    setMessage("");
    try {
      const { blob, filename } = await exportOrgProductDataEntryBatch({
        year: selectedYear,
        month_index: selectedMonth,
        items: batchExportItems,
        include_saved_values: false,
        version_id: versionNameToId(selectedVersionName),
        version_name: selectedVersionName,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `机构产品数据录入批量模板_${selectedYear}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMessage(`已开始下载批量模板，共 ${batchExportItems.length} 个工作表。`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "批量导出失败");
    } finally {
      setBatchExporting(false);
    }
  };

  const exportCurrent = async () => {
    const code = selectedEntityCode.trim();
    const tn = selectedTableName.trim();
    if (!code) {
      setError("请选择机构或产品");
      return;
    }
    if (!tn) {
      setError("请选择指标表");
      return;
    }
    setExporting(true);
    setError("");
    setMessage("");
    try {
      const { blob, filename } = await exportOrgProductDataEntry(buildSavePayload("draft"));
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `机构产品数据录入_${code}_${selectedYear}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMessage("已开始下载数据录入底稿。");
    } catch (e) {
      setError(e instanceof Error ? e.message : "导出失败");
    } finally {
      setExporting(false);
    }
  };

  const confirmVersion = async () => {
    const saved = await saveRefresh("confirmed");
    if (saved) {
      await syncBudgetFacts({ requireConfirmed: false, afterConfirm: true });
    }
  };

  const modifyVersion = () => {
    setVersionConfirmed(false);
    setMessage("已进入修改模式，编辑后请再次点击「确认并写入预算事实」。");
  };

  const onExcelSelected = async (file: File | null) => {
    if (!file) return;
    setError("");
    setMessage("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (batchMode) {
        const ok = window.confirm(
          `将按工作表名称批量导入并保存到 ${selectedVersionName}（${selectedYear}年${selectedMonth}月）。未匹配的工作表会跳过。是否继续？`
        );
        if (!ok) return;
        setBatchImporting(true);
        const resp = await applyDataEntryWorkbookImport(selectedYear, selectedMonth, fd, {
          version_id: versionNameToId(selectedVersionName),
          version_name: selectedVersionName,
          entry_status: "draft",
        });
        const savedNames = (resp.saved ?? []).map((item) => item.sheet_name).join("、");
        const unmatchedCount = resp.unmatched_count ?? 0;
        setMessage(
          `批量导入完成：已保存 ${resp.saved_count ?? 0} 个工作表${savedNames ? `（${savedNames}）` : ""}${unmatchedCount ? `，跳过 ${unmatchedCount} 个未匹配 sheet` : ""}。`
        );
        const currentCode = selectedEntityCode.trim();
        const currentTable = selectedTableName.trim();
        const savedCurrent = (resp.saved ?? []).find(
          (item) => item.entity_code === currentCode && item.table_name === currentTable
        );
        if (savedCurrent && metricSnapshot) {
          const forest = getMetricForestForEntity(metricSnapshot, currentCode, currentTable);
          await loadSnapshot(
            currentCode,
            selectedYear,
            versionNameToId(selectedVersionName),
            currentTable,
            forest
          );
        }
        return;
      }

      const resp = await (importDataEntryWorkbook(
        selectedYear,
        selectedMonth,
        fd
      ) as Promise<ImportWorkbookResponseDto>);
      const sheets = resp.sheets ?? [];
      const code = selectedEntityCode.trim();
      const tn = selectedTableName.trim();
      let matched = sheets.find((s) => s.matched && s.entity_code === code && s.table_name === tn);
      if (!matched && tn) {
        const byTable = sheets.filter((s) => s.matched && s.table_name === tn);
        if (byTable.length === 1) matched = byTable[0];
      }
      if (!matched) {
        matched = sheets.find((s) => s.matched && s.entity_code === code);
      }
      let entityChanged = false;
      if (!matched) {
        matched = sheets.find((s) => s.matched);
        if (matched) {
          entityChanged = matched.entity_code !== code || matched.table_name !== tn;
          setSelectedEntityCode(matched.entity_code);
          setSelectedTableName(matched.table_name);
        }
      }
      if (!matched) {
        setError("未能根据工作表名称匹配到机构/产品与指标表，请检查表名（如 A01泛微粒贷业务状况表）。");
        return;
      }
      const forestForImport = getMetricForestForEntity(
        metricSnapshot,
        matched!.entity_code,
        matched!.table_name
      );
      const sameScope = matched.entity_code === code && matched.table_name === tn;
      const baseRows = buildRowsFromMetrics(
        forestForImport,
        sameScope ? rows : [],
        matched!.entity_code,
        selectedMonth
      );
      skipSnapshotLoadRef.current = entityChanged || !sameScope;
      setRows(mergeImportedMetrics(baseRows, matched.metrics, matched.entity_code, selectedMonth));
      setMessage(`已从工作表「${matched.sheet_name}」导入 ${matched.row_count} 行数据。`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Excel 导入失败");
    } finally {
      setBatchImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const selectEntity = (node: OrgProductNode) => {
    const code = node.code.trim();
    if (!entityHasMetricConfig(tree, metricSnapshot, code)) {
      setMessage("");
      setError(`「${node.code} ${node.name}」尚未配置指标表，请先在「机构及产品指标」中维护。`);
      return;
    }
    setError("");
    setSelectedEntityCode(code);
    setOrgDropdownOpen(false);
  };

  const renderOrgNode = (node: OrgProductNode, level: number) => {
    const hasChildren = node.children.length > 0;
    const isOpen = orgExpanded[node.id] ?? false;
    const shouldShowChildren = orgSearchInput.trim() ? true : isOpen;
    const selected = node.code === selectedEntityCode;
    const hasMetrics = entityCodesWithMetrics.has(node.code.trim());

    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-1.5 px-2 py-1.5 text-[11px] ${
            selected ? "bg-blue-50 text-blue-800" : hasMetrics ? "hover:bg-gray-50 cursor-pointer text-gray-800" : "text-gray-400"
          }`}
          style={{ paddingLeft: `${level * 14 + 8}px` }}
          onClick={() => {
            if (hasMetrics) selectEntity(node);
          }}
        >
          {batchMode && hasMetrics ? (
            <input
              type="checkbox"
              checked={batchSelectedEntities.includes(node.code.trim())}
              onClick={(e) => e.stopPropagation()}
              onChange={() => toggleBatchEntity(node.code)}
              className="h-3.5 w-3.5 shrink-0 rounded border-gray-300"
            />
          ) : null}
          {hasChildren ? (
            <button
              type="button"
              className="shrink-0 rounded p-0.5 hover:bg-gray-200"
              onClick={(e) => {
                e.stopPropagation();
                setOrgExpanded((prev) => ({ ...prev, [node.id]: !isOpen }));
              }}
            >
              {shouldShowChildren ? (
                <ChevronDown className="h-3 w-3 text-gray-500" />
              ) : (
                <ChevronRight className="h-3 w-3 text-gray-500" />
              )}
            </button>
          ) : (
            <span className="w-4 shrink-0" />
          )}
          <span className="min-w-0 flex-1 truncate">{formatOrgNodeSegment(node)}</span>
        </div>
        {hasChildren && shouldShowChildren ? node.children.map((c) => renderOrgNode(c, level + 1)) : null}
      </div>
    );
  };

  const cellReadOnly = versionConfirmed;

  if (loading) {
    return <div className="p-4 text-sm text-gray-600">正在加载数据录入...</div>;
  }

  return (
    <div className="relative z-10 flex h-full flex-col bg-gray-50 p-3">
      <div className="mb-2 shrink-0 rounded border border-gray-300 bg-white">
        <div className="border-b border-gray-300 bg-gray-100 px-3 py-1">
          <div className="flex flex-wrap items-start gap-2">
            <span className={entryLabelClass}>时间</span>
            <select
              value={String(selectedYear)}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className={`${entrySelectClass} min-w-[84px]`}
            >
              {yearOptions.map((y) => (
                <option key={y} value={y}>
                  {y}年
                </option>
              ))}
            </select>
            <select
              value={String(selectedMonth)}
              onChange={(e) => setSelectedMonth(Number(e.target.value))}
              className={`${entrySelectClass} min-w-[64px]`}
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>
                  {m}月
                </option>
              ))}
            </select>

            <span className={entryLabelClass}>版本管理</span>
            <select
              value={selectedVersionName}
              onChange={(e) => setSelectedVersionName(e.target.value)}
              className={`${entrySelectClass} min-w-[120px] font-mono`}
            >
              {versionOptions.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={saving || syncing || versionConfirmed}
              onClick={() => void confirmVersion()}
              className={`${secondaryActionClass} ${entryToolbarBtn}`}
              title="确认当前机构产品录入版本，并写入年度库 budget_data"
            >
              <Database className="h-3.5 w-3.5" />
              {saving || syncing ? "处理中..." : "确认并写入预算事实"}
            </button>
            <button
              type="button"
              disabled={!versionConfirmed}
              onClick={modifyVersion}
              className={`${neutralActionClass} ${entryToolbarBtn}`}
            >
              版本修改
            </button>
            <span
              className={`inline-flex min-h-[30px] items-center rounded-full border px-2 py-0.5 text-[11px] ${
                versionConfirmed
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }`}
            >
              {versionConfirmed ? "已确认 · 只读" : "可编辑"}
            </span>

            <div className="ml-auto flex min-w-[100px] flex-wrap items-start justify-end gap-2">
              <button
                type="button"
                disabled={syncing || saving}
                onClick={() => void syncCatalog({ notifyMessage: "已手动拉取最新机构与指标配置。" })}
                title="手动拉取最新机构树与指标配置"
                className={`${neutralActionClass} ${entryToolbarBtn}`}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
                <span>同步配置</span>
              </button>
            </div>
          </div>
        </div>

        <div className="px-3 py-1">
          <div className="flex flex-wrap items-start gap-2">
            <div className="flex min-w-[200px] flex-1 items-start gap-2 max-w-[480px]">
              <span className={entryLabelClass}>机构及产品</span>
              <div className="relative min-w-0 flex-1" ref={orgDialogRef}>
                <button
                  type="button"
                  onClick={() => setOrgDropdownOpen((v) => !v)}
                  className={`${entryEntityPickerClass} ${
                    orgDropdownOpen ? "border-blue-400 ring-1 ring-blue-400/30" : ""
                  }`}
                >
                  <span className="truncate text-gray-800">{selectedEntityLabel}</span>
                  <ChevronDown className={`h-4 w-4 shrink-0 text-gray-400 ${orgDropdownOpen ? "rotate-180" : ""}`} />
                </button>
                {orgDropdownOpen ? (
                  <div className="absolute left-0 right-0 top-[calc(100%+8px)] z-50 overflow-hidden rounded-lg border border-gray-300 bg-white shadow-xl">
                    <div className="border-b border-gray-200 p-3">
                      <div className="relative">
                        <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
                        <input
                          value={orgSearchInput}
                          onChange={(e) => setOrgSearchInput(e.target.value)}
                          placeholder="搜索机构或产品..."
                          className="w-full rounded border border-gray-300 py-1.5 pl-8 pr-8 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                        {orgSearchInput ? (
                          <button
                            type="button"
                            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 hover:bg-gray-100"
                            onClick={() => setOrgSearchInput("")}
                          >
                            <X className="h-3.5 w-3.5 text-gray-500" />
                          </button>
                        ) : null}
                      </div>
                    </div>
                    <div className="max-h-64 overflow-auto py-0.5">
                      {visibleOrgTree ? (
                        renderOrgNode(visibleOrgTree, 0)
                      ) : (
                        <div className="px-3 py-4 text-xs text-gray-500">未找到匹配项</div>
                      )}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
              <input
                value={subjectSearch}
                onChange={(e) => setSubjectSearch(e.target.value)}
                placeholder="搜索科目名称或代码"
                className={`${entryInputClass} w-[168px] pl-8 pr-2`}
              />
            </div>

            <span className={entryLabelClass}>指标表</span>
            <select
              value={selectedTableName}
              onChange={(e) => setSelectedTableName(e.target.value)}
              className={`${entrySelectClass} min-w-[128px]`}
            >
              {tablesForEntity.length ? (
                tablesForEntity.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))
              ) : (
                <option value="">暂无指标表</option>
              )}
            </select>

            {batchMode ? (
              <div className="flex min-w-[220px] flex-wrap items-center gap-x-3 gap-y-1 rounded border border-blue-100 bg-blue-50/40 px-2 py-1">
                <span className="w-full text-[10px] font-medium text-blue-700">批量范围</span>
                {batchTableOptions.length ? (
                  batchTableOptions.map((t) => (
                    <label key={t} className="inline-flex items-center gap-1 text-[11px] text-gray-700">
                      <input
                        type="checkbox"
                        checked={batchSelectedTables.includes(t)}
                        onChange={() => toggleBatchTable(t)}
                        className="h-3.5 w-3.5 rounded border-gray-300"
                      />
                      <span>{t}</span>
                    </label>
                  ))
                ) : (
                  <span className="text-[11px] text-gray-500">请先勾选机构/产品</span>
                )}
              </div>
            ) : null}

            {batchMode ? (
              <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] text-blue-700">
                已选 {batchExportItems.length} 个 sheet
              </span>
            ) : null}

            <div className="ml-auto flex shrink-0 flex-wrap items-start justify-end gap-2">
              <button
                type="button"
                onClick={() => setBatchMode((v) => !v)}
                className={`${neutralActionClass} ${entryToolbarBtn} ${batchMode ? "border-blue-300 bg-blue-50 text-blue-700" : ""}`}
                title="开启后可多选机构/产品与指标表，批量导出模板或按 sheet 名批量导入"
              >
                <span>{batchMode ? "退出批量" : "批量模式"}</span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xlsm"
                className="hidden"
                onChange={(e) => void onExcelSelected(e.target.files?.[0] ?? null)}
              />
              <button
                type="button"
                disabled={cellReadOnly || batchImporting}
                onClick={() => fileInputRef.current?.click()}
                className={`${neutralActionClass} ${entryToolbarBtn}`}
                title={batchMode ? "按工作表名称批量导入并保存到当前版本" : "导入当前 sheet 到编辑区"}
              >
                <Upload className="h-3.5 w-3.5" />
                <span>{batchImporting ? "导入中..." : batchMode ? "批量导入" : "Excel导入"}</span>
              </button>
              {batchMode ? (
                <button
                  type="button"
                  disabled={batchExporting || !batchExportItems.length}
                  onClick={() => void exportBatchTemplate()}
                  className={`${neutralActionClass} ${entryToolbarBtn}`}
                  title="导出所选机构/产品×指标表组合，每个组合一个 sheet"
                >
                  <Download className="h-3.5 w-3.5" />
                  <span>{batchExporting ? "导出中..." : "批量导出模板"}</span>
                </button>
              ) : (
                <button
                  type="button"
                  disabled={exporting || !rows.length}
                  onClick={() => void exportCurrent()}
                  className={`${neutralActionClass} ${entryToolbarBtn}`}
                  title="导出当前数据录入底稿"
                >
                  <Download className="h-3.5 w-3.5" />
                  <span>{exporting ? "导出中..." : "Excel导出"}</span>
                </button>
              )}
              <button
                type="button"
                disabled={saving || cellReadOnly}
                onClick={() => void saveRefresh("draft")}
                className={`${primaryActionClass} ${entryToolbarBtn}`}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${saving ? "animate-spin" : ""}`} />
                <span>保存刷新</span>
              </button>
            </div>
          </div>
        </div>

        {message ? (
          <div className="border-t border-gray-200 bg-emerald-50/80 px-3 py-1.5 text-[11px] text-emerald-800">{message}</div>
        ) : null}
        {error ? (
          <div className="border-t border-gray-200 bg-red-50/80 px-3 py-1.5 text-[11px] text-red-700">{error}</div>
        ) : null}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded border border-gray-300 bg-white shadow-sm">
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-max min-w-full border-separate border-spacing-0 text-xs">
              <thead>
                <tr>
                  {ENTRY_FROZEN_COLUMNS.map((col, idx) => (
                    <th
                      key={col.label}
                      className={frozenHeaderThClass(idx === ENTRY_FROZEN_COLUMNS.length - 1)}
                      style={frozenColBoxStyle(col.left, col.width)}
                    >
                      {col.label}
                    </th>
                  ))}
                  {dataColumns.map((c) => (
                    <th
                      key={c.key}
                      className={scrollableHeaderThClass()}
                      style={dataColWidthStyle(dataColumnWidths[c.key] ?? estimateHeaderWidthPx(c.label))}
                    >
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((r) => {
                  const emphasize = isPrimaryMetricLevel(r.levelLabel);
                  return (
                    <tr key={r.metric_id} className={`group ${metricRowToneClass(r.levelLabel)}`}>
                      <td
                        className={`${frozenBodyTdClass(r.levelLabel, false)} whitespace-nowrap text-gray-700 ${emphasize ? "font-semibold" : ""}`}
                        style={frozenColBoxStyle(ENTRY_FROZEN_COLUMNS[0].left, ENTRY_FROZEN_COLUMNS[0].width)}
                      >
                        {r.levelLabel}
                      </td>
                      <td
                        className={`${frozenBodyTdClass(r.levelLabel, false)} whitespace-nowrap text-gray-700 ${emphasize ? "font-semibold" : ""}`}
                        style={frozenColBoxStyle(ENTRY_FROZEN_COLUMNS[1].left, ENTRY_FROZEN_COLUMNS[1].width)}
                      >
                        {r.nature}
                      </td>
                      <td
                        className={`${frozenBodyTdClass(r.levelLabel, false)} font-mono text-gray-700 ${emphasize ? "font-semibold" : ""}`}
                        style={frozenColBoxStyle(ENTRY_FROZEN_COLUMNS[2].left, ENTRY_FROZEN_COLUMNS[2].width)}
                        title={r.displayCode}
                      >
                        <span className="block truncate">{r.displayCode}</span>
                      </td>
                      <td
                        className={`${frozenBodyTdClass(r.levelLabel, true)} text-gray-800 ${emphasize ? "font-semibold" : ""}`}
                        style={frozenColBoxStyle(ENTRY_FROZEN_COLUMNS[3].left, ENTRY_FROZEN_COLUMNS[3].width)}
                      >
                        <div className="flex min-w-0 items-center">
                          {Array.from({ length: r.depth }).map((_, index) => (
                            <span
                              key={`${r.metric_id}-indent-${index}`}
                              className="mr-1.5 h-4 w-2 shrink-0 border-l border-slate-300/90"
                              aria-hidden="true"
                            />
                          ))}
                          <span className="min-w-0 truncate" title={r.metric_name}>
                            {r.displayName.trimStart()}
                          </span>
                        </div>
                      </td>
                      {dataColumns.map((c) => {
                        const colReadOnly =
                          cellReadOnly || Boolean(c.computed) || !isRollingDataColumnEditable(c.key, selectedMonth);
                        const cellVal = getCellValue(r.values, c.key);
                        const colW = dataColumnWidths[c.key] ?? estimateHeaderWidthPx(c.label);
                        return (
                          <td
                            key={`${r.metric_id}-${c.key}`}
                            className="border border-gray-200 p-0 align-middle"
                            style={dataColWidthStyle(colW)}
                          >
                            <input
                              value={cellVal}
                              readOnly={colReadOnly}
                              title={
                                c.computed
                                  ? "由当年已发生月实际与未发生月预测自动汇总"
                                  : cellVal || undefined
                              }
                              onChange={(e) => {
                                const val = e.target.value;
                                setRows((prev) =>
                                  prev.map((row) =>
                                    row.metric_id === r.metric_id
                                      ? {
                                          ...row,
                                          values: applyRollingForecastLogic(
                                            setCellValue(row.values, c.key, val),
                                            selectedMonth
                                          ),
                                        }
                                      : row
                                  )
                                );
                              }}
                              className={`box-border w-full max-w-full px-1.5 py-1 text-right text-[11px] tabular-nums border-0 focus:outline-none focus:ring-1 focus:ring-inset focus:ring-blue-400 ${
                                colReadOnly
                                  ? c.computed
                                    ? "bg-slate-100 text-slate-800 font-medium"
                                    : "bg-gray-50 text-gray-700"
                                  : "bg-white group-hover:bg-gray-50"
                              }`}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
                {filteredRows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={ENTRY_FROZEN_COLUMNS.length + dataColumns.length}
                      className="border border-gray-200 px-3 py-8 text-center text-gray-500"
                    >
                      {!metricForest.length
                        ? `「${selectedTableName || "当前指标表"}」暂无科目，可在「机构及产品指标」中维护并保存；保存后会自动更新，亦可点「同步配置」。`
                        : subjectSearch.trim()
                          ? "暂无匹配科目，请调整搜索条件。"
                          : "暂无科目。"}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
