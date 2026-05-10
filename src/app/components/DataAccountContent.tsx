import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  Search,
  Plus,
  Edit,
  Trash2,
  Save,
  Download,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Calculator,
  ChevronDown,
  ChevronRight,
  Upload,
  X,
} from "lucide-react";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  buildApiUrl,
  type DataAccountDto,
  type DataAccountMetricBindingDto,
  type DataAccountMetricNodeDto,
  type DataAccountMetricTreeDto,
  type ProductTypeDto,
} from "@/lib/api";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableColumnWidths } from "@/lib/useTableColumnWidths";
import { useTableRowHeights } from "@/lib/useTableRowHeights";
import { ColumnResizeHandle } from "./ColumnResizeHandle";
import { ExcelUploadDialog } from "./ExcelUploadDialog";
import { FormulaEditorDialog } from "./FormulaEditorDialog";
import { TableRowResizeHandle } from "./TableRowResizeHandle";
import { ProductMultiSelectDialog } from "./ProductMultiSelectDialog";

type SortDirection = "asc" | "desc" | null;
type ViewMode = "metricTree" | "flat";

type MetricTreeNode = DataAccountMetricNodeDto & {
  children: MetricTreeNode[];
};

type DisplayItem = {
  row: Row;
  originalIdx: number;
};

type DataAccountHierarchyGroup = {
  key: string;
  label: string;
  depth: number;
  rows: DisplayItem[];
  children: DataAccountHierarchyGroup[];
};

interface Row {
  dbCode: string;
  bindingCode: string;
  metricNodeCode: string;
  metricPath: string;
  scopeCode: string;
  code: string;
  name: string;
  metricGroupCode: string;
  metricGroupName: string;
  budgetFormula: string;
  actualFormula: string;
  product: string;
  /** 来自 API 的 product_codes（逗号分隔），用于产品范围迁移 */
  productCodesRaw?: string | null;
  /** 与具体产品互斥；为 true 时表示适用所有产品科目（product_codes 为 null 时为 true） */
  appliesToAll?: boolean;
  valueType: string;
  remark: string;
  isNew?: boolean;
  hasBudgetDataRecords?: boolean;
  budgetDataRefCount?: number;
  reportMappingRefCount?: number;
}

const DATA_ACCT_CODE_REGEX = /^[A-Z]\d{4}$/;
const DATA_ACCT_CODE_HINT = "数据科目代码格式不正确。正确格式：1位大写字母 + 4位数字，例如：A1001。";
const isPkConflict = (msg: string) =>
  msg.includes("已存在") || msg.includes("UNIQUE") || msg.includes("unique");

function dtoToRow(d: DataAccountDto): Row {
  const budgetDataRefCount = Number(d.budget_data_ref_count ?? 0);
  const reportMappingRefCount = Number(d.report_mapping_ref_count ?? 0);
  // 新逻辑：product_codes 为 null 或空 = 全行
  const appliesToAll = d.product_codes === null || d.product_codes === undefined || d.product_codes === "";
  return {
    dbCode: d.data_acct_code,
    bindingCode: "",
    metricNodeCode: "",
    metricPath: "",
    scopeCode: "",
    code: d.data_acct_code,
    name: d.data_acct_name,
    metricGroupCode: d.metric_group_code ?? "",
    metricGroupName: d.metric_group_name ?? "",
    budgetFormula: d.budget_formula ?? "",
    actualFormula: d.actual_formula ?? "",
    product: d.product_display ?? "",
    productCodesRaw: d.product_codes ?? null,
    appliesToAll,
    valueType: d.value_type,
    remark: d.remark ?? "",
    hasBudgetDataRecords: !!d.has_budget_data_records || budgetDataRefCount > 0,
    budgetDataRefCount,
    reportMappingRefCount,
  };
}

function buildMetricPathLabels(nodes: DataAccountMetricNodeDto[]): Map<string, string> {
  const byCode = new Map(nodes.map((node) => [node.node_code, node]));
  const memo = new Map<string, string>();
  const pathFor = (code: string): string => {
    const cached = memo.get(code);
    if (cached !== undefined) return cached;
    const node = byCode.get(code);
    if (!node) return "";
    const parent = node.parent_code ? pathFor(node.parent_code) : "";
    const path = [parent, node.node_name].filter(Boolean).join(" / ");
    memo.set(code, path);
    return path;
  };
  nodes.forEach((node) => pathFor(node.node_code));
  return memo;
}

function buildProductPathLabels(products: ProductTypeDto[]): Map<string, string> {
  const byCode = new Map(products.map((product) => [product.product_code, product]));
  const memo = new Map<string, string>();
  const pathFor = (code: string): string => {
    const cached = memo.get(code);
    if (cached !== undefined) return cached;
    const product = byCode.get(code);
    if (!product) return code;
    const parent = product.parent_code ? pathFor(product.parent_code) : "";
    const path = [parent, `${product.product_code}-${product.product_name}`].filter(Boolean).join(" / ");
    memo.set(code, path);
    return path;
  };
  products.forEach((product) => pathFor(product.product_code));
  return memo;
}

