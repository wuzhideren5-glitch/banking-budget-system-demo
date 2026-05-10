import { useCallback, useEffect, useState } from "react";
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
  type DeptAccountDto,
  type DeptProductMappingDto,
  type ProductScopeMigrationPreviewDto,
} from "@/lib/api";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableColumnWidths } from "@/lib/useTableColumnWidths";
import { useTableRowHeights } from "@/lib/useTableRowHeights";
import { ColumnResizeHandle } from "./ColumnResizeHandle";
import { ExcelUploadDialog } from "./ExcelUploadDialog";
import { FormulaEditorDialog } from "./FormulaEditorDialog";
import { TableRowResizeHandle } from "./TableRowResizeHandle";
import { ALL_PRODUCTS_PRODUCT_CODE, ProductSelectorDialog } from "./ProductSelectorDialog";

type SortDirection = "asc" | "desc" | null;

interface Row {
  dbCode: string;
  code: string;
  name: string;
  budgetFormula: string;
  actualFormula: string;
  product: string;
  /** 来自 API 的 product_code，用于产品范围迁移（不依赖「代码-名称」展示格式） */
  productCodeRaw?: string | null;
  /** 与具体产品互斥；为 true 时表示适用所有产品科目 */
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
  const appliesToAll = Number(d.applies_to_all_products ?? 0) === 1;
  return {
    dbCode: d.data_acct_code,
    code: d.data_acct_code,
    name: d.data_acct_name,
    budgetFormula: d.budget_formula ?? "",
    actualFormula: d.actual_formula ?? "",
    product: d.product_display ?? "",
    productCodeRaw: d.product_code ?? null,
    appliesToAll,
    valueType: d.value_type,
    remark: d.remark ?? "",
    hasBudgetDataRecords: !!d.has_budget_data_records || budgetDataRefCount > 0,
    budgetDataRefCount,
    reportMappingRefCount,
  };
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
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [flatProducts, setFlatProducts] = useState<{ code: string; name: string }[]>([]);
  const [deptAccounts, setDeptAccounts] = useState<DeptAccountDto[]>([]);
  const [deptProductMappings, setDeptProductMappings] = useState<DeptProductMappingDto[]>([]);

