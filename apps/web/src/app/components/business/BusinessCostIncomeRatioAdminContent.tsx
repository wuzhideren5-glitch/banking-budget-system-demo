import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Trash2, RefreshCw, X, ChevronUp, ChevronDown, ChevronRight, FolderOpen, FileText, Edit } from "lucide-react";
import {
  createBusinessCostIncomeIndicator,
  createBusinessCostIncomeItem,
  deleteBusinessCostIncomeIndicator,
  deleteBusinessCostIncomeItem,
  listBusinessCostIncomeIndicators,
  listBusinessCostIncomeItems,
  reorderBusinessCostIncomeIndicators,
  reorderBusinessCostIncomeItems,
  updateBusinessCostIncomeIndicator,
  updateBusinessCostIncomeItem,
} from "@/lib/business/businessCostIncomeApi";
import type {
  BusinessCostIncomeManualEntryMode,
  BusinessCostIncomeIndicatorDto,
  BusinessCostIncomeIndicatorFormat,
  BusinessCostIncomeItemDto,
  BusinessCostIncomeItemSection,
  BusinessCostIncomeValueMode,
} from "@/lib/business/businessCostIncomeApi";
import { getOrgProductMetricSnapshot } from "@/lib/org-product/orgProductMetricApi";
import { listOrgProductRuntimeProducts, type OrgProductRuntimeProductDto } from "@/lib/expense/masterDataApi";
import { deriveRuntimeRefFromOrgProductMetricCode } from "@/lib/org-product/orgProductMetricCode";

type ItemSectionType = BusinessCostIncomeItemSection;
type IndicatorFormatType = BusinessCostIncomeIndicatorFormat | "number";
type ItemDto = BusinessCostIncomeItemDto;
type IndicatorDto = BusinessCostIncomeIndicatorDto;
type ValueMode = BusinessCostIncomeValueMode;
type ManualEntryMode = BusinessCostIncomeManualEntryMode;

type TreeItemNode = ItemDto & {
  depth: number;
  children: TreeItemNode[];
};

type TreeItemRow = TreeItemNode & {
  hasChildren: boolean;
  isExpanded: boolean;
};

type IndicatorTreeNode = IndicatorDto & {
  depth: number;
  children: IndicatorTreeNode[];
};

type IndicatorTreeRow = IndicatorTreeNode & {
  hasChildren: boolean;
  isExpanded: boolean;
};

type EditItemDraft = {
  id: number;
  section: ItemSectionType;
  name: string;
  parentId: number | null;
  originalParentId: number | null;
  displayGroup: boolean;
  dataAcctCode: string;
  orgProductRef: string;
  orgProductEntityCode: string;
  orgProductTableName: string;
  orgProductMetricCode: string;
  orgProductMetricName: string;
  manualEntryMode: ManualEntryMode;
  valueMode: ValueMode;
  sortOrder: number;
  enabled: boolean;
};

type EditIndicatorDraft = {
  id: number;
  name: string;
  parentId: number | null;
  displayGroup: boolean;
  topicMetricNodeCode: string | null;
  numeratorSection: ItemSectionType;
  numeratorItemId: number;
  numeratorValueMode: ValueMode;
  denominatorSection: ItemSectionType;
  denominatorItemId: number;
  denominatorValueMode: ValueMode;
  format: IndicatorFormatType;
  annualize: boolean;
  sortOrder: number;
  enabled: boolean;
};

type AddParentTarget = {
  id: number;
  section: ItemSectionType;
  name: string;
  parentId: number | null;
  displayGroup: boolean;
  sortOrder: number;
  enabled: boolean;
};

type OrgProductMetricNodeDto = {
  id?: string;
  levelLabel?: string;
  nature?: string;
  code?: string;
  name?: string;
  children?: OrgProductMetricNodeDto[];
};

type OrgProductMetricSnapshotDto = {
  entities: Array<{
    entity_code: string;
    entity_name: string;
    tables: Array<{
      id?: string;
      name: string;
      metrics: OrgProductMetricNodeDto[];
    }>;
  }>;
};

type OrgProductMappedAccountOption = {
  key: string;
  entityCode: string;
  entityName: string;
  tableName: string;
  metricCode: string;
  metricName: string;
  dataAcctCode: string;
  dataAcctName: string;
  metricNodeCode: string;
  mappingStatus: string;
};

type OrgProductTopicMetricOption = {
  key: string;
  entityCode: string;
  entityName: string;
  tableName: string;
  metricCode: string;
  metricName: string;
  value: string;
  mappingStatus: string;
};

const SECTION_LABELS: Record<ItemSectionType, string> = {
  input: "业务投入",
  output: "业务产出",
};

const FORMAT_LABELS: Record<IndicatorFormatType, string> = {
  ratio: "比率",
  percent: "百分比(×100)",
  number: "数值",
};

const PRODUCT_STORAGE_KEY = "bcir_admin_selected_product_code";
const MANUAL_ENTRY_MODE_LABELS: Record<ManualEntryMode, string> = {
  disabled: "关闭手工",
  manual: "补录",
  manual_preferred: "录入优先",
};

function compareRuntimeProduct(a: OrgProductRuntimeProductDto, b: OrgProductRuntimeProductDto): number {
  const groupA = a.parent_code === "CORP" ? a.product_code : a.parent_code ?? a.product_code;
  const groupB = b.parent_code === "CORP" ? b.product_code : b.parent_code ?? b.product_code;
  if (groupA !== groupB) return groupA.localeCompare(groupB, "zh-CN");
  return (a.level - b.level) || a.product_code.localeCompare(b.product_code, "zh-CN");
}

function readStoredProductCode(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(PRODUCT_STORAGE_KEY) ?? "";
}

function productRuntimeLabel(item: OrgProductRuntimeProductDto, options?: { showLineSuffix?: boolean }): string {
  const isLine = item.parent_code === "CORP";
  const prefix = isLine ? "" : "　　└ ";
  const lineSuffix = options?.showLineSuffix !== false && isLine ? "（群级）" : "";
  return `${prefix}${item.product_code} · ${item.product_name}${lineSuffix}`;
}

function productRuntimeGroupLabel(line: OrgProductRuntimeProductDto): string {
  return `${line.product_code} · ${line.product_name}`;
}

function orgProductRefForMappedAccount(option: OrgProductMappedAccountOption): string {
  return `${option.entityCode}:${option.tableName}:${option.metricCode}`;
}

function flattenOrgProductMappedAccountOptions(
  snapshot: OrgProductMetricSnapshotDto | null
): OrgProductMappedAccountOption[] {
  const rows: OrgProductMappedAccountOption[] = [];
  const walk = (
    entityCode: string,
    entityName: string,
    tableName: string,
    metrics: OrgProductMetricNodeDto[]
  ) => {
    for (const metric of metrics) {
      const metricCode = String(metric.code || "").trim().toUpperCase();
      const runtimeRef = deriveRuntimeRefFromOrgProductMetricCode(entityCode, metricCode);
      if (metricCode && runtimeRef) {
        rows.push({
          key: `${entityCode}::${tableName}::${String(metric.id || metricCode)}`,
          entityCode,
          entityName,
          tableName,
          metricCode,
          metricName: String(metric.name || "").trim(),
          dataAcctCode: runtimeRef,
          dataAcctName: String(metric.name || runtimeRef).trim(),
          metricNodeCode: runtimeRef,
          mappingStatus: "",
        });
      }
      walk(entityCode, entityName, tableName, Array.isArray(metric.children) ? metric.children : []);
    }
  };
  for (const entity of snapshot?.entities ?? []) {
    const entityCode = String(entity.entity_code || "").trim();
    if (!entityCode) continue;
    for (const table of entity.tables ?? []) {
      walk(entityCode, String(entity.entity_name || "").trim(), String(table.name || "").trim(), table.metrics ?? []);
    }
  }
  return rows;
}

function flattenOrgProductTopicMetricOptions(snapshot: OrgProductMetricSnapshotDto | null): OrgProductTopicMetricOption[] {
  const rows: OrgProductTopicMetricOption[] = [];
  const walk = (
    entityCode: string,
    entityName: string,
    tableName: string,
    metrics: OrgProductMetricNodeDto[]
  ) => {
    for (const metric of metrics) {
      const code = String(metric.code || "").trim();
      if (code) {
        rows.push({
          key: `${entityCode}::${tableName}::${String(metric.id || code)}`,
          entityCode,
          entityName,
          tableName,
          metricCode: code,
          metricName: String(metric.name || "").trim(),
          value: `${entityCode}:${tableName}:${code}`,
          mappingStatus: "",
        });
      }
      walk(entityCode, entityName, tableName, Array.isArray(metric.children) ? metric.children : []);
    }
  };
  for (const entity of snapshot?.entities ?? []) {
    const entityCode = String(entity.entity_code || "").trim();
    if (!entityCode) continue;
    for (const table of entity.tables ?? []) {
      walk(entityCode, String(entity.entity_name || "").trim(), String(table.name || "").trim(), table.metrics ?? []);
    }
  }
  return rows;
}

type RuntimeProductGroup = {
  line: OrgProductRuntimeProductDto;
  items: OrgProductRuntimeProductDto[];
};

function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
          <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

