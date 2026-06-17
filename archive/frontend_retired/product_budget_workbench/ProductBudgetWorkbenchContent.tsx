import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  Bot,
  ChevronsLeft,
  ChevronsRight,
  CheckCircle2,
  Copy,
  Database,
  FileSpreadsheet,
  Link2,
  Loader2,
  Plus,
  Save,
  Search,
  Send,
  Sparkles,
  Table2,
  Wand2,
  X,
} from "lucide-react";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { FormulaEditorDialog } from "./FormulaEditorDialog";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import type { ImperativePanelHandle } from "react-resizable-panels";

type WorkbenchStatus = "draft" | "ready" | "warning" | "dispatched";

type WorkbenchProduct = {
  product_code: string;
  product_name: string;
  owner: string;
  status: WorkbenchStatus;
  component_count: number;
};

type WorkbenchComponent = {
  component_id: string;
  component_name: string;
  template_id: string | null;
  template_name: string | null;
  rule_code: string;
  rule_label: string;
  source_type: string;
  metric_node_code: string | null;
  metric_node_name: string | null;
  metric_binding_code: string | null;
  data_acct_code: string | null;
  data_acct_name: string | null;
  formula: string;
  value_type: string;
  status: WorkbenchStatus;
  ai_reason: string | null;
  trial_m01: number;
  trial_m02: number;
  trial_m03: number;
  trial_annual: number;
};

type WorkbenchRow = {
  report_acct_code: string;
  report_acct_name: string;
  metric_node_code: string | null;
  metric_node_name: string | null;
  compat_report_acct_code: string | null;
  parent_code: string | null;
  level: number;
  row_type?: "group" | "metric" | "compat";
  component_count?: number;
  status: WorkbenchStatus;
  trial_m01: number;
  trial_m02: number;
  trial_m03: number;
  trial_annual: number;
  components: WorkbenchComponent[];
};

type WorkbenchTemplate = {
  template_id: string;
  template_name: string;
  component_name: string;
  rule_code: string;
  source_type: string;
  formula: string | null;
  value_type: string;
  data_acct_code: string | null;
};

type RuleOption = {
  code: string;
  label: string;
};

type WorkbenchOverview = {
  products: WorkbenchProduct[];
  selected_product_code: string | null;
  rows: WorkbenchRow[];
  templates: WorkbenchTemplate[];
  rule_options: RuleOption[];
  summary: {
    report_row_count?: number;
    component_count?: number;
    ready_count?: number;
    warning_count?: number;
    trial_annual?: number;
  };
};

type AiSuggestion = {
  component_id?: string;
  product_code?: string;
  metric_node_code?: string;
  report_acct_code?: string;
  component_name?: string;
  title?: string;
  rule_code?: string;
  source_type?: string;
  formula?: string;
  data_account_name?: string;
  reason?: string;
};

type AiPendingDataAccount = {
  component_id: string;
  product_code: string;
  metric_node_code: string;
  metric_node_name?: string;
  suggested_data_acct_name?: string;
  value_type?: string;
  reason?: string;
};

type AiPendingMetricNode = {
  component_id: string;
  product_code: string;
  compat_report_acct_code?: string;
  suggested_name?: string;
  component_name?: string;
  reason?: string;
};

type AiConfigProductResult = {
  model: string;
  product_code: string;
  applied_count: number;
  skipped_count: number;
  warnings: string[];
  suggestions?: AiSuggestion[];
  configured_drafts?: AiSuggestion[];
  pending_data_accounts?: AiPendingDataAccount[];
  pending_metric_nodes?: AiPendingMetricNode[];
  result_groups?: {
    configured_drafts?: AiSuggestion[];
    pending_data_accounts?: AiPendingDataAccount[];
    pending_metric_nodes?: AiPendingMetricNode[];
  };
};

type AiConfigWorkbenchResult = {
  model: string;
  scopeLabel: string;
  productCodes: string[];
  configuredDrafts: AiSuggestion[];
  pendingDataAccounts: AiPendingDataAccount[];
  pendingMetricNodes: AiPendingMetricNode[];
  warnings: string[];
};

type DraftState = {
  component_name: string;
  rule_code: string;
  source_type: string;
  data_acct_code: string;
  formula: string;
  value_type: string;
};

type NewMetricDraftState = {
  parent_metric_node_code: string;
  metric_node_name: string;
  formula: string;
  value_type: string;
};

type CreateMetricDataAccountResult = {
  component_id: string;
  metric_node_code: string;
  metric_node_name: string;
  metric_node_created: boolean;
  data_acct_code: string;
  data_account_created: boolean;
  component_created: boolean;
};

