import { useEffect, useMemo, useRef, useState } from "react";
import { Download, FileUp, Plus, RefreshCw, Save, Trash2, Copy } from "lucide-react";
import { downloadBlob } from "@/lib/shared/api";
import { getOrgProductMetricSnapshot } from "@/lib/org-product/orgProductMetricApi";
import {
  applyExpenseForecastRuleImport,
  copyExpenseForecastRulesFromVersion,
  createExpenseForecastRule,
  deleteExpenseForecastRule,
  downloadExpenseForecastRuleTemplate,
  fetchExpenseForecastMeta,
  listExpenseForecastRules,
  previewExpenseForecastRuleImport,
  recalculateExpenseForecast,
  updateExpenseForecastRule,
  type ExpenseForecastMetaResponseDto,
  type ExpenseForecastRuleImportApplyResponseDto,
  type ExpenseForecastRuleImportPreviewResponseDto,
  type ExpenseForecastRuleParamItemDto,
  type ExpenseForecastRuleRowDto,
  type ExpenseForecastRuleSaveRequestDto,
  type ExpenseForecastRuleVariableItemDto,
} from "@/lib/expense/expenseForecastApi";
import { listBudgetSubjectCatalog, listDeptAccounts } from "@/lib/expense/masterDataApi";
import type { BudgetSubjectCatalogDto, DeptAccountDto } from "@/lib/expense/masterDataApi";
import { deriveRuntimeRefFromOrgProductMetricCode } from "@/lib/org-product/orgProductMetricCode";

type SchemeCode = "MANUAL" | "RESIDUAL_ALLOC" | "METRIC_EXPR";
type RuleTab = "manage" | "config";
type EditorMode = "empty" | "new" | "selected";
type TreeOptionItem = {
  key: string;
  label: string;
  value: string;
  depth: number;
};
type OrgProductMetricNodeDto = {
  code?: string;
  name?: string;
  children?: OrgProductMetricNodeDto[];
};
type OrgProductMetricSnapshotDto = {
  entities: Array<{
    entity_code: string;
    entity_name?: string;
    tables: Array<{
      table_name: string;
      metrics: OrgProductMetricNodeDto[];
    }>;
  }>;
};
type OrgProductMetricVariableCandidate = {
  key: string;
  label: string;
  data_acct_code: string;
  metric_code: string;
  entity_code: string;
  table_name: string;
  org_product_ref: string;
  source_key: string;
  source_subkey: string;
  variable_name: string;
  org_product_refs: string[];
};
type Scheme2Form = {
  allocationMode: "progressive" | "custom";
  progressiveCurveType: "arithmetic" | "geometric";
  allowNegative: boolean;
  weightJson: string;
};

const SCHEME_LABELS: Record<SchemeCode, string> = {
  MANUAL: "手工/导入",
  RESIDUAL_ALLOC: "余额分摊",
  METRIC_EXPR: "指标表达式",
};

const SCHEME_HINTS: Record<SchemeCode, string> = {
  MANUAL: "适用于手工录入或 Excel 导入分月预测的科目。",
  RESIDUAL_ALLOC: "适用于“资划建议 - 累计实际”后按未来月份自动分摊的科目。",
  METRIC_EXPR: "适用于按经营指标、业务规模等变量自动测算的科目。",
};

function normalizeCode(value: string | null | undefined): string {
  return String(value ?? "").trim().toUpperCase();
}

const EMPTY_RULE: ExpenseForecastRuleSaveRequestDto = {
  forecast_year: new Date().getFullYear(),
  forecast_version: "",
  owner_name: "",
  subject_id: 0,
  scheme_code: "MANUAL",
  enabled: true,
  allow_manual_override: false,
  auto_refresh_enabled: true,
  manual_recalc_enabled: true,
  metric_source_priority: "metric_first",
  effective_from_month: 1,
  effective_to_month: 12,
  priority: 100,
  remark: "",
  params: [],
  variables: [],
};

const EMPTY_SCHEME2_FORM: Scheme2Form = {
  allocationMode: "progressive",
  progressiveCurveType: "arithmetic",
  allowNegative: false,
  weightJson: '{"7":1,"8":1,"9":1,"10":1,"11":1,"12":1}',
};

function parseJsonText<T>(text: string, fallback: T): T {
  const trimmed = text.trim();
  if (!trimmed) return fallback;
  try {
    return JSON.parse(trimmed) as T;
  } catch {
    return fallback;
  }
}

function encodeParamsForEditor(params: ExpenseForecastRuleParamItemDto[], scheme: SchemeCode) {
  const expression =
    scheme === "METRIC_EXPR"
      ? params.find((item) => item.param_group === "metric_expr" && item.param_key === "expression")?.param_value ?? ""
      : "";
  if (scheme === "RESIDUAL_ALLOC") {
    const payload: Record<string, unknown> = {};
    params
      .filter((item) => item.param_group === "scheme2")
      .forEach((item) => {
        payload[item.param_key] = item.value_type === "json" ? parseJsonText(item.param_value ?? "", item.param_value ?? "") : item.param_value ?? "";
      });
    return {
      expression,
      scheme2Form: {
        allocationMode: (String(payload.allocation_mode ?? "progressive") === "custom" ? "custom" : "progressive") as "progressive" | "custom",
        progressiveCurveType: (String(payload.progressive_curve_type ?? "arithmetic") === "geometric" ? "geometric" : "arithmetic") as "arithmetic" | "geometric",
        allowNegative: Boolean(payload.allow_negative ?? false),
        weightJson: typeof payload.weight_json === "string"
          ? payload.weight_json
          : JSON.stringify(payload.weight_json ?? {"7":1,"8":1,"9":1,"10":1,"11":1,"12":1}, null, 2),
      },
    };
  }
  return { expression, scheme2Form: EMPTY_SCHEME2_FORM };
}

function buildParamsFromEditor(scheme: SchemeCode, expression: string, scheme2Form: Scheme2Form): ExpenseForecastRuleParamItemDto[] {
  const params: ExpenseForecastRuleParamItemDto[] = [];
  if (scheme === "RESIDUAL_ALLOC") {
    const payload: Record<string, unknown> = {
      allocation_mode: scheme2Form.allocationMode,
      progressive_curve_type: scheme2Form.progressiveCurveType,
      auto_direction_mode: "auto_last_vs_avg",
      last_value_source_mode: "actual_first_then_forecast",
      rounding_mode: "last_month_adjust",
      allow_negative: scheme2Form.allowNegative,
    };
    if (scheme2Form.allocationMode === "custom") {
      payload.weight_json = parseJsonText<Record<string, number>>(scheme2Form.weightJson, {});
    }
    Object.entries(payload).forEach(([key, value]) => {
      params.push({
        param_group: "scheme2",
        param_key: key,
        param_value: typeof value === "object" ? JSON.stringify(value) : String(value ?? ""),
        value_type: typeof value === "object" ? "json" : "string",
      });
    });
  }
  if (scheme === "METRIC_EXPR" && expression.trim()) {
    params.push({
      param_group: "metric_expr",
      param_key: "expression",
      param_value: expression.trim(),
      value_type: "string",
    });
  }
  return params;
}

