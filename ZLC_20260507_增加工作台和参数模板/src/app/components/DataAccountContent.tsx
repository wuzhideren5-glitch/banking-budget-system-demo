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
  type AssumptionRuleTemplateDto,
  type DataAccountDto,
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

interface Row {
  dbCode: string;
  code: string;
  name: string;
  budgetFormula: string;
  actualFormula: string;
  budgetRuleCode: string;
  budgetRuleConfigJson: string;
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

type RuleConfigEditorState = {
  rowId: number;
  ruleCode: string;
  ruleName: string;
  productScopeKey: string;
  annualTotalParam: string;
  dataBindings: Record<string, string>;
  parameterBindings: Record<string, string>;
  extraConfig: Record<string, unknown>;
};

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
    code: d.data_acct_code,
    name: d.data_acct_name,
    budgetFormula: d.budget_formula ?? "",
    actualFormula: d.actual_formula ?? "",
    budgetRuleCode: d.budget_rule_code ?? "",
    budgetRuleConfigJson: d.budget_rule_config_json ?? "",
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
  const [productTypes, setProductTypes] = useState<ProductTypeDto[]>([]);
  const [showProductDialog, setShowProductDialog] = useState(false);
  const [editingProduct, setEditingProduct] = useState<{ rowId: number; currentCodes: string | null } | null>(
    null
  );
  const [showExcelDialog, setShowExcelDialog] = useState(false);
  const [deleteBlockedReason, setDeleteBlockedReason] = useState<string | null>(null);
  const [showFormulaDialog, setShowFormulaDialog] = useState(false);
  const [ruleTemplates, setRuleTemplates] = useState<AssumptionRuleTemplateDto[]>([]);
  const [ruleConfigEditor, setRuleConfigEditor] = useState<RuleConfigEditorState | null>(null);
  const [editingFormula, setEditingFormula] = useState<{
    rowId: number;
    field: "budgetFormula" | "actualFormula";
    currentValue: string;
  } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [rows, products, templates] = await Promise.all([
        apiGet<DataAccountDto[]>("/api/data-accounts"),
        apiGet<ProductTypeDto[]>("/api/product-types"),
        apiGet<AssumptionRuleTemplateDto[]>("/api/budget-assumptions/rule-templates"),
      ]);
      setData(rows.map(dtoToRow));
      setProductTypes(products);
      setFlatProducts(products.map((p) => ({ code: p.product_code, name: p.product_name })));
      setRuleTemplates(templates);
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
              product_codes: updatedRow.appliesToAll ? null : (updatedRow.productCodesRaw ? updatedRow.productCodesRaw.split(",") : null),
              budget_formula: updatedRow.budgetFormula || null,
              actual_formula: updatedRow.actualFormula || null,
              budget_rule_code: updatedRow.budgetRuleCode || null,
              budget_rule_config_json: updatedRow.budgetRuleConfigJson || null,
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
      budgetRuleCode: "",
      budgetRuleConfigJson: "",
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
            product_codes: row.appliesToAll ? null : (row.productCodesRaw ? row.productCodesRaw.split(",") : null),
            budget_formula: row.budgetFormula || null,
            actual_formula: row.actualFormula || null,
            budget_rule_code: row.budgetRuleCode || null,
            budget_rule_config_json: row.budgetRuleConfigJson || null,
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
        ? { budget_formula: formula || null, budget_rule_code: null, budget_rule_config_json: null }
        : { actual_formula: formula || null };
    if (row.isNew) {
      const newData = [...data];
      newData[editingFormula.rowId] = {
        ...newData[editingFormula.rowId],
        [editingFormula.field]: formula,
        ...(editingFormula.field === "budgetFormula"
          ? { budgetRuleCode: "", budgetRuleConfigJson: "" }
          : {}),
      };
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

  const buildSuggestedRuleConfig = (row: Row, ruleCode: string) => {
    const depositActualMap: Record<string, { balance: string; rate: string }> = {
      C3201: { balance: "A3100", rate: "L3100" },
      C3221: { balance: "A3120", rate: "L3120" },
      C3251: { balance: "A3150", rate: "L3161" },
      C3261: { balance: "A3160", rate: "L3163" },
    };
    const loanBalanceMap: Record<string, string> = {
      C1200: "A1200",
      C1201: "A1201",
      C1250: "A1202",
    };
    const template = ruleTemplates.find((item) => item.rule_code === ruleCode);
    let config = template ? JSON.parse(template.config_json || "{}") : {};
    const matchedDeposit = depositActualMap[row.code];
    if (matchedDeposit) {
      config = {
        ...config,
        product_scope_key: row.productCodesRaw?.split(",")[0] || "",
        data_bindings: {
          ...(config.data_bindings || {}),
          AVG_BALANCE: matchedDeposit.balance,
          ACTUAL_CUSTOMER_RATE: matchedDeposit.rate,
        },
      };
    } else if (loanBalanceMap[row.code]) {
      config = {
        ...config,
        product_scope_key: row.productCodesRaw?.split(",")[0] || "",
        data_bindings: {
          ...(config.data_bindings || {}),
          AVG_BALANCE: loanBalanceMap[row.code],
        },
      };
    }
    return JSON.stringify(config, null, 2);
  };

  const handleBudgetRuleChange = async (rowId: number, nextRuleCode: string) => {
    const row = data[rowId];
    const normalizedRuleCode = nextRuleCode.trim();
    const nextPatch = normalizedRuleCode
      ? {
          budget_rule_code: normalizedRuleCode,
          budget_rule_config_json: row.budgetRuleConfigJson || buildSuggestedRuleConfig(row, normalizedRuleCode),
          budget_formula: null,
        }
      : {
          budget_rule_code: null,
          budget_rule_config_json: null,
        };
    if (row.isNew) {
      const newData = [...data];
      newData[rowId] = {
        ...newData[rowId],
        budgetRuleCode: normalizedRuleCode,
        budgetRuleConfigJson: normalizedRuleCode ? (row.budgetRuleConfigJson || buildSuggestedRuleConfig(row, normalizedRuleCode)) : "",
        budgetFormula: normalizedRuleCode ? "" : newData[rowId].budgetFormula,
      };
      setData(newData);
      return;
    }
    try {
      await persistPatch(row.dbCode, rowId, nextPatch);
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存模板失败");
    }
  };

  const handleEditBudgetRuleConfig = async (rowId: number) => {
    const row = data[rowId];
    if (!row.budgetRuleCode) {
      alert("请先选择预算模板。");
      return;
    }
    const template = ruleTemplates.find((item) => item.rule_code === row.budgetRuleCode);
    const baseConfig = template ? JSON.parse(template.config_json || "{}") : {};
    const currentConfig = row.budgetRuleConfigJson ? JSON.parse(row.budgetRuleConfigJson) : {};
    const nextConfigObj: Record<string, unknown> = {
      ...baseConfig,
      ...currentConfig,
      data_bindings: { ...(baseConfig.data_bindings || {}), ...(currentConfig.data_bindings || {}) },
      parameter_bindings: { ...(baseConfig.parameter_bindings || {}), ...(currentConfig.parameter_bindings || {}) },
    };
    const { data_bindings, parameter_bindings, product_scope_key, annual_total_param, ...extraConfig } = nextConfigObj;
    setRuleConfigEditor({
      rowId,
      ruleCode: row.budgetRuleCode,
      ruleName: template?.rule_name || row.budgetRuleCode,
      productScopeKey: String(product_scope_key || ""),
      annualTotalParam: String(annual_total_param || ""),
      dataBindings: { ...(data_bindings as Record<string, string>) },
      parameterBindings: { ...(parameter_bindings as Record<string, string>) },
      extraConfig,
    });
  };

  const handleRuleConfigBindingChange = (
    section: "dataBindings" | "parameterBindings",
    alias: string,
    value: string,
  ) => {
    if (!ruleConfigEditor) return;
    setRuleConfigEditor({
      ...ruleConfigEditor,
      [section]: {
        ...ruleConfigEditor[section],
        [alias]: value.toUpperCase(),
      },
    });
  };

  const handleSaveRuleConfigEditor = async () => {
    if (!ruleConfigEditor) return;
    const row = data[ruleConfigEditor.rowId];
    const nextConfig = JSON.stringify(
      {
        ...ruleConfigEditor.extraConfig,
        product_scope_key: ruleConfigEditor.productScopeKey.toUpperCase(),
        data_bindings: ruleConfigEditor.dataBindings,
        parameter_bindings: ruleConfigEditor.parameterBindings,
        annual_total_param: ruleConfigEditor.annualTotalParam.toUpperCase() || undefined,
      },
      null,
      2,
    );
    if (row.isNew) {
      const newData = [...data];
      newData[ruleConfigEditor.rowId] = { ...newData[ruleConfigEditor.rowId], budgetRuleConfigJson: nextConfig };
      setData(newData);
      setRuleConfigEditor(null);
      return;
    }
    try {
      await persistPatch(row.dbCode, ruleConfigEditor.rowId, {
        budget_rule_config_json: nextConfig,
      });
      setRuleConfigEditor(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存模板配置失败");
    }
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
    { key: "budgetRuleCode", label: "预算模板", required: false },
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
        row.budgetRuleCode.toLowerCase().includes(s) ||
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
                style={colStyle("acc-budgetRule", 220)}
              >
                <button type="button" onClick={() => handleSort("budgetRuleCode")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  预算预测模板
                  {getSortIcon("budgetRuleCode")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("acc-budgetRule", e, 220)} />
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
                <td className="px-2 py-0.5 border-r border-gray-200" style={colStyle("acc-budgetRule", 220)}>
                  <div className="flex items-center gap-1">
                    <select
                      value={row.budgetRuleCode}
                      onChange={(e) => void handleBudgetRuleChange(originalIdx, e.target.value)}
                      className="flex-1 px-2 py-0.5 text-xs border border-gray-300 rounded bg-white"
                    >
                      <option value="">不使用模板</option>
                      {ruleTemplates.map((tpl) => (
                        <option key={tpl.rule_code} value={tpl.rule_code}>
                          {tpl.rule_name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => void handleEditBudgetRuleConfig(originalIdx)}
                      className={`px-2 py-0.5 text-[10px] rounded border ${
                        row.budgetRuleCode
                          ? "border-blue-300 text-blue-700 hover:bg-blue-50"
                          : "border-gray-200 text-gray-400 cursor-not-allowed"
                      }`}
                      disabled={!row.budgetRuleCode}
                      title={row.budgetRuleCode ? "按模板字段配置数据科目和参数绑定" : "请先选择模板"}
                    >
                      配置
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
      {ruleConfigEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-[760px] max-w-[94vw] max-h-[88vh] overflow-auto rounded bg-white shadow-lg border border-gray-200">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-800">模板配置</div>
                <div className="text-xs text-gray-500 mt-1">
                  {ruleConfigEditor.ruleCode} - {ruleConfigEditor.ruleName}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setRuleConfigEditor(null)}
                className="px-2 py-1 text-xs rounded border border-gray-200 hover:bg-gray-50"
              >
                关闭
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <label className="block">
                  <div className="mb-1 text-xs text-gray-600">产品范围键</div>
                  <input
                    value={ruleConfigEditor.productScopeKey}
                    onChange={(e) => setRuleConfigEditor({ ...ruleConfigEditor, productScopeKey: e.target.value.toUpperCase() })}
                    className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                    placeholder="通常填产品代码，留空默认当前产品"
                  />
                </label>
                {"annual_total_param" in ruleConfigEditor.extraConfig && (
                  <label className="block">
                    <div className="mb-1 text-xs text-gray-600">费用年度总额参数编码</div>
                    <input
                      value={ruleConfigEditor.annualTotalParam}
                      onChange={(e) => setRuleConfigEditor({ ...ruleConfigEditor, annualTotalParam: e.target.value.toUpperCase() })}
                      className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                    />
                  </label>
                )}
              </div>

              <div>
                <div className="mb-2 text-xs font-medium text-gray-700">数据科目绑定</div>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {Object.entries(ruleConfigEditor.dataBindings).map(([alias, value]) => (
                    <label key={alias} className="block rounded border border-gray-200 p-2">
                      <div className="mb-1 text-[11px] text-gray-500">{alias}</div>
                      <input
                        value={value}
                        onChange={(e) => handleRuleConfigBindingChange("dataBindings", alias, e.target.value)}
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono"
                        placeholder="数据科目编码"
                      />
                    </label>
                  ))}
                  {Object.keys(ruleConfigEditor.dataBindings).length === 0 && (
                    <div className="text-xs text-gray-400">当前模板没有需要绑定的数据科目字段。</div>
                  )}
                </div>
              </div>

              <div>
                <div className="mb-2 text-xs font-medium text-gray-700">假设参数绑定</div>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {Object.entries(ruleConfigEditor.parameterBindings).map(([alias, value]) => (
                    <label key={alias} className="block rounded border border-gray-200 p-2">
                      <div className="mb-1 text-[11px] text-gray-500">{alias}</div>
                      <input
                        value={value}
                        onChange={(e) => handleRuleConfigBindingChange("parameterBindings", alias, e.target.value)}
                        className="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono"
                        placeholder="参数编码"
                      />
                    </label>
                  ))}
                  {Object.keys(ruleConfigEditor.parameterBindings).length === 0 && (
                    <div className="text-xs text-gray-400">当前模板没有需要绑定的假设参数字段。</div>
                  )}
                </div>
              </div>

              <div>
                <div className="mb-2 text-xs font-medium text-gray-700">模板底层配置预览</div>
                <pre className="overflow-auto rounded bg-gray-50 p-3 text-[11px] text-gray-600">
                  {JSON.stringify(
                    {
                      ...ruleConfigEditor.extraConfig,
                      product_scope_key: ruleConfigEditor.productScopeKey,
                      data_bindings: ruleConfigEditor.dataBindings,
                      parameter_bindings: ruleConfigEditor.parameterBindings,
                      annual_total_param: ruleConfigEditor.annualTotalParam || undefined,
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>
            </div>
            <div className="px-4 py-3 border-t border-gray-100 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRuleConfigEditor(null)}
                className="px-3 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleSaveRuleConfigEditor()}
                className="px-3 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-700"
              >
                保存模板配置
              </button>
            </div>
          </div>
        </div>
      )}
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