function buildTreeRows(items: ItemDto[], section: ItemSectionType): (ItemDto & { depth: number })[] {
  const sectionItems = items.filter((it) => it.section === section);
  const childrenMap = new Map<number | null, ItemDto[]>();
  for (const item of sectionItems) {
    const siblings = childrenMap.get(item.parent_id) ?? [];
    siblings.push(item);
    childrenMap.set(item.parent_id, siblings);
  }
  for (const siblings of childrenMap.values()) {
    siblings.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  }

  const rows: (ItemDto & { depth: number })[] = [];
  const walk = (parentId: number | null, depth: number) => {
    for (const child of childrenMap.get(parentId) ?? []) {
      rows.push({ ...child, depth });
      walk(child.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

function buildItemTree(items: ItemDto[], section: ItemSectionType): TreeItemNode[] {
  const treeRows = buildTreeRows(items, section);
  const nodeMap = new Map<number, TreeItemNode>();
  const roots: TreeItemNode[] = [];
  for (const row of treeRows) {
    nodeMap.set(row.id, { ...row, children: [] });
  }
  for (const row of treeRows) {
    const node = nodeMap.get(row.id)!;
    if (row.parent_id != null && nodeMap.has(row.parent_id)) {
      nodeMap.get(row.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

function itemExpandKey(section: ItemSectionType, id: number): string {
  return `${section}:${id}`;
}

function flattenVisibleTree(
  nodes: TreeItemNode[],
  expanded: Record<string, boolean>,
  section: ItemSectionType
): TreeItemRow[] {
  const rows: TreeItemRow[] = [];
  const walk = (list: TreeItemNode[]) => {
    for (const node of list) {
      const hasChildren = node.children.length > 0;
      const isExpanded = expanded[itemExpandKey(section, node.id)] ?? true;
      rows.push({ ...node, hasChildren, isExpanded });
      if (hasChildren && isExpanded) walk(node.children);
    }
  };
  walk(nodes);
  return rows;
}

function buildLeafOptions(items: ItemDto[], section: ItemSectionType): { id: number; name: string; depth: number }[] {
  const sectionItems = items.filter((it) => it.section === section);
  const hasChildren = new Set<number>();
  for (const it of sectionItems) {
    if (it.parent_id != null) hasChildren.add(it.parent_id);
  }
  const leaves = sectionItems.filter((it) => !hasChildren.has(it.id));
  const treeRows = buildTreeRows(items, section);
  const depthMap = new Map(treeRows.map((r) => [r.id, r.depth]));
  return leaves.map((it) => ({
    id: it.id,
    name: it.name,
    depth: depthMap.get(it.id) ?? 0,
  }));
}

function buildIndicatorTreeRows(indicators: IndicatorDto[]): (IndicatorDto & { depth: number })[] {
  const childrenMap = new Map<number | null, IndicatorDto[]>();
  for (const indicator of indicators) {
    const siblings = childrenMap.get(indicator.parent_id) ?? [];
    siblings.push(indicator);
    childrenMap.set(indicator.parent_id, siblings);
  }
  for (const siblings of childrenMap.values()) {
    siblings.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
  }
  const rows: (IndicatorDto & { depth: number })[] = [];
  const walk = (parentId: number | null, depth: number) => {
    for (const child of childrenMap.get(parentId) ?? []) {
      rows.push({ ...child, depth });
      walk(child.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

function buildIndicatorTree(indicators: IndicatorDto[]): IndicatorTreeNode[] {
  const treeRows = buildIndicatorTreeRows(indicators);
  const nodeMap = new Map<number, IndicatorTreeNode>();
  const roots: IndicatorTreeNode[] = [];
  for (const row of treeRows) {
    nodeMap.set(row.id, { ...row, children: [] });
  }
  for (const row of treeRows) {
    const node = nodeMap.get(row.id)!;
    if (row.parent_id != null && nodeMap.has(row.parent_id)) {
      nodeMap.get(row.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

function indicatorExpandKey(id: number): string {
  return `indicator:${id}`;
}

function flattenVisibleIndicatorTree(
  nodes: IndicatorTreeNode[],
  expanded: Record<string, boolean>
): IndicatorTreeRow[] {
  const rows: IndicatorTreeRow[] = [];
  const walk = (list: IndicatorTreeNode[]) => {
    for (const node of list) {
      const hasChildren = node.children.length > 0;
      const isExpanded = expanded[indicatorExpandKey(node.id)] ?? true;
      rows.push({ ...node, hasChildren, isExpanded });
      if (hasChildren && isExpanded) walk(node.children);
    }
  };
  walk(nodes);
  return rows;
}

export function BusinessCostIncomeRatioAdminContent() {
  const [items, setItems] = useState<ItemDto[]>([]);
  const [indicators, setIndicators] = useState<IndicatorDto[]>([]);
  const [orgProductRuntimeProducts, setOrgProductRuntimeProducts] = useState<OrgProductRuntimeProductDto[]>([]);
  const [orgProductMetricSnapshot, setOrgProductMetricSnapshot] = useState<OrgProductMetricSnapshotDto | null>(null);
  const [selectedProductCode, setSelectedProductCode] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [indicatorExpanded, setIndicatorExpanded] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [addItemOpen, setAddItemOpen] = useState(false);
  const [addItemSection, setAddItemSection] = useState<ItemSectionType>("input");
  const [addItemName, setAddItemName] = useState("");
  const [addItemParentId, setAddItemParentId] = useState<number | null>(null);
  const [addItemDisplayGroup, setAddItemDisplayGroup] = useState(false);
  const [addItemDataAcctCode, setAddItemDataAcctCode] = useState("");
  const [addItemOrgProductRef, setAddItemOrgProductRef] = useState("");
  const [addItemOrgProductEntityCode, setAddItemOrgProductEntityCode] = useState("");
  const [addItemOrgProductTableName, setAddItemOrgProductTableName] = useState("");
  const [addItemOrgProductMetricCode, setAddItemOrgProductMetricCode] = useState("");
  const [addItemOrgProductMetricName, setAddItemOrgProductMetricName] = useState("");
  const [addItemManualEntryMode, setAddItemManualEntryMode] = useState<ManualEntryMode>("disabled");
  const [addItemAccountKeyword, setAddItemAccountKeyword] = useState("");
  const [addParentTarget, setAddParentTarget] = useState<AddParentTarget | null>(null);
  const [editItem, setEditItem] = useState<EditItemDraft | null>(null);

  const [addIndicatorOpen, setAddIndicatorOpen] = useState(false);
  const [newIndicatorName, setNewIndicatorName] = useState("");
  const [newIndicatorTopicMetricNodeCode, setNewIndicatorTopicMetricNodeCode] = useState("");
  const [newIndicatorNumeratorSection, setNewIndicatorNumeratorSection] = useState<ItemSectionType>("input");
  const [newIndicatorNumeratorItemId, setNewIndicatorNumeratorItemId] = useState<number>(0);
  const [newIndicatorDenominatorSection, setNewIndicatorDenominatorSection] = useState<ItemSectionType>("output");
  const [newIndicatorDenominatorItemId, setNewIndicatorDenominatorItemId] = useState<number>(0);
  const [newIndicatorFormat, setNewIndicatorFormat] = useState<IndicatorFormatType>("ratio");
  const [editIndicator, setEditIndicator] = useState<EditIndicatorDraft | null>(null);

  const clearMsg = () => { setError(""); setSuccess(""); };

  const loadData = useCallback(async () => {
    setLoading(true);
    clearMsg();
    try {
      const [itemList, indicatorList, products, orgMetricSnapshot] = await Promise.all([
        listBusinessCostIncomeItems(selectedProductCode),
        listBusinessCostIncomeIndicators(selectedProductCode),
        listOrgProductRuntimeProducts(),
        (getOrgProductMetricSnapshot() as Promise<OrgProductMetricSnapshotDto>).catch(() => ({ entities: [] })),
      ]);
      setItems(itemList);
      setIndicators(indicatorList);
      setOrgProductRuntimeProducts(products);
      setOrgProductMetricSnapshot(orgMetricSnapshot);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "加载失败";
      setError(msg);
      console.error("[BCIR-Admin] loadData failed:", msg, e);
    } finally {
      setLoading(false);
    }
  }, [selectedProductCode]);

  useEffect(() => {
    const stored = readStoredProductCode();
    if (stored) setSelectedProductCode(stored);
  }, []);

  const runtimeProducts = useMemo(() => {
    const parentCodes = new Set(
      orgProductRuntimeProducts.map((item) => item.parent_code).filter((code): code is string => Boolean(code))
    );
    return orgProductRuntimeProducts
      .filter((item) => item.parent_code === "CORP" || !parentCodes.has(item.product_code))
      .sort(compareRuntimeProduct);
  }, [orgProductRuntimeProducts]);

  const runtimeProductGroups = useMemo((): RuntimeProductGroup[] => {
    const lines = orgProductRuntimeProducts
      .filter((item) => item.parent_code === "CORP" && item.product_code !== "CORP")
      .sort(compareRuntimeProduct);
    const runtimeCodes = new Set(runtimeProducts.map((item) => item.product_code));
    return lines
      .map((line) => ({
        line,
        items: orgProductRuntimeProducts
          .filter((item) => item.parent_code === line.product_code && runtimeCodes.has(item.product_code))
          .sort(compareRuntimeProduct),
      }))
      .filter((group) => runtimeCodes.has(group.line.product_code) || group.items.length > 0);
  }, [runtimeProducts, orgProductRuntimeProducts]);

  const selectedProductMeta = useMemo(() => {
    const selected = orgProductRuntimeProducts.find((item) => item.product_code === selectedProductCode);
    if (!selected) return null;
    const line =
      selected.parent_code && selected.parent_code !== "CORP"
        ? orgProductRuntimeProducts.find((item) => item.product_code === selected.parent_code) ?? null
        : selected.parent_code === "CORP"
          ? selected
          : null;
    return { selected, line };
  }, [orgProductRuntimeProducts, selectedProductCode]);

  useEffect(() => {
    if (!selectedProductCode && runtimeProducts.length > 0) {
      const stored = readStoredProductCode();
      const preferred =
        runtimeProducts.find((item) => item.product_code === stored)?.product_code ??
        runtimeProducts[0].product_code;
      setSelectedProductCode(preferred);
    }
  }, [runtimeProducts, selectedProductCode]);

  useEffect(() => {
    if (!selectedProductCode || typeof window === "undefined") return;
    window.localStorage.setItem(PRODUCT_STORAGE_KEY, selectedProductCode);
  }, [selectedProductCode]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const clearAddItemOrgProductIdentity = () => {
    setAddItemOrgProductRef("");
    setAddItemOrgProductEntityCode("");
    setAddItemOrgProductTableName("");
    setAddItemOrgProductMetricCode("");
    setAddItemOrgProductMetricName("");
  };

  const applyAddItemOrgProductOption = (option: OrgProductMappedAccountOption) => {
    setAddItemDataAcctCode(option.dataAcctCode);
    setAddItemName(option.metricName);
    setAddItemOrgProductRef(orgProductRefForMappedAccount(option));
    setAddItemOrgProductEntityCode(option.entityCode);
    setAddItemOrgProductTableName(option.tableName);
    setAddItemOrgProductMetricCode(option.metricCode);
    setAddItemOrgProductMetricName(option.metricName);
  };

  const openAddItemDialog = (section: ItemSectionType, parentId: number | null = null) => {
    setAddItemSection(section);
    setAddItemName("");
    setAddItemParentId(parentId);
    setAddItemDisplayGroup(false);
    setAddItemDataAcctCode("");
    clearAddItemOrgProductIdentity();
    setAddItemManualEntryMode("disabled");
    setAddItemAccountKeyword("");
    setAddParentTarget(null);
    if (parentId != null) {
      setExpanded((prev) => ({ ...prev, [itemExpandKey(section, parentId)]: true }));
    }
    setAddItemOpen(true);
  };

  const openAddParentDialog = (item: ItemDto) => {
    setAddItemSection(item.section);
    setAddItemName("");
    setAddItemParentId(item.parent_id);
    setAddParentTarget({
      id: item.id,
      section: item.section,
      name: item.name,
      parentId: item.parent_id,
      displayGroup: true,
      sortOrder: item.sort_order,
      enabled: item.enabled,
    });
    setAddItemDisplayGroup(true);
    setAddItemName("");
    setAddItemDataAcctCode("");
    clearAddItemOrgProductIdentity();
    setAddItemManualEntryMode("disabled");
    setAddItemAccountKeyword("");
    if (item.parent_id != null) {
      setExpanded((prev) => ({ ...prev, [itemExpandKey(item.section, item.parent_id!)]: true }));
    }
    setAddItemOpen(true);
  };

  const handleCreateItem = async () => {
    const trimmed = addItemName.trim();
    if (addItemDisplayGroup && !trimmed) return;
    if (!addItemDisplayGroup && !addItemDataAcctCode) {
      setError("请选择已确认机构产品指标");
      return;
    }
    clearMsg();
    setSubmitting(true);
    try {
      const created = await createBusinessCostIncomeItem({
        product_code: selectedProductCode,
        section: addItemSection,
        name: trimmed,
        parent_id: addItemParentId,
        display_group: addItemDisplayGroup,
        data_acct_code: addItemDisplayGroup ? null : addItemDataAcctCode,
        org_product_ref: addItemDisplayGroup ? "" : addItemOrgProductRef,
        org_product_entity_code: addItemDisplayGroup ? "" : addItemOrgProductEntityCode,
        org_product_table_name: addItemDisplayGroup ? "" : addItemOrgProductTableName,
        org_product_metric_code: addItemDisplayGroup ? "" : addItemOrgProductMetricCode,
        org_product_metric_name: addItemDisplayGroup ? "" : addItemOrgProductMetricName,
        manual_entry_mode: addItemManualEntryMode,
        value_mode: addItemDisplayGroup ? "self" : "tree",
        sort_order: 0,
        enabled: true,
      });
      if (addParentTarget) {
        const siblings = items
          .filter(
            (it) =>
              it.section === addParentTarget.section &&
              it.parent_id === addParentTarget.parentId
          )
          .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
        const currentIndex = siblings.findIndex((it) => it.id === addParentTarget.id);
        await updateBusinessCostIncomeItem(created.id, {
          product_code: selectedProductCode,
          name: created.name,
          parent_id: addParentTarget.parentId,
          display_group: created.display_group,
          data_acct_code: created.data_acct_code,
          org_product_ref: created.org_product_ref,
          org_product_entity_code: created.org_product_entity_code,
          org_product_table_name: created.org_product_table_name,
          org_product_metric_code: created.org_product_metric_code,
          org_product_metric_name: created.org_product_metric_name,
          manual_entry_mode: created.manual_entry_mode,
          value_mode: created.value_mode,
          sort_order: addParentTarget.sortOrder,
          enabled: created.enabled,
        });
        await updateBusinessCostIncomeItem(addParentTarget.id, {
          product_code: selectedProductCode,
          name: addParentTarget.name,
          parent_id: created.id,
          display_group: addParentTarget.displayGroup,
          data_acct_code: "",
          org_product_ref: "",
          org_product_entity_code: "",
          org_product_table_name: "",
          org_product_metric_code: "",
          org_product_metric_name: "",
          manual_entry_mode: addParentTarget.displayGroup ? "disabled" : "disabled",
          value_mode: "tree",
          sort_order: 0,
          enabled: addParentTarget.enabled,
        });
        const reorderedSiblingIds = siblings
          .filter((it) => it.id !== addParentTarget.id)
          .map((it) => it.id);
        const insertAt = currentIndex === -1 ? reorderedSiblingIds.length : currentIndex;
        reorderedSiblingIds.splice(insertAt, 0, created.id);
        await reorderBusinessCostIncomeItems(reorderedSiblingIds);
        setExpanded((prev) => ({
          ...prev,
          [itemExpandKey(addParentTarget.section, created.id)]: true,
        }));
      }
      setSuccess(`${SECTION_LABELS[addItemSection]}细项添加成功`);
      setAddItemOpen(false);
      setAddParentTarget(null);
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "创建失败";
      setError(`添加细项失败: ${msg}`);
      console.error("[BCIR-Admin] createItem failed:", msg, e);
    } finally {
      setSubmitting(false);
    }
  };

  const descendantIdsOf = (section: ItemSectionType, itemId: number): Set<number> => {
    const descendants = new Set<number>();
    const stack = items.filter((it) => it.section === section && it.parent_id === itemId).map((it) => it.id);
    while (stack.length > 0) {
      const current = stack.pop()!;
      if (descendants.has(current)) continue;
      descendants.add(current);
      for (const child of items) {
        if (child.section === section && child.parent_id === current) stack.push(child.id);
      }
    }
    return descendants;
  };

  const openEditItemDialog = (item: ItemDto) => {
    setEditItem({
      id: item.id,
      section: item.section,
      name: item.name,
      parentId: item.parent_id,
      originalParentId: item.parent_id,
      displayGroup: item.display_group,
      dataAcctCode: item.data_acct_code,
      orgProductRef: item.org_product_ref,
      orgProductEntityCode: item.org_product_entity_code,
      orgProductTableName: item.org_product_table_name,
      orgProductMetricCode: item.org_product_metric_code,
      orgProductMetricName: item.org_product_metric_name,
      manualEntryMode: item.manual_entry_mode,
      valueMode: item.value_mode,
      sortOrder: item.sort_order,
      enabled: item.enabled,
    });
  };

  const handleUpdateItem = async () => {
    if (!editItem) return;
    const trimmed = editItem.name.trim();
    if (editItem.displayGroup && !trimmed) return;
    if (!editItem.displayGroup && !editItem.dataAcctCode) {
      setError("请选择已确认机构产品指标");
      return;
    }
    clearMsg();
    setSubmitting(true);
    try {
      let nextSort = editItem.sortOrder;
      if (editItem.parentId !== editItem.originalParentId) {
        const siblings = items
          .filter(
            (it) =>
              it.section === editItem.section &&
              it.parent_id === editItem.parentId &&
              it.id !== editItem.id
          )
          .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
        nextSort = siblings.length > 0 ? Math.max(...siblings.map((it) => it.sort_order)) + 1 : 0;
      }
      await updateBusinessCostIncomeItem(editItem.id, {
        product_code: selectedProductCode,
        name: trimmed,
        parent_id: editItem.parentId,
        display_group: editItem.displayGroup,
        data_acct_code: editItem.displayGroup ? null : editItem.dataAcctCode,
        org_product_ref: editItem.displayGroup ? "" : editItem.orgProductRef,
        org_product_entity_code: editItem.displayGroup ? "" : editItem.orgProductEntityCode,
        org_product_table_name: editItem.displayGroup ? "" : editItem.orgProductTableName,
        org_product_metric_code: editItem.displayGroup ? "" : editItem.orgProductMetricCode,
        org_product_metric_name: editItem.displayGroup ? "" : editItem.orgProductMetricName,
        manual_entry_mode: editItem.manualEntryMode,
        value_mode: editItem.valueMode,
        sort_order: nextSort,
        enabled: editItem.enabled,
      });
      setSuccess("细项更新成功");
      setEditItem(null);
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "更新失败";
      setError(`更新细项失败: ${msg}`);
      console.error("[BCIR-Admin] updateItem failed:", msg, e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteItem = async (id: number) => {
    clearMsg();
    setSubmitting(true);
    try {
      await deleteBusinessCostIncomeItem(id);
      setSuccess("删除成功");
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "删除失败";
      setError(`删除失败: ${msg}`);
      console.error("[BCIR-Admin] deleteItem failed:", msg, e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleItem = async (item: ItemDto) => {
    clearMsg();
    try {
      await updateBusinessCostIncomeItem(item.id, {
        product_code: selectedProductCode,
        name: item.name,
        parent_id: item.parent_id,
        display_group: item.display_group,
        data_acct_code: item.data_acct_code,
        manual_entry_mode: item.manual_entry_mode,
        value_mode: item.value_mode,
        sort_order: item.sort_order,
        enabled: !item.enabled,
      });
      setSuccess(item.enabled ? "已停用" : "已启用");
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "更新失败";
      setError(`更新失败: ${msg}`);
      console.error("[BCIR-Admin] toggleItem failed:", msg, e);
    }
  };

  const handleMoveItem = async (item: ItemDto, direction: "up" | "down") => {
    const sibs = items
      .filter((it) => it.section === item.section && it.parent_id === item.parent_id)
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
    const sibIdx = sibs.findIndex((s) => s.id === item.id);
    if (sibIdx < 0) return;
    const sibTarget = direction === "up" ? sibIdx - 1 : sibIdx + 1;
    if (sibTarget < 0 || sibTarget >= sibs.length) return;
    const newSibs = [...sibs];
    [newSibs[sibIdx], newSibs[sibTarget]] = [newSibs[sibTarget], newSibs[sibIdx]];
    const itemIds = newSibs.map((it) => it.id);
    clearMsg();
    setSubmitting(true);
    try {
      await reorderBusinessCostIncomeItems(itemIds);
      setSuccess("排序已更新");
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "排序更新失败";
      setError(msg);
      console.error("[BCIR-Admin] reorderItems failed:", msg, e);
    } finally {
      setSubmitting(false);
    }
  };

  const openAddIndicatorDialog = () => {
    setNewIndicatorName("");
    setNewIndicatorTopicMetricNodeCode("");
    setNewIndicatorNumeratorSection("input");
    setNewIndicatorNumeratorItemId(0);
    setNewIndicatorDenominatorSection("output");
    setNewIndicatorDenominatorItemId(0);
    setNewIndicatorFormat("ratio");
    setAddIndicatorOpen(true);
  };

  const handleCreateIndicator = async () => {
    if (!newIndicatorName.trim()) return;
    if (!newIndicatorNumeratorItemId || !newIndicatorDenominatorItemId) {
      setError("请选择分子和分母细项");
      return;
    }
    clearMsg();
    setSubmitting(true);
    try {
      await createBusinessCostIncomeIndicator({
        product_code: selectedProductCode,
        name: newIndicatorName.trim(),
        parent_id: null,
        display_group: false,
        topic_metric_node_code: newIndicatorTopicMetricNodeCode || null,
        numerator_section: newIndicatorNumeratorSection,
        numerator_item_id: newIndicatorNumeratorItemId,
        numerator_value_mode: "tree",
        denominator_section: newIndicatorDenominatorSection,
        denominator_item_id: newIndicatorDenominatorItemId,
        denominator_value_mode: "tree",
        format: newIndicatorFormat,
        annualize: false,
        sort_order: 0,
        enabled: true,
      });
      setSuccess(`指标"${newIndicatorName.trim()}"添加成功`);
      setAddIndicatorOpen(false);
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "创建失败";
      setError(`添加指标失败: ${msg}`);
      console.error("[BCIR-Admin] createIndicator failed:", msg, e);
    } finally {
      setSubmitting(false);
    }
  };

  const openEditIndicatorDialog = (ind: IndicatorDto) => {
    if (ind.display_group) return;
    setEditIndicator({
      id: ind.id,
      name: ind.name,
      parentId: ind.parent_id,
      displayGroup: ind.display_group,
      topicMetricNodeCode: ind.topic_metric_node_code,
      numeratorSection: ind.numerator_section,
      numeratorItemId: ind.numerator_item_id,
      numeratorValueMode: ind.numerator_value_mode,
      denominatorSection: ind.denominator_section,
      denominatorItemId: ind.denominator_item_id,
      denominatorValueMode: ind.denominator_value_mode,
      format: ind.format,
      annualize: ind.annualize,
      sortOrder: ind.sort_order,
      enabled: ind.enabled,
    });
  };

  const handleUpdateIndicator = async () => {
    if (!editIndicator) return;
    const trimmed = editIndicator.name.trim();
    if (!trimmed) return;
    if (!editIndicator.numeratorItemId || !editIndicator.denominatorItemId) {
      setError("请选择分子和分母细项");
      return;
    }
    clearMsg();
    setSubmitting(true);
    try {
      await updateBusinessCostIncomeIndicator(editIndicator.id, {
        product_code: selectedProductCode,
        name: trimmed,
        parent_id: editIndicator.parentId,
        display_group: editIndicator.displayGroup,
        topic_metric_node_code: editIndicator.topicMetricNodeCode,
        numerator_section: editIndicator.numeratorSection,
        numerator_item_id: editIndicator.numeratorItemId,
        numerator_value_mode: editIndicator.numeratorValueMode,
        denominator_section: editIndicator.denominatorSection,
        denominator_item_id: editIndicator.denominatorItemId,
        denominator_value_mode: editIndicator.denominatorValueMode,
        format: editIndicator.format,
        annualize: editIndicator.annualize,
        sort_order: editIndicator.sortOrder,
        enabled: editIndicator.enabled,
      });
      setSuccess(`指标"${trimmed}"已更新`);
      setEditIndicator(null);
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "更新失败";
      setError(`更新指标失败: ${msg}`);
      console.error("[BCIR-Admin] updateIndicator failed:", msg, e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteIndicator = async (id: number) => {
    clearMsg();
    setSubmitting(true);
    try {
      await deleteBusinessCostIncomeIndicator(id);
      setSuccess("删除成功");
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "删除失败";
      setError(`删除失败: ${msg}`);
      console.error("[BCIR-Admin] deleteIndicator failed:", msg, e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleIndicator = async (ind: IndicatorDto) => {
    clearMsg();
    try {
      await updateBusinessCostIncomeIndicator(ind.id, {
        product_code: selectedProductCode,
        name: ind.name,
        parent_id: ind.parent_id,
        display_group: ind.display_group,
        topic_metric_node_code: ind.topic_metric_node_code,
        numerator_section: ind.numerator_section,
        numerator_item_id: ind.numerator_item_id,
        numerator_value_mode: ind.numerator_value_mode,
        denominator_section: ind.denominator_section,
        denominator_item_id: ind.denominator_item_id,
        denominator_value_mode: ind.denominator_value_mode,
        format: ind.format,
        annualize: ind.annualize,
        sort_order: ind.sort_order,
        enabled: !ind.enabled,
      });
      setSuccess(ind.enabled ? "已停用" : "已启用");
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "更新失败";
      setError(`更新失败: ${msg}`);
      console.error("[BCIR-Admin] toggleIndicator failed:", msg, e);
    }
  };

  const handleMoveIndicator = async (indicator: IndicatorDto, direction: "up" | "down") => {
    const siblings = indicators
      .filter((it) => it.parent_id === indicator.parent_id)
      .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
    const currentIndex = siblings.findIndex((it) => it.id === indicator.id);
    if (currentIndex < 0) return;
    const targetIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= siblings.length) return;
    const newOrder = [...siblings];
    [newOrder[currentIndex], newOrder[targetIndex]] = [newOrder[targetIndex], newOrder[currentIndex]];
    const indicatorIds = newOrder.map((ind) => ind.id);
    clearMsg();
    setSubmitting(true);
    try {
      await reorderBusinessCostIncomeIndicators(indicatorIds);
      setSuccess("排序已更新");
      await loadData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "排序更新失败";
      setError(msg);
      console.error("[BCIR-Admin] reorderIndicators failed:", msg, e);
    } finally {
      setSubmitting(false);
    }
  };

  const sectionParentOptions = (section: ItemSectionType) => {
    const treeRows = buildTreeRows(items, section);
    return treeRows.map((r) => ({ id: r.id, name: r.name, depth: r.depth }));
  };

  const editableParentOptions = (section: ItemSectionType, currentId: number) => {
    const blockedIds = descendantIdsOf(section, currentId);
    blockedIds.add(currentId);
    return buildTreeRows(items, section).filter((row) => !blockedIds.has(row.id));
  };

  const orgProductMappedAccountOptions = useMemo(() => {
    const selected = selectedProductCode.trim().toUpperCase();
    return flattenOrgProductMappedAccountOptions(orgProductMetricSnapshot)
      .filter((option) => {
        if (selected && option.entityCode.trim().toUpperCase() !== selected) return false;
        return true;
      })
      .sort(
        (a, b) =>
          a.tableName.localeCompare(b.tableName, "zh-CN") ||
          a.metricCode.localeCompare(b.metricCode, "zh-CN") ||
          a.metricName.localeCompare(b.metricName, "zh-CN")
      );
  }, [orgProductMetricSnapshot, selectedProductCode]);

  const orgProductTopicMetricOptions = useMemo(() => {
    const selected = selectedProductCode.trim().toUpperCase();
    return flattenOrgProductTopicMetricOptions(orgProductMetricSnapshot)
      .filter((option) => !selected || option.entityCode.trim().toUpperCase() === selected)
      .sort(
        (a, b) =>
          a.tableName.localeCompare(b.tableName, "zh-CN") ||
          a.metricCode.localeCompare(b.metricCode, "zh-CN") ||
          a.metricName.localeCompare(b.metricName, "zh-CN")
      );
  }, [orgProductMetricSnapshot, selectedProductCode]);

  const filteredOrgProductMappedAccountOptions = useMemo(() => {
    const keyword = addItemAccountKeyword.trim().toLowerCase();
    if (!keyword) return orgProductMappedAccountOptions;
    const terms = keyword.split(/\s+/).filter(Boolean);
    return orgProductMappedAccountOptions.filter((option) => {
      const haystack = [
        option.entityCode,
        option.entityName,
        option.tableName,
        option.metricCode,
        option.metricName,
        option.dataAcctCode,
        option.dataAcctName,
        option.metricNodeCode,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });
  }, [addItemAccountKeyword, orgProductMappedAccountOptions]);

  const toggleItemExpanded = (section: ItemSectionType, id: number) => {
    setExpanded((prev) => ({ ...prev, [itemExpandKey(section, id)]: !(prev[itemExpandKey(section, id)] ?? true) }));
  };

  const setSectionExpanded = (section: ItemSectionType, open: boolean) => {
    const parentIds = new Set<number>();
    for (const item of items) {
      if (item.section === section && items.some((candidate) => candidate.section === section && candidate.parent_id === item.id)) {
        parentIds.add(item.id);
      }
    }
    setExpanded((prev) => {
      const next = { ...prev };
      parentIds.forEach((id) => {
        next[itemExpandKey(section, id)] = open;
      });
      return next;
    });
  };

  const toggleIndicatorExpanded = (id: number) => {
    setIndicatorExpanded((prev) => ({
      ...prev,
      [indicatorExpandKey(id)]: !(prev[indicatorExpandKey(id)] ?? true),
    }));
  };

  const setIndicatorSectionExpanded = (open: boolean) => {
    const parentIds = new Set<number>();
    for (const indicator of indicators) {
      if (indicators.some((candidate) => candidate.parent_id === indicator.id)) {
        parentIds.add(indicator.id);
      }
    }
    setIndicatorExpanded((prev) => {
      const next = { ...prev };
      parentIds.forEach((id) => {
        next[indicatorExpandKey(id)] = open;
      });
      return next;
    });
  };

  const indicatorGroupOptions = useMemo(
    () =>
      indicators
        .filter((ind) => ind.display_group)
        .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [indicators]
  );

  const numeratorLeafOptions = buildLeafOptions(items, newIndicatorNumeratorSection);
  const denominatorLeafOptions = buildLeafOptions(items, newIndicatorDenominatorSection);
  const editNumeratorLeafOptions = useMemo(
    () => (editIndicator ? buildLeafOptions(items, editIndicator.numeratorSection) : []),
    [editIndicator, items]
  );
  const editDenominatorLeafOptions = useMemo(
    () => (editIndicator ? buildLeafOptions(items, editIndicator.denominatorSection) : []),
    [editIndicator, items]
  );

  const renderItemTable = (section: ItemSectionType) => {
    const tree = buildItemTree(items, section);
    const treeRows = flattenVisibleTree(tree, expanded, section);
    const label = SECTION_LABELS[section];
    const canMoveUp = (row: ItemDto) => {
      const siblings = items
        .filter((it) => it.section === section && it.parent_id === row.parent_id)
        .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
      return siblings.findIndex((candidate) => candidate.id === row.id) > 0;
    };
    const canMoveDown = (row: ItemDto) => {
      const siblings = items
        .filter((it) => it.section === section && it.parent_id === row.parent_id)
        .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
      const index = siblings.findIndex((candidate) => candidate.id === row.id);
      return index >= 0 && index < siblings.length - 1;
    };

    return (
      <section className="rounded border border-gray-200 bg-white">
        <div className="px-4 py-2.5 border-b border-gray-200 bg-slate-50 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-slate-700">{label}细项</span>
            <span className="text-gray-400">({treeRows.length}项)</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSectionExpanded(section, false)}
              className="px-2 py-0.5 border border-gray-300 bg-white text-gray-700 rounded hover:bg-gray-50"
            >
              全部收起
            </button>
            <button
              type="button"
              onClick={() => setSectionExpanded(section, true)}
              className="px-2 py-0.5 border border-gray-300 bg-white text-gray-700 rounded hover:bg-gray-50"
            >
              全部展开
            </button>
            <button
              type="button"
              onClick={() => openAddItemDialog(section)}
              className="px-2 py-0.5 bg-blue-500 text-white rounded hover:bg-blue-600 inline-flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              添加顶级
            </button>
          </div>
        </div>
        <div className="overflow-auto">
          <table className="w-full border-collapse text-xs whitespace-nowrap">
            <thead className="bg-gray-100">
              <tr className="text-left text-gray-700">
                <th className="border border-gray-200 px-2 py-2 w-[40px]">ID</th>
                <th className="border border-gray-200 px-2 py-2">名称</th>
                <th className="border border-gray-200 px-2 py-2 w-[60px]">层级</th>
                <th className="border border-gray-200 px-2 py-2 w-[100px]">手工录入</th>
                <th className="border border-gray-200 px-2 py-2 w-[80px]">排序</th>
                <th className="border border-gray-200 px-2 py-2 w-[60px]">启用</th>
                <th className="border border-gray-200 px-2 py-2 w-[80px]">操作</th>
              </tr>
            </thead>
            <tbody>
              {treeRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-2 py-6 text-center text-gray-500">
                    暂无细项，点击右上角"+ 添加"新增
                  </td>
                </tr>
              ) : (
                treeRows.map((item) => {
                  const isParent = item.hasChildren;
                  return (
                    <tr key={item.id} className={isParent ? "bg-blue-50/40 hover:bg-blue-50/60" : "hover:bg-gray-50"}>
                      <td className="border border-gray-200 px-2 py-1.5 text-gray-500">{item.id}</td>
                      <td className="border border-gray-200 px-2 py-1.5">
                        <div className="flex items-center" style={{ paddingLeft: `${item.depth * 20}px` }}>
                          {isParent ? (
                            <button
                              type="button"
                              onClick={() => toggleItemExpanded(section, item.id)}
                              className="mr-1 rounded p-0.5 hover:bg-blue-100"
                              title={item.isExpanded ? "收起下级" : "展开下级"}
                            >
                              {item.isExpanded ? (
                                <ChevronDown className="w-3.5 h-3.5 text-blue-500" />
                              ) : (
                                <ChevronRight className="w-3.5 h-3.5 text-blue-500" />
                              )}
                            </button>
                          ) : (
                            <span className="mr-1 inline-block w-4" />
                          )}
                          {isParent ? (
                            <FolderOpen className="w-3.5 h-3.5 text-blue-500 mr-1.5 flex-shrink-0" />
                          ) : (
                            <FileText className="w-3.5 h-3.5 text-gray-400 mr-1.5 flex-shrink-0" />
                          )}
                          <span className="inline-flex min-w-0 flex-col">
                            <span className={`font-medium ${isParent ? "text-blue-700" : "text-gray-800"}`}>{item.name}</span>
                            {item.org_product_ref ? (
                              <span className="truncate font-mono text-[10px] font-normal text-blue-500">
                                {item.org_product_metric_name ? `${item.org_product_ref} ${item.org_product_metric_name}` : item.org_product_ref}
                              </span>
                            ) : null}
                          </span>
                          {!item.display_group ? (
                            <span className="ml-1.5 text-[10px] text-slate-500">
                              ({MANUAL_ENTRY_MODE_LABELS[item.manual_entry_mode]})
                            </span>
                          ) : null}
                          {item.display_group ? (
                            <span className="ml-1.5 text-[10px] text-violet-500">(分组)</span>
                          ) : isParent ? (
                            <span className="ml-1.5 text-[10px] text-blue-400">(汇总)</span>
                          ) : null}
                        </div>
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-gray-500">
                        {item.depth === 0 ? "父级" : `子${item.depth}`}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-gray-700">
                        {MANUAL_ENTRY_MODE_LABELS[item.manual_entry_mode]}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5">
                        <div className="flex items-center gap-1">
                          <span className="text-gray-700">{item.sort_order}</span>
                          <button
                            type="button"
                            onClick={() => handleMoveItem(item, "up")}
                            disabled={!canMoveUp(item) || submitting}
                            className="p-0.5 text-gray-400 hover:text-blue-600 disabled:opacity-20 disabled:cursor-not-allowed"
                            title="上移"
                          >
                            <ChevronUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleMoveItem(item, "down")}
                            disabled={!canMoveDown(item) || submitting}
                            className="p-0.5 text-gray-400 hover:text-blue-600 disabled:opacity-20 disabled:cursor-not-allowed"
                            title="下移"
                          >
                            <ChevronDown className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5">
                        <button
                          type="button"
                          onClick={() => handleToggleItem(item)}
                          disabled={submitting}
                          className={`px-2 py-0.5 rounded text-xs ${
                            item.enabled
                              ? "bg-green-100 text-green-700 hover:bg-green-200"
                              : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                          }`}
                        >
                          {item.enabled ? "启用" : "停用"}
                        </button>
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5">
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => openEditItemDialog(item)}
                            disabled={submitting}
                            className="px-1.5 py-0.5 rounded text-xs bg-amber-50 text-amber-700 hover:bg-amber-100 inline-flex items-center gap-1 disabled:opacity-50"
                            title="编辑父级或名称"
                          >
                            <Edit className="w-3 h-3" />
                            编辑
                          </button>
                          <button
                            type="button"
                            onClick={() => openAddParentDialog(item)}
                            disabled={submitting}
                            className="px-1.5 py-0.5 rounded text-xs bg-violet-50 text-violet-700 hover:bg-violet-100 inline-flex items-center gap-1 disabled:opacity-50"
                            title="在当前节点上方插入一个新上级"
                          >
                            <Plus className="w-3 h-3" />
                            上级
                          </button>
                          <button
                            type="button"
                            onClick={() => openAddItemDialog(section, item.id)}
                            disabled={submitting}
                            className="px-1.5 py-0.5 rounded text-xs bg-blue-50 text-blue-600 hover:bg-blue-100 inline-flex items-center gap-1 disabled:opacity-50"
                            title="新增下级"
                          >
                            <Plus className="w-3 h-3" />
                            下级
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteItem(item.id)}
                            disabled={submitting}
                            className="px-1.5 py-0.5 rounded text-xs bg-red-50 text-red-600 hover:bg-red-100 inline-flex items-center gap-1 disabled:opacity-50"
                          >
                            <Trash2 className="w-3 h-3" />
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  };

  const renderIndicatorTable = () => {
    const tree = buildIndicatorTree(indicators);
    const treeRows = flattenVisibleIndicatorTree(tree, indicatorExpanded);
    const canMoveUp = (row: IndicatorDto) => {
      const siblings = indicators
        .filter((it) => it.parent_id === row.parent_id)
        .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
      return siblings.findIndex((candidate) => candidate.id === row.id) > 0;
    };
    const canMoveDown = (row: IndicatorDto) => {
      const siblings = indicators
        .filter((it) => it.parent_id === row.parent_id)
        .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
      const index = siblings.findIndex((candidate) => candidate.id === row.id);
      return index >= 0 && index < siblings.length - 1;
    };

    return (
      <section className="rounded border border-gray-200 bg-white">
        <div className="px-4 py-2.5 border-b border-gray-200 bg-slate-50 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-slate-700">评估指标</span>
            <span className="text-gray-400">({treeRows.length}项)</span>
            <span className="text-[10px] text-violet-600">核心费率 / 营销费率 / 运营专项</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIndicatorSectionExpanded(false)}
              className="px-2 py-0.5 border border-gray-300 bg-white text-gray-700 rounded hover:bg-gray-50"
            >
              全部收起
            </button>
            <button
              type="button"
              onClick={() => setIndicatorSectionExpanded(true)}
              className="px-2 py-0.5 border border-gray-300 bg-white text-gray-700 rounded hover:bg-gray-50"
            >
              全部展开
            </button>
            <button
              type="button"
              onClick={openAddIndicatorDialog}
              className="px-2 py-0.5 bg-blue-500 text-white rounded hover:bg-blue-600 inline-flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              添加指标
            </button>
          </div>
        </div>
        <div className="overflow-auto">
          <table className="w-full border-collapse text-xs whitespace-nowrap">
            <thead className="bg-gray-100">
              <tr className="text-left text-gray-700">
                <th className="border border-gray-200 px-2 py-2 w-[40px]">ID</th>
                <th className="border border-gray-200 px-2 py-2">名称</th>
                <th className="border border-gray-200 px-2 py-2">分子</th>
                <th className="border border-gray-200 px-2 py-2">分母</th>
                <th className="border border-gray-200 px-2 py-2 w-[80px]">格式</th>
                <th className="border border-gray-200 px-2 py-2 w-[80px]">排序</th>
                <th className="border border-gray-200 px-2 py-2 w-[60px]">启用</th>
                <th className="border border-gray-200 px-2 py-2 w-[120px]">操作</th>
              </tr>
            </thead>
            <tbody>
              {treeRows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-2 py-6 text-center text-gray-500">
                    暂无指标，点击右上角「添加指标」新增
                  </td>
                </tr>
              ) : (
                treeRows.map((ind) => {
                  const isDisplayGroup = ind.display_group ?? false;
                  const nItem = items.find(
                    (it) => it.section === ind.numerator_section && it.id === ind.numerator_item_id
                  );
                  const dItem = items.find(
                    (it) => it.section === ind.denominator_section && it.id === ind.denominator_item_id
                  );
                  return (
                    <tr
                      key={ind.id}
                      className={ind.hasChildren || isDisplayGroup ? "bg-blue-50/40 hover:bg-blue-50/60" : "hover:bg-gray-50"}
                    >
                      <td className="border border-gray-200 px-2 py-1.5 text-gray-500">{ind.id}</td>
                      <td className="border border-gray-200 px-2 py-1.5">
                        <div className="flex items-center" style={{ paddingLeft: `${ind.depth * 20}px` }}>
                          {ind.hasChildren ? (
                            <button
                              type="button"
                              onClick={() => toggleIndicatorExpanded(ind.id)}
                              className="mr-1 rounded p-0.5 hover:bg-blue-100"
                              title={ind.isExpanded ? "收起下级" : "展开下级"}
                            >
                              {ind.isExpanded ? (
                                <ChevronDown className="w-3.5 h-3.5 text-blue-500" />
                              ) : (
                                <ChevronRight className="w-3.5 h-3.5 text-blue-500" />
                              )}
                            </button>
                          ) : (
                            <span className="mr-1 inline-block w-4" />
                          )}
                          {ind.hasChildren ? (
                            <FolderOpen className="w-3.5 h-3.5 text-blue-500 mr-1.5 flex-shrink-0" />
                          ) : (
                            <FileText className="w-3.5 h-3.5 text-gray-400 mr-1.5 flex-shrink-0" />
                          )}
                          <span className={`font-medium ${ind.hasChildren ? "text-blue-700" : "text-gray-800"}`}>
                            {ind.name}
                          </span>
                          {isDisplayGroup ? (
                            <span className="ml-1.5 text-[10px] text-violet-500">(展示分组)</span>
                          ) : null}
                        </div>
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-gray-700">
                        {isDisplayGroup ? (
                          <span className="text-gray-400">-</span>
                        ) : (
                          <>
                            {SECTION_LABELS[ind.numerator_section]}: {nItem?.name ?? `#${ind.numerator_item_id}`}
                          </>
                        )}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-gray-700">
                        {isDisplayGroup ? (
                          <span className="text-gray-400">-</span>
                        ) : (
                          <>
                            {SECTION_LABELS[ind.denominator_section]}: {dItem?.name ?? `#${ind.denominator_item_id}`}
                          </>
                        )}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5 text-gray-700">
                        {isDisplayGroup ? <span className="text-gray-400">-</span> : FORMAT_LABELS[ind.format]}
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5">
                        <div className="flex items-center gap-1">
                          <span className="text-gray-700">{ind.sort_order}</span>
                          <button
                            type="button"
                            onClick={() => handleMoveIndicator(ind, "up")}
                            disabled={!canMoveUp(ind) || submitting}
                            className="p-0.5 text-gray-400 hover:text-blue-600 disabled:opacity-20 disabled:cursor-not-allowed"
                            title="上移"
                          >
                            <ChevronUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleMoveIndicator(ind, "down")}
                            disabled={!canMoveDown(ind) || submitting}
                            className="p-0.5 text-gray-400 hover:text-blue-600 disabled:opacity-20 disabled:cursor-not-allowed"
                            title="下移"
                          >
                            <ChevronDown className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5">
                        <button
                          type="button"
                          onClick={() => handleToggleIndicator(ind)}
                          disabled={submitting}
                          className={`px-2 py-0.5 rounded text-xs ${
                            ind.enabled
                              ? "bg-green-100 text-green-700 hover:bg-green-200"
                              : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                          }`}
                        >
                          {ind.enabled ? "启用" : "停用"}
                        </button>
                      </td>
                      <td className="border border-gray-200 px-2 py-1.5">
                        <div className="flex items-center gap-1">
                          {!isDisplayGroup && (
                            <button
                              type="button"
                              onClick={() => openEditIndicatorDialog(ind)}
                              disabled={submitting}
                              className="px-1.5 py-0.5 rounded text-xs bg-blue-50 text-blue-600 hover:bg-blue-100 inline-flex items-center gap-1 disabled:opacity-50"
                            >
                              <Edit className="w-3 h-3" />
                              编辑
                            </button>
                          )}
                          {!isDisplayGroup && (
                            <button
                              type="button"
                              onClick={() => handleDeleteIndicator(ind.id)}
                              disabled={submitting}
                              className="px-1.5 py-0.5 rounded text-xs bg-red-50 text-red-600 hover:bg-red-100 inline-flex items-center gap-1 disabled:opacity-50"
                            >
                              <Trash2 className="w-3 h-3" />
                              删除
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    );
  };

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 text-xs space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] font-semibold text-slate-700">细项与指标维护</span>
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 inline-flex items-center gap-1 shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className="text-gray-600 shrink-0">当前产品</span>
            <select
              value={selectedProductCode}
              onChange={(e) => setSelectedProductCode(e.target.value)}
              className="border border-gray-300 rounded px-2 py-1.5 bg-white min-w-0 flex-1 max-w-[28rem] font-mono text-[12px]"
            >
              {runtimeProductGroups.map(({ line, items }) => (
                <optgroup key={line.product_code} label={productRuntimeGroupLabel(line)}>
                  {runtimeProducts.some((item) => item.product_code === line.product_code) ? (
                    <option value={line.product_code}>{productRuntimeLabel(line)}</option>
                  ) : null}
                  {items.map((item) => (
                    <option key={item.product_code} value={item.product_code}>
                      {productRuntimeLabel(item, { showLineSuffix: false })}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          {selectedProductMeta ? (
            <div className="flex items-center gap-1.5 text-[11px] text-slate-600 min-w-0">
              <span className="text-gray-400 shrink-0">层级</span>
              {selectedProductMeta.line && selectedProductMeta.selected.product_code !== selectedProductMeta.line.product_code ? (
                <>
                  <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 shrink-0">
                    {selectedProductMeta.line.product_code} · {selectedProductMeta.line.product_name}
                  </span>
                  <ChevronRight className="w-3 h-3 text-gray-400 shrink-0" />
                  <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-medium truncate">
                    {selectedProductMeta.selected.product_code} · {selectedProductMeta.selected.product_name}
                  </span>
                </>
              ) : (
                <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-medium truncate">
                  {selectedProductMeta.selected.product_code} · {selectedProductMeta.selected.product_name}
                  {selectedProductMeta.selected.parent_code === "CORP" ? "（群级模板）" : ""}
                </span>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {error && (
        <div className="mx-4 mt-2 px-3 py-2 bg-red-50 border border-red-200 rounded text-xs text-red-700 flex items-center justify-between">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} className="text-red-400 hover:text-red-600 ml-2">✕</button>
        </div>
      )}
      {success && (
        <div className="mx-4 mt-2 px-3 py-2 bg-emerald-50 border border-emerald-200 rounded text-xs text-emerald-700 flex items-center justify-between">
          <span>{success}</span>
          <button type="button" onClick={() => setSuccess("")} className="text-emerald-400 hover:text-emerald-600 ml-2">✕</button>
        </div>
      )}

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {renderItemTable("input")}
        {renderItemTable("output")}
        {renderIndicatorTable()}
      </div>

      <Dialog
        open={addItemOpen}
        onClose={() => {
          setAddItemOpen(false);
          setAddParentTarget(null);
        }}
        title={addParentTarget ? `新增${SECTION_LABELS[addItemSection]}上级细项` : `添加${SECTION_LABELS[addItemSection]}细项`}
      >
        <div className="space-y-4">
          {addParentTarget ? (
            <div className="rounded border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-800">
              新增的上级会插入到“{addParentTarget.name}”与其当前父级之间，并自动保留现有下级结构。
            </div>
          ) : (
            <div>
              <label className="block text-xs text-gray-600 mb-1">父级细项（留空为顶级）</label>
              <select
                value={addItemParentId ?? ""}
                onChange={(e) => setAddItemParentId(e.target.value ? Number(e.target.value) : null)}
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="">无（顶级细项）</option>
                {sectionParentOptions(addItemSection).map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {"　".repeat(opt.depth)}{opt.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <label className="flex items-center gap-2 text-xs text-gray-700">
            <input
              type="checkbox"
              checked={addItemDisplayGroup}
              onChange={(e) => {
                setAddItemDisplayGroup(e.target.checked);
                if (e.target.checked) {
                  setAddItemDataAcctCode("");
                  setAddItemManualEntryMode("disabled");
                }
              }}
            />
            创建展示分组（分组名称手填，不绑定指标）
          </label>
          <div>
            <label className="block text-xs text-gray-600 mb-1">
              {addItemDisplayGroup ? "细项名称" : "关联机构产品指标"}
            </label>
            {addItemDisplayGroup ? (
              <input
                type="text"
                value={addItemName}
                onChange={(e) => setAddItemName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleCreateItem(); }}
                placeholder="请输入展示分组名称"
                autoFocus
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            ) : (
              <div className="space-y-2">
                <input
                  type="text"
                  value={addItemAccountKeyword}
                  onChange={(e) => setAddItemAccountKeyword(e.target.value)}
                  placeholder="搜索机构产品指标、名称或编码..."
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
                <select
                  value={addItemOrgProductRef ? `org:${addItemOrgProductRef}` : ""}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (value.startsWith("org:")) {
                      const ref = value.slice(4);
                      const option = orgProductMappedAccountOptions.find((candidate) => orgProductRefForMappedAccount(candidate) === ref);
                      if (option) applyAddItemOrgProductOption(option);
                      return;
                    }
                    setAddItemDataAcctCode("");
                    setAddItemName("");
                    clearAddItemOrgProductIdentity();
                  }}
                  className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
                >
                  <option value="">请选择机构产品指标</option>
                  {filteredOrgProductMappedAccountOptions.length > 0 ? (
                    <optgroup label="机构产品指标（已确认）">
                      {filteredOrgProductMappedAccountOptions.map((option) => (
                        <option key={option.key} value={`org:${orgProductRefForMappedAccount(option)}`}>
                          {option.tableName} / {option.metricCode} {option.metricName}
                        </option>
                      ))}
                    </optgroup>
                  ) : (
                    <option value="" disabled>当前产品暂无已确认机构产品指标</option>
                  )}
                </select>
                {orgProductMappedAccountOptions.length > 0 ? (
                  <div className="text-[11px] text-gray-500">
                    当前产品有 {orgProductMappedAccountOptions.length} 条已确认机构产品指标可用于选取；未确认行不会进入该列表。
                  </div>
                ) : null}
              </div>
            )}
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">手工录入模式</label>
            <select
              value={addItemManualEntryMode}
              onChange={(e) => setAddItemManualEntryMode(e.target.value as ManualEntryMode)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
            >
              {Object.entries(MANUAL_ENTRY_MODE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => {
                setAddItemOpen(false);
                setAddParentTarget(null);
              }}
              className="px-4 py-1.5 border border-gray-300 rounded text-xs text-gray-600 hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleCreateItem}
              disabled={(!addItemDisplayGroup && !addItemDataAcctCode) || (addItemDisplayGroup && !addItemName.trim()) || submitting}
              className="px-4 py-1.5 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
            >
              {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              确认添加
            </button>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(editItem)}
        onClose={() => setEditItem(null)}
        title={editItem ? `编辑${SECTION_LABELS[editItem.section]}细项` : "编辑细项"}
      >
        {editItem && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-gray-600 mb-1">父级细项（留空为顶级）</label>
              <select
                value={editItem.parentId ?? ""}
                onChange={(e) => setEditItem({ ...editItem, parentId: e.target.value ? Number(e.target.value) : null })}
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="">无（顶级细项）</option>
                {editableParentOptions(editItem.section, editItem.id).map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {"　".repeat(opt.depth)}{opt.name}
                  </option>
                ))}
              </select>
              <div className="mt-1 text-[11px] text-gray-500">
                可直接调整父子关系，例如把“营销费用”挂到“营销支出”下面。
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-gray-700">
              <input
                type="checkbox"
                checked={editItem.displayGroup}
                onChange={(e) =>
                  setEditItem({
                    ...editItem,
                    displayGroup: e.target.checked,
                    dataAcctCode: e.target.checked ? "" : editItem.dataAcctCode,
                    manualEntryMode: e.target.checked ? "disabled" : editItem.manualEntryMode,
                    valueMode: e.target.checked ? "self" : editItem.valueMode,
                  })
                }
              />
              展示分组
            </label>
            <div>
              <label className="block text-xs text-gray-600 mb-1">
                {editItem.displayGroup ? "细项名称" : "关联机构产品指标/运行编码"}
              </label>
              {editItem.displayGroup ? (
                <input
                  type="text"
                  value={editItem.name}
                  onChange={(e) => setEditItem({ ...editItem, name: e.target.value })}
                  onKeyDown={(e) => { if (e.key === "Enter") void handleUpdateItem(); }}
                  placeholder="请输入展示分组名称"
                  autoFocus
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
              ) : (
                <select
                  value={editItem.orgProductRef ? `org:${editItem.orgProductRef}` : ""}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (value.startsWith("org:")) {
                      const ref = value.slice(4);
                      const option = orgProductMappedAccountOptions.find((candidate) => orgProductRefForMappedAccount(candidate) === ref);
                      if (option) {
                        setEditItem({
                          ...editItem,
                          name: option.metricName || editItem.name,
                          dataAcctCode: option.dataAcctCode,
                          orgProductRef: orgProductRefForMappedAccount(option),
                          orgProductEntityCode: option.entityCode,
                          orgProductTableName: option.tableName,
                          orgProductMetricCode: option.metricCode,
                          orgProductMetricName: option.metricName,
                        });
                      }
                      return;
                    }
                    setEditItem({
                      ...editItem,
                      dataAcctCode: "",
                      orgProductRef: "",
                      orgProductEntityCode: "",
                      orgProductTableName: "",
                      orgProductMetricCode: "",
                      orgProductMetricName: "",
                    });
                  }}
                  className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
                >
                  <option value="">请选择机构产品指标</option>
                  {orgProductMappedAccountOptions.length > 0 ? (
                    <optgroup label="机构产品指标（已确认）">
                      {orgProductMappedAccountOptions.map((option) => (
                        <option key={option.key} value={`org:${orgProductRefForMappedAccount(option)}`}>
                          {option.tableName} / {option.metricCode} {option.metricName}
                        </option>
                      ))}
                    </optgroup>
                  ) : (
                    <option value="" disabled>当前产品暂无已确认机构产品指标</option>
                  )}
                </select>
              )}
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">手工录入模式</label>
              <select
                value={editItem.manualEntryMode}
                onChange={(e) => setEditItem({ ...editItem, manualEntryMode: e.target.value as ManualEntryMode })}
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                {Object.entries(MANUAL_ENTRY_MODE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditItem(null)}
                className="px-4 py-1.5 border border-gray-300 rounded text-xs text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleUpdateItem()}
                disabled={(editItem.displayGroup ? !editItem.name.trim() : !editItem.dataAcctCode) || submitting}
                className="px-4 py-1.5 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
              >
                {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Edit className="w-3.5 h-3.5" />}
                保存调整
              </button>
            </div>
          </div>
        )}
      </Dialog>

      <Dialog
        open={addIndicatorOpen}
        onClose={() => setAddIndicatorOpen(false)}
        title="添加评估指标"
      >
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-600 mb-1">指标名称</label>
            <input
              type="text"
              value={newIndicatorName}
              onChange={(e) => setNewIndicatorName(e.target.value)}
              placeholder="请输入指标名称"
              autoFocus
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">机构产品指标主题（可选）</label>
            <select
              value={newIndicatorTopicMetricNodeCode}
              onChange={(e) => setNewIndicatorTopicMetricNodeCode(e.target.value)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
            >
              <option value="">不绑定主题指标</option>
              {orgProductTopicMetricOptions.map((option) => (
                <option key={option.key} value={option.value}>
                  {option.tableName} / {option.metricCode} {option.metricName}
                </option>
              ))}
            </select>
            <div className="mt-1 text-[11px] text-gray-500">
              主题仅用于评估指标口径追溯，不改变分子分母计算；仅展示已确认机构产品指标。
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">分子（被除数）</label>
            <div className="flex gap-2">
              <select
                value={newIndicatorNumeratorSection}
                onChange={(e) => {
                  setNewIndicatorNumeratorSection(e.target.value as ItemSectionType);
                  setNewIndicatorNumeratorItemId(0);
                }}
                className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="input">业务投入</option>
                <option value="output">业务产出</option>
              </select>
              <select
                value={newIndicatorNumeratorItemId}
                onChange={(e) => setNewIndicatorNumeratorItemId(Number(e.target.value))}
                className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white flex-1"
              >
                <option value={0}>选择叶子细项</option>
                {numeratorLeafOptions.map((it) => (
                  <option key={it.id} value={it.id}>
                    {"　".repeat(it.depth)}{it.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">分母（除数）</label>
            <div className="flex gap-2">
              <select
                value={newIndicatorDenominatorSection}
                onChange={(e) => {
                  setNewIndicatorDenominatorSection(e.target.value as ItemSectionType);
                  setNewIndicatorDenominatorItemId(0);
                }}
                className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="input">业务投入</option>
                <option value="output">业务产出</option>
              </select>
              <select
                value={newIndicatorDenominatorItemId}
                onChange={(e) => setNewIndicatorDenominatorItemId(Number(e.target.value))}
                className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white flex-1"
              >
                <option value={0}>选择叶子细项</option>
                {denominatorLeafOptions.map((it) => (
                  <option key={it.id} value={it.id}>
                    {"　".repeat(it.depth)}{it.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">显示格式</label>
            <select
              value={newIndicatorFormat}
              onChange={(e) => setNewIndicatorFormat(e.target.value as IndicatorFormatType)}
              className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
            >
              <option value="ratio">比率（直接显示比值）</option>
              <option value="percent">百分比（比值×100）</option>
            </select>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setAddIndicatorOpen(false)}
              className="px-4 py-1.5 border border-gray-300 rounded text-xs text-gray-600 hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleCreateIndicator}
              disabled={!newIndicatorName.trim() || !newIndicatorNumeratorItemId || !newIndicatorDenominatorItemId || submitting}
              className="px-4 py-1.5 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
            >
              {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              确认添加
            </button>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(editIndicator)}
        onClose={() => setEditIndicator(null)}
        title={editIndicator ? `编辑评估指标：${editIndicator.name}` : "编辑评估指标"}
      >
        {editIndicator && (
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">所属分组</label>
              <select
                value={editIndicator.parentId ?? ""}
                onChange={(e) =>
                  setEditIndicator({
                    ...editIndicator,
                    parentId: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="">无（顶级）</option>
                {indicatorGroupOptions.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">指标名称</label>
              <input
                type="text"
                value={editIndicator.name}
                onChange={(e) => setEditIndicator({ ...editIndicator, name: e.target.value })}
                placeholder="请输入指标名称"
                autoFocus
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">机构产品指标主题（可选）</label>
              <select
                value={editIndicator.topicMetricNodeCode ?? ""}
                onChange={(e) =>
                  setEditIndicator({
                    ...editIndicator,
                    topicMetricNodeCode: e.target.value || null,
                  })
                }
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="">不绑定主题指标</option>
                {orgProductTopicMetricOptions.map((option) => (
                  <option key={option.key} value={option.value}>
                    {option.tableName} / {option.metricCode} {option.metricName}
                  </option>
                ))}
              </select>
              <div className="mt-1 text-[11px] text-gray-500">
                主题仅用于评估指标口径追溯，不改变分子分母计算；仅展示已确认机构产品指标。
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">分子（被除数）</label>
              <div className="flex gap-2">
                <select
                  value={editIndicator.numeratorSection}
                  onChange={(e) => {
                    const section = e.target.value as ItemSectionType;
                    setEditIndicator({
                      ...editIndicator,
                      numeratorSection: section,
                      numeratorItemId: 0,
                    });
                  }}
                  className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
                >
                  <option value="input">业务投入</option>
                  <option value="output">业务产出</option>
                </select>
                <select
                  value={editIndicator.numeratorItemId}
                  onChange={(e) =>
                    setEditIndicator({ ...editIndicator, numeratorItemId: Number(e.target.value) })
                  }
                  className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white flex-1"
                >
                  <option value={0}>选择叶子细项</option>
                  {editNumeratorLeafOptions.map((it) => (
                    <option key={it.id} value={it.id}>
                      {"　".repeat(it.depth)}
                      {it.name}
                    </option>
                  ))}
                </select>
              </div>
              <select
                value={editIndicator.numeratorValueMode}
                onChange={(e) =>
                  setEditIndicator({
                    ...editIndicator,
                    numeratorValueMode: e.target.value as ValueMode,
                  })
                }
                className="mt-2 w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="tree">分子取值：子树汇总</option>
                <option value="self">分子取值：仅本节点</option>
                <option value="self_and_tree">分子取值：本节点+子树</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">分母（除数）</label>
              <div className="flex gap-2">
                <select
                  value={editIndicator.denominatorSection}
                  onChange={(e) => {
                    const section = e.target.value as ItemSectionType;
                    setEditIndicator({
                      ...editIndicator,
                      denominatorSection: section,
                      denominatorItemId: 0,
                    });
                  }}
                  className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
                >
                  <option value="input">业务投入</option>
                  <option value="output">业务产出</option>
                </select>
                <select
                  value={editIndicator.denominatorItemId}
                  onChange={(e) =>
                    setEditIndicator({ ...editIndicator, denominatorItemId: Number(e.target.value) })
                  }
                  className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white flex-1"
                >
                  <option value={0}>选择叶子细项</option>
                  {editDenominatorLeafOptions.map((it) => (
                    <option key={it.id} value={it.id}>
                      {"　".repeat(it.depth)}
                      {it.name}
                    </option>
                  ))}
                </select>
              </div>
              <select
                value={editIndicator.denominatorValueMode}
                onChange={(e) =>
                  setEditIndicator({
                    ...editIndicator,
                    denominatorValueMode: e.target.value as ValueMode,
                  })
                }
                className="mt-2 w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="tree">分母取值：子树汇总</option>
                <option value="self">分母取值：仅本节点</option>
                <option value="self_and_tree">分母取值：本节点+子树</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">显示格式</label>
              <select
                value={editIndicator.format}
                onChange={(e) =>
                  setEditIndicator({ ...editIndicator, format: e.target.value as IndicatorFormatType })
                }
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="ratio">比率（直接显示比值）</option>
                <option value="percent">百分比（比值×100）</option>
                <option value="number">数值</option>
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditIndicator(null)}
                className="px-4 py-1.5 border border-gray-300 rounded text-xs text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleUpdateIndicator()}
                disabled={
                  !editIndicator.name.trim() ||
                  !editIndicator.numeratorItemId ||
                  !editIndicator.denominatorItemId ||
                  submitting
                }
                className="px-4 py-1.5 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-1"
              >
                {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Edit className="w-3.5 h-3.5" />}
                保存调整
              </button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