function summarizeRule(row: ExpenseForecastRuleRowDto): string {
  const parts = [
    row.enabled ? "启用" : "停用",
    row.allow_manual_override ? "允许覆盖" : "不允许覆盖",
    row.auto_refresh_enabled ? "自动刷新" : "手动刷新",
  ];
  return parts.join(" / ");
}

function createEmptyVariable(): ExpenseForecastRuleVariableItemDto {
  return {
    variable_code: "",
    variable_name: "",
    source_type: "metric_tree",
    source_key: "",
    source_subkey: "",
    default_value: 0,
    sort_order: 0,
  };
}

function orgProductRefLabelsForVariable(
  item: ExpenseForecastRuleVariableItemDto,
  candidates: OrgProductMetricVariableCandidate[],
): string[] {
  if (item.source_type !== "metric_tree" && item.source_type !== "org_product_metric") return [];
  const directRefs = (item.org_product_refs ?? []).map((ref) => ref.trim()).filter(Boolean);
  if (directRefs.length) return directRefs;
  const matched = orgProductCandidateForVariable(item, candidates);
  return matched?.org_product_refs ?? [];
}

function orgProductCandidateForVariable(
  item: ExpenseForecastRuleVariableItemDto,
  candidates: OrgProductMetricVariableCandidate[],
): OrgProductMetricVariableCandidate | undefined {
  const sourceKey = normalizeCode(item.source_key);
  const sourceSubkey = normalizeCode(item.source_subkey);
  const orgProductRef = String(item.org_product_ref ?? "").trim();
  if (item.source_type === "org_product_metric") {
    return candidates.find(
      (candidate) =>
        (orgProductRef ? candidate.org_product_ref === orgProductRef : candidate.metric_code === sourceKey) &&
        candidate.entity_code === sourceSubkey,
    );
  }
  return candidates.find(
    (candidate) => candidate.data_acct_code === sourceKey && candidate.entity_code === sourceSubkey,
  );
}

function buildEditorSnapshot(
  form: ExpenseForecastRuleSaveRequestDto,
  expressionText: string,
  scheme2Form: Scheme2Form,
  variableItems: ExpenseForecastRuleVariableItemDto[],
): string {
  return JSON.stringify({
    form,
    expressionText,
    scheme2Form,
    variableItems: variableItems.map((item) => ({
      variable_code: item.variable_code,
      variable_name: item.variable_name ?? "",
      source_type: item.source_type,
      source_key: item.source_key ?? "",
      source_subkey: item.source_subkey ?? "",
      org_product_ref: item.org_product_ref ?? "",
      org_product_metric_code: item.org_product_metric_code ?? "",
      org_product_entity_code: item.org_product_entity_code ?? "",
      org_product_table_name: item.org_product_table_name ?? "",
      default_value: item.default_value ?? 0,
      sort_order: item.sort_order ?? 0,
    })),
  });
}

