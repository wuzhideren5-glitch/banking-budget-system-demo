import { useEffect, useMemo, useRef, useState } from "react";
import {
  Download,
  FileUp,
  RefreshCw,
  Search,
} from "lucide-react";
import { downloadBlob } from "@/lib/shared/api";
import { ExpenseForecastExportFieldsDialog } from "./ExpenseForecastExportFieldsDialog";
import { ExpenseForecastImportDialog } from "./ExpenseForecastImportDialog";
import {
  ExpenseForecastScopeCompileTable,
  type ExpenseForecastScopeEditingCell,
} from "./ExpenseForecastScopeCompileTable";
import {
  ExpenseForecastSubjectPicker,
} from "./ExpenseForecastSubjectPicker";
import {
  ExpenseForecastSubjectCompileTable,
  type ExpenseForecastSubjectEditingCell,
} from "./ExpenseForecastSubjectCompileTable";
import {
  applyExpenseForecastImport,
  exportExpenseForecastGroupWorkbook,
  exportExpenseForecastWorkbook,
  fetchExpenseForecastGroupView,
  fetchExpenseForecastMeta,
  fetchExpenseForecastSubjectView,
  fetchExpenseForecastView,
  previewExpenseForecastImport,
  saveExpenseForecastCell,
  type ExpenseForecastCellUpsertRequestDto,
  type ExpenseForecastGroupViewResponseDto,
  type ExpenseForecastImportApplyResponseDto,
  type ExpenseForecastImportPreviewResponseDto,
  type ExpenseForecastLeafSubjectOptionDto,
  type ExpenseForecastMetaResponseDto,
  type ExpenseForecastMonthCellDto,
  type ExpenseForecastOwnerGroupOptionDto,
  type ExpenseForecastRowDto,
  type ExpenseForecastScopeOptionDto,
  type ExpenseForecastSubjectViewResponseDto,
  type ExpenseForecastViewResponseDto,
} from "@/lib/expense/expenseForecastApi";
import { listBudgetSubjectCatalog, listDeptAccounts } from "@/lib/expense/masterDataApi";
import type { BudgetSubjectCatalogDto, DeptAccountDto } from "@/lib/expense/masterDataApi";
import {
  ALL_FIELD_KEYS,
  ALL_OWNER_DEPARTMENTS_VALUE,
  AMOUNT_UNIT_STORAGE_KEY,
  amountUnitOptions,
  buildBudgetSubjectPathMap,
  buildBudgetSubjectRowMap,
  buildBudgetSubjectTree,
  buildDeptTree,
  buildExpenseForecastRowDepthMap,
  buildExpenseForecastRowMap,
  buildSubjectOwnerTree,
  buildVisibleExpenseForecastRows,
  filterSubjectOwnerTree,
  filterExpenseForecastRows,
  findMatchedExpenseForecastRowIds,
  flattenVisibleSubjectOwnerNodes,
  groupExpenseForecastRowsByParent,
  parseNumberInput,
  searchBudgetSubjects,
  scopeLabel,
  suggestedScopeType,
  type AmountUnit,
  type CompileMode,
  type ImportMode,
  type ScopeType,
} from "@/lib/expense/expenseForecastViewModel";

type ContextMenuState = {
  x: number;
  y: number;
  rowId: number;
} | null;