export function DataAccountContent() {
  const uPfx = useUserStorageKeyPrefix();
  const { colStyle, beginColumnResize } = useTableColumnWidths(`${uPfx}::data-account-cols`, {
    minWidth: 56,
    maxWidth: 480,
  });
  const { rowStyle, beginResize } = useTableRowHeights(`${uPfx}::data-account-main`, {
    minHeight: 22,
    maxHeight: 200,
  });
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [editingCell, setEditingCell] = useState<{ rowId: number; field: string } | null>(null);
  const [searchText, setSearchText] = useState("");
  const [data, setData] = useState<Row[]>([]);
  const [viewMode] = useState<ViewMode>("flat");
  const [metricNodes, setMetricNodes] = useState<DataAccountMetricNodeDto[]>([]);
  const [metricBindings, setMetricBindings] = useState<DataAccountMetricBindingDto[]>([]);
  const [selectedMetricNode, setSelectedMetricNode] = useState<string | null>(null);
  const [collapsedMetricNodes, setCollapsedMetricNodes] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [flatProducts, setFlatProducts] = useState<{ code: string; name: string }[]>([]);
  const [productTypes, setProductTypes] = useState<ProductTypeDto[]>([]);
  const [showProductDialog, setShowProductDialog] = useState(false);
  const [editingProduct, setEditingProduct] = useState<{ rowId: number; currentCodes: string | null } | null>(
    null
  );
  const [showExcelDialog, setShowExcelDialog] = useState(false);
  const [deleteBlockedReason, setDeleteBlockedReason] = useState<string | null>(null);
  const [showFormulaDialog, setShowFormulaDialog] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [editingFormula, setEditingFormula] = useState<{
    rowId: number;
    field: "budgetFormula" | "actualFormula";
    currentValue: string;
  } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [rows, products, metricTree] = await Promise.all([
        apiGet<DataAccountDto[]>("/api/data-accounts"),
        apiGet<ProductTypeDto[]>("/api/product-types"),
        apiGet<DataAccountMetricTreeDto>("/api/data-account-metric-tree"),
      ]);
      const pathLabels = buildMetricPathLabels(metricTree.nodes ?? []);
      const productNameByCode = new Map(products.map((product) => [product.product_code, product.product_name]));
      const firstBindingByData = new Map<string, DataAccountMetricBindingDto>();
      (metricTree.bindings ?? []).forEach((binding) => {
        if (!firstBindingByData.has(binding.data_acct_code)) {
          firstBindingByData.set(binding.data_acct_code, binding);
        }
      });
      setData(rows.map((dto) => {
        const row = dtoToRow(dto);
        const binding = firstBindingByData.get(dto.data_acct_code);
        if (!binding) return row;
        return {
          ...row,
          bindingCode: binding.binding_code,
          metricNodeCode: binding.metric_node_code,
          metricPath: pathLabels.get(binding.metric_node_code) || binding.metric_node_name || "",
          scopeCode: binding.scope_code,
          product:
            binding.scope_type === "PRODUCT" && binding.scope_code
              ? `${binding.scope_code}-${binding.product_name || productNameByCode.get(binding.scope_code) || ""}`
              : row.product,
        };
      }));
      setProductTypes(products);
      setFlatProducts(products.map((p) => ({ code: p.product_code, name: p.product_name })));
      setMetricNodes(metricTree.nodes ?? []);
      setMetricBindings(metricTree.bindings ?? []);
      setSelectedMetricNode((prev) => prev ?? metricTree.nodes?.[0]?.node_code ?? null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const persistPatch = async (dbCode: string, rowId: number, patch: Record<string, unknown>) => {
    const updated = await apiPatch<DataAccountDto>(`/api/data-accounts/${encodeURIComponent(dbCode)}`, patch);
    const row = dtoToRow(updated);
    setData((prev) => prev.map((r, idx) => (idx === rowId ? row : r)));
    return updated;
  };

  const handleOpenProductSelector = (rowId: number) => {
    setEditingProduct({ rowId, currentCodes: data[rowId].productCodesRaw ?? null });
    setShowProductDialog(true);
  };

  const handleProductConfirm = async (
    products: { code: string; name: string }[],
    isAllSelected: boolean
  ) => {
    if (!editingProduct) return;
    const row = data[editingProduct.rowId];
    const newCodes = isAllSelected ? null : products.map((p) => p.code).join(",");

    // 计算 product_display（用于前端展示）
    let newDisplay = "";
    if (isAllSelected) {
      newDisplay = "适用所有产品科目";
    } else if (products.length === 0) {
      newDisplay = "未分配";
    } else if (products.length === 1) {
      newDisplay = `${products[0].code}-${products[0].name}`;
    } else {
      newDisplay = `${products[0].code} 等${products.length}个产品`;
    }

    if (row.isNew) {
      const newData = [...data];
      newData[editingProduct.rowId] = {
        ...newData[editingProduct.rowId],
        product: newDisplay,
        productCodesRaw: newCodes,
        appliesToAll: isAllSelected,
      };
      setData(newData);
      setShowProductDialog(false);
      setEditingProduct(null);
      return;
    }

    // 判断是否有变化
    const oldCodes = row.productCodesRaw ?? null;
    const changed =
      (oldCodes === null && newCodes === null && isAllSelected) ||
      (oldCodes === null && !isAllSelected && newCodes !== null && newCodes !== "") ||
      (oldCodes !== null && !isAllSelected && oldCodes !== newCodes) ||
      (oldCodes !== null && isAllSelected) ||
      (oldCodes === null && !isAllSelected && newCodes !== null && newCodes === "");

    if (!changed) {
      setShowProductDialog(false);
      setEditingProduct(null);
      return;
    }

    try {
      // 使用新的 product_codes 字段
      await persistPatch(row.dbCode, editingProduct.rowId, {
        product_codes: isAllSelected ? null : products.map((p) => p.code),
      });
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存失败");
    }
    setShowProductDialog(false);
    setEditingProduct(null);
  };

  const validateField = (field: string, value: string): { valid: boolean; message?: string } => {
    const trimmed = value.trim();
    if (field === "code") {
      if (!trimmed) return { valid: false, message: "数据科目代码不能为空。" };
      if (!DATA_ACCT_CODE_REGEX.test(trimmed)) {
        return { valid: false, message: DATA_ACCT_CODE_HINT };
      }
    }
    if (field === "name") {
      if (!trimmed) return { valid: false, message: "数据科目名称不能为空。" };
    }
    if (field === "valueType") {
      if (!trimmed) return { valid: false, message: "数值类型不能为空。" };
    }
    return { valid: true };
  };

  const refocusCell = (rowId: number, field: string) => {
    setEditingCell({ rowId, field });
    setTimeout(() => {
      const el = document.getElementById(`data-account-input-${rowId}-${field}`) as HTMLInputElement | null;
      el?.focus();
      el?.select?.();
    }, 0);
  };

  const handleCellBlur = async (rowId: number, field: string, value: string): Promise<boolean> => {
    const currentRow = data[rowId];
    const trimmedValue = value.trim();

    if (currentRow.isNew) {
      const newData = [...data];
      newData[rowId] = { ...newData[rowId], [field]: value };
      const updatedRow = newData[rowId];
      const isReadyToCreate =
        updatedRow.name.trim() &&
        updatedRow.metricNodeCode &&
        updatedRow.scopeCode &&
        updatedRow.bindingCode;
      if (isReadyToCreate) {
        const scopeErr = validateNewRowProductScope(updatedRow);
        if (scopeErr) {
          alert(scopeErr);
          return false;
        }
        try {
          const created = await apiPost<DataAccountDto>("/api/data-accounts", {
            data_acct_name: updatedRow.name.trim(),
            metric_node_code: updatedRow.metricNodeCode,
            scope_code: updatedRow.scopeCode,
            metric_binding_code: updatedRow.bindingCode,
            metric_group_code: updatedRow.metricGroupCode.trim() || null,
            metric_group_name: updatedRow.metricGroupName.trim() || null,
            product_codes: updatedRow.appliesToAll ? null : (updatedRow.productCodesRaw ? updatedRow.productCodesRaw.split(",") : null),
            budget_formula: updatedRow.budgetFormula || null,
            actual_formula: updatedRow.actualFormula || null,
            value_type: updatedRow.valueType,
            remark: updatedRow.remark || null,
          });
          const without = newData.filter((_, i) => i !== rowId);
          setData([
            {
              ...dtoToRow(created),
              bindingCode: updatedRow.bindingCode,
              metricNodeCode: updatedRow.metricNodeCode,
              metricPath: updatedRow.metricPath,
              scopeCode: updatedRow.scopeCode,
            },
            ...without,
          ]);
          setEditingCell(null);
          return true;
        } catch (e) {
          const msg = e instanceof Error ? e.message : "创建失败";
          alert(msg);
          refocusCell(rowId, isPkConflict(msg) ? "code" : field);
          return false;
        }
      }
      setData(newData);
      setEditingCell(null);
      return true;
    }

    const validation = validateField(field, value);
    if (!validation.valid) {
      alert(validation.message);
      refocusCell(rowId, field);
      return false;
    }

    const apiField =
      field === "code"
        ? { data_acct_code: trimmedValue.toUpperCase() }
        : field === "name"
        ? { data_acct_name: value }
        : field === "metricGroupCode"
        ? { metric_group_code: trimmedValue.toUpperCase() || null }
        : field === "metricGroupName"
        ? { metric_group_name: value || null }
        : field === "remark"
          ? { remark: value || null }
          : field === "valueType"
            ? { value_type: value }
            : null;

    if (apiField) {
      try {
        await persistPatch(currentRow.dbCode, rowId, apiField);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "保存失败";
        alert(msg);
        refocusCell(rowId, isPkConflict(msg) ? "code" : field);
        return false;
      }
    }

    setEditingCell(null);
    return true;
  };

  const handleAddNewRecord = () => {
    const hasIncompleteNew = data.some((row) => row.isNew);
    if (hasIncompleteNew) {
      alert("请先完成当前新增记录（填写科目名称，并选择指标树节点和产品范围）");
      return;
    }
    const newRecord: Row = {
      dbCode: "",
      bindingCode: "",
      metricNodeCode: "",
      metricPath: "",
      scopeCode: "",
      code: "",
      name: "",
      metricGroupCode: "",
      metricGroupName: "",
      budgetFormula: "",
      actualFormula: "",
      product: "适用所有产品科目",
      appliesToAll: true,
      valueType: "金额",
      remark: "",
      isNew: true,
    };
    setData([newRecord, ...data]);
    setTimeout(() => setEditingCell({ rowId: 0, field: "name" }), 0);
  };

  const handleSaveAndRefresh = async () => {
    const incomplete = data.filter(
      (row) => row.isNew && (!row.name.trim() || !row.metricNodeCode || !row.scopeCode || !row.bindingCode)
    );
    if (incomplete.length > 0) {
      if (
        !confirm(
          '存在未完成的新记录（科目名称、指标树节点或产品范围未填写完整）。\n\n点击"确定"放弃这些记录并重新加载，\n点击"取消"返回继续编辑。'
        )
      ) {
        return;
      }
    }

    // 兜底：若仍有完整但未落库的新行，点击“保存并刷新”时强制写库，避免刷新后消失。
    const pendingCreates = data.filter(
      (row) => row.isNew && row.name.trim() && row.metricNodeCode && row.scopeCode && row.bindingCode
    );
    if (pendingCreates.length > 0) {
      const errors: string[] = [];
      for (const row of pendingCreates) {
        const scopeErr = validateNewRowProductScope(row);
        if (scopeErr) {
          alert(scopeErr);
          return;
        }
        if (!row.metricNodeCode || !row.scopeCode || !row.bindingCode) {
          alert("新增数据科目必须先选择指标树节点和产品范围，系统会自动生成完整层级编码。");
          return;
        }
        try {
          await apiPost<DataAccountDto>("/api/data-accounts", {
            data_acct_name: row.name.trim(),
            metric_node_code: row.metricNodeCode,
            scope_code: row.scopeCode,
            metric_binding_code: row.bindingCode,
            metric_group_code: row.metricGroupCode.trim() || null,
            metric_group_name: row.metricGroupName.trim() || null,
            product_codes: row.appliesToAll ? null : (row.productCodesRaw ? row.productCodesRaw.split(",") : null),
            budget_formula: row.budgetFormula || null,
            actual_formula: row.actualFormula || null,
            value_type: row.valueType,
            remark: row.remark || null,
          });
        } catch (e) {
          errors.push(`${row.name || "(空名称)"}: ${e instanceof Error ? e.message : "创建失败"}`);
        }
      }
      if (errors.length > 0) {
        alert(`存在新增未保存成功：\n${errors.join("\n")}`);
        return;
      }
    }

    await refresh();
    alert("已从服务器刷新");
  };

  const handleExportExcel = async () => {
    const proceed = confirm(
      "即将导出Excel文件。\n\n默认会保存到浏览器设置的下载目录（通常为系统“下载”文件夹）。\n如果你在浏览器中配置了其它下载路径，将保存到你配置的位置。\n\n是否继续导出？"
    );
    if (!proceed) return;
    try {
      const resp = await fetch(buildApiUrl("/api/data-accounts/export"), { credentials: "include" });
      if (!resp.ok) throw new Error((await resp.text()) || "导出失败");
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") ?? "";
      const nameMatch = cd.match(/filename="?([^"]+)"?/i);
      const fileName = nameMatch?.[1] || "data_account_export.xlsx";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "导出失败");
    }
  };

  const handleSort = (column: string) => {
    let nextSortColumn: string | null = column;
    let nextSortDirection: SortDirection = "asc";
    if (sortColumn === column) {
      if (sortDirection === "asc") {
        nextSortDirection = "desc";
      } else if (sortDirection === "desc") {
        nextSortColumn = null;
        nextSortDirection = null;
      }
    }

    setSortColumn(nextSortColumn);
    setSortDirection(nextSortDirection);
    if (!nextSortColumn || !nextSortDirection) return;

    const col = nextSortColumn as keyof Row;
    setData((prev) =>
      [...prev].sort((a, b) => {
        const va = String(a[col] ?? "");
        const vb = String(b[col] ?? "");
        const c = va.localeCompare(vb, "zh-CN");
        return nextSortDirection === "asc" ? c : -c;
      })
    );
  };

  const handleCellEdit = (rowId: number, field: string, value: string) => {
    const newData = [...data];
    newData[rowId] = { ...newData[rowId], [field]: value };
    setData(newData);
  };

  const metricPathLabels = useMemo(() => buildMetricPathLabels(metricNodes), [metricNodes]);
  const metricNodeOptions = useMemo(
    () => {
      const parentCodes = new Set(metricNodes.map((node) => node.parent_code).filter(Boolean));
      return [...metricNodes]
        .filter((node) => !parentCodes.has(node.node_code))
        .sort((a, b) => a.node_code.localeCompare(b.node_code, "zh-CN"))
        .map((node) => ({
          code: node.node_code,
          label: `${node.node_code} ${metricPathLabels.get(node.node_code) || node.node_name}`,
        }));
    },
    [metricNodes, metricPathLabels]
  );
  const productPathLabels = useMemo(() => buildProductPathLabels(productTypes), [productTypes]);
  const productNameByCode = useMemo(
    () => new Map(productTypes.map((product) => [product.product_code, product.product_name])),
    [productTypes]
  );
  const getProductScopeLabel = useCallback(
    (scopeCode: string): string => {
      if (!scopeCode) return "未绑定产品范围";
      if (scopeCode === "CORP") return "全行";
      const productName = productNameByCode.get(scopeCode);
      return productName ? `${scopeCode}-${productName}` : scopeCode;
    },
    [productNameByCode]
  );
  const productScopeOptions = useMemo(
    () => {
      const parentCodes = new Set(productTypes.map((product) => product.parent_code).filter(Boolean));
      return [...productTypes]
        .filter((product) => !parentCodes.has(product.product_code))
        .sort((a, b) => a.product_code.localeCompare(b.product_code, "zh-CN"))
        .map((product) => ({
          code: product.product_code,
          label: productPathLabels.get(product.product_code) || `${product.product_code}-${product.product_name}`,
          name: product.product_name,
        }));
    },
    [productPathLabels, productTypes]
  );

  const handleNewRowMetricNodeChange = (rowId: number, metricNodeCode: string) => {
    setData((prev) => {
      const next = [...prev];
      const row = next[rowId];
      if (!row?.isNew) return prev;
      const metricPath = metricNodeCode ? metricPathLabels.get(metricNodeCode) || "" : "";
      next[rowId] = {
        ...row,
        metricNodeCode,
        metricPath,
        bindingCode: metricNodeCode && row.scopeCode ? `${metricNodeCode}.${row.scopeCode}` : "",
      };
      return next;
    });
  };

  const handleNewRowProductScopeChange = (rowId: number, scopeCode: string) => {
    setData((prev) => {
      const next = [...prev];
      const row = next[rowId];
      if (!row?.isNew) return prev;
      const product = productScopeOptions.find((item) => item.code === scopeCode);
      next[rowId] = {
        ...row,
        scopeCode,
        bindingCode: row.metricNodeCode && scopeCode ? `${row.metricNodeCode}.${scopeCode}` : "",
        product: product ? `${product.code}-${product.name}` : "",
        productCodesRaw: scopeCode || null,
        appliesToAll: false,
      };
      return next;
    });
  };

  const handleValueTypeChange = async (rowId: number, value: string) => {
    const row = data[rowId];
    handleCellEdit(rowId, "valueType", value);
    if (!row.isNew) {
      try {
        await persistPatch(row.dbCode, rowId, { value_type: value });
      } catch (e) {
        alert(e instanceof Error ? e.message : "保存失败");
        void refresh();
      }
    }
  };

  const handleOpenFormulaEditor = (rowId: number, field: "budgetFormula" | "actualFormula") => {
    setEditingFormula({ rowId, field, currentValue: data[rowId][field] });
    setShowFormulaDialog(true);
  };

  const handleFormulaConfirm = async (formula: string) => {
    if (!editingFormula) return;
    const row = data[editingFormula.rowId];
    const patch =
      editingFormula.field === "budgetFormula"
        ? { budget_formula: formula || null }
        : { actual_formula: formula || null };
    if (row.isNew) {
      const newData = [...data];
      newData[editingFormula.rowId] = { ...newData[editingFormula.rowId], [editingFormula.field]: formula };
      setData(newData);
    } else {
      try {
        await persistPatch(row.dbCode, editingFormula.rowId, patch);
      } catch (e) {
        alert(e instanceof Error ? e.message : "保存失败");
      }
    }
    setShowFormulaDialog(false);
    setEditingFormula(null);
  };

  const getCodeLockReason = (row: Row): string | null => {
    const reasons: string[] = [];
    const mappingCount = row.reportMappingRefCount ?? 0;
    const budgetCount = row.budgetDataRefCount ?? 0;
    if (mappingCount > 0) {
      reasons.push(`该数据科目已经和报告科目建立映射（${mappingCount} 条）`);
    }
    if (budgetCount > 0 || row.hasBudgetDataRecords) {
      reasons.push(`该数据科目已在预算数据库中有数据（${budgetCount > 0 ? `${budgetCount} 条` : "已存在记录"}）`);
    }
    if (reasons.length === 0) return null;
    return `${reasons.join("，")}，因此科目代码不能修改。`;
  };

  const getDeleteDisabledReason = (row: Row): string | null => {
    const reasons: string[] = [];
    const mappingCount = row.reportMappingRefCount ?? 0;
    const budgetCount = row.budgetDataRefCount ?? 0;
    if (mappingCount > 0) {
      reasons.push(`该数据科目已经和报告科目建立映射（${mappingCount} 条）`);
    }
    if (budgetCount > 0 || row.hasBudgetDataRecords) {
      reasons.push(`该数据科目已在预算数据库中有数据（${budgetCount > 0 ? `${budgetCount} 条` : "已存在记录"}）`);
    }
    if (reasons.length === 0) return null;
    return `${reasons.join("，")}，因此不能删除。`;
  };

  const handleDeleteRow = async (rowId: number) => {
    const row = data[rowId];
    if (row.isNew) {
      setData(data.filter((_, i) => i !== rowId));
      return;
    }
    const deleteDisabledReason = getDeleteDisabledReason(row);
    if (deleteDisabledReason) {
      setDeleteBlockedReason(deleteDisabledReason);
      return;
    }
    if (!confirm(`确定删除数据科目 ${row.code}？`)) return;
    try {
      await apiDelete(`/api/data-accounts/${encodeURIComponent(row.dbCode || row.code)}`);
      setData(data.filter((_, i) => i !== rowId));
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
  };

  const dataAccountFields = [
    { key: "metricBindingCode", label: "完整层级编码", required: false },
    { key: "metricPath", label: "指标路径", required: false },
    { key: "metricNodeCode", label: "指标口径编码", required: false },
    { key: "scopeCode", label: "产品范围码", required: false },
    { key: "code", label: "数据科目代码", required: true },
    { key: "name", label: "数据科目名称", required: true },
    { key: "metricGroupCode", label: "指标族编码", required: false },
    { key: "metricGroupName", label: "指标族名称", required: false },
    { key: "budgetFormula", label: "预算数计算公式", required: false },
    { key: "actualFormula", label: "实际数计算公式", required: false },
    { key: "product", label: "产品科目代码", required: false },
    { key: "valueType", label: "数值类型", required: true },
    { key: "remark", label: "备注", required: false },
  ];

  const getSortIcon = (column: string) => {
    if (sortColumn !== column) return <ArrowUpDown className="w-3 h-3 text-gray-400" />;
    return sortDirection === "asc" ? (
      <ArrowUp className="w-3 h-3 text-blue-600" />
    ) : (
      <ArrowDown className="w-3 h-3 text-blue-600" />
    );
  };

  let displayData = data.map((row, originalIdx) => ({ row, originalIdx }));
  if (searchText) {
    const s = searchText.toLowerCase();
    displayData = displayData.filter(
      ({ row }) =>
        row.code.toLowerCase().includes(s) ||
        row.bindingCode.toLowerCase().includes(s) ||
        row.metricPath.toLowerCase().includes(s) ||
        row.scopeCode.toLowerCase().includes(s) ||
        getProductScopeLabel(row.scopeCode).toLowerCase().includes(s) ||
        row.name.toLowerCase().includes(s) ||
        row.metricGroupCode.toLowerCase().includes(s) ||
        row.metricGroupName.toLowerCase().includes(s) ||
        row.budgetFormula.toLowerCase().includes(s) ||
        row.actualFormula.toLowerCase().includes(s) ||
        row.product.toLowerCase().includes(s) ||
        row.valueType.toLowerCase().includes(s) ||
        row.remark.toLowerCase().includes(s)
    );
  }

  const isSearching = searchText.length > 0;
  const groupedDisplayData = displayData.reduce<DataAccountHierarchyGroup[]>((groups, item) => {
    const pathParts = item.row.metricPath
      ? item.row.metricPath.split("/").map((part) => part.trim()).filter(Boolean)
      : ["未绑定指标树"];
    let currentGroups = groups;
    let currentKey = "";
    pathParts.forEach((part, index) => {
      currentKey = currentKey ? `${currentKey}/${part}` : part;
      let group = currentGroups.find((g) => g.key === currentKey);
      if (!group) {
        group = {
          key: currentKey,
          label: part,
          depth: index,
          rows: [],
          children: [],
        };
        currentGroups.push(group);
      }
      if (index === pathParts.length - 1) {
        group.rows.push(item);
      }
      currentGroups = group.children;
    });
    return groups;
  }, []);

  const toggleGroup = (key: string) => {
    setCollapsedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const metricTreeRoots = useMemo(() => {
    const byCode = new Map<string, MetricTreeNode>();
    metricNodes.forEach((node) => {
      byCode.set(node.node_code, { ...node, children: [] });
    });
    const roots: MetricTreeNode[] = [];
    byCode.forEach((node) => {
      if (node.parent_code && byCode.has(node.parent_code)) {
        byCode.get(node.parent_code)!.children.push(node);
      } else {
        roots.push(node);
      }
    });
    const sortTree = (nodes: MetricTreeNode[]) => {
      nodes.sort((a, b) => a.node_code.localeCompare(b.node_code, "zh-CN"));
      nodes.forEach((node) => sortTree(node.children));
    };
    sortTree(roots);
    return roots;
  }, [metricNodes]);

  const metricDescendantsByNode = useMemo(() => {
    const childMap = new Map<string, string[]>();
    metricNodes.forEach((node) => {
      if (!node.parent_code) return;
      childMap.set(node.parent_code, [...(childMap.get(node.parent_code) ?? []), node.node_code]);
    });
    const collect = (code: string): string[] => {
      const children = childMap.get(code) ?? [];
      return [code, ...children.flatMap(collect)];
    };
    const result = new Map<string, Set<string>>();
    metricNodes.forEach((node) => result.set(node.node_code, new Set(collect(node.node_code))));
    return result;
  }, [metricNodes]);

  const selectedMetricBindings = useMemo(() => {
    if (!selectedMetricNode) return metricBindings;
    const descendantCodes = metricDescendantsByNode.get(selectedMetricNode) ?? new Set([selectedMetricNode]);
    return metricBindings.filter((binding) => descendantCodes.has(binding.metric_node_code));
  }, [metricBindings, metricDescendantsByNode, selectedMetricNode]);

  const toggleMetricNode = (nodeCode: string) => {
    setCollapsedMetricNodes((prev) => ({ ...prev, [nodeCode]: !prev[nodeCode] }));
  };

  const renderMetricNode = (node: MetricTreeNode, depth = 0): JSX.Element => {
    const hasChildren = node.children.length > 0;
    const collapsed = !!collapsedMetricNodes[node.node_code];
    const isSelected = selectedMetricNode === node.node_code;
    const directBindingCount = metricBindings.filter((binding) => binding.metric_node_code === node.node_code).length;
    return (
      <Fragment key={node.node_code}>
        <button
          type="button"
          onClick={() => setSelectedMetricNode(node.node_code)}
          className={`flex w-full items-center gap-1.5 px-2 py-1 text-left text-xs ${
            isSelected ? "bg-blue-50 text-blue-700" : "text-slate-700 hover:bg-slate-50"
          }`}
          style={{ paddingLeft: `${8 + depth * 16}px` }}
        >
          <span
            role="button"
            tabIndex={-1}
            onClick={(event) => {
              event.stopPropagation();
              if (hasChildren) toggleMetricNode(node.node_code);
            }}
            className="inline-flex h-4 w-4 items-center justify-center"
          >
            {hasChildren ? (
              collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <span className="h-3.5 w-3.5" />
            )}
          </span>
          <span className="font-mono text-[11px] text-slate-500">{node.node_code}</span>
          <span className="truncate">{node.node_name}</span>
          {directBindingCount > 0 && (
            <span className="ml-auto rounded bg-white px-1.5 py-0.5 text-[10px] text-slate-500">{directBindingCount}</span>
          )}
        </button>
        {!collapsed && node.children.map((child) => renderMetricNode(child, depth + 1))}
      </Fragment>
    );
  };

  const countHierarchyRows = (group: DataAccountHierarchyGroup): number =>
    group.rows.length + group.children.reduce((sum, child) => sum + countHierarchyRows(child), 0);

  const renderDataAccountRow = (row: Row, originalIdx: number) => {
    const accRowKey = `acc-row-${originalIdx}`;
    return (
      <tr
        key={`row-${originalIdx}`}
        style={rowStyle(accRowKey)}
        className={`border-b border-gray-200 ${row.isNew ? "bg-yellow-50 hover:bg-yellow-100" : "hover:bg-gray-50"}`}
      >
        <td className="px-2 py-0.5 border-r border-gray-200 font-mono text-slate-700" style={colStyle("acc-bindingCode", 160)}>
          {row.isNew ? (
            <div className="space-y-1">
              <select
                value={row.metricNodeCode}
                onChange={(e) => handleNewRowMetricNodeChange(originalIdx, e.target.value)}
                className="w-full px-1 py-0.5 text-[11px] border border-gray-300 rounded bg-white font-sans"
                title="选择指标树节点"
              >
                <option value="">选择指标树节点</option>
                {metricNodeOptions.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
              <div className="truncate text-[10px] text-slate-500" title={row.bindingCode || "选择产品范围后自动生成"}>
                {row.bindingCode || "自动生成完整层级编码"}
              </div>
            </div>
          ) : (
            row.bindingCode || <span className="text-gray-400">未绑定</span>
          )}
        </td>
        <td className="px-2 py-0.5 border-r border-gray-200 text-slate-700" style={colStyle("acc-metricPath", 240)}>
          <span title={row.metricPath}>{row.metricPath || <span className="text-gray-400">未绑定指标树</span>}</span>
        </td>
        <td className="px-2 py-0.5 border-r border-gray-200 font-mono text-slate-600" style={colStyle("acc-scopeCode", 160)}>
          {row.isNew ? (
            <select
              value={row.scopeCode}
              onChange={(e) => handleNewRowProductScopeChange(originalIdx, e.target.value)}
              className="w-full px-1 py-0.5 text-[11px] border border-gray-300 rounded bg-white font-sans"
              title="选择产品范围"
            >
              <option value="">选择产品</option>
              {productScopeOptions.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : (
            <span title={row.scopeCode}>{getProductScopeLabel(row.scopeCode)}</span>
          )}
        </td>
        <td className="relative px-2 py-0.5 pb-1.5 border-r border-gray-200" style={colStyle("acc-code", 100)}>
          {row.isNew ? (
            <div className="rounded bg-gray-50 px-1 py-0.5 font-mono text-[11px] text-gray-500" title="保存成功后由系统自动生成">
              保存后系统生成
            </div>
          ) : editingCell?.rowId === originalIdx && editingCell?.field === "code" ? (
            <input
              type="text"
              id={`data-account-input-${originalIdx}-code`}
              value={row.code}
              onChange={(e) => handleCellEdit(originalIdx, "code", e.target.value)}
              onBlur={(e) => void handleCellBlur(originalIdx, "code", e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === "Tab") {
                  e.preventDefault();
                  void (async () => {
                    const ok = await handleCellBlur(originalIdx, "code", e.currentTarget.value);
                    if (ok) setEditingCell({ rowId: originalIdx, field: "name" });
                  })();
                }
              }}
              autoFocus
              className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
            />
          ) : (
            <div
              role="button"
              tabIndex={0}
              onClick={() => {
                const codeLockReason = getCodeLockReason(row);
                if (codeLockReason && !row.isNew) {
                  alert(codeLockReason);
                  return;
                }
                setEditingCell({ rowId: originalIdx, field: "code" });
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const codeLockReason = getCodeLockReason(row);
                  if (codeLockReason && !row.isNew) {
                    alert(codeLockReason);
                    return;
                  }
                  setEditingCell({ rowId: originalIdx, field: "code" });
                }
              }}
              className="cursor-text font-mono text-gray-700 hover:bg-blue-50 px-1 rounded min-h-[18px] w-full"
            >
              {row.code || <span className="text-gray-400">点击输入科目代码</span>}
            </div>
          )}
          <TableRowResizeHandle onResizeStart={(e) => beginResize(accRowKey, e)} />
        </td>
        <td className="px-2 py-0.5 border-r border-gray-200" style={colStyle("acc-name", 200)}>
          {editingCell?.rowId === originalIdx && editingCell?.field === "name" ? (
            <input
              type="text"
              id={`data-account-input-${originalIdx}-name`}
              value={row.name}
              onChange={(e) => handleCellEdit(originalIdx, "name", e.target.value)}
              onBlur={(e) => void handleCellBlur(originalIdx, "name", e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void handleCellBlur(originalIdx, "name", e.currentTarget.value);
                }
              }}
              autoFocus
              className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
            />
          ) : (
            <div
              role="button"
              tabIndex={0}
              onClick={() => setEditingCell({ rowId: originalIdx, field: "name" })}
              onKeyDown={(e) => e.key === "Enter" && setEditingCell({ rowId: originalIdx, field: "name" })}
              className="cursor-text text-gray-700 hover:bg-blue-50 px-1 rounded min-h-[18px] w-full"
            >
              {row.name || <span className="text-gray-400">点击输入科目名称</span>}
            </div>
          )}
        </td>
        <td className="px-2 py-0.5 bg-gray-50 border-r border-gray-200" style={colStyle("acc-budgetFormula", 200)}>
          <div className="flex items-start justify-between gap-1">
            <span
              className="text-gray-500 text-[10px] font-mono flex-1 whitespace-normal break-all leading-4 overflow-hidden"
              style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", maxHeight: "2rem" }}
              title={row.budgetFormula || "-"}
            >
              {row.budgetFormula || "-"}
            </span>
            <button
              type="button"
              onClick={() => handleOpenFormulaEditor(originalIdx, "budgetFormula")}
              className="ml-1 p-0.5 hover:bg-blue-200 rounded flex-shrink-0 transition-colors"
              title="编辑公式"
            >
              <Calculator className="w-4 h-4 text-blue-600" />
            </button>
          </div>
        </td>
        <td className="px-2 py-0.5 bg-gray-50 border-r border-gray-200" style={colStyle("acc-actualFormula", 200)}>
          <div className="flex items-start justify-between gap-1">
            <span
              className="text-gray-500 text-[10px] font-mono flex-1 whitespace-normal break-all leading-4 overflow-hidden"
              style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", maxHeight: "2rem" }}
              title={row.actualFormula || "-"}
            >
              {row.actualFormula || "-"}
            </span>
            <button
              type="button"
              onClick={() => handleOpenFormulaEditor(originalIdx, "actualFormula")}
              className="ml-1 p-0.5 hover:bg-blue-200 rounded flex-shrink-0 transition-colors"
              title="编辑公式"
            >
              <Calculator className="w-4 h-4 text-blue-600" />
            </button>
          </div>
        </td>
        <td className="px-2 py-0.5 border-r border-gray-200" style={colStyle("acc-product", 160)}>
          {row.isNew ? (
            <div className="truncate rounded border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-gray-600" title={row.product || "由产品范围决定"}>
              {row.product || "由产品范围决定"}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => handleOpenProductSelector(originalIdx)}
              className="w-full px-2 py-0.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 flex items-center justify-between gap-1 text-left"
            >
              <span className="flex-1 truncate">{row.product || "选择产品"}</span>
              <ChevronDown className="w-3 h-3 text-gray-600 flex-shrink-0" />
            </button>
          )}
        </td>
        <td className="px-2 py-0.5 text-center border-r border-gray-200" style={colStyle("acc-valueType", 96)}>
          <select
            value={row.valueType}
            onChange={(e) => void handleValueTypeChange(originalIdx, e.target.value)}
            className="px-2 py-0.5 text-xs border border-gray-300 rounded bg-white"
          >
            <option>金额</option>
            <option>百分比</option>
            <option>户数</option>
          </select>
        </td>
        <td className="px-2 py-0.5 text-center border-r border-gray-200" style={colStyle("acc-actions", 72)}>
          <div className="flex items-center justify-center gap-1">
            <button
              type="button"
              onClick={() => setEditingCell({ rowId: originalIdx, field: "name" })}
              className="p-1 hover:bg-gray-200 rounded"
              title="编辑（定位到可编辑字段）"
            >
              <Edit className="w-4 h-4 text-gray-600" />
            </button>
            <button
              type="button"
              onClick={() => {
                const reason = getDeleteDisabledReason(row);
                if (reason) {
                  setDeleteBlockedReason(reason);
                  return;
                }
                void handleDeleteRow(originalIdx);
              }}
              className={`p-1 rounded ${getDeleteDisabledReason(row) ? "cursor-not-allowed opacity-50" : "hover:bg-gray-200"}`}
              title={getDeleteDisabledReason(row) || "删除"}
            >
              <Trash2 className="w-4 h-4 text-gray-600" />
            </button>
          </div>
        </td>
        <td className="px-2 py-0.5" style={colStyle("acc-remark", 180)}>
          {editingCell?.rowId === originalIdx && editingCell?.field === "remark" ? (
            <input
              type="text"
              id={`data-account-input-${originalIdx}-remark`}
              value={row.remark}
              onChange={(e) => handleCellEdit(originalIdx, "remark", e.target.value)}
              onBlur={(e) => void handleCellBlur(originalIdx, "remark", e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void handleCellBlur(originalIdx, "remark", e.currentTarget.value);
                }
              }}
              autoFocus
              className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
            />
          ) : (
            <div
              role="button"
              tabIndex={0}
              onClick={() => setEditingCell({ rowId: originalIdx, field: "remark" })}
              className="cursor-text text-gray-600 hover:bg-blue-50 px-1 rounded min-w-[100px]"
            >
              {row.remark || "-"}
            </div>
          )}
        </td>
      </tr>
    );
  };

  const renderHierarchyGroup = (group: DataAccountHierarchyGroup): JSX.Element => {
    const collapsed = !isSearching && !!collapsedGroups[group.key];
    const rowCount = countHierarchyRows(group);
    return (
      <Fragment key={`group-${group.key}`}>
        <tr className="border-b border-gray-300 bg-slate-100">
          <td colSpan={11} className="px-3 py-1.5">
            <button
              type="button"
              onClick={() => toggleGroup(group.key)}
              className="flex w-full items-center gap-2 text-left text-xs font-medium text-slate-700"
              style={{ paddingLeft: `${group.depth * 18}px` }}
            >
              {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              <span>{group.label}</span>
              <span className="rounded bg-white px-1.5 py-0.5 text-[10px] text-slate-500">
                第 {group.depth + 1} 层
              </span>
              <span className="text-[10px] text-slate-500">共 {rowCount} 条数据科目</span>
            </button>
          </td>
        </tr>
        {!collapsed && group.children.map((child) => renderHierarchyGroup(child))}
        {!collapsed && group.rows.map(({ row, originalIdx }) => renderDataAccountRow(row, originalIdx))}
      </Fragment>
    );
  };

  if (loading && data.length === 0) {
    return (
      <div className="p-4 text-xs text-gray-600">加载数据科目…</div>
    );
  }

  return (
    <div className="p-4 h-full flex flex-col">
      {loadError && (
        <div className="mb-2 text-xs text-red-600">
          {loadError}（请确认后端已启动，且 VITE_API_BASE 指向正确）
        </div>
      )}
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">数据科目维护</h3>
        <div className="flex-1" />
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索科目..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-48 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          {searchText && (
            <button
              type="button"
              onClick={() => setSearchText("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded transition-colors"
              title="清除搜索"
            >
              <X className="w-3.5 h-3.5 text-gray-500" />
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => setShowExcelDialog(true)}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954]"
        >
          <Upload className="w-3 h-3" />
          Excel上传科目
        </button>
        <button
          type="button"
          onClick={() => void handleExportExcel()}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-[#16a085] text-white rounded hover:bg-[#138d75]"
        >
          <Download className="w-3 h-3" />
          Excel格式导出
        </button>
        <button
          type="button"
          onClick={handleAddNewRecord}
          disabled={isSearching}
          className={`flex items-center gap-1 px-3 py-1 text-xs rounded ${
            isSearching ? "bg-gray-300 text-gray-500 cursor-not-allowed" : "bg-[#3498db] text-white hover:bg-[#2980b9]"
          }`}
        >
          <Plus className="w-3 h-3" />
          新增数据科目
        </button>
        <button
          type="button"
          onClick={() => void handleSaveAndRefresh()}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-[#e67e22] text-white rounded hover:bg-[#d35400]"
        >
          <Save className="w-3 h-3" />
          保存并刷新
        </button>
      </div>

      {viewMode === "metricTree" ? (
        <div className="flex-1 min-h-0 grid grid-cols-[360px_minmax(0,1fr)] border border-gray-300 rounded overflow-hidden bg-white">
          <div className="border-r border-gray-200 overflow-auto bg-slate-50">
            <div className="sticky top-0 z-10 border-b border-gray-200 bg-slate-100 px-3 py-2 text-xs font-medium text-slate-700">
              指标口径树
            </div>
            <div className="py-1">
              {metricTreeRoots.length === 0 ? (
                <div className="px-3 py-2 text-xs text-slate-500">暂无指标树节点</div>
              ) : (
                metricTreeRoots.map((node) => renderMetricNode(node))
              )}
            </div>
          </div>
          <div className="overflow-auto">
            <table className="min-w-full text-xs border-collapse">
              <thead className="sticky top-0 z-20 bg-gray-100 border-b border-gray-300">
                <tr>
                  <th className="px-2 py-1 text-left font-medium text-gray-700 border-r border-gray-200">完整层级编码</th>
                  <th className="px-2 py-1 text-left font-medium text-gray-700 border-r border-gray-200">产品范围</th>
                  <th className="px-2 py-1 text-left font-medium text-gray-700 border-r border-gray-200">产品</th>
                  <th className="px-2 py-1 text-left font-medium text-gray-700 border-r border-gray-200">数据科目代码</th>
                  <th className="px-2 py-1 text-left font-medium text-gray-700 border-r border-gray-200">数据科目名称</th>
                  <th className="px-2 py-1 text-left font-medium text-gray-700">指标口径</th>
                </tr>
              </thead>
              <tbody>
                {selectedMetricBindings.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-xs text-gray-500">
                      当前节点下暂无绑定
                    </td>
                  </tr>
                ) : (
                  selectedMetricBindings.map((binding) => (
                    <tr key={binding.binding_code} className="border-b border-gray-100 hover:bg-blue-50/40">
                      <td className="px-2 py-1 border-r border-gray-100 font-mono text-slate-700">{binding.binding_code}</td>
                      <td className="px-2 py-1 border-r border-gray-100">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] ${binding.scope_type === "CORP" ? "bg-slate-100 text-slate-600" : "bg-blue-50 text-blue-700"}`}>
                          {binding.scope_type === "CORP" ? "全行" : "产品"}
                        </span>
                      </td>
                      <td className="px-2 py-1 border-r border-gray-100">
                        {binding.scope_type === "CORP" ? (
                          <span className="text-gray-500">CORP</span>
                        ) : (
                          <span>{binding.product_code} {binding.product_name ? `- ${binding.product_name}` : ""}</span>
                        )}
                      </td>
                      <td className="px-2 py-1 border-r border-gray-100 font-mono text-slate-600">{binding.data_acct_code}</td>
                      <td className="px-2 py-1 border-r border-gray-100">{binding.data_acct_name}</td>
                      <td className="px-2 py-1">{binding.metric_node_code} {binding.metric_node_name}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
      <div className="flex-1 border border-gray-300 rounded overflow-auto">
        <table className="text-xs border-collapse" style={{ minWidth: "100%" }}>
          <thead className="bg-gray-100 border-b border-gray-300 sticky top-0 z-30">
            <tr>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-bindingCode", 160)}
              >
                <button type="button" onClick={() => handleSort("bindingCode")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  完整层级编码
                  {getSortIcon("bindingCode")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-bindingCode", e, 160)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-metricPath", 240)}
              >
                <button type="button" onClick={() => handleSort("metricPath")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  指标路径
                  {getSortIcon("metricPath")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-metricPath", e, 240)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-scopeCode", 160)}
              >
                <button type="button" onClick={() => handleSort("scopeCode")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  产品范围码
                  {getSortIcon("scopeCode")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-scopeCode", e, 160)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-code", 100)}
              >
                <button type="button" onClick={() => handleSort("code")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  数据科目代码
                  {getSortIcon("code")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-code", e, 100)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-name", 200)}
              >
                <button type="button" onClick={() => handleSort("name")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  数据科目名称
                  {getSortIcon("name")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-name", e, 200)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-budgetFormula", 200)}
              >
                <button type="button" onClick={() => handleSort("budgetFormula")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  预算数计算公式
                  {getSortIcon("budgetFormula")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-budgetFormula", e, 200)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-actualFormula", 200)}
              >
                <button type="button" onClick={() => handleSort("actualFormula")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  实际数计算公式
                  {getSortIcon("actualFormula")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-actualFormula", e, 200)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-product", 160)}
              >
                <button type="button" onClick={() => handleSort("product")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  产品科目
                  {getSortIcon("product")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-product", e, 160)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-center text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-valueType", 96)}
              >
                <button type="button" onClick={() => handleSort("valueType")} className="flex items-center gap-1 hover:text-blue-600 transition-colors mx-auto">
                  数值类型
                  {getSortIcon("valueType")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-valueType", e, 96)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-center text-gray-700 font-medium border-r border-gray-200 bg-gray-100"
                style={colStyle("acc-actions", 72)}
              >
                操作
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-actions", e, 72)} />
              </th>
              <th
                className="relative px-2 py-1 pr-2.5 text-xs text-left text-gray-700 font-medium bg-gray-100"
                style={colStyle("acc-remark", 180)}
              >
                <button type="button" onClick={() => handleSort("remark")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  备注
                  {getSortIcon("remark")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-remark", e, 180)} />
              </th>
            </tr>
          </thead>
          <tbody className="bg-white">
            {groupedDisplayData.map((group) => renderHierarchyGroup(group))}
            {false && groupedDisplayData.map((group) => {
              const collapsed = !isSearching && !!collapsedGroups[group.key];
              const groupLabel = group.label || "未分组指标";
              const groupCodeLabel = `第 ${group.depth + 1} 层`;
              return (
                <Fragment key={`group-${group.key}`}>
                  <tr key={`group-${group.key}`} className="border-b border-gray-300 bg-slate-100">
                    <td colSpan={11} className="px-3 py-1.5">
                      <button
                        type="button"
                        onClick={() => toggleGroup(group.key)}
                        className="flex w-full items-center gap-2 text-left text-xs font-medium text-slate-700"
                      >
                        {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                        <span>{groupLabel}</span>
                        <span className="rounded bg-white px-1.5 py-0.5 text-[10px] text-slate-500">{groupCodeLabel}</span>
                        <span className="text-[10px] text-slate-500">共 {group.rows.length} 条数据科目</span>
                      </button>
                    </td>
                  </tr>
                  {!collapsed &&
                    group.rows.map(({ row, originalIdx }) => {
                      const accRowKey = `acc-row-${originalIdx}`;
                      return (
              <tr
                key={`row-${originalIdx}`}
                style={rowStyle(accRowKey)}
                className={`border-b border-gray-200 ${row.isNew ? "bg-yellow-50 hover:bg-yellow-100" : "hover:bg-gray-50"}`}
              >
                <td className="px-2 py-0.5 border-r border-gray-200 font-mono text-slate-700" style={colStyle("acc-bindingCode", 160)}>
                  {row.bindingCode || <span className="text-gray-400">未绑定</span>}
                </td>
                <td className="px-2 py-0.5 border-r border-gray-200 text-slate-700" style={colStyle("acc-metricPath", 240)}>
                  <span title={row.metricPath}>{row.metricPath || <span className="text-gray-400">未绑定指标树</span>}</span>
                </td>
                <td className="px-2 py-0.5 border-r border-gray-200 font-mono text-slate-600" style={colStyle("acc-scopeCode", 90)}>
                  {row.scopeCode || "-"}
                </td>
                <td
                  className="relative px-2 py-0.5 pb-1.5 border-r border-gray-200"
                  style={colStyle("acc-code", 100)}
                >
                  {editingCell?.rowId === originalIdx && editingCell?.field === "code" ? (
                    <input
                      type="text"
                      id={`data-account-input-${originalIdx}-code`}
                      value={row.code}
                      onChange={(e) => handleCellEdit(originalIdx, "code", e.target.value)}
                      onBlur={(e) => void handleCellBlur(originalIdx, "code", e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === "Tab") {
                          e.preventDefault();
                          void (async () => {
                            const ok = await handleCellBlur(originalIdx, "code", e.currentTarget.value);
                            if (ok) setEditingCell({ rowId: originalIdx, field: "name" });
                          })();
                        }
                      }}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
                    />
                  ) : (
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => {
                        const codeLockReason = getCodeLockReason(row);
                        if (codeLockReason && !row.isNew) {
                          alert(codeLockReason);
                          return;
                        }
                        setEditingCell({ rowId: originalIdx, field: "code" });
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          const codeLockReason = getCodeLockReason(row);
                          if (codeLockReason && !row.isNew) {
                            alert(codeLockReason);
                            return;
                          }
                          setEditingCell({ rowId: originalIdx, field: "code" });
                        }
                      }}
                      className="cursor-text font-mono text-gray-700 hover:bg-blue-50 px-1 rounded min-h-[18px] w-full"
                    >
                      {row.code || <span className="text-gray-400">点击输入科目代码</span>}
                    </div>
                  )}
                  <TableRowResizeHandle onResizeStart={(e) => beginResize(accRowKey, e)} />
                </td>
                <td className="px-2 py-0.5 border-r border-gray-200" style={colStyle("acc-name", 200)}>
                  {editingCell?.rowId === originalIdx && editingCell?.field === "name" ? (
                    <input
                      type="text"
                      id={`data-account-input-${originalIdx}-name`}
                      value={row.name}
                      onChange={(e) => handleCellEdit(originalIdx, "name", e.target.value)}
                      onBlur={(e) => void handleCellBlur(originalIdx, "name", e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void handleCellBlur(originalIdx, "name", e.currentTarget.value);
                        }
                      }}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                    />
                  ) : (
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setEditingCell({ rowId: originalIdx, field: "name" })}
                      onKeyDown={(e) => e.key === "Enter" && setEditingCell({ rowId: originalIdx, field: "name" })}
                      className="cursor-text text-gray-700 hover:bg-blue-50 px-1 rounded min-h-[18px] w-full"
                    >
                      {row.name || <span className="text-gray-400">点击输入科目名称</span>}
                    </div>
                  )}
                </td>
                <td className="px-2 py-0.5 bg-gray-50 border-r border-gray-200" style={colStyle("acc-budgetFormula", 200)}>
                  <div className="flex items-start justify-between gap-1">
                    <span
                      className="text-gray-500 text-[10px] font-mono flex-1 whitespace-normal break-all leading-4 overflow-hidden"
                      style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", maxHeight: "2rem" }}
                      title={row.budgetFormula || "-"}
                    >
                      {row.budgetFormula || "-"}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleOpenFormulaEditor(originalIdx, "budgetFormula")}
                      className="ml-1 p-0.5 hover:bg-blue-200 rounded flex-shrink-0 transition-colors"
                      title="编辑公式"
                    >
                      <Calculator className="w-4 h-4 text-blue-600" />
                    </button>
                  </div>
                </td>
                <td className="px-2 py-0.5 bg-gray-50 border-r border-gray-200" style={colStyle("acc-actualFormula", 200)}>
                  <div className="flex items-start justify-between gap-1">
                    <span
                      className="text-gray-500 text-[10px] font-mono flex-1 whitespace-normal break-all leading-4 overflow-hidden"
                      style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", maxHeight: "2rem" }}
                      title={row.actualFormula || "-"}
                    >
                      {row.actualFormula || "-"}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleOpenFormulaEditor(originalIdx, "actualFormula")}
                      className="ml-1 p-0.5 hover:bg-blue-200 rounded flex-shrink-0 transition-colors"
                      title="编辑公式"
                    >
                      <Calculator className="w-4 h-4 text-blue-600" />
                    </button>
                  </div>
                </td>
                <td className="px-2 py-0.5 border-r border-gray-200" style={colStyle("acc-product", 160)}>
                  <button
                    type="button"
                    onClick={() => handleOpenProductSelector(originalIdx)}
                    className="w-full px-2 py-0.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 flex items-center justify-between gap-1 text-left"
                  >
                    <span className="flex-1 truncate">{row.product || "选择产品"}</span>
                    <ChevronDown className="w-3 h-3 text-gray-600 flex-shrink-0" />
                  </button>
                </td>
                <td className="px-2 py-0.5 text-center border-r border-gray-200" style={colStyle("acc-valueType", 96)}>
                  <select
                    value={row.valueType}
                    onChange={(e) => void handleValueTypeChange(originalIdx, e.target.value)}
                    className="px-2 py-0.5 text-xs border border-gray-300 rounded bg-white"
                  >
                    <option>金额</option>
                    <option>百分比</option>
                    <option>户数</option>
                  </select>
                </td>
                <td className="px-2 py-0.5 text-center border-r border-gray-200" style={colStyle("acc-actions", 72)}>
                  <div className="flex items-center justify-center gap-1">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingCell({ rowId: originalIdx, field: "name" });
                      }}
                      className="p-1 hover:bg-gray-200 rounded"
                      title="编辑（定位到可编辑字段）"
                    >
                      <Edit className="w-4 h-4 text-gray-600" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const reason = getDeleteDisabledReason(row);
                        if (reason) {
                          setDeleteBlockedReason(reason);
                          return;
                        }
                        void handleDeleteRow(originalIdx);
                      }}
                      className={`p-1 rounded ${getDeleteDisabledReason(row) ? "cursor-not-allowed opacity-50" : "hover:bg-gray-200"}`}
                      title={getDeleteDisabledReason(row) || "删除"}
                    >
                      <Trash2 className="w-4 h-4 text-gray-600" />
                    </button>
                  </div>
                </td>
                <td className="px-2 py-0.5" style={colStyle("acc-remark", 180)}>
                  {editingCell?.rowId === originalIdx && editingCell?.field === "remark" ? (
                    <input
                      type="text"
                      id={`data-account-input-${originalIdx}-remark`}
                      value={row.remark}
                      onChange={(e) => handleCellEdit(originalIdx, "remark", e.target.value)}
                      onBlur={(e) => void handleCellBlur(originalIdx, "remark", e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void handleCellBlur(originalIdx, "remark", e.currentTarget.value);
                        }
                      }}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                    />
                  ) : (
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setEditingCell({ rowId: originalIdx, field: "remark" })}
                      className="cursor-text text-gray-600 hover:bg-blue-50 px-1 rounded min-w-[100px]"
                    >
                      {row.remark || "-"}
                    </div>
                  )}
                </td>
              </tr>
                      );
                    })}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      )}

      <ExcelUploadDialog
        isOpen={showExcelDialog}
        onClose={() => setShowExcelDialog(false)}
        title="数据科目维护"
        fields={dataAccountFields}
        templateName="data_acct_temp"
        onImportComplete={() => void refresh()}
      />

      <FormulaEditorDialog
        isOpen={showFormulaDialog}
        onClose={() => {
          setShowFormulaDialog(false);
          setEditingFormula(null);
        }}
        onConfirm={(f) => void handleFormulaConfirm(f)}
        initialFormula={editingFormula?.currentValue || ""}
        title={editingFormula?.field === "budgetFormula" ? "预算数计算公式编辑" : "实际数计算公式编辑"}
        currentDataSubject={
          editingFormula
            ? `${data[editingFormula.rowId]?.code || ""} ${data[editingFormula.rowId]?.name || ""}`.trim()
            : ""
        }
        currentAppliesToAllProducts={
          editingFormula ? Boolean(data[editingFormula.rowId]?.appliesToAll) : false
        }
        formulaType={editingFormula?.field === "actualFormula" ? "actual" : "budget"}
      />

      <ProductMultiSelectDialog
        isOpen={showProductDialog}
        onClose={() => {
          setShowProductDialog(false);
          setEditingProduct(null);
        }}
        onConfirm={(products, isAll) => void handleProductConfirm(products, isAll)}
        initialProductCodes={editingProduct?.currentCodes}
        flatProducts={flatProducts}
        productTypes={productTypes}
      />
      {deleteBlockedReason && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-[420px] max-w-[90vw] rounded bg-white shadow-lg border border-gray-200">
            <div className="px-4 py-3 border-b border-gray-100 text-sm font-medium text-gray-800">无法删除数据科目</div>
            <div className="px-4 py-3 text-xs text-gray-700 leading-5">{deleteBlockedReason}</div>
            <div className="px-4 py-3 border-t border-gray-100 flex justify-end">
              <button
                type="button"
                onClick={() => setDeleteBlockedReason(null)}
                className="px-3 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-700"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** 单产品模式下解析出的产品代码（「适用所有」时不用）。 */
/** 新增行：既没选全行也没选任何产品时提示。 */
function validateNewRowProductScope(row: Row): string | null {
  if (!row.isNew || row.appliesToAll) return null;
  const codes = row.productCodesRaw?.trim();
  if (codes && codes !== "") return null;
  return "请选择具体产品科目，或将范围设为「适用所有产品」。";
}