function TreeSearchSelect(props: {
  label: string;
  placeholder: string;
  items: TreeOptionItem[];
  selectedValue: string;
  selectedLabel?: string;
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (item: TreeOptionItem | null) => void;
}) {
  const { label, placeholder, items, selectedValue, selectedLabel, query, onQueryChange, onSelect } = props;
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const filteredItems = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return items;
    return items.filter((item) => item.label.toLowerCase().includes(keyword));
  }, [items, query]);

  return (
    <div ref={wrapperRef} className="relative flex min-w-[220px] flex-col gap-1">
      <span className="text-gray-500">{label}</span>
      <button
        type="button"
        className="h-8 rounded border border-gray-300 bg-white px-2 text-left hover:bg-gray-50"
        onClick={() => setOpen((value) => !value)}
      >
        {selectedValue ? selectedLabel || selectedValue : placeholder}
      </button>
      {open ? (
        <div className="absolute left-0 top-[calc(100%+4px)] z-20 w-[320px] rounded border border-gray-200 bg-white shadow-lg">
          <div className="border-b border-gray-200 p-2">
            <input
              className="h-8 w-full rounded border border-gray-300 px-2"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder={`请输入${label}关键字`}
              autoFocus
            />
          </div>
          <div className="max-h-72 overflow-auto py-1">
            <button
              type="button"
              className="block w-full px-3 py-2 text-left text-gray-500 hover:bg-gray-50"
              onClick={() => {
                onSelect(null);
                setOpen(false);
              }}
            >
              全部
            </button>
            {filteredItems.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`block w-full px-3 py-2 text-left hover:bg-blue-50 ${selectedValue === item.value ? "bg-blue-50 text-blue-700" : ""}`}
                style={{ paddingLeft: `${12 + item.depth * 16}px` }}
                onClick={() => {
                  onSelect(item);
                  setOpen(false);
                }}
              >
                {item.label}
              </button>
            ))}
            {!filteredItems.length ? (
              <div className="px-3 py-6 text-center text-gray-400">无匹配结果</div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function ExpenseForecastRuleContent() {
  const [meta, setMeta] = useState<ExpenseForecastMetaResponseDto | null>(null);
  const [subjectRows, setSubjectRows] = useState<BudgetSubjectCatalogDto[]>([]);
  const [deptRows, setDeptRows] = useState<DeptAccountDto[]>([]);
  const [orgProductMetricSnapshot, setOrgProductMetricSnapshot] = useState<OrgProductMetricSnapshotDto | null>(null);
  const [activeTab, setActiveTab] = useState<RuleTab>("manage");
  const [editorMode, setEditorMode] = useState<EditorMode>("empty");
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [forecastVersion, setForecastVersion] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [ownerFilterQuery, setOwnerFilterQuery] = useState("");
  const [subjectFilterId, setSubjectFilterId] = useState<number | null>(null);
  const [subjectFilterQuery, setSubjectFilterQuery] = useState("");
  const [configOwnerQuery, setConfigOwnerQuery] = useState("");
  const [configSubjectQuery, setConfigSubjectQuery] = useState("");
  const [schemeFilter, setSchemeFilter] = useState<"ALL" | SchemeCode>("ALL");
  const [enabledFilter, setEnabledFilter] = useState<"ALL" | "ENABLED" | "DISABLED">("ALL");
  const [rows, setRows] = useState<ExpenseForecastRuleRowDto[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState<number | null>(null);
  const [form, setForm] = useState<ExpenseForecastRuleSaveRequestDto>(EMPTY_RULE);
  const [expressionText, setExpressionText] = useState("");
  const [scheme2Form, setScheme2Form] = useState<Scheme2Form>(EMPTY_SCHEME2_FORM);
  const [variableItems, setVariableItems] = useState<ExpenseForecastRuleVariableItemDto[]>([]);
  const [copySourceVersion, setCopySourceVersion] = useState("");
  const [copyTargetVersion, setCopyTargetVersion] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<ExpenseForecastRuleImportPreviewResponseDto | null>(null);
  const [importResult, setImportResult] = useState<ExpenseForecastRuleImportApplyResponseDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [versionCopyDialogOpen, setVersionCopyDialogOpen] = useState(false);
  const [savedEditorSnapshot, setSavedEditorSnapshot] = useState("");
  const [navigationPrompt, setNavigationPrompt] = useState<{
    title: string;
    description: string;
    onDiscard: () => void;
    onSave: () => void;
  } | null>(null);

  const ownerOptions = useMemo(() => {
    const childrenMap = new Map<string, DeptAccountDto[]>();
    deptRows.forEach((row) => {
      const key = row.parent_code ?? "__root__";
      const list = childrenMap.get(key) ?? [];
      list.push(row);
      childrenMap.set(key, list);
    });
    const result: TreeOptionItem[] = [];
    const walk = (parentCode: string | null, depth: number) => {
      const list = childrenMap.get(parentCode ?? "__root__") ?? [];
      list.forEach((row) => {
        result.push({
          key: row.dept_code,
          label: row.dept_name,
          value: row.dept_name,
          depth,
        });
        walk(row.dept_code, depth + 1);
      });
    };
    walk(null, 0);
    return result;
  }, [deptRows]);

  const leafSubjects = useMemo(() => subjectRows.filter((row) => row.is_leaf && !row.formula_text), [subjectRows]);

  const subjectTreeOptions = useMemo(() => {
    const childrenMap = new Map<string, BudgetSubjectCatalogDto[]>();
    subjectRows.forEach((row) => {
      const key = row.parent_id == null ? "__root__" : String(row.parent_id);
      const list = childrenMap.get(key) ?? [];
      list.push(row);
      childrenMap.set(key, list);
    });
    childrenMap.forEach((list) => {
      list.sort((a, b) => {
        if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
        return a.subject_name.localeCompare(b.subject_name, "zh-CN");
      });
    });
    const result: TreeOptionItem[] = [];
    const walk = (parentId: number | null, depth: number) => {
      const list = childrenMap.get(parentId == null ? "__root__" : String(parentId)) ?? [];
      list.forEach((row) => {
        result.push({
          key: String(row.id),
          label: row.subject_name,
          value: String(row.id),
          depth,
        });
        walk(row.id, depth + 1);
      });
    };
    walk(null, 0);
    return result;
  }, [subjectRows]);

  const leafSubjectTreeOptions = useMemo(() => {
    const leafIds = new Set(leafSubjects.map((item) => item.id));
    return subjectTreeOptions.filter((item) => leafIds.has(Number(item.value)));
  }, [leafSubjects, subjectTreeOptions]);

  const orgProductMetricVariableCandidates = useMemo<OrgProductMetricVariableCandidate[]>(() => {
    const result: OrgProductMetricVariableCandidate[] = [];
    const seen = new Set<string>();
    for (const entity of orgProductMetricSnapshot?.entities ?? []) {
      const entityCode = normalizeCode(entity.entity_code);
      for (const table of entity.tables ?? []) {
        const walk = (metrics: OrgProductMetricNodeDto[]) => {
          for (const metric of metrics) {
            const metricCode = normalizeCode(metric.code);
            const dataAcctCode = deriveRuntimeRefFromOrgProductMetricCode(entityCode, metricCode);
            if (metricCode && dataAcctCode) {
              const sourceRef = `${entityCode}:${table.table_name}:${metricCode}`;
              const key = `${sourceRef}:${dataAcctCode}`;
              if (!seen.has(key)) {
                seen.add(key);
                const name = String(metric.name || dataAcctCode);
                const orgProductRef = `${sourceRef} ${name}`.trim();
                result.push({
                  key,
                  label: `${name} · ${dataAcctCode} · ${sourceRef}`,
                  data_acct_code: dataAcctCode,
                  metric_code: metricCode,
                  entity_code: entityCode,
                  table_name: table.table_name,
                  org_product_ref: sourceRef,
                  source_key: dataAcctCode,
                  source_subkey: entityCode,
                  variable_name: name,
                  org_product_refs: [orgProductRef],
                });
              }
            }
            if (metric.children?.length) walk(metric.children);
          }
        };
        walk(table.metrics ?? []);
      }
    }
    return result.sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
  }, [orgProductMetricSnapshot]);

  const applyEditorState = (
    nextForm: ExpenseForecastRuleSaveRequestDto,
    nextExpressionText: string,
    nextScheme2Form: Scheme2Form,
    nextVariableItems: ExpenseForecastRuleVariableItemDto[],
    nextMode: EditorMode,
    nextRuleId: number | null,
  ) => {
    setForm(nextForm);
    setExpressionText(nextExpressionText);
    setScheme2Form(nextScheme2Form);
    setVariableItems(nextVariableItems);
    setEditorMode(nextMode);
    setSelectedRuleId(nextRuleId);
    setSavedEditorSnapshot(
      buildEditorSnapshot(nextForm, nextExpressionText, nextScheme2Form, nextVariableItems),
    );
  };

  const resetForm = (nextVersion?: string, nextMode: EditorMode = "empty") => {
    const version = nextVersion ?? forecastVersion ?? meta?.default_version ?? "";
    const nextForm = {
      ...EMPTY_RULE,
      forecast_year: year,
      forecast_version: version,
    };
    applyEditorState(nextForm, "", EMPTY_SCHEME2_FORM, [], nextMode, null);
  };

  const loadBase = async () => {
    const [metaResp, budgetSubjects, departments, orgProductSnapshot] = await Promise.all([
      fetchExpenseForecastMeta(year),
      listBudgetSubjectCatalog(),
      listDeptAccounts(),
      (getOrgProductMetricSnapshot() as Promise<OrgProductMetricSnapshotDto>).catch(() => ({ entities: [] })),
    ]);
    setMeta(metaResp);
    setSubjectRows(budgetSubjects);
    setDeptRows(departments);
    setOrgProductMetricSnapshot(orgProductSnapshot);
    setForecastVersion((prev) => prev || metaResp.default_version);
    setCopySourceVersion((prev) => prev || metaResp.default_version);
    setCopyTargetVersion((prev) => prev || metaResp.default_version);
  };

  const loadRules = async () => {
    const resp = await listExpenseForecastRules({
      year,
      forecastVersion: forecastVersion || meta?.default_version || "",
      ownerName: ownerFilter || undefined,
      subjectId: subjectFilterId,
    });
    setRows(resp.items);
  };

  useEffect(() => {
    void (async () => {
      try {
        setLoading(true);
        await loadBase();
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载规则配置失败");
      } finally {
        setLoading(false);
      }
    })();
  }, [year]);

  useEffect(() => {
    if (!forecastVersion) return;
    void (async () => {
      try {
        setLoading(true);
        await loadRules();
        setError("");
        if (!selectedRuleId) {
          resetForm(forecastVersion, "empty");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载规则列表失败");
      } finally {
        setLoading(false);
      }
    })();
  }, [forecastVersion, ownerFilter, subjectFilterId]);

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      if (schemeFilter !== "ALL" && row.scheme_code !== schemeFilter) return false;
      if (enabledFilter === "ENABLED" && !row.enabled) return false;
      if (enabledFilter === "DISABLED" && row.enabled) return false;
      return true;
    });
  }, [rows, schemeFilter, enabledFilter]);

  const currentEditorSnapshot = useMemo(
    () => buildEditorSnapshot(form, expressionText, scheme2Form, variableItems),
    [form, expressionText, scheme2Form, variableItems],
  );
  const hasUnsavedChanges =
    activeTab === "config" &&
    editorMode !== "empty" &&
    savedEditorSnapshot !== "" &&
    currentEditorSnapshot !== savedEditorSnapshot;

  const selectRule = (row: ExpenseForecastRuleRowDto) => {
    const { expression, scheme2Form } = encodeParamsForEditor(row.params, row.scheme_code);
    const nextForm = {
      forecast_year: row.forecast_year,
      forecast_version: row.forecast_version,
      owner_name: row.owner_name,
      subject_id: row.subject_id,
      scheme_code: row.scheme_code,
      enabled: row.enabled,
      allow_manual_override: row.allow_manual_override,
      auto_refresh_enabled: row.auto_refresh_enabled,
      manual_recalc_enabled: row.manual_recalc_enabled,
      metric_source_priority: row.metric_source_priority,
      effective_from_month: row.effective_from_month,
      effective_to_month: row.effective_to_month,
      priority: row.priority,
      remark: row.remark ?? "",
      params: row.params,
      variables: row.variables,
    };
    applyEditorState(nextForm, expression, scheme2Form, row.variables.length ? row.variables : [], "selected", row.id);
    setMessage("");
    setError("");
  };

  const saveCurrentRule = async (): Promise<boolean> => {
    try {
      setLoading(true);
      const variables = variableItems
        .map((item, index) => ({ ...item, sort_order: index }))
        .filter((item) => item.variable_code.trim());
      const body: ExpenseForecastRuleSaveRequestDto = {
        ...form,
        forecast_year: year,
        forecast_version: forecastVersion,
        params: buildParamsFromEditor(form.scheme_code, expressionText, scheme2Form),
        variables,
      };
      if (!body.owner_name || !body.subject_id) {
        throw new Error("请选择归属部门和预算科目");
      }
      let savedRow: ExpenseForecastRuleRowDto;
      if (selectedRuleId) {
        savedRow = await updateExpenseForecastRule(selectedRuleId, body);
        setMessage("规则已更新");
      } else {
        savedRow = await createExpenseForecastRule(body);
        setMessage("规则已新增");
      }
      await loadRules();
      selectRule(savedRow);
      setActiveTab("config");
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存规则失败");
      return false;
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    await saveCurrentRule();
  };

  const handleDelete = async (ruleId: number | null = selectedRuleId) => {
    if (!ruleId) return;
    if (!window.confirm("确认删除当前规则吗？")) return;
    try {
      setLoading(true);
      await deleteExpenseForecastRule(ruleId);
      setMessage("规则已删除");
      await loadRules();
      if (selectedRuleId === ruleId) resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除规则失败");
    } finally {
      setLoading(false);
    }
  };

  const handleCopyVersion = async () => {
    try {
      setLoading(true);
      const resp = await copyExpenseForecastRulesFromVersion({
        forecast_year: year,
        source_version: copySourceVersion,
        target_version: copyTargetVersion,
      });
      setMessage(`已复制 ${resp.copied_rules} 条规则`);
      setForecastVersion(copyTargetVersion);
      await loadRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "复制版本规则失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRecalculate = async () => {
    try {
      setLoading(true);
      const resp = await recalculateExpenseForecast({
        forecast_year: year,
        forecast_version: forecastVersion,
        owner_name: form.owner_name || null,
        subject_id: form.subject_id || null,
      });
      setMessage(`已重算 ${resp.recalculated_rules} 条规则，更新 ${resp.updated_cells} 个单元格`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重算失败");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadTemplate = async () => {
    try {
      const result = await downloadExpenseForecastRuleTemplate();
      downloadBlob(result.blob, result.filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "下载模板失败");
    }
  };

  const handleImportPreview = async () => {
    if (!importFile) {
      setError("请先选择导入文件");
      return;
    }
    try {
      setLoading(true);
      setImportPreview(await previewExpenseForecastRuleImport(importFile));
      setImportResult(null);
      setMessage("");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "规则导入预览失败");
    } finally {
      setLoading(false);
    }
  };

  const handleImportApply = async () => {
    if (!importFile) {
      setError("请先选择导入文件");
      return;
    }
    try {
      setLoading(true);
      const payload = await applyExpenseForecastRuleImport(importFile);
      setImportResult(payload);
      setMessage(`导入完成：新增 ${payload.inserted_rules}，更新 ${payload.updated_rules}，错误 ${payload.error_rules}`);
      await loadRules();
    } catch (err) {
      setError(err instanceof Error ? err.message : "规则导入失败");
    } finally {
      setLoading(false);
    }
  };

  const updateVariableItem = (index: number, patch: Partial<ExpenseForecastRuleVariableItemDto>) => {
    setVariableItems((prev) =>
      prev.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  };

  const selectOrgProductMetricVariable = (index: number, candidateKey: string) => {
    if (!candidateKey) return;
    const candidate = orgProductMetricVariableCandidates.find((item) => item.key === candidateKey);
    if (!candidate) return;
    updateVariableItem(index, {
      source_type: "org_product_metric",
      source_key: candidate.metric_code,
      source_subkey: candidate.entity_code,
      org_product_ref: candidate.org_product_ref,
      org_product_metric_code: candidate.metric_code,
      org_product_entity_code: candidate.entity_code,
      org_product_table_name: candidate.table_name,
      variable_name: candidate.variable_name,
      org_product_refs: candidate.org_product_refs,
    });
  };

  const addVariableItem = () => {
    setVariableItems((prev) => [...prev, { ...createEmptyVariable(), sort_order: prev.length }]);
  };

  const removeVariableItem = (index: number) => {
    setVariableItems((prev) => prev.filter((_, itemIndex) => itemIndex !== index));
  };

  const openVersionCopyDialog = () => {
    setCopySourceVersion((prev) => prev || forecastVersion || meta?.default_version || "");
    setCopyTargetVersion((prev) => prev || forecastVersion || meta?.default_version || "");
    setVersionCopyDialogOpen(true);
  };

  const runGuardedAction = (action: () => void, title: string, description: string) => {
    if (!hasUnsavedChanges) {
      action();
      return;
    }
    setNavigationPrompt({
      title,
      description,
      onDiscard: () => {
        setNavigationPrompt(null);
        action();
      },
      onSave: () => {
        void (async () => {
          const ok = await saveCurrentRule();
          if (ok) {
            setNavigationPrompt(null);
            action();
          }
        })();
      },
    });
  };

  const openNewRule = () => {
    runGuardedAction(
      () => {
        resetForm(forecastVersion, "new");
        setActiveTab("config");
      },
      "切换到新建规则",
      "当前规则有未保存修改。你可以先保存，再新建规则；也可以放弃修改后继续。",
    );
  };

  const openRuleForEdit = (row: ExpenseForecastRuleRowDto, goConfig: boolean) => {
    runGuardedAction(
      () => {
        selectRule(row);
        if (goConfig) {
          setActiveTab("config");
        }
      },
      "切换规则",
      "当前规则有未保存修改。是否先保存后再切换到其他规则？",
    );
  };

  const switchTab = (nextTab: RuleTab) => {
    if (nextTab === activeTab) return;
    runGuardedAction(
      () => {
        setActiveTab(nextTab);
      },
      nextTab === "manage" ? "返回规则管理" : "进入参数配置",
      nextTab === "manage"
        ? "当前规则有未保存修改。你可以保存后返回规则管理，也可以放弃修改。"
        : "当前规则有未保存修改。你可以保存后进入参数配置，也可以放弃修改。",
    );
  };

  const discardChanges = () => {
    if (editorMode === "selected" && selectedRuleId) {
      const matched = rows.find((item) => item.id === selectedRuleId);
      if (matched) {
        selectRule(matched);
        return;
      }
    }
    resetForm(forecastVersion, editorMode);
  };

  return (
    <div className="flex h-full flex-col bg-white text-xs text-gray-700">
      <div className="space-y-3 border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-medium text-gray-800">费用预测逻辑配置</div>
            <div className="mt-1 text-[11px] text-gray-500">通过“规则管理”维护规则列表和批量操作，通过“参数配置”专注编辑当前规则。</div>
          </div>
          <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-[11px] text-gray-500">
            当前规则数：<span className="font-medium text-gray-700">{filteredRows.length}</span>
            <span className="mx-1 text-gray-400">/</span>
            总数：<span className="font-medium text-gray-700">{rows.length}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className={`h-9 rounded border px-4 ${activeTab === "manage" ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-300 bg-white hover:bg-gray-50"}`}
            onClick={() => switchTab("manage")}
          >
            规则管理
          </button>
          <button
            type="button"
            className={`h-9 rounded border px-4 ${activeTab === "config" ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-300 bg-white hover:bg-gray-50"}`}
            onClick={() => switchTab("config")}
          >
            参数配置
          </button>
        </div>

        {message ? <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-700">{message}</div> : null}
        {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-red-600">{error}</div> : null}
      </div>
      {activeTab === "manage" ? (
        <div className="flex-1 overflow-auto px-4 py-4">
          <div className="space-y-4">
            <div className="rounded border border-gray-200 bg-[#f8fafc] px-3 py-3">
              <div className="mb-2 text-[11px] font-medium text-gray-600">查询范围</div>
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500">年份</span>
                  <input className="h-8 w-24 rounded border border-gray-300 px-2" type="number" value={year} onChange={(e) => setYear(Number(e.target.value || 0))} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500">版本</span>
                  <input className="h-8 w-40 rounded border border-gray-300 px-2" list="expense-rule-versions" value={forecastVersion} onChange={(e) => setForecastVersion(e.target.value)} />
                  <datalist id="expense-rule-versions">
                    {(meta?.version_suggestions ?? []).map((item) => (
                      <option key={item} value={item} />
                    ))}
                  </datalist>
                </label>
                <TreeSearchSelect
                  label="部门"
                  placeholder="全部部门"
                  items={ownerOptions}
                  selectedValue={ownerFilter}
                  selectedLabel={ownerFilter}
                  query={ownerFilterQuery}
                  onQueryChange={setOwnerFilterQuery}
                  onSelect={(item) => {
                    setOwnerFilter(item?.value ?? "");
                    setOwnerFilterQuery(item?.label ?? "");
                  }}
                />
                <TreeSearchSelect
                  label="预算科目"
                  placeholder="全部预算科目"
                  items={subjectTreeOptions}
                  selectedValue={subjectFilterId == null ? "" : String(subjectFilterId)}
                  selectedLabel={subjectTreeOptions.find((item) => item.value === String(subjectFilterId ?? ""))?.label}
                  query={subjectFilterQuery}
                  onQueryChange={setSubjectFilterQuery}
                  onSelect={(item) => {
                    setSubjectFilterId(item ? Number(item.value) : null);
                    setSubjectFilterQuery(item?.label ?? "");
                  }}
                />
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500">预测逻辑</span>
                  <select className="h-8 min-w-[180px] rounded border border-gray-300 px-2" value={schemeFilter} onChange={(e) => setSchemeFilter(e.target.value as "ALL" | SchemeCode)}>
                    <option value="ALL">全部逻辑</option>
                    <option value="MANUAL">{SCHEME_LABELS.MANUAL}</option>
                    <option value="RESIDUAL_ALLOC">{SCHEME_LABELS.RESIDUAL_ALLOC}</option>
                    <option value="METRIC_EXPR">{SCHEME_LABELS.METRIC_EXPR}</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-gray-500">启用状态</span>
                  <select className="h-8 min-w-[140px] rounded border border-gray-300 px-2" value={enabledFilter} onChange={(e) => setEnabledFilter(e.target.value as "ALL" | "ENABLED" | "DISABLED")}>
                    <option value="ALL">全部状态</option>
                    <option value="ENABLED">仅启用</option>
                    <option value="DISABLED">仅停用</option>
                  </select>
                </label>
                <button type="button" className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50" onClick={() => void loadRules()}>
                  <RefreshCw className={`mr-1 inline h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                  刷新列表
                </button>
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded border border-gray-200 bg-white">
                <div className="border-b border-gray-200 px-4 py-3">
                  <div className="text-sm font-medium text-gray-800">规则列表</div>
                  <div className="mt-1 text-[11px] text-gray-500">列表仅保留“去配置”入口，点击后直接进入第 2 个标签页编辑参数。</div>
                </div>
                <div className="border-b border-gray-200 bg-[#fafbfc] px-4 py-3">
                  <div className="flex flex-wrap items-end gap-3">
                    <button type="button" className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50" onClick={openNewRule}>
                      <Plus className="mr-1 inline h-3.5 w-3.5" />
                      新建规则
                    </button>
                    <button type="button" className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50" onClick={() => void handleDownloadTemplate()}>
                      <Download className="mr-1 inline h-3.5 w-3.5" />
                      下载模板
                    </button>
                    <label className="flex flex-col gap-1">
                      <span className="text-gray-500">导入文件</span>
                      <input className="block h-8 rounded border border-gray-300 px-2 py-1" type="file" accept=".xlsx" onChange={(e) => setImportFile(e.target.files?.[0] ?? null)} />
                    </label>
                    <button type="button" className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50" onClick={() => void handleImportPreview()}>
                      <FileUp className="mr-1 inline h-3.5 w-3.5" />
                      预览导入
                    </button>
                    <button type="button" className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50" onClick={() => void handleImportApply()}>
                      应用导入
                    </button>
                    <button type="button" className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50" onClick={openVersionCopyDialog}>
                      <Copy className="mr-1 inline h-3.5 w-3.5" />
                      版本复制
                    </button>
                  </div>
                </div>
                <div className="overflow-auto">
                  <table className="min-w-full border-collapse">
                    <thead className="bg-[#f8fafc]">
                      <tr>
                        <th className="border-b border-gray-200 px-3 py-2 text-left font-medium">归属部门</th>
                        <th className="border-b border-gray-200 px-3 py-2 text-left font-medium">预算科目</th>
                        <th className="border-b border-gray-200 px-3 py-2 text-left font-medium">预测逻辑</th>
                        <th className="border-b border-gray-200 px-3 py-2 text-left font-medium">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRows.map((row) => (
                        <tr
                          key={row.id}
                          className={`${selectedRuleId === row.id ? "bg-blue-50" : "hover:bg-gray-50"}`}
                        >
                          <td className="border-b border-gray-100 px-3 py-2 align-top">{row.owner_name}</td>
                          <td className="border-b border-gray-100 px-3 py-2 align-top">{row.subject_name}</td>
                          <td className="border-b border-gray-100 px-3 py-2">
                            <div>{SCHEME_LABELS[row.scheme_code]}</div>
                            <div className="mt-1 text-[10px] text-gray-500">{summarizeRule(row)}</div>
                          </td>
                          <td className="border-b border-gray-100 px-3 py-2">
                            <div className="flex flex-wrap gap-2">
                              <button type="button" className="h-8 rounded border border-blue-500 px-3 text-blue-700 hover:bg-blue-50" onClick={() => openRuleForEdit(row, true)}>
                                去配置
                              </button>
                              <button type="button" className="h-8 rounded border border-red-200 px-3 text-red-600 hover:bg-red-50" onClick={() => void handleDelete(row.id)}>
                                <Trash2 className="mr-1 inline h-3.5 w-3.5" />
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!filteredRows.length ? (
                        <tr>
                          <td colSpan={4} className="px-3 py-10 text-center text-gray-400">
                            当前筛选条件下暂无规则
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>

              {importPreview ? (
                <div className="space-y-2 rounded border border-gray-200 bg-white px-4 py-4">
                  <div className="font-medium text-gray-800">导入预览</div>
                  <div className="grid grid-cols-4 gap-3">
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">新增：{importPreview.insertable_rules}</div>
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">更新：{importPreview.updatable_rules}</div>
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">跳过：{importPreview.skipped_rules}</div>
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">错误：{importPreview.error_rules}</div>
                  </div>
                </div>
              ) : null}

              {importResult ? (
                <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-3 text-emerald-700">
                  导入结果：新增 {importResult.inserted_rules}，更新 {importResult.updated_rules}，错误 {importResult.error_rules}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-auto px-4 py-4">
          {editorMode === "empty" ? (
            <div className="flex h-full items-center justify-center">
              <div className="w-full max-w-xl rounded border border-dashed border-gray-300 bg-white px-6 py-12 text-center">
                <div className="text-base font-medium text-gray-800">请先选择规则</div>
                <div className="mt-2 text-[12px] text-gray-500">请先到“规则管理”标签页选择一条规则，或新建规则后再进入参数配置。</div>
                <div className="mt-4 flex justify-center gap-2">
                  <button type="button" className="h-9 rounded border border-gray-300 px-4 hover:bg-gray-50" onClick={() => switchTab("manage")}>
                    返回规则管理
                  </button>
                  <button type="button" className="h-9 rounded border border-blue-500 bg-blue-500 px-4 text-white hover:bg-blue-600" onClick={openNewRule}>
                    新建规则
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4 pb-24">
              <div className="rounded border border-gray-200 bg-white px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-gray-800">当前规则</div>
                    <div className="mt-1 text-[11px] text-gray-500">{SCHEME_HINTS[form.scheme_code]}</div>
                  </div>
                  <div className="rounded bg-gray-100 px-2 py-1 text-[11px] text-gray-600">
                    {editorMode === "new" ? "新建规则" : `规则ID：${selectedRuleId ?? "-"}`}
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
                  <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                    <div className="text-[10px] text-gray-500">归属部门</div>
                    <div className="mt-1 font-medium text-gray-700">{form.owner_name || "-"}</div>
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                    <div className="text-[10px] text-gray-500">预算科目</div>
                    <div className="mt-1 font-medium text-gray-700">{leafSubjects.find((item) => item.id === form.subject_id)?.subject_name ?? "-"}</div>
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                    <div className="text-[10px] text-gray-500">预测逻辑</div>
                    <div className="mt-1 font-medium text-gray-700">{SCHEME_LABELS[form.scheme_code]}</div>
                  </div>
                  <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
                    <div className="text-[10px] text-gray-500">未保存状态</div>
                    <div className="mt-1 font-medium text-gray-700">{hasUnsavedChanges ? "有修改未保存" : "已保存"}</div>
                  </div>
                </div>
              </div>

              <div className="rounded border border-gray-200 bg-white px-4 py-4">
                <div className="mb-3 text-[11px] font-medium text-gray-600">1. 适用范围</div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  <TreeSearchSelect
                    label="归属部门"
                    placeholder="请选择归属部门"
                    items={ownerOptions}
                    selectedValue={form.owner_name}
                    selectedLabel={form.owner_name}
                    query={configOwnerQuery}
                    onQueryChange={setConfigOwnerQuery}
                    onSelect={(item) => {
                      setForm((prev) => ({ ...prev, owner_name: item?.value ?? "" }));
                      setConfigOwnerQuery(item?.label ?? "");
                    }}
                  />
                  <TreeSearchSelect
                    label="预算科目"
                    placeholder="请选择预算科目"
                    items={leafSubjectTreeOptions}
                    selectedValue={form.subject_id ? String(form.subject_id) : ""}
                    selectedLabel={leafSubjectTreeOptions.find((item) => item.value === String(form.subject_id || ""))?.label}
                    query={configSubjectQuery}
                    onQueryChange={setConfigSubjectQuery}
                    onSelect={(item) => {
                      setForm((prev) => ({ ...prev, subject_id: item ? Number(item.value) : 0 }));
                      setConfigSubjectQuery(item?.label ?? "");
                    }}
                  />
                  <label className="flex flex-col gap-1">
                    <span className="text-gray-500">预测逻辑</span>
                    <select className="h-8 rounded border border-gray-300 px-2" value={form.scheme_code} onChange={(e) => setForm((prev) => ({ ...prev, scheme_code: e.target.value as SchemeCode }))}>
                      <option value="MANUAL">{SCHEME_LABELS.MANUAL}</option>
                      <option value="RESIDUAL_ALLOC">{SCHEME_LABELS.RESIDUAL_ALLOC}</option>
                      <option value="METRIC_EXPR">{SCHEME_LABELS.METRIC_EXPR}</option>
                    </select>
                  </label>
                </div>
              </div>

              <div className="rounded border border-gray-200 bg-white px-4 py-4">
                <div className="mb-3 text-[11px] font-medium text-gray-600">2. 生效与控制</div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                  <label className="flex flex-col gap-1">
                    <span className="text-gray-500">生效开始月</span>
                    <input className="h-8 rounded border border-gray-300 px-2" type="number" min={1} max={12} value={form.effective_from_month} onChange={(e) => setForm((prev) => ({ ...prev, effective_from_month: Number(e.target.value || 1) }))} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-gray-500">生效结束月</span>
                    <input className="h-8 rounded border border-gray-300 px-2" type="number" min={1} max={12} value={form.effective_to_month} onChange={(e) => setForm((prev) => ({ ...prev, effective_to_month: Number(e.target.value || 12) }))} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-gray-500">规则优先级</span>
                    <input className="h-8 rounded border border-gray-300 px-2" type="number" value={form.priority} onChange={(e) => setForm((prev) => ({ ...prev, priority: Number(e.target.value || 100) }))} />
                    <span className="text-[10px] leading-4 text-gray-400">
                      数字越小优先级越高；当前同一部门+科目仅允许一条规则，主要为后续扩展预留。
                    </span>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-gray-500">数据源优先级</span>
                    <select className="h-8 rounded border border-gray-300 px-2" value={form.metric_source_priority} onChange={(e) => setForm((prev) => ({ ...prev, metric_source_priority: e.target.value as "metric_first" | "inline_first" }))}>
                      <option value="metric_first">机构及产品指标编码优先</option>
                      <option value="inline_first">表内维护优先</option>
                    </select>
                  </label>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                  <label className="flex items-center gap-2 rounded border border-gray-200 px-3 py-2">
                    <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((prev) => ({ ...prev, enabled: e.target.checked }))} />
                    <span>启用规则</span>
                  </label>
                  <label className="flex items-center gap-2 rounded border border-gray-200 px-3 py-2">
                    <input type="checkbox" checked={form.allow_manual_override} onChange={(e) => setForm((prev) => ({ ...prev, allow_manual_override: e.target.checked }))} />
                    <span>允许人工覆盖</span>
                  </label>
                  <label className="flex items-center gap-2 rounded border border-gray-200 px-3 py-2">
                    <input type="checkbox" checked={form.auto_refresh_enabled} onChange={(e) => setForm((prev) => ({ ...prev, auto_refresh_enabled: e.target.checked }))} />
                    <span>自动刷新</span>
                  </label>
                  <label className="flex items-center gap-2 rounded border border-gray-200 px-3 py-2">
                    <input type="checkbox" checked={form.manual_recalc_enabled} onChange={(e) => setForm((prev) => ({ ...prev, manual_recalc_enabled: e.target.checked }))} />
                    <span>允许手动重算</span>
                  </label>
                </div>
              </div>

              <div className="rounded border border-gray-200 bg-white px-4 py-4">
                <div className="mb-3 text-[11px] font-medium text-gray-600">3. 预测逻辑参数</div>
                {form.scheme_code === "MANUAL" ? (
                  <div className="rounded border border-blue-100 bg-blue-50 px-3 py-3 text-blue-700">
                    当前规则为手工/Excel 导入模式，分月预测通过费用预测表直接录入或导入。
                  </div>
                ) : null}
                {form.scheme_code === "RESIDUAL_ALLOC" ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                      <label className="flex flex-col gap-1">
                        <span className="text-gray-500">分摊模式</span>
                        <select className="h-8 rounded border border-gray-300 px-2" value={scheme2Form.allocationMode} onChange={(e) => setScheme2Form((prev) => ({ ...prev, allocationMode: e.target.value as "progressive" | "custom" }))}>
                          <option value="progressive">逐月递增</option>
                          <option value="custom">自定义系数</option>
                        </select>
                      </label>
                      <label className="flex flex-col gap-1">
                        <span className="text-gray-500">自动反推方式</span>
                        <select className="h-8 rounded border border-gray-300 px-2" value={scheme2Form.progressiveCurveType} onChange={(e) => setScheme2Form((prev) => ({ ...prev, progressiveCurveType: e.target.value as "arithmetic" | "geometric" }))} disabled={scheme2Form.allocationMode !== "progressive"}>
                          <option value="arithmetic">等差金额</option>
                          <option value="geometric">等比比例</option>
                        </select>
                      </label>
                      <label className="flex items-center gap-2 rounded border border-gray-200 px-3 py-2">
                        <input type="checkbox" checked={scheme2Form.allowNegative} onChange={(e) => setScheme2Form((prev) => ({ ...prev, allowNegative: e.target.checked }))} />
                        <span>允许剩余金额为负</span>
                      </label>
                    </div>
                    <div className="rounded border border-gray-100 bg-gray-50 px-3 py-2 text-[11px] leading-5 text-gray-500">
                      固定口径：剩余金额 = 资划建议 - 本年累计实际。
                      <br />
                      选择“逐月递增”时，系统会自动按“优先实际，没有实际则取预测”的上月金额与未来月均值比较，自动判断递增/递减，并反推等差金额或等比比例；尾差统一在末月补差。
                    </div>
                    {scheme2Form.allocationMode === "custom" ? (
                      <div className="space-y-2">
                        <div className="text-gray-500">月份权重 JSON</div>
                        <textarea className="min-h-[140px] w-full rounded border border-gray-300 px-3 py-2 font-mono text-[12px]" value={scheme2Form.weightJson} onChange={(e) => setScheme2Form((prev) => ({ ...prev, weightJson: e.target.value }))} placeholder='{"7":1,"8":1.1,"9":1.2,"10":1.3,"11":1.4,"12":1.5}' />
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {form.scheme_code === "METRIC_EXPR" ? (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <div className="text-gray-500">表达式</div>
                      <textarea className="min-h-[100px] w-full rounded border border-gray-300 px-3 py-2 font-mono text-[12px]" value={expressionText} onChange={(e) => setExpressionText(e.target.value)} placeholder="例如：base_amount * (1 + revenue_growth * factor)" />
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="text-gray-500">变量映射</div>
                        <button type="button" className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50" onClick={addVariableItem}>
                          <Plus className="mr-1 inline h-3.5 w-3.5" />
                          新增变量
                        </button>
                      </div>
                      <div className="overflow-hidden rounded border border-gray-200">
                        <table className="min-w-full border-collapse">
                          <thead className="bg-[#f8fafc]">
                            <tr>
                              <th className="border-b border-gray-200 px-2 py-2 text-left font-medium">变量名</th>
                              <th className="border-b border-gray-200 px-2 py-2 text-left font-medium">显示名</th>
                              <th className="border-b border-gray-200 px-2 py-2 text-left font-medium">来源类型</th>
                              <th className="border-b border-gray-200 px-2 py-2 text-left font-medium">来源编码</th>
                              <th className="border-b border-gray-200 px-2 py-2 text-left font-medium">附加键</th>
                              <th className="border-b border-gray-200 px-2 py-2 text-left font-medium">默认值</th>
                              <th className="border-b border-gray-200 px-2 py-2 text-left font-medium">操作</th>
                            </tr>
                          </thead>
                          <tbody>
                            {variableItems.map((item, index) => {
                              const orgProductRefLabels = orgProductRefLabelsForVariable(
                                item,
                                orgProductMetricVariableCandidates,
                              );
                              return (
                              <tr key={`${item.variable_code || "new"}-${index}`} className="odd:bg-white even:bg-gray-50">
                                <td className="border-b border-gray-100 px-2 py-2">
                                  <input className="h-8 w-full rounded border border-gray-300 px-2" value={item.variable_code} onChange={(e) => updateVariableItem(index, { variable_code: e.target.value })} placeholder="revenue_growth" />
                                </td>
                                <td className="border-b border-gray-100 px-2 py-2">
                                  <input className="h-8 w-full rounded border border-gray-300 px-2" value={item.variable_name ?? ""} onChange={(e) => updateVariableItem(index, { variable_name: e.target.value })} placeholder="营收增幅" />
                                </td>
                                <td className="border-b border-gray-100 px-2 py-2">
                                  <select
                                    className="h-8 w-full rounded border border-gray-300 px-2"
                                    value={item.source_type}
                                    onChange={(e) =>
                                      updateVariableItem(index, {
                                        source_type: e.target.value as ExpenseForecastRuleVariableItemDto["source_type"],
                                        org_product_ref: "",
                                        org_product_metric_code: "",
                                        org_product_entity_code: "",
                                        org_product_table_name: "",
                                        org_product_refs: [],
                                      })
                                    }
                                  >
                                    <option value="metric_tree">机构及产品指标编码</option>
                                    <option value="org_product_metric">机构产品指标</option>
                                    <option value="forecast_inline">表内字段</option>
                                    <option value="actual">实际值</option>
                                    <option value="annual_field">年度字段</option>
                                    <option value="constant">固定常量</option>
                                  </select>
                                </td>
                                <td className="border-b border-gray-100 px-2 py-2">
                                  <div className="space-y-1">
                                    {item.source_type === "metric_tree" || item.source_type === "org_product_metric" ? (
                                      <select
                                        className="h-8 w-full rounded border border-blue-200 bg-blue-50 px-2 text-blue-800"
                                        value={orgProductCandidateForVariable(item, orgProductMetricVariableCandidates)?.key ?? ""}
                                        onChange={(e) => selectOrgProductMetricVariable(index, e.target.value)}
                                      >
                                        <option value="">选择已确认机构产品指标</option>
                                        {orgProductMetricVariableCandidates.map((candidate) => (
                                          <option key={candidate.key} value={candidate.key}>
                                            {candidate.label}
                                          </option>
                                        ))}
                                      </select>
                                    ) : null}
                                    <input
                                      className="h-8 w-full rounded border border-gray-300 px-2"
                                      value={item.source_key ?? ""}
                                      onChange={(e) => updateVariableItem(index, { source_key: e.target.value, org_product_ref: "", org_product_metric_code: "", org_product_entity_code: "", org_product_table_name: "", org_product_refs: [] })}
                                      placeholder="A0111 / A01.01.01.001"
                                    />
                                    {orgProductRefLabels.length ? (
                                      <div className="text-[11px] leading-4 text-emerald-700">
                                        机构产品来源：{orgProductRefLabels.slice(0, 2).join("；")}
                                        {orgProductRefLabels.length > 2 ? ` 等${orgProductRefLabels.length}项` : ""}
                                      </div>
                                    ) : null}
                                  </div>
                                </td>
                                <td className="border-b border-gray-100 px-2 py-2">
                                  <input className="h-8 w-full rounded border border-gray-300 px-2" value={item.source_subkey ?? ""} onChange={(e) => updateVariableItem(index, { source_subkey: e.target.value, org_product_ref: "", org_product_metric_code: "", org_product_entity_code: "", org_product_table_name: "", org_product_refs: [] })} placeholder="product_code / cumulative" />
                                </td>
                                <td className="border-b border-gray-100 px-2 py-2">
                                  <input className="h-8 w-full rounded border border-gray-300 px-2" type="number" value={item.default_value ?? 0} onChange={(e) => updateVariableItem(index, { default_value: Number(e.target.value || 0) })} />
                                </td>
                                <td className="border-b border-gray-100 px-2 py-2">
                                  <button type="button" className="h-8 rounded border border-gray-300 px-3 hover:bg-gray-50" onClick={() => removeVariableItem(index)}>
                                    删除
                                  </button>
                                </td>
                              </tr>
                              );
                            })}
                            {!variableItems.length ? (
                              <tr>
                                <td colSpan={7} className="px-3 py-6 text-center text-gray-400">
                                  当前未配置变量，点击“新增变量”开始配置
                                </td>
                              </tr>
                            ) : null}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="rounded border border-gray-200 bg-white px-4 py-4">
                <div className="mb-3 text-[11px] font-medium text-gray-600">4. 备注</div>
                <textarea className="min-h-[80px] w-full rounded border border-gray-300 px-3 py-2" value={form.remark ?? ""} onChange={(e) => setForm((prev) => ({ ...prev, remark: e.target.value }))} />
              </div>

              <div className="sticky bottom-0 z-10 rounded border border-gray-200 bg-white px-4 py-3 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-[11px] text-gray-500">{hasUnsavedChanges ? "当前有未保存修改" : "当前修改已保存"}</div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className="h-9 rounded border border-gray-300 px-4 hover:bg-gray-50" onClick={() => switchTab("manage")}>
                      返回规则管理
                    </button>
                    <button type="button" className="h-9 rounded border border-gray-300 px-4 hover:bg-gray-50" onClick={discardChanges}>
                      放弃修改
                    </button>
                    <button type="button" className="h-9 rounded border border-gray-300 px-4 hover:bg-gray-50" onClick={() => void handleRecalculate()}>
                      <RefreshCw className="mr-1 inline h-3.5 w-3.5" />
                      重算
                    </button>
                    <button type="button" className="h-9 rounded border border-blue-500 bg-blue-500 px-4 text-white hover:bg-blue-600" onClick={() => void handleSave()}>
                      <Save className="mr-1 inline h-3.5 w-3.5" />
                      保存规则
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {navigationPrompt ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded border border-gray-200 bg-white p-4 shadow-xl">
            <div className="text-sm font-medium text-gray-800">{navigationPrompt.title}</div>
            <div className="mt-2 text-[12px] text-gray-500">{navigationPrompt.description}</div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="h-9 rounded border border-gray-300 px-4 hover:bg-gray-50" onClick={() => setNavigationPrompt(null)}>
                继续编辑
              </button>
              <button type="button" className="h-9 rounded border border-gray-300 px-4 hover:bg-gray-50" onClick={navigationPrompt.onDiscard}>
                放弃修改
              </button>
              <button type="button" className="h-9 rounded border border-blue-500 bg-blue-500 px-4 text-white hover:bg-blue-600" onClick={navigationPrompt.onSave}>
                保存并继续
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {versionCopyDialogOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded border border-gray-200 bg-white p-4 shadow-xl">
            <div className="text-sm font-medium text-gray-800">版本复制</div>
            <div className="mt-2 text-[12px] text-gray-500">将来源版本下的整套预测逻辑规则复制到目标版本，适合沿用上一版本配置。</div>
            <div className="mt-4 space-y-3">
              <label className="flex flex-col gap-1">
                <span className="text-gray-500">来源版本</span>
                <input
                  className="h-9 rounded border border-gray-300 px-3"
                  list="expense-rule-versions"
                  value={copySourceVersion}
                  onChange={(e) => setCopySourceVersion(e.target.value)}
                  placeholder="请选择来源版本"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-gray-500">目标版本</span>
                <input
                  className="h-9 rounded border border-gray-300 px-3"
                  list="expense-rule-versions"
                  value={copyTargetVersion}
                  onChange={(e) => setCopyTargetVersion(e.target.value)}
                  placeholder="请选择目标版本"
                />
              </label>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="h-9 rounded border border-gray-300 px-4 hover:bg-gray-50"
                onClick={() => setVersionCopyDialogOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="h-9 rounded border border-blue-500 bg-blue-500 px-4 text-white hover:bg-blue-600"
                onClick={() => {
                  void (async () => {
                    await handleCopyVersion();
                    setVersionCopyDialogOpen(false);
                  })();
                }}
              >
                开始复制
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