const statusMeta: Record<WorkbenchStatus, { label: string; cls: string; icon: typeof CheckCircle2 }> = {
  draft: { label: "草稿", cls: "border-sky-200 bg-sky-50 text-sky-700", icon: Save },
  ready: { label: "可下发", cls: "border-emerald-200 bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
  warning: { label: "待补齐", cls: "border-amber-200 bg-amber-50 text-amber-700", icon: AlertTriangle },
  dispatched: { label: "已下发", cls: "border-indigo-200 bg-indigo-50 text-indigo-700", icon: Send },
};

function formatAmount(value: number | null | undefined) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

function normalizeAiConfigResult(result: AiConfigProductResult, scopeLabel: string): AiConfigWorkbenchResult {
  const groups = result.result_groups || {};
  const configuredDrafts = groups.configured_drafts || result.configured_drafts || result.suggestions || [];
  const pendingDataAccounts = groups.pending_data_accounts || result.pending_data_accounts || [];
  const pendingMetricNodes = groups.pending_metric_nodes || result.pending_metric_nodes || [];
  return {
    model: result.model,
    scopeLabel,
    productCodes: [result.product_code].filter(Boolean),
    configuredDrafts,
    pendingDataAccounts,
    pendingMetricNodes,
    warnings: result.warnings || [],
  };
}

function StatusPill({ status }: { status: WorkbenchStatus }) {
  const meta = statusMeta[status] ?? statusMeta.draft;
  const Icon = meta.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] ${meta.cls}`}>
      <Icon className="h-3 w-3" />
      {meta.label}
    </span>
  );
}

function IconButton({
  children,
  onClick,
  tone = "plain",
  disabled = false,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: "plain" | "primary" | "soft";
  disabled?: boolean;
  title?: string;
}) {
  const cls =
    tone === "primary"
      ? "bb-btn-primary"
      : tone === "soft"
        ? "border-[#c9d8ea] bg-[var(--bb-primary-soft)] text-[var(--bb-primary)]"
        : "bb-btn-secondary";
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`bb-btn h-8 px-2.5 ${cls} disabled:cursor-not-allowed disabled:opacity-50`}
    >
      {children}
    </button>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      className="bb-input h-8 w-full"
    />
  );
}

function SelectInput({
  value,
  onChange,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="bb-select h-8 w-full"
    >
      {children}
    </select>
  );
}

export function ProductBudgetWorkbenchContent() {
  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);
  const [overview, setOverview] = useState<WorkbenchOverview | null>(null);
  const [selectedProductCode, setSelectedProductCode] = useState<string>("");
  const [selectedReportCode, setSelectedReportCode] = useState<string>("");
  const [selectedComponentId, setSelectedComponentId] = useState<string>("");
  const [query, setQuery] = useState("");
  const [activeStep, setActiveStep] = useState<"rule" | "trial">("rule");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<AiSuggestion[]>([]);
  const [aiConfigResult, setAiConfigResult] = useState<AiConfigWorkbenchResult | null>(null);
  const [bulkProductCodes, setBulkProductCodes] = useState<string[]>([]);
  const [trialWarnings, setTrialWarnings] = useState<string[]>([]);
  const [dispatchWarnings, setDispatchWarnings] = useState<string[]>([]);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [newMetricOpen, setNewMetricOpen] = useState(false);
  const [draft, setDraft] = useState<DraftState>({
    component_name: "",
    rule_code: "formula",
    source_type: "manual",
    data_acct_code: "",
    formula: "",
    value_type: "金额",
  });
  const [newMetricDraft, setNewMetricDraft] = useState<NewMetricDraftState>({
    parent_metric_node_code: "",
    metric_node_name: "",
    formula: "",
    value_type: "金额",
  });

  const loadOverview = async (productCode?: string) => {
    setLoading(true);
    setError(null);
    try {
      const suffix = productCode ? `?product_code=${encodeURIComponent(productCode)}` : "";
      const data = await apiGet<WorkbenchOverview>(`/api/product-budget-workbench/overview${suffix}`);
      setOverview(data);
      const resolvedProduct = data.selected_product_code ?? data.products[0]?.product_code ?? "";
      setSelectedProductCode(resolvedProduct);
      const firstRow = data.rows.find((row) => row.components.length > 0) ?? data.rows[0];
      setSelectedReportCode((prev) => (prev && data.rows.some((row) => row.report_acct_code === prev) ? prev : firstRow?.report_acct_code ?? ""));
      const allComponents = data.rows.flatMap((row) => row.components);
      setSelectedComponentId((prev) =>
        prev && allComponents.some((component) => component.component_id === prev)
          ? prev
          : allComponents[0]?.component_id ?? ""
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载产品预算配置台失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  const selectedProduct = useMemo(
    () => overview?.products.find((product) => product.product_code === selectedProductCode) ?? overview?.products[0] ?? null,
    [overview, selectedProductCode]
  );

  const filteredProducts = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!overview) return [];
    if (!q) return overview.products;
    return overview.products.filter(
      (product) =>
        product.product_code.toLowerCase().includes(q) ||
        product.product_name.toLowerCase().includes(q)
    );
  }, [overview, query]);

  const selectedRow = useMemo(
    () => overview?.rows.find((row) => row.report_acct_code === selectedReportCode) ?? overview?.rows[0] ?? null,
    [overview, selectedReportCode]
  );

  const selectedComponent = useMemo(() => {
    const allComponents = overview?.rows.flatMap((row) => row.components) ?? [];
    return allComponents.find((component) => component.component_id === selectedComponentId) ?? allComponents[0] ?? null;
  }, [overview, selectedComponentId]);

  const newMetricParent = useMemo(() => {
    if (!overview || !selectedRow) return null;
    const parentCode = newMetricDraft.parent_metric_node_code || selectedRow.metric_node_code || selectedRow.report_acct_code;
    if (!parentCode) return null;
    const parentRow = overview.rows.find((row) => row.report_acct_code === parentCode || row.metric_node_code === parentCode);
    return {
      code: parentCode,
      name: parentRow?.report_acct_name || selectedRow.report_acct_name || "当前指标",
    };
  }, [newMetricDraft.parent_metric_node_code, overview, selectedRow]);

  const metricParentOptions = useMemo(() => {
    if (!overview) return [];
    return overview.rows
      .filter((row) => row.metric_node_code && row.row_type !== "compat")
      .map((row) => ({
        code: row.metric_node_code || row.report_acct_code,
        name: row.report_acct_name,
        level: row.level,
        rowType: row.row_type || "metric",
      }));
  }, [overview]);

  useEffect(() => {
    if (!selectedComponent) return;
    setDraft({
      component_name: selectedComponent.component_name,
      rule_code: selectedComponent.rule_code || "formula",
      source_type: selectedComponent.source_type || "manual",
      data_acct_code: selectedComponent.data_acct_code || "",
      formula: selectedComponent.formula || "",
      value_type: selectedComponent.value_type || "金额",
    });
  }, [selectedComponent]);

  const saveDraft = async (showNotice = true) => {
    if (!selectedComponent) return;
    setBusy("save");
    setError(null);
    try {
      await apiPut(`/api/product-budget-workbench/components/${encodeURIComponent(selectedComponent.component_id)}`, {
        component_name: draft.component_name,
        rule_code: draft.rule_code,
        source_type: draft.source_type,
        data_acct_code: draft.data_acct_code || null,
        formula: draft.formula,
        value_type: draft.value_type,
      });
      if (showNotice) setNotice("草稿已保存");
      await loadOverview(selectedProductCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存草稿失败");
    } finally {
      setBusy(null);
    }
  };

  const openNewMetricDialog = () => {
    if (!selectedRow) return;
    const defaultParentCode = selectedRow.metric_node_code || selectedRow.report_acct_code;
    setNewMetricDraft({
      parent_metric_node_code: defaultParentCode,
      metric_node_name: "",
      formula: "",
      value_type: selectedComponent?.value_type || "金额",
    });
    setNewMetricOpen(true);
  };

  const createMetricDataAccount = async () => {
    if (!selectedProduct || !newMetricParent) return;
    const metricName = newMetricDraft.metric_node_name.trim();
    if (!metricName) {
      setError("请填写新增数据科目名称");
      return;
    }
    setBusy("create-metric-data-account");
    setError(null);
    try {
      const result = await apiPost<CreateMetricDataAccountResult>("/api/product-budget-workbench/metric-data-accounts", {
        product_code: selectedProduct.product_code,
        parent_metric_node_code: newMetricParent.code,
        metric_node_name: metricName,
        component_name: metricName,
        formula: newMetricDraft.formula,
        value_type: newMetricDraft.value_type,
        rule_code: "formula",
        source_type: "manual_metric_create",
      });
      setSelectedReportCode(result.metric_node_code);
      setSelectedComponentId(result.component_id);
      setNewMetricOpen(false);
      setNotice("已新增数据科目，并自动完成指标树绑定");
      await loadOverview(selectedProduct.product_code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "新增数据科目失败");
    } finally {
      setBusy(null);
    }
  };

  const createDataAccount = async () => {
    if (!selectedComponent) return;
    await saveDraft(false);
    setBusy("create-data-account");
    try {
      const result = await apiPost<{ data_acct_code: string; created: boolean }>(
        `/api/product-budget-workbench/components/${encodeURIComponent(selectedComponent.component_id)}/create-data-account`,
        { data_acct_name: draft.component_name }
      );
      setNotice(result.created ? `已生成并绑定数据科目 ${result.data_acct_code}` : `已绑定数据科目 ${result.data_acct_code}`);
      await loadOverview(selectedProductCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成数据科目失败");
    } finally {
      setBusy(null);
    }
  };

  const saveTemplate = async () => {
    if (!selectedComponent) return;
    await saveDraft(false);
    setBusy("save-template");
    try {
      await apiPost(`/api/product-budget-workbench/components/${encodeURIComponent(selectedComponent.component_id)}/save-template`, {
        template_name: `${draft.component_name}模板`,
      });
      setNotice("组件模板已保存");
      await loadOverview(selectedProductCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存模板失败");
    } finally {
      setBusy(null);
    }
  };

  const applyTemplate = async (templateId: string) => {
    if (!selectedProduct || !selectedRow || !templateId) return;
    if (selectedRow.row_type === "group") return;
    setBusy("apply-template");
    try {
      const result = await apiPost<{ component_id: string }>(
        `/api/product-budget-workbench/templates/${encodeURIComponent(templateId)}/apply`,
        {
          product_code: selectedProduct.product_code,
          report_acct_code: selectedRow.compat_report_acct_code || selectedRow.report_acct_code,
          metric_node_code: selectedRow.metric_node_code || selectedRow.report_acct_code,
        }
      );
      setSelectedComponentId(result.component_id);
      setNotice("已复制应用组件模板");
      await loadOverview(selectedProduct.product_code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用模板失败");
    } finally {
      setBusy(null);
    }
  };

  const requestAiSuggestions = async () => {
    if (!selectedProduct || !selectedRow || !selectedComponent) return;
    setBusy("ai");
    setActiveStep("rule");
    setAiSuggestions([]);
    setAiConfigResult(null);
    try {
      const result = await apiPost<{ model: string; suggestions: AiSuggestion[] }>("/api/product-budget-workbench/ai-suggestions", {
        product_code: selectedProduct.product_code,
        report_acct_code: selectedRow.report_acct_code,
        component_id: selectedComponent.component_id,
      });
      setAiSuggestions(result.suggestions || []);
      setNotice(`AI 建议已生成：${result.model}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成 AI 建议失败");
    } finally {
      setBusy(null);
    }
  };

  const oneClickAiConfig = async () => {
    if (!selectedProduct) return;
    setBusy("one-click-ai");
    setActiveStep("rule");
    setAiSuggestions([]);
    setAiConfigResult(null);
    try {
      const result = await apiPost<AiConfigProductResult>("/api/product-budget-workbench/ai-configure-product", {
        product_code: selectedProduct.product_code,
      });
      const normalized = normalizeAiConfigResult(result, selectedProduct.product_name);
      setAiConfigResult(normalized);
      setAiSuggestions(normalized.configuredDrafts);
      setTrialWarnings(normalized.warnings);
      const skippedText = result.skipped_count ? `，${result.skipped_count} 项需人工补齐` : "";
      setNotice(`已完成产品级 AI 配置：采纳 ${result.applied_count} 项${skippedText}`);
      await loadOverview(selectedProductCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "产品级一键 AI 配置失败");
    } finally {
      setBusy(null);
    }
  };

  const bulkAiConfig = async () => {
    const scope = bulkProductCodes.length ? bulkProductCodes : selectedProduct ? [selectedProduct.product_code] : [];
    if (!scope.length) return;
    setBusy("bulk-ai");
    setActiveStep("rule");
    setAiSuggestions([]);
    setAiConfigResult(null);
    try {
      const result = await apiPost<{ product_codes: string[]; results: AiConfigProductResult[] }>(
        "/api/product-budget-workbench/ai-configure-products",
        { product_codes: scope }
      );
      const normalizedResults = (result.results || []).map((item) => normalizeAiConfigResult(item, item.product_code));
      const merged: AiConfigWorkbenchResult = {
        model: normalizedResults[0]?.model || "none",
        scopeLabel: `已选 ${result.product_codes.length} 个产品`,
        productCodes: result.product_codes,
        configuredDrafts: normalizedResults.flatMap((item) => item.configuredDrafts),
        pendingDataAccounts: normalizedResults.flatMap((item) => item.pendingDataAccounts),
        pendingMetricNodes: normalizedResults.flatMap((item) => item.pendingMetricNodes),
        warnings: normalizedResults.flatMap((item) => item.warnings),
      };
      setAiConfigResult(merged);
      setAiSuggestions(merged.configuredDrafts);
      setTrialWarnings(merged.warnings);
      setNotice(`跨产品 AI 配置完成：${merged.configuredDrafts.length} 项写入草稿，${merged.pendingDataAccounts.length + merged.pendingMetricNodes.length} 项待确认`);
      await loadOverview(selectedProductCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "跨产品一键 AI 配置失败");
    } finally {
      setBusy(null);
    }
  };

  const confirmPendingDataAccount = async (item: AiPendingDataAccount) => {
    setBusy(`confirm-data-${item.component_id}`);
    try {
      const result = await apiPost<{ data_acct_code: string; created: boolean }>(
        `/api/product-budget-workbench/components/${encodeURIComponent(item.component_id)}/create-data-account`,
        { data_acct_name: item.suggested_data_acct_name || item.metric_node_name || "产品预算数据科目" }
      );
      setAiConfigResult((prev) =>
        prev
          ? {
              ...prev,
              pendingDataAccounts: prev.pendingDataAccounts.filter((pending) => pending.component_id !== item.component_id),
            }
          : prev
      );
      setNotice(result.created ? `已确认创建数据科目 ${result.data_acct_code}` : `已绑定现有数据科目 ${result.data_acct_code}`);
      await loadOverview(item.product_code || selectedProductCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认创建数据科目失败");
    } finally {
      setBusy(null);
    }
  };

  const confirmPendingMetricNode = async (item: AiPendingMetricNode) => {
    setBusy(`confirm-metric-${item.component_id}`);
    try {
      const result = await apiPost<{ metric_node_code: string; metric_node_name: string; created: boolean }>(
        `/api/product-budget-workbench/components/${encodeURIComponent(item.component_id)}/confirm-metric-node`,
        { suggested_name: item.suggested_name || item.component_name || "产品预算指标" }
      );
      setAiConfigResult((prev) =>
        prev
          ? {
              ...prev,
              pendingMetricNodes: prev.pendingMetricNodes.filter((pending) => pending.component_id !== item.component_id),
            }
          : prev
      );
      setNotice(result.created ? `已确认新增指标节点 ${result.metric_node_code}` : `已绑定现有指标节点 ${result.metric_node_code}`);
      await loadOverview(item.product_code || selectedProductCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认新增指标节点失败");
    } finally {
      setBusy(null);
    }
  };

  const adoptSuggestion = async (suggestion: AiSuggestion) => {
    if (!selectedComponent) return;
    setBusy("adopt-ai");
    try {
      await apiPost(`/api/product-budget-workbench/components/${encodeURIComponent(selectedComponent.component_id)}/adopt-ai-suggestion`, {
        suggestion,
      });
      setNotice("已采纳 AI 建议到草稿");
      await loadOverview(selectedProductCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "采纳 AI 建议失败");
    } finally {
      setBusy(null);
    }
  };

  const runTrial = async () => {
    if (!selectedProduct) return;
    setBusy("trial");
    try {
      const result = await apiPost<{ warnings: string[]; trial_annual: number }>("/api/product-budget-workbench/trial", {
        product_code: selectedProduct.product_code,
      });
      setTrialWarnings(result.warnings || []);
      setNotice(`试算完成，全年合计 ${formatAmount(result.trial_annual)}`);
      setActiveStep("trial");
      await loadOverview(selectedProduct.product_code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "试算失败");
    } finally {
      setBusy(null);
    }
  };

  const dispatch = async () => {
    if (!selectedProduct) return;
    setBusy("dispatch");
    try {
      const result = await apiPost<{ dispatched_count: number; warnings: string[] }>("/api/product-budget-workbench/dispatch", {
        product_code: selectedProduct.product_code,
      });
      setDispatchWarnings(result.warnings || []);
      setNotice(`已下发 ${result.dispatched_count} 个数据科目配置`);
      setActiveStep("trial");
      await loadOverview(selectedProduct.product_code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "下发失败");
    } finally {
      setBusy(null);
    }
  };

  const toggleBulkProduct = (productCode: string) => {
    setBulkProductCodes((prev) =>
      prev.includes(productCode)
        ? prev.filter((code) => code !== productCode)
        : [...prev, productCode]
    );
  };

  if (loading && !overview) {
    return (
      <div className="bb-page items-center justify-center text-xs text-[var(--bb-text-muted)]">
        <Loader2 className="mr-2 h-4 w-4 animate-spin text-blue-600" />
        加载产品预算配置台
      </div>
    );
  }

  if (!overview || !selectedProduct) {
    return (
      <div className="bb-page text-xs text-[var(--bb-text-muted)]">
        {error || "暂无可配置产品，请先维护产品科目。"}
      </div>
    );
  }

  return (
    <PanelGroup direction="horizontal" className="h-full bg-[var(--bb-bg-page)] text-xs text-[var(--bb-text)]">
      <Panel
        ref={leftPanelRef}
        defaultSize={18}
        minSize={8}
        maxSize={30}
        collapsible
        collapsedSize={4}
        onCollapse={() => setLeftCollapsed(true)}
        onExpand={() => setLeftCollapsed(false)}
        className="min-h-0 min-w-0"
      >
        <aside className="flex h-full min-h-0 min-w-0 flex-col border-r border-[var(--bb-border)] bg-[var(--bb-bg-subtle)]">
          {leftCollapsed ? (
            <button
              type="button"
              onClick={() => leftPanelRef.current?.expand()}
              title="展开产品栏"
              className="flex h-full w-full flex-col items-center justify-start gap-2 px-1 py-3 text-slate-500 transition hover:bg-white hover:text-blue-700"
            >
              <ChevronsRight className="h-4 w-4" />
              <span className="text-[11px] [writing-mode:vertical-rl]">产品</span>
            </button>
          ) : (
            <>
              <div className="border-b border-slate-200 px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold text-slate-900">我的负责产品</div>
                  <div className="flex items-center gap-1">
                    <span className="rounded bg-white px-2 py-1 text-[11px] text-slate-500">{overview.products.length} 个</span>
                    <button
                      type="button"
                      onClick={() => leftPanelRef.current?.collapse()}
                      title="收起产品栏"
                      className="bb-icon-btn border border-[var(--bb-border)] bg-[var(--bb-bg-surface)]"
                    >
                      <ChevronsLeft className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
                <div className="mt-2 flex h-8 items-center gap-2 rounded-[var(--bb-radius-sm)] border border-[var(--bb-border)] bg-[var(--bb-bg-surface)] px-2 text-[var(--bb-text-muted)]">
                  <Search className="h-3.5 w-3.5" />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索产品"
                    className="min-w-0 flex-1 bg-transparent text-xs text-slate-700 outline-none"
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                  <span>勾选后可跨产品批量配置</span>
                  {bulkProductCodes.length ? <span className="font-medium text-blue-700">已选 {bulkProductCodes.length}</span> : null}
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-auto p-2">
                {filteredProducts.map((product) => (
                  <div
                    key={product.product_code}
                    onClick={() => {
                      setSelectedProductCode(product.product_code);
                      setSelectedReportCode("");
                      setSelectedComponentId("");
                      void loadOverview(product.product_code);
                    }}
                    className={`mb-1 w-full cursor-pointer rounded border px-2.5 py-2 text-left transition ${
                      selectedProduct.product_code === product.product_code
                        ? "border-blue-300 bg-white shadow-sm"
                        : "border-transparent hover:border-slate-200 hover:bg-white"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-start gap-2">
                        <input
                          type="checkbox"
                          checked={bulkProductCodes.includes(product.product_code)}
                          onClick={(event) => event.stopPropagation()}
                          onChange={() => toggleBulkProduct(product.product_code)}
                          className="mt-0.5 h-3.5 w-3.5 rounded border-slate-300"
                          aria-label={`选择 ${product.product_name} 参与跨产品 AI 配置`}
                        />
                        <div className="min-w-0">
                          <div className="truncate font-medium text-slate-900">{product.product_name}</div>
                          <div className="mt-0.5 font-mono text-[11px] text-slate-400">{product.product_code}</div>
                        </div>
                      </div>
                      <StatusPill status={product.status} />
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500">数据科目 {product.component_count} 个</div>
                  </div>
                ))}
              </div>
            </>
          )}
      </aside>
      </Panel>

      <PanelResizeHandle className="group relative w-1 bg-[var(--bb-border-soft)] transition hover:bg-[var(--bb-primary)] data-[resize-handle-active]:bg-[var(--bb-primary)]">
        <div className="absolute left-1/2 top-1/2 h-10 w-1 -translate-x-1/2 -translate-y-1/2 rounded bg-slate-300 opacity-0 transition group-hover:opacity-100" />
      </PanelResizeHandle>

      <Panel defaultSize={51} minSize={36} className="min-h-0 min-w-0">
      <main className="flex h-full min-w-0 flex-col">
        <div className="border-b border-[var(--bb-border)] bg-[var(--bb-bg-surface)] px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-slate-950">{selectedProduct.product_name} 产品预算配置台</h2>
                <StatusPill status={selectedProduct.status} />
              </div>
              <div className="mt-1 text-slate-500">
                产品范围 {selectedProduct.product_code} | 指标 {overview.summary.report_row_count || 0} 个 | 数据科目 {overview.summary.component_count || 0} 个
              </div>
            </div>
            <div className="flex items-center gap-2">
              <IconButton onClick={oneClickAiConfig} tone="primary" disabled={!selectedProduct || busy === "one-click-ai"}>
                {busy === "one-click-ai" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                产品一键AI配置
              </IconButton>
              <IconButton onClick={bulkAiConfig} tone="soft" disabled={bulkProductCodes.length === 0 || busy === "bulk-ai"}>
                {busy === "bulk-ai" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                跨产品AI配置
              </IconButton>
              <IconButton onClick={runTrial} disabled={busy === "trial"}>
                {busy === "trial" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Table2 className="h-3.5 w-3.5" />}
                试算
              </IconButton>
              <IconButton onClick={dispatch} tone="primary" disabled={busy === "dispatch"}>
                {busy === "dispatch" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                下发
              </IconButton>
            </div>
          </div>
          {(notice || error) && (
            <div className={`bb-status-banner mt-2 ${error ? "bb-status-banner-danger" : "bg-[var(--bb-primary-soft)] text-[var(--bb-primary)]"}`}>
              {error || notice}
            </div>
          )}
        </div>

        {aiConfigResult && (
          <section className="border-b border-slate-200 bg-white px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-blue-700" />
                <div>
                  <div className="font-semibold text-slate-950">AI一键配置结果</div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    {aiConfigResult.scopeLabel} | 模型 {aiConfigResult.model || "none"} | 产品 {aiConfigResult.productCodes.join(", ")}
                  </div>
                </div>
              </div>
              <div className="grid min-w-[360px] grid-cols-3 overflow-hidden rounded border border-slate-200 text-center">
                <div className="border-r border-slate-200 px-3 py-2">
                  <div className="text-[11px] text-slate-500">已写入草稿</div>
                  <div className="text-base font-semibold text-emerald-700">{aiConfigResult.configuredDrafts.length}</div>
                </div>
                <div className="border-r border-slate-200 px-3 py-2">
                  <div className="text-[11px] text-slate-500">待建数据科目</div>
                  <div className="text-base font-semibold text-amber-700">{aiConfigResult.pendingDataAccounts.length}</div>
                </div>
                <div className="px-3 py-2">
                  <div className="text-[11px] text-slate-500">待增指标节点</div>
                  <div className="text-base font-semibold text-blue-700">{aiConfigResult.pendingMetricNodes.length}</div>
                </div>
              </div>
            </div>

            {(aiConfigResult.pendingDataAccounts.length > 0 || aiConfigResult.pendingMetricNodes.length > 0 || aiConfigResult.warnings.length > 0) && (
              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                <div className="rounded border border-amber-200 bg-amber-50">
                  <div className="border-b border-amber-200 px-3 py-2 font-semibold text-amber-900">待确认创建数据科目</div>
                  <div className="max-h-44 overflow-auto p-2">
                    {aiConfigResult.pendingDataAccounts.length === 0 ? (
                      <div className="px-2 py-3 text-center text-amber-700">无待确认项</div>
                    ) : (
                      aiConfigResult.pendingDataAccounts.map((item) => (
                        <div key={item.component_id} className="mb-2 rounded border border-amber-200 bg-white p-2 last:mb-0">
                          <div className="font-medium text-slate-900">{item.suggested_data_acct_name || item.metric_node_name || item.component_id}</div>
                          <div className="mt-0.5 font-mono text-[11px] text-slate-500">{item.product_code} / {item.metric_node_code}</div>
                          <div className="mt-1 text-[11px] text-slate-500">{item.reason}</div>
                          <button
                            type="button"
                            onClick={() => confirmPendingDataAccount(item)}
                            disabled={busy === `confirm-data-${item.component_id}`}
                            className="bb-btn bb-btn-primary mt-2 h-7 px-2 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {busy === `confirm-data-${item.component_id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
                            确认创建数据科目
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded border border-blue-200 bg-blue-50">
                  <div className="border-b border-blue-200 px-3 py-2 font-semibold text-blue-900">待确认新增指标节点</div>
                  <div className="max-h-44 overflow-auto p-2">
                    {aiConfigResult.pendingMetricNodes.length === 0 ? (
                      <div className="px-2 py-3 text-center text-blue-700">无待确认项</div>
                    ) : (
                      aiConfigResult.pendingMetricNodes.map((item) => (
                        <div key={item.component_id} className="mb-2 rounded border border-blue-200 bg-white p-2 last:mb-0">
                          <div className="font-medium text-slate-900">{item.suggested_name || item.component_name || item.component_id}</div>
                          <div className="mt-0.5 font-mono text-[11px] text-slate-500">{item.product_code} / {item.compat_report_acct_code || "未绑定指标节点"}</div>
                          <div className="mt-1 text-[11px] text-slate-500">{item.reason}</div>
                          <button
                            type="button"
                            onClick={() => confirmPendingMetricNode(item)}
                            disabled={busy === `confirm-metric-${item.component_id}`}
                            className="bb-btn bb-btn-primary mt-2 h-7 px-2 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {busy === `confirm-metric-${item.component_id}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
                            确认新增指标节点
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded border border-slate-200 bg-slate-50">
                  <div className="border-b border-slate-200 px-3 py-2 font-semibold text-slate-900">AI跳过原因</div>
                  <div className="max-h-44 overflow-auto p-2">
                    {aiConfigResult.warnings.length === 0 ? (
                      <div className="px-2 py-3 text-center text-slate-500">无跳过项</div>
                    ) : (
                      aiConfigResult.warnings.map((warning, index) => (
                        <div key={`${warning}-${index}`} className="mb-2 flex items-start gap-2 rounded border border-slate-200 bg-white px-2 py-1.5 last:mb-0">
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-600" />
                          <span className="text-slate-600">{warning}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
          <div className="flex items-center gap-2 text-slate-600">
            <FileSpreadsheet className="h-4 w-4 text-blue-600" />
            产品试算表
            <span className="text-slate-400">按指标层级展开数据科目</span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value=""
              onChange={(event) => {
                void applyTemplate(event.target.value);
                event.target.value = "";
              }}
              className="bb-select h-8"
            >
              <option value="">套用公式模板</option>
              {overview.templates.map((template) => (
                <option key={template.template_id} value={template.template_id}>
                  {template.template_name}
                </option>
              ))}
            </select>
            <IconButton onClick={openNewMetricDialog} tone="primary" disabled={!selectedRow}>
              <Plus className="h-3.5 w-3.5" />
              新增数据科目
            </IconButton>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          <table className="bb-table bb-table-dense min-w-[920px] w-full">
            <thead className="sticky top-0 z-10 bg-slate-100 text-slate-600">
              <tr>
                <th className="border-b border-slate-200 px-2 py-2 text-left font-medium">数据科目指标 / 数据科目</th>
                <th className="border-b border-slate-200 px-2 py-2 text-left font-medium">状态</th>
                <th className="border-b border-slate-200 px-2 py-2 text-left font-medium">规则/底层数据科目</th>
                <th className="border-b border-slate-200 px-2 py-2 text-right font-medium">1月</th>
                <th className="border-b border-slate-200 px-2 py-2 text-right font-medium">2月</th>
                <th className="border-b border-slate-200 px-2 py-2 text-right font-medium">3月</th>
                <th className="border-b border-slate-200 px-2 py-2 text-right font-medium">全年</th>
                <th className="border-b border-slate-200 px-2 py-2 text-center font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {overview.rows.map((row) => {
                const isGroupRow = row.row_type === "group";
                const isMetricRow = row.row_type === "metric" || row.row_type === "compat";
                return (
                <Fragment key={row.report_acct_code}>
                  {isGroupRow ? (
                    <tr
                    onClick={() => setSelectedReportCode(row.report_acct_code)}
                    className="cursor-pointer bg-slate-50 hover:bg-slate-100"
                  >
                    <td className="border-b border-slate-100 px-2 py-2">
                      <div className="flex items-center gap-2" style={{ paddingLeft: `${Math.max(0, row.level - 1) * 14}px` }}>
                        <span className="font-mono text-[11px] text-slate-500">{row.metric_node_code || row.report_acct_code}</span>
                        <span className="font-semibold text-slate-800">{row.report_acct_name}</span>
                      </div>
                    </td>
                    <td className="border-b border-slate-100 px-2 py-2"><StatusPill status={row.status} /></td>
                    <td className="border-b border-slate-100 px-2 py-2 text-slate-500">
                      {row.component_count || 0} 个下级数据科目
                    </td>
                    <td className="border-b border-slate-100 px-2 py-2 text-right">{formatAmount(row.trial_m01)}</td>
                    <td className="border-b border-slate-100 px-2 py-2 text-right">{formatAmount(row.trial_m02)}</td>
                    <td className="border-b border-slate-100 px-2 py-2 text-right">{formatAmount(row.trial_m03)}</td>
                    <td className="border-b border-slate-100 px-2 py-2 text-right font-semibold text-slate-950">{formatAmount(row.trial_annual)}</td>
                    <td className="border-b border-slate-100 px-2 py-2 text-center">
                    </td>
                  </tr>
                  ) : null}
                  {isMetricRow && row.components.map((component) => (
                    <tr
                      key={component.component_id}
                      onClick={() => {
                        setSelectedReportCode(row.report_acct_code);
                        setSelectedComponentId(component.component_id);
                        setActiveStep("rule");
                      }}
                      className={`cursor-pointer ${selectedComponentId === component.component_id ? "bg-sky-50" : "bg-white hover:bg-slate-50"}`}
                    >
                      <td className="border-b border-slate-100 px-2 py-2">
                        <div style={{ paddingLeft: `${Math.max(0, row.level) * 14}px` }}>
                          <div className="flex items-center gap-2">
                            <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                            <span>{component.component_name}</span>
                          </div>
                          {component.metric_node_code ? (
                            <div className="mt-0.5 pl-3.5 font-mono text-[11px] text-slate-400">
                              {component.metric_node_code} {component.metric_node_name || ""}
                            </div>
                          ) : null}
                        </div>
                      </td>
                      <td className="border-b border-slate-100 px-2 py-2"><StatusPill status={component.status} /></td>
                      <td className="border-b border-slate-100 px-2 py-2">
                        <div className="text-slate-700">{component.rule_label}</div>
                        <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                          {component.data_acct_code ? `${component.data_acct_code} ${component.data_acct_name || ""}` : "待生成数据科目"}
                        </div>
                      </td>
                      <td className="border-b border-slate-100 px-2 py-2 text-right">{formatAmount(component.trial_m01)}</td>
                      <td className="border-b border-slate-100 px-2 py-2 text-right">{formatAmount(component.trial_m02)}</td>
                      <td className="border-b border-slate-100 px-2 py-2 text-right">{formatAmount(component.trial_m03)}</td>
                      <td className="border-b border-slate-100 px-2 py-2 text-right">{formatAmount(component.trial_annual)}</td>
                      <td className="border-b border-slate-100 px-2 py-2 text-center text-blue-700">配置</td>
                    </tr>
                  ))}
                </Fragment>
              )})}
            </tbody>
          </table>
        </div>
      </main>
      </Panel>

      <PanelResizeHandle className="group relative w-1 bg-[var(--bb-border-soft)] transition hover:bg-[var(--bb-primary)] data-[resize-handle-active]:bg-[var(--bb-primary)]">
        <div className="absolute left-1/2 top-1/2 h-10 w-1 -translate-x-1/2 -translate-y-1/2 rounded bg-slate-300 opacity-0 transition group-hover:opacity-100" />
      </PanelResizeHandle>

      <Panel
        ref={rightPanelRef}
        defaultSize={31}
        minSize={16}
        maxSize={46}
        collapsible
        collapsedSize={5}
        onCollapse={() => setRightCollapsed(true)}
        onExpand={() => setRightCollapsed(false)}
        className="min-h-0 min-w-0"
      >
      <aside className="flex h-full min-h-0 min-w-0 flex-col border-l border-[var(--bb-border)] bg-[var(--bb-bg-surface)]">
        {rightCollapsed ? (
          <button
            type="button"
            onClick={() => rightPanelRef.current?.expand()}
            title="展开配置栏"
            className="flex h-full w-full flex-col items-center justify-start gap-2 px-1 py-3 text-slate-500 transition hover:bg-slate-50 hover:text-blue-700"
          >
            <ChevronsLeft className="h-4 w-4" />
            <span className="text-[11px] [writing-mode:vertical-rl]">配置</span>
          </button>
        ) : (
          <>
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="font-semibold text-slate-950">{activeStep === "rule" ? "数据科目公式" : "试算与下发"}</div>
              <div className="mt-1 text-slate-500">{selectedRow?.report_acct_name || "请选择数据科目指标"}</div>
            </div>
            <div className="flex items-center gap-2">
              {selectedComponent && <StatusPill status={selectedComponent.status} />}
              <button
                type="button"
                onClick={() => rightPanelRef.current?.collapse()}
                title="收起配置栏"
                className="bb-icon-btn border border-[var(--bb-border)] bg-[var(--bb-bg-surface)]"
              >
                <ChevronsRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <div className="bb-tabs mt-3 grid grid-cols-2">
            <button
              type="button"
              onClick={() => setActiveStep("rule")}
              className={`bb-tab ${activeStep === "rule" ? "bb-tab-active" : ""}`}
            >
              数据科目公式
            </button>
            <button
              type="button"
              onClick={() => setActiveStep("trial")}
              className={`bb-tab ${activeStep === "trial" ? "bb-tab-active" : ""}`}
            >
              试算与下发
            </button>
          </div>
          {activeStep === "rule" && (
            <button
              type="button"
              onClick={oneClickAiConfig}
              disabled={!selectedProduct || busy === "one-click-ai"}
              className="bb-btn bb-btn-primary mt-3 h-9 w-full disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy === "one-click-ai" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
              当前产品一键AI配置
            </button>
          )}
        </div>

        {activeStep === "rule" ? (
          <div className="min-h-0 flex-1 overflow-auto p-4">
            {!selectedComponent ? (
              <div className="rounded border border-dashed border-slate-300 p-4 text-center text-slate-500">
                请选择或新增一个数据科目
              </div>
            ) : (
              <div className="space-y-4">
                <section className="rounded border border-slate-200">
                  <div className="border-b border-slate-200 bg-blue-50 px-3 py-2 font-semibold text-blue-900">数据科目配置</div>
                  <div className="grid gap-3 p-3">
                    <Field label="数据科目名称">
                      <TextInput value={draft.component_name} onChange={(value) => setDraft((prev) => ({ ...prev, component_name: value }))} />
                    </Field>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="规则">
                        <SelectInput value={draft.rule_code} onChange={(value) => setDraft((prev) => ({ ...prev, rule_code: value }))}>
                          {(overview.rule_options || []).map((option) => (
                            <option key={option.code} value={option.code}>{option.label}</option>
                          ))}
                        </SelectInput>
                      </Field>
                      <Field label="数值类型">
                        <SelectInput value={draft.value_type} onChange={(value) => setDraft((prev) => ({ ...prev, value_type: value }))}>
                          <option value="金额">金额</option>
                          <option value="百分比">百分比</option>
                          <option value="户数">户数</option>
                        </SelectInput>
                      </Field>
                    </div>
                    <Field label="来源">
                      <SelectInput value={draft.source_type} onChange={(value) => setDraft((prev) => ({ ...prev, source_type: value }))}>
                        <option value="manual">人工配置</option>
                        <option value="existing_data_account">引用现有数据科目</option>
                        <option value="template_copy">模板复制</option>
                        <option value="driver">预算动因</option>
                        <option value="ai_suggestion">AI 建议</option>
                      </SelectInput>
                    </Field>
                    <Field label="底层数据科目">
                      <div className="flex gap-2">
                        <div className="flex h-8 min-w-0 flex-1 items-center rounded border border-slate-200 bg-slate-50 px-2 font-mono text-[11px] text-slate-600">
                          {draft.data_acct_code ? `${draft.data_acct_code} ${selectedComponent?.data_acct_name || ""}` : "未生成"}
                        </div>
                        <IconButton onClick={createDataAccount} disabled={busy === "create-data-account"} title="同步底层数据科目">
                          <Database className="h-3.5 w-3.5" />
                          {draft.data_acct_code ? "同步" : "生成"}
                        </IconButton>
                      </div>
                    </Field>
                  </div>
                </section>

                <section className="rounded border border-slate-200">
                  <div className="flex items-center justify-between border-b border-slate-200 bg-blue-50 px-3 py-2">
                    <div className="font-semibold text-blue-900">公式</div>
                    <IconButton onClick={() => setFormulaOpen(true)} tone="soft">
                      <FileSpreadsheet className="h-3.5 w-3.5" />
                      公式编辑器
                    </IconButton>
                  </div>
                  <div className="p-3">
                    <textarea
                      value={draft.formula}
                      onChange={(event) => setDraft((prev) => ({ ...prev, formula: event.target.value }))}
                      className="bb-textarea h-28 w-full resize-none font-mono"
                      placeholder="从指标库插入或直接输入公式"
                    />
                    <div className="mt-2 text-[11px] text-slate-500">公式保存后会写回唯一的数据科目维护表，并同步结构化规则配置。</div>
                  </div>
                </section>

                <section className="rounded border border-slate-200">
                  <div className="flex items-center justify-between border-b border-slate-200 bg-blue-50 px-3 py-2">
                    <div className="flex items-center gap-1.5 font-semibold text-blue-900">
                      <Bot className="h-3.5 w-3.5" />
                      AI 配置建议明细
                    </div>
                    <IconButton onClick={requestAiSuggestions} disabled={busy === "ai"} tone="soft">
                      {busy === "ai" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                      只生成建议
                    </IconButton>
                  </div>
                  <div className="space-y-2 p-3">
                    {aiSuggestions.length === 0 ? (
                      <div className="rounded border border-dashed border-slate-300 p-3 text-center text-slate-500">
                        上方“当前产品一键AI配置”会生成分组结果；这里保留明细，便于人工逐条查看和采纳
                      </div>
                    ) : (
                      aiSuggestions.map((suggestion, index) => (
                        <div key={`${suggestion.title || "suggestion"}-${index}`} className="rounded border border-slate-200 bg-white p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="font-medium text-slate-900">{suggestion.title || "配置建议"}</div>
                              <div className="mt-1 text-[11px] text-slate-500">{suggestion.reason || "可采纳为当前数据科目公式草稿"}</div>
                            </div>
                            <IconButton onClick={() => adoptSuggestion(suggestion)} tone="primary" disabled={busy === "adopt-ai"}>
                              <Wand2 className="h-3.5 w-3.5" />
                              采纳
                            </IconButton>
                          </div>
                          <div className="mt-2 rounded bg-slate-50 p-2 font-mono text-[11px] text-slate-600">{suggestion.formula || "无公式"}</div>
                        </div>
                      ))
                    )}
                  </div>
                </section>
              </div>
            )}
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded border border-slate-200 p-3">
                <div className="text-[11px] text-slate-500">全年试算</div>
                <div className="mt-1 text-lg font-semibold text-slate-950">{formatAmount(overview.summary.trial_annual)}</div>
              </div>
              <div className="rounded border border-slate-200 p-3">
                <div className="text-[11px] text-slate-500">待补齐数据科目</div>
                <div className="mt-1 text-lg font-semibold text-amber-700">{overview.summary.warning_count || 0}</div>
              </div>
            </div>
            <div className="mt-4 rounded border border-slate-200">
              <div className="border-b border-slate-200 bg-blue-50 px-3 py-2 font-semibold text-blue-900">下发检查</div>
              <div className="space-y-2 p-3">
                {[...trialWarnings, ...dispatchWarnings].length === 0 ? (
                  <div className="flex items-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-700">
                    <CheckCircle2 className="h-4 w-4" />
                    当前没有阻塞提示
                  </div>
                ) : (
                  [...trialWarnings, ...dispatchWarnings].map((warning, index) => (
                    <div key={`${warning}-${index}`} className="flex items-start gap-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                      <span>{warning}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-3">
          <IconButton onClick={saveTemplate} disabled={!selectedComponent || busy === "save-template"}>
            <Copy className="h-3.5 w-3.5" />
            存为模板
          </IconButton>
          <div className="flex items-center gap-2">
            <IconButton onClick={() => void saveDraft()} disabled={!selectedComponent || busy === "save"}>
              {busy === "save" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              保存草稿
            </IconButton>
            <IconButton onClick={runTrial} tone="primary">
              <Link2 className="h-3.5 w-3.5" />
              试算
            </IconButton>
          </div>
        </div>
          </>
        )}
      </aside>
      </Panel>

      {newMetricOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/25 px-4">
          <div className="w-full max-w-lg rounded border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div>
                <div className="font-semibold text-slate-950">新增数据科目</div>
                <div className="mt-0.5 font-mono text-[11px] text-slate-500">
                  挂到所选指标层级下，并自动生成数据科目编码
                </div>
              </div>
              <button
                type="button"
                onClick={() => setNewMetricOpen(false)}
                className="bb-icon-btn"
                title="关闭"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="grid gap-3 p-4">
              <Field label="上级指标">
                <SelectInput
                  value={newMetricDraft.parent_metric_node_code}
                  onChange={(value) => setNewMetricDraft((prev) => ({ ...prev, parent_metric_node_code: value }))}
                >
                  {metricParentOptions.map((option) => (
                    <option key={option.code} value={option.code}>
                      {`${"　".repeat(Math.max(0, option.level - 1))}${option.code} ${option.name}`}
                    </option>
                  ))}
                </SelectInput>
              </Field>
              <Field label="数据科目名称">
                <TextInput
                  value={newMetricDraft.metric_node_name}
                  onChange={(value) => setNewMetricDraft((prev) => ({ ...prev, metric_node_name: value }))}
                  placeholder="例如 新增预算数据科目"
                />
              </Field>
              <Field label="数值类型">
                <SelectInput
                  value={newMetricDraft.value_type}
                  onChange={(value) => setNewMetricDraft((prev) => ({ ...prev, value_type: value }))}
                >
                  <option value="金额">金额</option>
                  <option value="百分比">百分比</option>
                  <option value="户数">户数</option>
                </SelectInput>
              </Field>
              <Field label="预算加工公式">
                <textarea
                  value={newMetricDraft.formula}
                  onChange={(event) => setNewMetricDraft((prev) => ({ ...prev, formula: event.target.value }))}
                  className="bb-textarea h-24 w-full resize-none font-mono"
                  placeholder="A1001 + A1002"
                />
              </Field>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-4 py-3">
              <IconButton onClick={() => setNewMetricOpen(false)}>
                取消
              </IconButton>
              <IconButton onClick={createMetricDataAccount} tone="primary" disabled={busy === "create-metric-data-account"}>
                {busy === "create-metric-data-account" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                确认新增
              </IconButton>
            </div>
          </div>
        </div>
      ) : null}

      <FormulaEditorDialog
        isOpen={formulaOpen}
        onClose={() => setFormulaOpen(false)}
        onConfirm={(formula) => {
          setDraft((prev) => ({ ...prev, formula }));
          setFormulaOpen(false);
        }}
        initialFormula={draft.formula}
        title="数据科目加工公式"
        currentDataSubject={`${draft.data_acct_code || "待生成数据科目"} ${draft.component_name || ""}`.trim()}
        currentProductCode={selectedProductCode}
        formulaType="budget"
      />
    </PanelGroup>
  );
}