  const [showProductDialog, setShowProductDialog] = useState(false);
  const [editingProduct, setEditingProduct] = useState<{ rowId: number; currentValue: string } | null>(
    null
  );
  const [showExcelDialog, setShowExcelDialog] = useState(false);
  const [deleteBlockedReason, setDeleteBlockedReason] = useState<string | null>(null);
  const [showFormulaDialog, setShowFormulaDialog] = useState(false);
  const [editingFormula, setEditingFormula] = useState<{
    rowId: number;
    field: "budgetFormula" | "actualFormula";
    currentValue: string;
  } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [rows, products, depts, deptMappings] = await Promise.all([
        apiGet<DataAccountDto[]>("/api/data-accounts"),
        apiGet<{ product_code: string; product_name: string }[]>("/api/product-types"),
        apiGet<DeptAccountDto[]>("/api/dept-accounts"),
        apiGet<DeptProductMappingDto[]>("/api/dept-product-mappings"),
      ]);
      setData(rows.map(dtoToRow));
      setFlatProducts(products.map((p) => ({ code: p.product_code, name: p.product_name })));
      setDeptAccounts(depts);
      setDeptProductMappings(deptMappings);
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
    setEditingProduct({ rowId, currentValue: data[rowId].product });
    setShowProductDialog(true);
  };

  const handleProductConfirm = async (product: { code: string; name: string }) => {
    if (!editingProduct) return;
    const row = data[editingProduct.rowId];
    const isAll = product.code === ALL_PRODUCTS_PRODUCT_CODE;
    if (row.isNew) {
      const newData = [...data];
      newData[editingProduct.rowId] = {
        ...newData[editingProduct.rowId],
        product: isAll ? "适用所有产品科目" : `${product.code}-${product.name}`,
        appliesToAll: isAll,
      };
      setData(newData);
      setShowProductDialog(false);
      setEditingProduct(null);
      return;
    }
    try {
      const oldAll = !!row.appliesToAll;
      const oldPc = row.appliesToAll
        ? null
        : (row.productCodeRaw?.trim() || parseProductCode(row.product));
      const targetAll = isAll;
      const targetPc = isAll ? null : product.code;
      const scopeChanged =
        targetAll !== oldAll || String(targetPc ?? "") !== String(oldPc ?? "");
      if (!scopeChanged) {
        setShowProductDialog(false);
        setEditingProduct(null);
        return;
      }
      const needsExpand = !oldAll && targetAll && !!oldPc;
      const needsShrink = oldAll && !targetAll && !!targetPc;
      const migrationKind = needsExpand || needsShrink;
      const hasBudget = !!row.hasBudgetDataRecords;

      if (migrationKind && hasBudget) {
        const qs = new URLSearchParams();
        qs.set("target_applies_to_all", String(targetAll));
        if (!targetAll && targetPc) qs.set("target_product_code", targetPc);
        const preview = await apiGet<ProductScopeMigrationPreviewDto>(
          `/api/data-accounts/${encodeURIComponent(row.dbCode)}/product-scope-migration-preview?${qs.toString()}`
        );
        if (needsExpand) {
          const ok = confirm(
            `${preview.message}\n\n将插入合计 ${preview.total_rows_to_insert} 行（Data 目录下全部 budget_*.db）。\n是否继续？`
          );
          if (!ok) return;
          const updated = await persistPatch(row.dbCode, editingProduct.rowId, {
            applies_to_all_products: true,
            product_code: null,
            confirm_product_scope_migration: true,
          });
          if (updated.migration_inserted_total != null || updated.migration_deleted_total != null) {
            alert(
              `迁移完成：插入 ${updated.migration_inserted_total ?? 0} 行，删除 ${updated.migration_deleted_total ?? 0} 行。`
            );
          }
        } else {
          const ok1 = confirm(
            `${preview.message}\n\n将删除合计 ${preview.total_rows_to_delete} 行（全部年度 budget_*.db）。\n第一次确认：是否继续？`
          );
          if (!ok1) return;
          const ok2 = confirm(
            `第二次确认：将永久删除 ${preview.total_rows_to_delete} 条预算明细（所有年度），不可恢复。\n是否删除？`
          );
          if (!ok2) return;
          const updated = await persistPatch(row.dbCode, editingProduct.rowId, {
            applies_to_all_products: false,
            product_code: targetPc,
            confirm_product_scope_migration: true,
            expected_delete_count_total: preview.total_rows_to_delete,
          });
          if (updated.migration_inserted_total != null || updated.migration_deleted_total != null) {
            alert(
              `迁移完成：插入 ${updated.migration_inserted_total ?? 0} 行，删除 ${updated.migration_deleted_total ?? 0} 行。`
            );
          }
        }
      } else if (isAll) {
        await persistPatch(row.dbCode, editingProduct.rowId, {
          applies_to_all_products: true,
          product_code: null,
        });
      } else {
        await persistPatch(row.dbCode, editingProduct.rowId, {
          applies_to_all_products: false,
          product_code: product.code,
        });
      }
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
      if (trimmedValue) {
        if (field === "code" && !DATA_ACCT_CODE_REGEX.test(trimmedValue)) {
          alert(DATA_ACCT_CODE_HINT);
          refocusCell(rowId, "code");
          return false;
        }
      }
      const newData = [...data];
      newData[rowId] = { ...newData[rowId], [field]: field === "code" ? trimmedValue.toUpperCase() : value };
      const updatedRow = newData[rowId];
      if (updatedRow.code && updatedRow.name) {
        if (DATA_ACCT_CODE_REGEX.test(updatedRow.code.trim()) && updatedRow.name.trim()) {
          const scopeErr = validateNewRowProductScope(updatedRow);
          if (scopeErr) {
            alert(scopeErr);
            return false;
          }
          try {
            const created = await apiPost<DataAccountDto>("/api/data-accounts", {
              data_acct_code: updatedRow.code.trim(),
              data_acct_name: updatedRow.name.trim(),
              applies_to_all_products: !!updatedRow.appliesToAll,
              product_code: updatedRow.appliesToAll ? null : singleProductCodeFromRow(updatedRow),
              budget_formula: updatedRow.budgetFormula || null,
              actual_formula: updatedRow.actualFormula || null,
              value_type: updatedRow.valueType,
              remark: updatedRow.remark || null,
            });
            const without = newData.filter((_, i) => i !== rowId);
            setData([dtoToRow(created), ...without]);
            setEditingCell(null);
            return true;
          } catch (e) {
            const msg = e instanceof Error ? e.message : "创建失败";
            alert(msg);
            refocusCell(rowId, isPkConflict(msg) ? "code" : field);
            return false;
          }
        }
      }
      setData(newData);
      if (!updatedRow.code.trim()) {
        refocusCell(rowId, "code");
        return false;
      }
      if (!updatedRow.name.trim()) {
        refocusCell(rowId, "name");
        return false;
      }
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
      alert("请先完成当前新增记录的编辑（填写科目代码和名称）");
      return;
    }
    const newRecord: Row = {
      dbCode: "",
      code: "",
      name: "",
      budgetFormula: "",
      actualFormula: "",
      product: "适用所有产品科目",
      appliesToAll: true,
      valueType: "金额",
      remark: "",
      isNew: true,
    };
    setData([newRecord, ...data]);
    setTimeout(() => setEditingCell({ rowId: 0, field: "code" }), 0);
  };

  const handleSaveAndRefresh = async () => {
    const incomplete = data.filter((row) => row.isNew && (!row.code.trim() || !row.name.trim()));
    if (incomplete.length > 0) {
      if (
        !confirm(
          '存在未完成的新记录（科目代码和名称未填写完整）。\n\n点击"确定"放弃这些记录并重新加载，\n点击"取消"返回继续编辑。'
        )
      ) {
        return;
      }
    }

    // 兜底：若仍有完整但未落库的新行，点击“保存并刷新”时强制写库，避免刷新后消失。
    const pendingCreates = data.filter((row) => row.isNew && row.code.trim() && row.name.trim());
    if (pendingCreates.length > 0) {
      const errors: string[] = [];
      for (const row of pendingCreates) {
        if (!DATA_ACCT_CODE_REGEX.test(row.code.trim())) {
          alert(DATA_ACCT_CODE_HINT);
          const idx = data.findIndex((r) => r === row);
          if (idx >= 0) refocusCell(idx, "code");
          return;
        }
        const scopeErr = validateNewRowProductScope(row);
        if (scopeErr) {
          alert(scopeErr);
          return;
        }
        try {
          await apiPost<DataAccountDto>("/api/data-accounts", {
            data_acct_code: row.code.trim(),
            data_acct_name: row.name.trim(),
            applies_to_all_products: !!row.appliesToAll,
            product_code: row.appliesToAll ? null : singleProductCodeFromRow(row),
            budget_formula: row.budgetFormula || null,
            actual_formula: row.actualFormula || null,
            value_type: row.valueType,
            remark: row.remark || null,
          });
        } catch (e) {
          errors.push(`${row.code || "(空编码)"}: ${e instanceof Error ? e.message : "创建失败"}`);
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
      const resp = await fetch(buildApiUrl("/api/data-accounts/export"));
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
    { key: "code", label: "数据科目代码", required: true },
    { key: "name", label: "数据科目名称", required: true },
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
        row.name.toLowerCase().includes(s) ||
        row.budgetFormula.toLowerCase().includes(s) ||
        row.actualFormula.toLowerCase().includes(s) ||
        row.product.toLowerCase().includes(s) ||
        row.valueType.toLowerCase().includes(s) ||
        row.remark.toLowerCase().includes(s)
    );
  }

  const isSearching = searchText.length > 0;

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

      <div className="flex-1 border border-gray-300 rounded overflow-auto">
        <table className="text-xs border-collapse" style={{ minWidth: "100%" }}>
          <thead className="bg-gray-100 border-b border-gray-300 sticky top-0 z-30">
            <tr>
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
            {displayData.map(({ row, originalIdx }) => {
              const accRowKey = `acc-row-${originalIdx}`;
              return (
              <tr
                key={`row-${originalIdx}`}
                style={rowStyle(accRowKey)}
                className={`border-b border-gray-200 ${row.isNew ? "bg-yellow-50 hover:bg-yellow-100" : "hover:bg-gray-50"}`}
              >
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
          </tbody>
        </table>
      </div>

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

      <ProductSelectorDialog
        isOpen={showProductDialog}
        onClose={() => {
          setShowProductDialog(false);
          setEditingProduct(null);
        }}
        onConfirm={(p) => void handleProductConfirm(p)}
        initialProduct={editingProduct?.currentValue || ""}
        showAllProductsOption
        flatProducts={flatProducts}
        deptAccounts={deptAccounts}
        deptProductMappings={deptProductMappings}
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
function singleProductCodeFromRow(
  row: Pick<Row, "product" | "productCodeRaw" | "appliesToAll">
): string | null {
  if (row.appliesToAll) return null;
  const raw = row.productCodeRaw?.trim();
  if (raw) return raw;
  return parseProductCode(row.product);
}

/** 新增行：选单产品但未解析到代码时返回提示。 */
function validateNewRowProductScope(row: Row): string | null {
  if (!row.isNew || row.appliesToAll) return null;
  if (singleProductCodeFromRow(row)) return null;
  return "请选择具体产品科目，或将范围设为「适用所有产品」。";
}

function parseProductCode(display: string): string | null {
  if (!display || !display.trim()) return null;
  const m = display.trim().match(/^([A-Z]\d{4})/);
  return m ? m[1] : null;
}