export function ExpenseForecastContent() {
  const [meta, setMeta] = useState<ExpenseForecastMetaResponseDto | null>(null);
  const [compileMode, setCompileMode] = useState<CompileMode>("scope");
  const [scopeType, setScopeType] = useState<ScopeType>("group");
  const [ownerGroupValue, setOwnerGroupValue] = useState("");
  const [scopeValue, setScopeValue] = useState("");
  const [subjectCompileId, setSubjectCompileId] = useState("");
  const [year, setYear] = useState<number>(0);
  const [forecastVersion, setForecastVersion] = useState("");
  const [view, setView] = useState<ExpenseForecastViewResponseDto | null>(null);
  const [groupView, setGroupView] = useState<ExpenseForecastGroupViewResponseDto | null>(null);
  const [subjectView, setSubjectView] = useState<ExpenseForecastSubjectViewResponseDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingCell, setSavingCell] = useState<string>("");
  const [searchText, setSearchText] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [contextMenu, setContextMenu] = useState<ContextMenuState>(null);
  const [editingCell, setEditingCell] = useState<ExpenseForecastScopeEditingCell | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const [subjectEditingCell, setSubjectEditingCell] = useState<ExpenseForecastSubjectEditingCell | null>(null);
  const [subjectDraftValue, setSubjectDraftValue] = useState("");
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importMode, setImportMode] = useState<ImportMode>("append");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importPreview, setImportPreview] = useState<ExpenseForecastImportPreviewResponseDto | null>(null);
  const [importResult, setImportResult] = useState<ExpenseForecastImportApplyResponseDto | null>(null);
  const [amountUnit, setAmountUnit] = useState<AmountUnit>("yuan");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showExportFieldsDialog, setShowExportFieldsDialog] = useState(false);
  const [exportGroupName, setExportGroupName] = useState("");
  const [selectedExportFields, setSelectedExportFields] = useState<Set<string>>(new Set(ALL_FIELD_KEYS));
  const [exportMode, setExportMode] = useState<"normal" | "group">("normal");
  const subjectPickerRef = useRef<HTMLLabelElement | null>(null);
  const [budgetSubjectRows, setBudgetSubjectRows] = useState<BudgetSubjectCatalogDto[]>([]);
  const [deptRows, setDeptRows] = useState<DeptAccountDto[]>([]);
  const [subjectPickerOpen, setSubjectPickerOpen] = useState(false);
  const [subjectPickerSearch, setSubjectPickerSearch] = useState("");
  const [subjectTreeExpandedIds, setSubjectTreeExpandedIds] = useState<Set<number>>(new Set());
  const [subjectOwnerExpandedKeys, setSubjectOwnerExpandedKeys] = useState<Set<string>>(new Set());
  const amountDivisor = amountUnitOptions.find((option) => option.value === amountUnit)?.divisor ?? 1;
  const leafSubjectOptions = meta?.leaf_subject_options ?? [];

  const loadMeta = async (targetYear?: number) => {
    const queryYear = targetYear ?? (year > 0 ? year : new Date().getFullYear());
    const resp = await fetchExpenseForecastMeta(queryYear);
    setMeta(resp);
    setYear(queryYear || resp.default_year);
    setForecastVersion((prev) => prev || resp.default_version);
    setScopeType((prev) => prev || suggestedScopeType(resp));
  };

  const scopeOptions = useMemo<ExpenseForecastScopeOptionDto[]>(() => {
    if (!meta) return [];
    if (scopeType === "entity") return meta.entity_options;
    if (scopeType === "group") return meta.group_options;
    const matchedGroup = (meta.owner_group_options ?? []).find((item) => item.group_value === ownerGroupValue);
    const ownerOptions = matchedGroup?.owner_options ?? [];
    return ownerGroupValue
      ? [{ value: ALL_OWNER_DEPARTMENTS_VALUE, label: "全部部门" }, ...ownerOptions]
      : ownerOptions;
  }, [meta, ownerGroupValue, scopeType]);

  const ownerGroupOptions = useMemo<ExpenseForecastOwnerGroupOptionDto[]>(() => {
    if (!meta || scopeType !== "owner") return [];
    return meta.owner_group_options ?? [];
  }, [meta, scopeType]);

  const budgetSubjectRowMap = useMemo(() => buildBudgetSubjectRowMap(budgetSubjectRows), [budgetSubjectRows]);

  const budgetSubjectTree = useMemo(() => buildBudgetSubjectTree(budgetSubjectRows), [budgetSubjectRows]);
  const deptTree = useMemo(() => buildDeptTree(deptRows), [deptRows]);
  const leafSubjectPathMap = useMemo(() => buildBudgetSubjectPathMap(budgetSubjectTree), [budgetSubjectTree]);

  const groupScopeOptions = useMemo<ExpenseForecastScopeOptionDto[]>(() => {
    return meta?.group_options ?? [];
  }, [meta]);

  const selectedLeafSubject = useMemo<ExpenseForecastLeafSubjectOptionDto | null>(() => {
    return leafSubjectOptions.find((item) => String(item.id) === subjectCompileId) ?? null;
  }, [leafSubjectOptions, subjectCompileId]);

  const selectedBudgetSubjectRow = useMemo(() => {
    if (!subjectCompileId) return null;
    return budgetSubjectRowMap.get(Number(subjectCompileId)) ?? null;
  }, [budgetSubjectRowMap, subjectCompileId]);

  const selectedBudgetSubjectPath = useMemo(() => {
    if (!subjectCompileId) return "";
    return leafSubjectPathMap.get(Number(subjectCompileId)) ?? "";
  }, [leafSubjectPathMap, subjectCompileId]);

  const currentScopeValueValid = useMemo(() => {
    if (!scopeValue) return false;
    return scopeOptions.some((item) => item.value === scopeValue);
  }, [scopeOptions, scopeValue]);
  const ownerEditableScope = scopeType === "owner";
  const subjectCompileEnabled = compileMode === "subject";
  const allOwnerDepartmentsSelected = scopeType === "owner" && scopeValue === ALL_OWNER_DEPARTMENTS_VALUE;
  const groupSelectorDisabled = scopeType === "entity";
  const groupSelectorValue = scopeType === "group" ? scopeValue : ownerGroupValue;
  const currentScopeDisplayLabel = useMemo(() => {
    if (subjectCompileEnabled && allOwnerDepartmentsSelected) {
      return ownerGroupValue ? `${ownerGroupValue} / 全部部门` : "全部部门";
    }
    return scopeOptions.find((item) => item.value === scopeValue)?.label ?? scopeValue ?? "-";
  }, [allOwnerDepartmentsSelected, ownerGroupValue, scopeOptions, scopeValue, subjectCompileEnabled]);

  const searchedLeafSubjects = useMemo(
    () => searchBudgetSubjects(budgetSubjectRows, leafSubjectPathMap, subjectPickerSearch),
    [budgetSubjectRows, leafSubjectPathMap, subjectPickerSearch],
  );

  const subjectOwnerTree = useMemo(
    () =>
      buildSubjectOwnerTree({
        enabled: subjectCompileEnabled,
        scopeType,
        scopeValue,
        deptTree,
        subjectView,
      }),
    [deptTree, scopeType, scopeValue, subjectCompileEnabled, subjectView],
  );

  const rowMap = useMemo(() => buildExpenseForecastRowMap(view?.rows ?? []), [view]);

  const childrenByParent = useMemo(() => groupExpenseForecastRowsByParent(view?.rows ?? []), [view]);

  useEffect(() => {
    void (async () => {
      try {
        await loadMeta(new Date().getFullYear());
        const subjectRows = await listBudgetSubjectCatalog();
        const departmentRows = await listDeptAccounts();
        setBudgetSubjectRows(subjectRows);
        setDeptRows(departmentRows);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载费用预测配置失败");
      }
    })();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedUnit = window.localStorage.getItem(AMOUNT_UNIT_STORAGE_KEY) as AmountUnit | null;
    if (savedUnit && amountUnitOptions.some((option) => option.value === savedUnit)) {
      setAmountUnit(savedUnit);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(AMOUNT_UNIT_STORAGE_KEY, amountUnit);
  }, [amountUnit]);

  useEffect(() => {
    if (!meta) return;
    if (scopeType === "owner") {
      if (!ownerGroupOptions.length) {
        setOwnerGroupValue("");
        setScopeValue("");
        return;
      }
      if (!ownerGroupOptions.some((item) => item.group_value === ownerGroupValue)) {
        setOwnerGroupValue(ownerGroupOptions[0].group_value);
        return;
      }
    } else if (ownerGroupValue) {
      setOwnerGroupValue("");
    }

    const options =
      scopeType === "entity" ? meta.entity_options : scopeType === "group" ? meta.group_options : scopeOptions;
    if (!options.length) {
      setScopeValue("");
      return;
    }
    if (!options.some((item) => item.value === scopeValue)) {
      const defaultOption =
        scopeType === "owner"
          ? options.find((item) => item.value !== ALL_OWNER_DEPARTMENTS_VALUE) ?? options[0]
          : options[0];
      setScopeValue(defaultOption.value);
    }
  }, [meta, ownerGroupOptions, ownerGroupValue, scopeOptions, scopeType, scopeValue]);

  useEffect(() => {
    if (!leafSubjectOptions.length) {
      setSubjectCompileId("");
      return;
    }
    if (!leafSubjectOptions.some((item) => String(item.id) === subjectCompileId)) {
      setSubjectCompileId(String(leafSubjectOptions[0].id));
    }
  }, [leafSubjectOptions, subjectCompileId]);

  useEffect(() => {
    if (!subjectCompileId || !budgetSubjectRowMap.size) return;
    expandBudgetSubjectPath(Number(subjectCompileId));
  }, [budgetSubjectRowMap, subjectCompileId]);

  const loadView = async () => {
    if (!scopeValue || !currentScopeValueValid || !forecastVersion || !year) return;
    if (subjectCompileEnabled && !subjectCompileId) return;
    if (allOwnerDepartmentsSelected && !ownerGroupValue) {
      setError("请选择事业群后再查看全部部门数据");
      return;
    }
    setLoading(true);
    setError("");
    try {
      if (subjectCompileEnabled && allOwnerDepartmentsSelected) {
        const resp = await fetchExpenseForecastSubjectView({
          year,
          forecastVersion,
          scopeType: "group",
          scopeValue: ownerGroupValue,
          subjectId: subjectCompileId,
        });
        setSubjectView(resp);
        setGroupView(null);
        setView(null);
        setSelectedRowId(null);
      } else if (allOwnerDepartmentsSelected) {
        const resp = await fetchExpenseForecastGroupView({
          year,
          forecastVersion,
          groupName: ownerGroupValue,
        });
        setGroupView(resp);
        setView(null);
        setSubjectView(null);
        setSelectedRowId(null);
      } else if (subjectCompileEnabled) {
        const resp = await fetchExpenseForecastSubjectView({
          year,
          forecastVersion,
          scopeType,
          scopeValue,
          subjectId: subjectCompileId,
        });
        setSubjectView(resp);
        setView(null);
        setGroupView(null);
      } else {
        const resp = await fetchExpenseForecastView({
          year,
          forecastVersion,
          scopeType,
          scopeValue,
        });
        setView(resp);
        setSubjectView(null);
        setGroupView(null);
        setExpandedIds(new Set(resp.rows.map((row) => row.id)));
        if (!selectedRowId && resp.rows.length > 0) {
          setSelectedRowId(resp.rows[0].id);
        }
      }
      setMessage("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载费用预测表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!scopeValue || !currentScopeValueValid || !forecastVersion || !year) return;
    if (subjectCompileEnabled && !subjectCompileId) return;
    void loadView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeValue, scopeType, forecastVersion, year, currentScopeValueValid, compileMode, subjectCompileId, ownerGroupValue]);

  useEffect(() => {
    const closeMenu = () => setContextMenu(null);
    window.addEventListener("click", closeMenu);
    return () => window.removeEventListener("click", closeMenu);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (subjectPickerRef.current && !subjectPickerRef.current.contains(event.target as Node)) {
        setSubjectPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const matchedRowIds = useMemo(
    () => findMatchedExpenseForecastRowIds(view?.rows ?? [], rowMap, searchText),
    [rowMap, searchText, view],
  );

  const visibleRows = useMemo(
    () => buildVisibleExpenseForecastRows(view?.rows ?? [], childrenByParent, matchedRowIds, expandedIds),
    [childrenByParent, expandedIds, matchedRowIds, view],
  );

  const visibleSubjectRows = useMemo(() => {
    const rows = subjectView?.rows ?? [];
    if (subjectCompileEnabled && scopeType === "entity") return rows;
    const keyword = searchText.trim().toLowerCase();
    if (!keyword) return rows;
    return rows.filter((row) => row.owner_name.toLowerCase().includes(keyword));
  }, [searchText, scopeType, subjectCompileEnabled, subjectView]);

  const visibleGroupOwnerViews = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    const ownerViews = groupView?.owner_views ?? [];
    return ownerViews
      .map((ownerView) => {
        if (!keyword) return ownerView;
        if (ownerView.owner_name.toLowerCase().includes(keyword)) return ownerView;
        return {
          ...ownerView,
          rows: filterExpenseForecastRows(ownerView.rows, keyword),
        };
      })
      .filter((ownerView) => ownerView.rows.length > 0);
  }, [groupView, searchText]);

  const filteredSubjectOwnerTree = useMemo(
    () => filterSubjectOwnerTree(subjectOwnerTree, searchText),
    [searchText, subjectOwnerTree],
  );

  useEffect(() => {
    if (!subjectCompileEnabled || scopeType !== "entity" || filteredSubjectOwnerTree.length === 0) return;
    setSubjectOwnerExpandedKeys(new Set(filteredSubjectOwnerTree.map((node) => node.key)));
  }, [filteredSubjectOwnerTree, scopeType, subjectCompileEnabled]);

  const depthByRowId = useMemo(() => buildExpenseForecastRowDepthMap(childrenByParent), [childrenByParent]);
  const expandableRowIds = useMemo(
    () =>
      new Set(
        Array.from(childrenByParent.entries())
          .filter(([parentId, children]) => parentId !== null && children.length > 0)
          .map(([parentId]) => parentId as number),
      ),
    [childrenByParent],
  );

  const startEdit = (row: ExpenseForecastRowDto, cell: ExpenseForecastMonthCellDto) => {
    if (!cell.editable) return;
    setEditingCell({ rowId: row.id, field: "month_forecast", month: cell.month });
    setDraftValue(String(cell.value || ""));
    setSelectedRowId(row.id);
  };

  const startAnnualEdit = (
    row: ExpenseForecastRowDto,
    field: "business_submission" | "capital_advice",
    value: number,
    editable: boolean,
    ownerName?: string,
  ) => {
    if (!editable) return;
    setEditingCell({ rowId: row.id, ownerName, field });
    setDraftValue(String(value || ""));
    setSelectedRowId(row.id);
  };

  const saveCell = async () => {
    if (!editingCell) return;
    const row = editingCell.ownerName
      ? groupView?.owner_views
          .find((ownerView) => ownerView.owner_name === editingCell.ownerName)
          ?.rows.find((item) => item.id === editingCell.rowId) ?? null
      : rowMap.get(editingCell.rowId) ?? null;
    if (!row) {
      setEditingCell(null);
      return;
    }
    const targetMonthCell =
      editingCell.field === "month_forecast"
        ? row.months.find((item) => item.month === editingCell.month)
        : null;
    let overrideReason: string | undefined;
    if (editingCell.field === "month_forecast" && targetMonthCell && ["auto", "override"].includes(targetMonthCell.value_source ?? "")) {
      const input = window.prompt("请输入人工覆盖原因", targetMonthCell.override_reason ?? "页面手工调整");
      if (input == null) {
        setSavingCell("");
        setEditingCell(null);
        return;
      }
      overrideReason = input.trim() || "页面手工调整";
    }
    const payload: ExpenseForecastCellUpsertRequestDto = {
      year,
      forecast_version: forecastVersion,
      scope_type: "owner",
      scope_value: editingCell.ownerName ?? scopeValue,
      subject_id: row.id,
      field_name: editingCell.field,
      month: editingCell.field === "month_forecast" ? editingCell.month ?? null : null,
      value: parseNumberInput(draftValue),
      override_reason: overrideReason,
    };
    const savingKey =
      editingCell.field === "month_forecast"
        ? `${editingCell.ownerName ?? scopeValue}:${editingCell.rowId}:${editingCell.field}:${editingCell.month}`
        : `${editingCell.ownerName ?? scopeValue}:${editingCell.rowId}:${editingCell.field}`;
    setSavingCell(savingKey);
    try {
      await saveExpenseForecastCell(payload);
      setMessage(
        `已保存 ${editingCell.ownerName ? `${editingCell.ownerName} / ` : ""}${row.subject_name} ${
          editingCell.field === "month_forecast"
            ? `${editingCell.month}月预估值`
            : editingCell.field === "business_submission"
              ? "业务报送"
              : "资划建议"
        }`,
      );
      setError("");
      await loadView();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存预估失败");
    } finally {
      setSavingCell("");
      setEditingCell(null);
    }
  };

  const saveSubjectCell = async () => {
    if (!subjectEditingCell) return;
    const row = subjectView?.rows.find(
      (item) => item.owner_name === subjectEditingCell.ownerName && item.subject_id === subjectEditingCell.subjectId,
    );
    if (!row) {
      setSubjectEditingCell(null);
      return;
    }
    const targetMonthCell =
      subjectEditingCell.field === "month_forecast"
        ? row.months.find((item) => item.month === subjectEditingCell.month)
        : null;
    let overrideReason: string | undefined;
    if (
      subjectEditingCell.field === "month_forecast" &&
      targetMonthCell &&
      ["auto", "override"].includes(targetMonthCell.value_source ?? "")
    ) {
      const input = window.prompt("请输入人工覆盖原因", targetMonthCell.override_reason ?? "页面手工调整");
      if (input == null) {
        setSavingCell("");
        setSubjectEditingCell(null);
        return;
      }
      overrideReason = input.trim() || "页面手工调整";
    }
    const payload: ExpenseForecastCellUpsertRequestDto = {
      year,
      forecast_version: forecastVersion,
      scope_type: "owner",
      scope_value: subjectEditingCell.ownerName,
      subject_id: subjectEditingCell.subjectId,
      field_name: subjectEditingCell.field,
      month: subjectEditingCell.field === "month_forecast" ? subjectEditingCell.month ?? null : null,
      value: parseNumberInput(subjectDraftValue),
      override_reason: overrideReason,
    };
    const savingKey =
      subjectEditingCell.field === "month_forecast"
        ? `${subjectEditingCell.ownerName}:${subjectEditingCell.field}:${subjectEditingCell.month}`
        : `${subjectEditingCell.ownerName}:${subjectEditingCell.field}`;
    setSavingCell(savingKey);
    try {
      await saveExpenseForecastCell(payload);
      setMessage(
        `已保存 ${subjectEditingCell.ownerName} / ${row.subject_name} ${
          subjectEditingCell.field === "month_forecast"
            ? `${subjectEditingCell.month}月预估值`
            : subjectEditingCell.field === "business_submission"
              ? "业务报送"
              : "资划建议"
        }`,
      );
      setError("");
      await loadView();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存预估失败");
    } finally {
      setSavingCell("");
      setSubjectEditingCell(null);
    }
  };

  const handleExport = async (excludeFields: string[] = []) => {
    try {
      setError("");
      if (subjectCompileEnabled && allOwnerDepartmentsSelected && !ownerGroupValue) {
        setError("请选择事业群后再导出全部部门Excel");
        return;
      }
      const exportScopeType =
        subjectCompileEnabled && allOwnerDepartmentsSelected ? "group" : scopeType;
      const exportScopeValue =
        subjectCompileEnabled && allOwnerDepartmentsSelected ? ownerGroupValue : scopeValue;
      const result = await exportExpenseForecastWorkbook({
        year,
        forecastVersion,
        scopeType: exportScopeType,
        scopeValue: exportScopeValue,
        compileMode: subjectCompileEnabled ? "subject" : "scope",
        subjectId: subjectCompileEnabled && subjectCompileId ? subjectCompileId : null,
        amountUnit,
        excludeFields,
      });
      downloadBlob(result.blob, result.filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出失败");
    }
  };

  const handleExportByGroup = async (groupName: string, excludeFields: string[] = []) => {
    try {
      setError("");
      const result = await exportExpenseForecastGroupWorkbook({
        year,
        forecastVersion,
        groupName,
        amountUnit,
        excludeFields,
      });
      downloadBlob(result.blob, result.filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出失败");
    }
  };

  const runImportPreview = async () => {
    if (!importFile) {
      setError("请先选择导入文件");
      return;
    }
    if (allOwnerDepartmentsSelected && !ownerGroupValue) {
      setError("请选择事业群后再导入全部部门Excel");
      return;
    }
    setImportLoading(true);
    setError("");
    setImportResult(null);
    try {
      const data = await previewExpenseForecastImport(
        {
          year,
          forecastVersion,
          scopeType,
          scopeValue,
          compileMode: subjectCompileEnabled ? "subject" : "scope",
          mode: importMode,
          subjectId: subjectCompileEnabled && subjectCompileId ? subjectCompileId : null,
          groupName: allOwnerDepartmentsSelected ? ownerGroupValue : null,
        },
        importFile,
      );
      setImportPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入预览失败");
      setImportPreview(null);
    } finally {
      setImportLoading(false);
    }
  };

  const applyImport = async () => {
    if (!importFile) {
      setError("请先选择导入文件");
      return;
    }
    if (allOwnerDepartmentsSelected && !ownerGroupValue) {
      setError("请选择事业群后再导入全部部门Excel");
      return;
    }
    if (!importPreview) {
      await runImportPreview();
      return;
    }
    setImportLoading(true);
    setError("");
    try {
      const payload = await applyExpenseForecastImport(
        {
          year,
          forecastVersion,
          scopeType,
          scopeValue,
          compileMode: subjectCompileEnabled ? "subject" : "scope",
          mode: importMode,
          subjectId: subjectCompileEnabled && subjectCompileId ? subjectCompileId : null,
          groupName: allOwnerDepartmentsSelected ? ownerGroupValue : null,
        },
        importFile,
      );
      setImportResult(payload);
      setMessage(`导入完成：新增 ${payload.inserted_cells}，覆盖 ${payload.updated_cells}，跳过 ${payload.skipped_cells}`);
      await loadMeta(year);
      await loadView();
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setImportLoading(false);
    }
  };

  const currentContextRow = contextMenu ? rowMap.get(contextMenu.rowId) ?? null : null;

  const expandBudgetSubjectPath = (subjectId: number) => {
    const expanded = new Set<number>();
    let current = budgetSubjectRowMap.get(subjectId);
    while (current?.parent_id != null) {
      expanded.add(current.parent_id);
      current = budgetSubjectRowMap.get(current.parent_id);
    }
    setSubjectTreeExpandedIds(expanded);
  };

  const selectBudgetSubject = (subjectId: number) => {
    setSubjectCompileId(String(subjectId));
    expandBudgetSubjectPath(subjectId);
    setSubjectPickerOpen(false);
    setSubjectPickerSearch("");
  };

  const visibleSubjectOwnerNodes = useMemo(
    () => flattenVisibleSubjectOwnerNodes(filteredSubjectOwnerTree, subjectOwnerExpandedKeys, searchText),
    [filteredSubjectOwnerTree, searchText, subjectOwnerExpandedKeys],
  );

  return (
    <div className="h-full flex flex-col bg-white text-xs text-gray-700">
      <div className="border-b border-gray-200 px-4 py-3 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">年份</span>
            <input
              className="h-8 w-24 rounded border border-gray-300 px-2"
              type="number"
              value={year || ""}
              onChange={(e) => setYear(Number.parseInt(e.target.value || "0", 10) || 0)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">版本</span>
            <input
              className="h-8 w-36 rounded border border-gray-300 px-2"
              value={forecastVersion}
              list="expense-forecast-versions"
              onChange={(e) => setForecastVersion(e.target.value)}
            />
            <datalist id="expense-forecast-versions">
              {(meta?.version_suggestions ?? []).map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">单位</span>
            <select
              className="h-8 w-24 rounded border border-gray-300 px-2"
              value={amountUnit}
              onChange={(e) => setAmountUnit(e.target.value as AmountUnit)}
            >
              {amountUnitOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">编制维度</span>
            <select
              className="h-8 w-36 rounded border border-gray-300 px-2"
              value={compileMode}
              onChange={(e) => setCompileMode(e.target.value as CompileMode)}
            >
              <option value="scope">按预算部门</option>
              <option value="subject">按预算科目</option>
            </select>
          </label>
          {subjectCompileEnabled ? (
            <ExpenseForecastSubjectPicker
              pickerRef={subjectPickerRef}
              isOpen={subjectPickerOpen}
              selectedSubjectId={subjectCompileId}
              selectedSubjectName={selectedBudgetSubjectRow?.subject_name ?? selectedLeafSubject?.label ?? "请选择预算科目"}
              selectedSubjectPath={selectedBudgetSubjectPath}
              searchText={subjectPickerSearch}
              expandedIds={subjectTreeExpandedIds}
              tree={budgetSubjectTree}
              searchMatches={searchedLeafSubjects}
              onToggleOpen={() => {
                setSubjectPickerOpen((prev) => !prev);
                if (!subjectPickerOpen && subjectCompileId) {
                  expandBudgetSubjectPath(Number(subjectCompileId));
                }
              }}
              onSearchChange={setSubjectPickerSearch}
              onSelectSubject={selectBudgetSubject}
              onToggleExpanded={(subjectId) =>
                setSubjectTreeExpandedIds((prev) => {
                  const next = new Set(prev);
                  if (next.has(subjectId)) next.delete(subjectId);
                  else next.add(subjectId);
                  return next;
                })
              }
            />
          ) : null}
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">统计口径</span>
            <div className="flex flex-wrap gap-2">
              <select
                className="h-8 w-32 rounded border border-gray-300 px-2"
                value={scopeType}
                onChange={(e) => setScopeType(e.target.value as ScopeType)}
              >
                <option value="entity">主体</option>
                <option value="group">事业群</option>
                <option value="owner">费用归属部门</option>
              </select>
              {scopeType === "entity" && (
                <select
                  className="h-8 min-w-[220px] rounded border border-gray-300 px-2"
                  value={scopeValue}
                  onChange={(e) => setScopeValue(e.target.value)}
                >
                  {scopeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">事业群</span>
            <select
              className="h-8 min-w-[180px] rounded border border-gray-300 px-2 disabled:bg-gray-100 disabled:text-gray-400"
              value={groupSelectorValue}
              disabled={groupSelectorDisabled}
              onChange={(e) => {
                if (scopeType === "group") {
                  setScopeValue(e.target.value);
                } else {
                  setOwnerGroupValue(e.target.value);
                }
              }}
            >
              {!groupSelectorValue ? <option value="">请选择事业群</option> : null}
              {(scopeType === "owner" ? ownerGroupOptions : groupScopeOptions).map((option) => (
                <option
                  key={"group_value" in option ? option.group_value : option.value}
                  value={"group_value" in option ? option.group_value : option.value}
                >
                  {"group_label" in option ? option.group_label : option.label}
                </option>
              ))}
            </select>
          </label>
          {scopeType === "owner" ? (
            <label className="flex flex-col gap-1">
              <span className="text-gray-500">费用归属部门</span>
              <select
                className="h-8 min-w-[220px] rounded border border-gray-300 px-2"
                value={scopeValue}
                onChange={(e) => setScopeValue(e.target.value)}
              >
                {scopeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">{subjectCompileEnabled ? "搜索费用归属部门" : "搜索预算科目"}</span>
            <div className="relative">
              <Search className="absolute left-2 top-2 h-4 w-4 text-gray-400" />
              <input
                className="h-8 w-64 rounded border border-gray-300 pl-8 pr-2"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
            </div>
          </label>
          <button
            className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50"
            onClick={() => void loadView()}
            type="button"
            title={allOwnerDepartmentsSelected ? "刷新当前事业群下全部部门视图" : "刷新"}
          >
            <RefreshCw className={`mr-1 inline h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            刷新
          </button>
          <button
            className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => { setShowImportDialog(true); setError(""); setMessage(""); }}
            type="button"
            disabled={!ownerEditableScope}
            title={
              ownerEditableScope
                ? allOwnerDepartmentsSelected
                  ? "导入当前事业群下全部部门的Excel"
                  : "导入Excel"
                : "仅费用归属部门口径支持导入Excel"
            }
          >
            <FileUp className="mr-1 inline h-3.5 w-3.5" />
            导入Excel
          </button>
          <button
            className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => {
              const groupMode = !subjectCompileEnabled && scopeType === "owner" && (allOwnerDepartmentsSelected || scopeType === "owner");
              setExportMode(groupMode ? "group" : "normal");
              if (groupMode && ownerGroupValue) {
                setExportGroupName(ownerGroupValue);
              }
              setShowExportFieldsDialog(true);
            }}
            type="button"
            title={subjectCompileEnabled ? "导出当前按预算科目编制视图" : "导出Excel"}
          >
            <Download className="mr-1 inline h-3.5 w-3.5" />
            导出Excel
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-[11px] text-gray-500">
          <span>当前维度：{subjectCompileEnabled ? "按预算科目编制" : "按预算部门编制"}</span>
          <span>当前统计口径：{scopeLabel(scopeType)}</span>
          <span>当前统计对象：{currentScopeDisplayLabel}</span>
          {subjectCompileEnabled ? <span>当前预算科目：{selectedLeafSubject?.label ?? "-"}</span> : null}
          <span>当前单位：{amountUnitOptions.find((option) => option.value === amountUnit)?.label ?? "元"}</span>
          <span>
            实际数据截至：
            {(subjectCompileEnabled
              ? subjectView?.actual_cutoff_month
              : groupView?.actual_cutoff_month ?? view?.actual_cutoff_month) ?? 0}
            月
          </span>
          <span>
            说明：
            {subjectCompileEnabled
              ? "当前按叶子预算科目逐部门编制；已有实际的月份显示实际，后续月份支持录入预估；业务报送和资划建议支持逐部门录入"
              : allOwnerDepartmentsSelected
                ? "当前按事业群展示全部费用归属部门；可直接查看、编辑、导入或导出该事业群下属所有部门的预算数据"
              : ownerEditableScope
                ? "已有实际的月份显示实际，后续月份支持录入预估；业务报送和资划建议支持手工输入与导入"
                : "当前口径仅作汇总展示，不支持录入预估、业务报送和资划建议"}
          </span>
        </div>
        {message ? <div className="text-emerald-600">{message}</div> : null}
        {error ? <div className="text-red-600">{error}</div> : null}
      </div>

      <div className="flex-1 overflow-auto">
        {subjectCompileEnabled ? (
          <ExpenseForecastSubjectCompileTable
            loading={loading}
            useOwnerTree={scopeType === "entity" && subjectCompileEnabled}
            searchText={searchText}
            amountDivisor={amountDivisor}
            savingCell={savingCell}
            editingCell={subjectEditingCell}
            draftValue={subjectDraftValue}
            visibleRows={visibleSubjectRows}
            visibleOwnerNodes={visibleSubjectOwnerNodes}
            expandedOwnerKeys={subjectOwnerExpandedKeys}
            onToggleOwnerExpanded={(key) =>
              setSubjectOwnerExpandedKeys((prev) => {
                const next = new Set(prev);
                if (next.has(key)) next.delete(key);
                else next.add(key);
                return next;
              })
            }
            onStartEdit={(cell, value) => {
              setSubjectEditingCell(cell);
              setSubjectDraftValue(String(value || ""));
            }}
            onDraftValueChange={setSubjectDraftValue}
            onSaveCell={() => void saveSubjectCell()}
            onCancelEdit={() => setSubjectEditingCell(null)}
          />
        ) : (
          <ExpenseForecastScopeCompileTable
            loading={loading}
            amountDivisor={amountDivisor}
            savingCell={savingCell}
            editingCell={editingCell}
            draftValue={draftValue}
            rows={visibleRows}
            groupOwnerViews={groupView ? visibleGroupOwnerViews : null}
            rowDepthById={depthByRowId}
            expandableRowIds={expandableRowIds}
            expandedRowIds={expandedIds}
            selectedRowId={selectedRowId}
            onSelectRow={setSelectedRowId}
            onOpenContextMenu={(rowId, x, y) => setContextMenu({ x, y, rowId })}
            onToggleExpandedRow={(rowId) =>
              setExpandedIds((prev) => {
                const next = new Set(prev);
                if (next.has(rowId)) next.delete(rowId);
                else next.add(rowId);
                return next;
              })
            }
            onStartMonthEdit={(row, cell, ownerName) => {
              if (!cell.editable) return;
              if (ownerName) {
                setEditingCell({
                  ownerName,
                  rowId: row.id,
                  field: "month_forecast",
                  month: cell.month,
                });
                setDraftValue(String(cell.value || ""));
                return;
              }
              startEdit(row, cell);
            }}
            onStartAnnualEdit={startAnnualEdit}
            onDraftValueChange={setDraftValue}
            onSaveCell={() => void saveCell()}
            onCancelEdit={() => setEditingCell(null)}
          />
        )}
      </div>

      {!subjectCompileEnabled && contextMenu && currentContextRow ? (
        <div
          className="fixed z-50 min-w-[160px] rounded border border-gray-200 bg-white py-1 shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setExpandedIds((prev) => new Set(prev).add(currentContextRow.id));
              setContextMenu(null);
            }}
          >
            展开下级
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setExpandedIds((prev) => {
                const next = new Set(prev);
                next.delete(currentContextRow.id);
                return next;
              });
              setContextMenu(null);
            }}
          >
            收起本级
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setExpandedIds(new Set(view?.rows.map((row) => row.id) ?? []));
              setContextMenu(null);
            }}
          >
            展开全部下级
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setExpandedIds(new Set());
              setContextMenu(null);
            }}
          >
            收起全部下级
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              setSelectedRowId(currentContextRow.id);
              setContextMenu(null);
            }}
          >
            定位当前科目
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-gray-50"
            onClick={() => {
              void loadView();
              setContextMenu(null);
            }}
          >
            刷新当前视图
          </button>
        </div>
      ) : null}

      {showImportDialog ? (
        <ExpenseForecastImportDialog
          scopeType={scopeType}
          scopeValue={scopeValue}
          forecastVersion={forecastVersion}
          ownerEditableScope={ownerEditableScope}
          importMode={importMode}
          importFile={importFile}
          importLoading={importLoading}
          importPreview={importPreview}
          importResult={importResult}
          amountDivisor={amountDivisor}
          error={error}
          message={message}
          onClose={() => setShowImportDialog(false)}
          onModeChange={setImportMode}
          onFileChange={(file) => {
            setImportFile(file);
            setImportPreview(null);
            setImportResult(null);
          }}
          onPreview={() => void runImportPreview()}
          onApply={() => void applyImport()}
        />
      ) : null}

      {showExportFieldsDialog && (
        <ExpenseForecastExportFieldsDialog
          exportMode={exportMode}
          exportGroupName={exportGroupName}
          ownerGroups={meta?.owner_group_options ?? []}
          selectedFields={selectedExportFields}
          onGroupNameChange={setExportGroupName}
          onSelectedFieldsChange={setSelectedExportFields}
          onClose={() => setShowExportFieldsDialog(false)}
          onExport={(excludeFields) => {
            setShowExportFieldsDialog(false);
            if (exportMode === "group") {
              void handleExportByGroup(exportGroupName, excludeFields);
            } else {
              void handleExport(excludeFields);
            }
          }}
        />
      )}
    </div>
  );
}
