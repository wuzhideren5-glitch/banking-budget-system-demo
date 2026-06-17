import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ChartNoAxesColumn,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Loader2,
  RefreshCw,
  Save,
  Search,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import {
  createSmartReportTextTemplate,
  downloadSmartReportGeneratedFile,
  downloadSmartReportInstance,
  generateSmartReport,
  generateSmartReportBlueprint,
  inspectSmartReportWithAI,
  listSmartReportCalcMetrics,
  listSmartReportInstances,
  listSmartReportTemplateVariables,
  listSmartReportTemplates,
  previewSmartReport,
  previewSmartReportBlueprint,
  refreshSmartReportInstance,
  saveSmartReportBlueprint,
  uploadSmartReportTemplate,
  upsertSmartReportCalcMetric,
  type SmartReportBlueprintDetailDto,
  type SmartReportBlueprintGenerateResponseDto,
  type SmartReportBlueprintSaveRequestDto,
  type SmartReportAIInspectionResponseDto,
  type SmartReportCalcMetricComponentDto,
  type SmartReportCalcMetricDto,
  type SmartReportCalcMetricUpsertDto,
  type SmartReportGenerateResponseDto,
  type SmartReportInstanceDto,
  type SmartReportTemplateDto,
  type SmartReportTextTemplateCreateDto,
  type SmartReportTemplateVariableDto,
} from "@/lib/system/smartReportApi";
import { getOrgProductMetricSnapshot } from "@/lib/org-product/orgProductMetricApi";
import { deriveRuntimeRefFromOrgProductMetricCode } from "@/lib/org-product/orgProductMetricCode";

type MetricTreeNode = {
  node_code: string;
  node_name: string;
  children: MetricTreeNode[];
};

type OrgProductMetricNodeDto = {
  code?: string;
  name?: string;
  formula?: string;
  formula_actual?: string;
  formula_forecast?: string;
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

type MetricFormulaCandidate = {
  metric_code: string;
  metric_name: string | null;
  metric_node_code: string;
  metric_node_name: string | null;
  scope_type: string;
  scope_code: string;
  product_name: string | null;
  data_acct_code: string;
  data_acct_name: string | null;
  sort_order: number;
  is_active: number;
  remark: string | null;
  candidate_key: string;
  source_type: "org_product_metric";
  source_label: string;
  source_ref?: string;
  display_name?: string;
  formula_text?: string;
};

function bindingMetricCode(binding: MetricFormulaCandidate): string {
  return binding.metric_code || binding.data_acct_code;
}

function bindingMetricName(binding: MetricFormulaCandidate): string {
  return binding.metric_name || binding.display_name || binding.data_acct_name || binding.metric_node_name || binding.data_acct_code;
}

function calcComponentMetricCode(component: SmartReportCalcMetricComponentDto): string {
  return component.metric_code || component.data_acct_code;
}

function calcComponentMetricName(component: SmartReportCalcMetricComponentDto): string {
  return component.metric_name || component.data_acct_name || "-";
}

function fmtTime(value?: string | null): string {
  if (!value) return "-";
  return value.replace("T", " ").replace("Z", "");
}

function paramKeyOf(variable: SmartReportTemplateVariableDto): string {
  const raw = variable.binding_config?.param_key;
  if (typeof raw === "string" && raw.trim()) return raw.trim();
  return variable.variable_key.includes(":") ? variable.variable_key.split(":").slice(1).join(":") : variable.variable_key;
}

function textKeyOf(variable: SmartReportTemplateVariableDto): string {
  const raw = variable.binding_config?.text_key;
  if (typeof raw === "string" && raw.trim()) return raw.trim();
  return variable.variable_key.includes(":") ? variable.variable_key.split(":").slice(1).join(":") : variable.variable_key;
}

function isChartVariable(variable: SmartReportTemplateVariableDto): boolean {
  return variable.variable_key.trim().toLowerCase().startsWith("chart:");
}

function chartCodeOf(variable: SmartReportTemplateVariableDto): string {
  return variable.variable_key.includes(":") ? variable.variable_key.split(":").slice(1).join(":").trim() : variable.variable_key;
}

export function AnalysisReportContent() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [templates, setTemplates] = useState<SmartReportTemplateDto[]>([]);
  const [instances, setInstances] = useState<SmartReportInstanceDto[]>([]);
  const [variables, setVariables] = useState<SmartReportTemplateVariableDto[]>([]);
  const [calcMetrics, setCalcMetrics] = useState<SmartReportCalcMetricDto[]>([]);
  const [orgProductMetricSnapshot, setOrgProductMetricSnapshot] = useState<OrgProductMetricSnapshotDto | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState("");
  const [templateCode, setTemplateCode] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [templateInputMode, setTemplateInputMode] = useState<"upload" | "text">("upload");
  const [templateContent, setTemplateContent] = useState("");
  const [showMetricPicker, setShowMetricPicker] = useState(false);
  const [metricPickerMode, setMetricPickerMode] = useState<"template" | "calc">("template");
  const [showCalcMetricDialog, setShowCalcMetricDialog] = useState(false);
  const [savingCalcMetric, setSavingCalcMetric] = useState(false);
  const [calcMetricCode, setCalcMetricCode] = useState("");
  const [calcMetricName, setCalcMetricName] = useState("");
  const [calcMetricExpression, setCalcMetricExpression] = useState("");
  const [calcMetricFormatType, setCalcMetricFormatType] = useState<"number" | "percent">("number");
  const [calcMetricComponents, setCalcMetricComponents] = useState<SmartReportCalcMetricComponentDto[]>([]);
  const [metricSearchText, setMetricSearchText] = useState("");
  const [selectedMetricNode, setSelectedMetricNode] = useState<string | null>(null);
  const [collapsedMetricNodes, setCollapsedMetricNodes] = useState<Record<string, boolean>>({});
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [aiReportFile, setAiReportFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [inspectingReport, setInspectingReport] = useState(false);
  const [savingBlueprint, setSavingBlueprint] = useState(false);
  const [previewingBlueprint, setPreviewingBlueprint] = useState(false);
  const [generatingBlueprint, setGeneratingBlueprint] = useState(false);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [refreshingInstanceId, setRefreshingInstanceId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [paramValues, setParamValues] = useState<Record<string, string>>({
    year: "2026",
    start_month: "1",
    end_month: "12",
    version_id: "1",
    budget_actual: "0",
  });
  const [textValues, setTextValues] = useState<Record<string, string>>({});
  const [previewText, setPreviewText] = useState("");
  const [previewWarnings, setPreviewWarnings] = useState<string[]>([]);
  const [lastGenerated, setLastGenerated] = useState<SmartReportGenerateResponseDto | null>(null);
  const [aiInspection, setAiInspection] = useState<SmartReportAIInspectionResponseDto | null>(null);
  const [savedBlueprint, setSavedBlueprint] = useState<SmartReportBlueprintDetailDto | null>(null);
  const [blueprintPreviewText, setBlueprintPreviewText] = useState("");
  const [blueprintGenerated, setBlueprintGenerated] = useState<SmartReportBlueprintGenerateResponseDto | null>(null);

  const selectedTemplate = templates.find((item) => item.template_id === selectedTemplateId) ?? null;

  const filteredTemplates = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return templates;
    return templates.filter(
      (item) =>
        item.template_code.toLowerCase().includes(q) ||
        item.template_name.toLowerCase().includes(q) ||
        (item.remark ?? "").toLowerCase().includes(q),
    );
  }, [searchText, templates]);

  const metricTreeRoots = useMemo(() => {
    const roots: MetricTreeNode[] = [];
    for (const entity of orgProductMetricSnapshot?.entities ?? []) {
      const entityCode = String(entity.entity_code || "").trim().toUpperCase();
      if (!entityCode) continue;
      const entityNode: MetricTreeNode = {
        node_code: entityCode,
        node_name: String(entity.entity_name || entityCode).trim(),
        children: [],
      };
      for (const table of entity.tables ?? []) {
        const tableName = String(table.table_name || "指标表").trim();
        const tableNode: MetricTreeNode = {
          node_code: `${entityCode}:${tableName}`,
          node_name: tableName,
          children: [],
        };
        const walk = (metrics: OrgProductMetricNodeDto[], parent: MetricTreeNode): boolean => {
          let hasConfirmedDescendant = false;
          for (const metric of metrics) {
            const metricCode = String(metric.code || "").trim().toUpperCase();
            const metricNodeCode = deriveRuntimeRefFromOrgProductMetricCode(entityCode, metricCode);
            const node: MetricTreeNode = {
              node_code: metricNodeCode || `${entityCode}:${tableName}:${metricCode}`,
              node_name: String(metric.name || metricCode || metricNodeCode || "未命名指标").trim(),
              children: [],
            };
            const childHasConfirmed = walk(metric.children ?? [], node);
            const selfConfirmed = Boolean(metricNodeCode);
            if (selfConfirmed || childHasConfirmed) {
              parent.children.push(node);
              hasConfirmedDescendant = true;
            }
          }
          return hasConfirmedDescendant;
        };
        walk(table.metrics ?? [], tableNode);
        if (tableNode.children.length > 0) entityNode.children.push(tableNode);
      }
      if (entityNode.children.length > 0) roots.push(entityNode);
    }
    const sortTree = (nodes: MetricTreeNode[]) => {
      nodes.sort((a, b) => a.node_code.localeCompare(b.node_code, "zh-CN"));
      nodes.forEach((node) => sortTree(node.children));
    };
    sortTree(roots);
    return roots;
  }, [orgProductMetricSnapshot]);

  const metricDescendantsByNode = useMemo(() => {
    const childMap = new Map<string, string[]>();
    const index = new Set<string>();
    const walk = (nodes: MetricTreeNode[]) => {
      for (const node of nodes) {
        index.add(node.node_code);
        for (const child of node.children) {
          childMap.set(node.node_code, [...(childMap.get(node.node_code) ?? []), child.node_code]);
        }
        walk(node.children);
      }
    };
    walk(metricTreeRoots);
    const collect = (code: string): string[] => {
      const children = childMap.get(code) ?? [];
      return [code, ...children.flatMap(collect)];
    };
    const result = new Map<string, Set<string>>();
    index.forEach((code) => result.set(code, new Set(collect(code))));
    return result;
  }, [metricTreeRoots]);

  const metricFormulaCandidates = useMemo<MetricFormulaCandidate[]>(() => {
    const orgProductCandidates: MetricFormulaCandidate[] = [];
    const seen = new Set<string>();
    for (const entity of orgProductMetricSnapshot?.entities ?? []) {
      const entityCode = String(entity.entity_code || "").trim().toUpperCase();
      const entityName = String(entity.entity_name || entityCode).trim();
      for (const table of entity.tables ?? []) {
        const walk = (metrics: OrgProductMetricNodeDto[]) => {
          for (const metric of metrics) {
            const metricCode = String(metric.code || "").trim().toUpperCase();
            const dataAcctCode = deriveRuntimeRefFromOrgProductMetricCode(entityCode, metricCode);
            if (metricCode && dataAcctCode) {
              const sourceRef = `${entityCode}:${table.table_name}:${metricCode}`;
              const key = `org_product:${sourceRef}:${dataAcctCode}`;
              if (!seen.has(key)) {
                seen.add(key);
                orgProductCandidates.push({
                  metric_code: metricCode,
                  metric_name: String(metric.name || dataAcctCode),
                  metric_node_code: dataAcctCode,
                  metric_node_name: String(metric.name || dataAcctCode),
                  scope_type: entityCode === "AA" ? "ALL" : "PRODUCT",
                  scope_code: entityCode,
                  product_name: entityName,
                  data_acct_code: dataAcctCode,
                  data_acct_name: String(metric.name || dataAcctCode),
                  sort_order: 0,
                  is_active: 1,
                  remark: null,
                  candidate_key: key,
                  source_type: "org_product_metric",
                  source_label: "机构产品指标",
                  source_ref: sourceRef,
                  display_name: String(metric.name || dataAcctCode),
                  formula_text: String(metric.formula_actual || metric.formula_forecast || metric.formula || "").trim(),
                });
              }
            }
            if (metric.children?.length) walk(metric.children);
          }
        };
        walk(table.metrics ?? []);
      }
    }
    return orgProductCandidates;
  }, [orgProductMetricSnapshot]);

  const selectedMetricBindings = useMemo(() => {
    const q = metricSearchText.trim().toLowerCase();
    const descendantCodes = selectedMetricNode
      ? metricDescendantsByNode.get(selectedMetricNode) ?? new Set([selectedMetricNode])
      : null;
    return metricFormulaCandidates.filter((binding) => {
      if (descendantCodes && !descendantCodes.has(binding.metric_node_code)) return false;
      if (!q) return true;
      return (
        binding.data_acct_code.toLowerCase().includes(q) ||
        bindingMetricCode(binding).toLowerCase().includes(q) ||
        bindingMetricName(binding).toLowerCase().includes(q) ||
        binding.source_label.toLowerCase().includes(q) ||
        (binding.source_ref ?? "").toLowerCase().includes(q) ||
        (binding.data_acct_name ?? "").toLowerCase().includes(q) ||
        (binding.display_name ?? "").toLowerCase().includes(q) ||
        (binding.metric_node_name ?? "").toLowerCase().includes(q) ||
        (binding.formula_text ?? "").toLowerCase().includes(q)
      );
    });
  }, [metricDescendantsByNode, metricFormulaCandidates, metricSearchText, selectedMetricNode]);

  const chartVariables = variables.filter(isChartVariable);
  const parameterVariables = variables.filter((item) => item.variable_type === "parameter" && !isChartVariable(item));
  const textVariables = variables.filter((item) => item.variable_type === "text" && !isChartVariable(item));
  const metricVariables = variables.filter((item) => item.variable_type === "metric" && !isChartVariable(item));

  const loadTemplates = async (keepSelected = true) => {
    const rows = await listSmartReportTemplates();
    setTemplates(rows);
    setSelectedTemplateId((current) => {
      if (keepSelected && current && rows.some((item) => item.template_id === current)) return current;
      return rows[0]?.template_id ?? null;
    });
  };

  const loadInstances = async () => {
    const rows = await listSmartReportInstances();
    setInstances(rows);
  };

  const loadCalcMetrics = async () => {
    const rows = await listSmartReportCalcMetrics();
    setCalcMetrics(rows);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      loadTemplates(false),
      loadInstances(),
      loadCalcMetrics(),
      (getOrgProductMetricSnapshot() as Promise<OrgProductMetricSnapshotDto>)
        .then(setOrgProductMetricSnapshot)
        .catch(() => setOrgProductMetricSnapshot({ entities: [] })),
    ])
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载智能报告数据失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedMetricNode || metricTreeRoots.length === 0) return;
    setSelectedMetricNode(metricTreeRoots[0]?.node_code ?? null);
  }, [metricTreeRoots, selectedMetricNode]);

  useEffect(() => {
    if (!selectedTemplateId) {
      setVariables([]);
      setPreviewText("");
      setPreviewWarnings([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listSmartReportTemplateVariables(selectedTemplateId)
      .then((rows) => {
        if (cancelled) return;
        setVariables(rows);
        setPreviewText("");
        setPreviewWarnings([]);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载模板变量失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedTemplateId]);

  useEffect(() => {
    setParamValues((current) => {
      const next = { ...current };
      for (const item of parameterVariables) {
        const key = paramKeyOf(item);
        if (next[key] === undefined) next[key] = "";
      }
      return next;
    });
    setTextValues((current) => {
      const next = { ...current };
      for (const item of textVariables) {
        const key = textKeyOf(item);
        if (next[key] === undefined) next[key] = "";
      }
      return next;
    });
  }, [variables]);

  const handleUpload = async () => {
    if (!selectedFile) {
      setError("请选择 .docx 模板文件");
      return;
    }
    const code = templateCode.trim() || selectedFile.name.replace(/\.docx$/i, "");
    const name = templateName.trim() || selectedFile.name.replace(/\.docx$/i, "");
    setUploading(true);
    setError("");
    setMessage("");
    try {
      const result = await uploadSmartReportTemplate({
        file: selectedFile,
        template_code: code,
        template_name: name,
        template_type: "analysis",
      });
      setMessage(`模板已上传，识别到 ${result.placeholders.length} 个占位符`);
      setSelectedTemplateId(result.template.template_id);
      setSelectedFile(null);
      setTemplateCode("");
      setTemplateName("");
      setTemplateContent("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      await Promise.all([loadTemplates(true), loadInstances()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传模板失败");
    } finally {
      setUploading(false);
    }
  };

  const handleInspectReportWithAI = async () => {
    if (!aiReportFile) {
      setError("请选择要 AI 解析的 .docx 报告");
      return;
    }
    setInspectingReport(true);
    setError("");
    setMessage("");
    try {
      const result = await inspectSmartReportWithAI(aiReportFile);
      setAiInspection(result);
      setSavedBlueprint(null);
      setBlueprintPreviewText("");
      setBlueprintGenerated(null);
      setMessage(`AI 已解析报告：${result.blocks.length} 个结构块，${result.issues.length} 个待确认项`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI 解析报告失败");
    } finally {
      setInspectingReport(false);
    }
  };

  const handleSaveBlueprint = async () => {
    if (!aiInspection) {
      setError("请先进行 AI 解析");
      return;
    }
    setSavingBlueprint(true);
    setError("");
    setMessage("");
    try {
      const payload: SmartReportBlueprintSaveRequestDto = {
        blueprint_name: aiInspection.summary || aiInspection.filename.replace(/\.docx$/i, ""),
        inspection: aiInspection,
      };
      const result = await saveSmartReportBlueprint(payload);
      setSavedBlueprint(result);
      setMessage(`报告蓝图已保存：${result.blueprint_name}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存报告蓝图失败");
    } finally {
      setSavingBlueprint(false);
    }
  };

  const handlePreviewBlueprint = async () => {
    if (!savedBlueprint) {
      setError("请先保存报告蓝图");
      return;
    }
    setPreviewingBlueprint(true);
    setError("");
    setMessage("");
    try {
      const result = await previewSmartReportBlueprint(savedBlueprint.blueprint_id);
      setBlueprintPreviewText(result.preview_text);
      setMessage(`蓝图预览已生成，待确认项 ${result.issue_count} 个`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成蓝图预览失败");
    } finally {
      setPreviewingBlueprint(false);
    }
  };

  const handleGenerateBlueprint = async () => {
    if (!savedBlueprint) {
      setError("请先保存报告蓝图");
      return;
    }
    setGeneratingBlueprint(true);
    setError("");
    setMessage("");
    try {
      const result = await generateSmartReportBlueprint(savedBlueprint.blueprint_id);
      setBlueprintGenerated(result);
      setMessage(`蓝图 Word 已生成：${result.output_filename}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成蓝图 Word 失败");
    } finally {
      setGeneratingBlueprint(false);
    }
  };

  const handleDownloadBlueprint = async () => {
    if (!blueprintGenerated) {
      setError("请先生成蓝图 Word");
      return;
    }
    await downloadSmartReportGeneratedFile(blueprintGenerated.download_url, blueprintGenerated.output_filename);
  };

  const handleSaveTextTemplate = async () => {
    const code = templateCode.trim();
    const name = templateName.trim();
    const content = templateContent.trim();
    if (!code || !name || !content) {
      setError("请填写模板编码、模板名称和模板内容");
      return;
    }
    setUploading(true);
    setError("");
    setMessage("");
    try {
      const payload: SmartReportTextTemplateCreateDto = {
        template_code: code,
        template_name: name,
        content: templateContent,
        template_type: "analysis",
      };
      const result = await createSmartReportTextTemplate(payload);
      setMessage(`模板已保存，识别到 ${result.placeholders.length} 个占位符`);
      setSelectedTemplateId(result.template.template_id);
      setTemplateCode("");
      setTemplateName("");
      setTemplateContent("");
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await Promise.all([loadTemplates(true), loadInstances()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存手工模板失败");
    } finally {
      setUploading(false);
    }
  };

  const insertMetricBinding = (binding: MetricFormulaCandidate) => {
    if (metricPickerMode === "calc") {
      let insertedAlias = "";
      setCalcMetricComponents((current) => {
        if (current.some((item) => item.data_acct_code === binding.data_acct_code)) return current;
        const alias = `M${current.length + 1}`;
        insertedAlias = alias;
        return [
          ...current,
          {
            alias,
            data_acct_code: binding.data_acct_code,
            data_acct_name: binding.display_name ?? binding.data_acct_name ?? binding.metric_node_name ?? "",
            metric_code: bindingMetricCode(binding),
            metric_name: bindingMetricName(binding),
          },
        ];
      });
      if (insertedAlias) setCalcMetricExpression((current) => (current.trim() ? current : insertedAlias));
      setShowMetricPicker(false);
      setShowCalcMetricDialog(true);
      return;
    }
    const token = `{{formula:${binding.data_acct_code}:auto}}`;
    const label = `${bindingMetricCode(binding)} ${bindingMetricName(binding)}`;
    const line = `\n${label}：${token}\n`;
    setTemplateContent((current) => `${current}${line}`);
    setShowMetricPicker(false);
    setError("");
  };

  const insertCalcMetric = (metric: SmartReportCalcMetricDto) => {
    const line = `\n${metric.metric_name}：{{calc:${metric.metric_code}}}\n`;
    setTemplateContent((current) => `${current}${line}`);
    setError("");
  };

  const handleSaveCalcMetric = async () => {
    const code = calcMetricCode.trim();
    const name = calcMetricName.trim();
    const expression = calcMetricExpression.trim();
    if (!code || !name || !expression || calcMetricComponents.length === 0) {
      setError("请填写计算指标编码、名称、表达式，并至少选择一个基础指标");
      return;
    }
    setSavingCalcMetric(true);
    setError("");
    setMessage("");
    try {
      const payload: SmartReportCalcMetricUpsertDto = {
        metric_code: code,
        metric_name: name,
        expression,
        components: calcMetricComponents,
        value_type: calcMetricFormatType === "percent" ? "百分比" : "金额",
        format_type: calcMetricFormatType,
      };
      const saved = await upsertSmartReportCalcMetric(code, payload);
      setMessage(`计算指标已保存：${saved.metric_name}`);
      setShowCalcMetricDialog(false);
      setCalcMetricCode("");
      setCalcMetricName("");
      setCalcMetricExpression("");
      setCalcMetricFormatType("number");
      setCalcMetricComponents([]);
      await loadCalcMetrics();
      insertCalcMetric(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存计算指标失败");
    } finally {
      setSavingCalcMetric(false);
    }
  };

  const toggleMetricNode = (nodeCode: string) => {
    setCollapsedMetricNodes((current) => ({ ...current, [nodeCode]: !current[nodeCode] }));
  };

  const handlePreview = async () => {
    if (!selectedTemplateId) {
      setError("请选择报告模板");
      return;
    }
    setPreviewing(true);
    setError("");
    setMessage("");
    try {
      const result = await previewSmartReport({
        template_id: selectedTemplateId,
        parameters: paramValues,
        text_values: textValues,
      });
      setPreviewText(result.preview_text);
      setPreviewWarnings(result.warnings);
      setMessage("预览已更新，确认无误后可生成 Word");
    } catch (err) {
      setError(err instanceof Error ? err.message : "预览报告失败");
    } finally {
      setPreviewing(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedTemplateId || !selectedTemplate) {
      setError("请选择报告模板");
      return;
    }
    setGenerating(true);
    setError("");
    setMessage("");
    try {
      const result = await generateSmartReport({
        template_id: selectedTemplateId,
        instance_name: `${selectedTemplate.template_name} ${new Date().toLocaleString()}`,
        parameters: paramValues,
        text_values: textValues,
      });
      setLastGenerated(result);
      setMessage(`报告已生成：${result.output_filename}，请在报告实例中下载`);
      await loadInstances();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成 Word 报告失败");
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadInstance = async (instance: SmartReportInstanceDto) => {
    await downloadSmartReportInstance(instance);
  };

  const handleRefreshInstance = async (instance: SmartReportInstanceDto) => {
    setRefreshingInstanceId(instance.instance_id);
    setError("");
    setMessage("");
    try {
      const result = await refreshSmartReportInstance(instance.instance_id);
      setLastGenerated(result);
      setMessage(`报告已刷新：${result.output_filename}，请在报告实例中下载`);
      await loadInstances();
    } catch (err) {
      setError(err instanceof Error ? err.message : "刷新 Word 报告失败");
    } finally {
      setRefreshingInstanceId(null);
    }
  };

  const renderMetricNode = (node: MetricTreeNode, depth = 0): JSX.Element => {
    const hasChildren = node.children.length > 0;
    const collapsed = !!collapsedMetricNodes[node.node_code];
    const directBindingCount = metricFormulaCandidates.filter((binding) => binding.metric_node_code === node.node_code).length;
    return (
      <div key={node.node_code}>
        <button
          type="button"
          onClick={() => setSelectedMetricNode(node.node_code)}
          className={`flex w-full items-center gap-1.5 px-2 py-1 text-left text-xs ${
            selectedMetricNode === node.node_code ? "bg-blue-50 text-blue-700" : "text-slate-700 hover:bg-slate-50"
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
      </div>
    );
  };

  return (
    <div className="bb-page">
      <div className="bb-page-header">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-[var(--bb-primary)]" />
          <h3 className="bb-page-title">智能分析报告</h3>
          {loading && <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />}
        </div>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索模板编码或名称"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="bb-input w-64 pl-8"
          />
        </div>
      </div>

      {(error || message) && (
        <div
          className={`bb-status-banner flex items-center gap-2 ${
            error ? "bb-status-banner-danger" : "bb-status-banner-success"
          }`}
        >
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{error || message}</span>
        </div>
      )}

      <div className="grid grid-cols-[minmax(360px,0.9fr)_minmax(520px,1.4fr)] gap-3 min-h-0 flex-1">
        <section className="bb-panel min-h-0 flex flex-col">
          <div className="bb-panel-header">
            <div className="bb-panel-title">报告模板</div>
            <button
              type="button"
              onClick={() => void loadTemplates(true)}
              className="bb-btn bb-btn-secondary h-7 px-2"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              刷新
            </button>
          </div>

          <div className="p-3 border-b border-gray-200 grid grid-cols-2 gap-2">
            <div className="bb-tabs col-span-2 grid grid-cols-2">
              <button
                type="button"
                onClick={() => setTemplateInputMode("upload")}
                className={`bb-tab ${
                  templateInputMode === "upload" ? "bb-tab-active" : ""
                }`}
              >
                上传 Word
              </button>
              <button
                type="button"
                onClick={() => setTemplateInputMode("text")}
                className={`bb-tab ${
                  templateInputMode === "text" ? "bb-tab-active" : ""
                }`}
              >
                手工录入
              </button>
            </div>
            <input
              value={templateCode}
              onChange={(e) => setTemplateCode(e.target.value)}
              placeholder="模板编码"
              className="bb-input"
            />
            <input
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="模板名称"
              className="bb-input"
            />
            {templateInputMode === "upload" ? (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".docx"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
                  className="col-span-2 text-xs file:mr-2 file:px-2 file:py-1 file:border file:border-gray-300 file:rounded file:bg-white file:text-xs"
                />
                <button
                  type="button"
                  onClick={() => void handleUpload()}
                  disabled={uploading}
                  className="bb-btn bb-btn-primary col-span-2"
                >
                  {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                  上传并识别占位符
                </button>
                <div className="bb-status-banner bb-status-banner-success col-span-2 mt-1 space-y-2">
                  <div className="text-[11px] text-emerald-700">
                    AI 报告理解：上传已有 Word 报告，自动抽取指标、分析任务和待确认项。
                  </div>
                  <input
                    type="file"
                    accept=".docx"
                    onChange={(e) => setAiReportFile(e.target.files?.[0] ?? null)}
                    className="w-full text-xs file:mr-2 file:px-2 file:py-1 file:border file:border-emerald-300 file:rounded file:bg-white file:text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => void handleInspectReportWithAI()}
                    disabled={inspectingReport}
                    className="bb-btn bb-btn-success w-full"
                  >
                    {inspectingReport ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                    AI 解析报告结构
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="bb-card col-span-2 grid grid-cols-5 gap-2 bg-[var(--bb-bg-subtle)]">
                  {["year", "start_month", "end_month", "version_id", "budget_actual"].map((key) => (
                    <label key={key} className="block">
                      <span className="block text-[11px] text-gray-500 mb-1">
                        {key === "year"
                          ? "年度"
                          : key === "start_month"
                            ? "开始月"
                            : key === "end_month"
                              ? "结束月"
                              : key === "version_id"
                                ? "版本"
                                : "预算/实际"}
                      </span>
                      {key === "budget_actual" ? (
                        <select
                          value={paramValues[key] ?? "0"}
                          onChange={(e) => setParamValues((current) => ({ ...current, [key]: e.target.value }))}
                          className="bb-select w-full"
                        >
                          <option value="0">预算</option>
                          <option value="1">实际</option>
                        </select>
                      ) : (
                        <input
                          value={paramValues[key] ?? ""}
                          onChange={(e) => setParamValues((current) => ({ ...current, [key]: e.target.value }))}
                          className="bb-input w-full"
                        />
                      )}
                    </label>
                  ))}
                </div>
                <div className="bb-card col-span-2 space-y-2">
                  <div className="text-[11px] text-gray-500">
                    从已确认机构产品指标选择指标，系统会按上方报告口径自动使用预算或实际公式。
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setMetricPickerMode("template");
                      setShowMetricPicker(true);
                    }}
                    className="bb-btn bb-btn-secondary w-full"
                  >
                    <Search className="w-3.5 h-3.5" />
                    打开指标树选择
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCalcMetricDialog(true)}
                    className="bb-btn bb-btn-success w-full"
                  >
                    <Wand2 className="w-3.5 h-3.5" />
                    新建/插入计算指标
                  </button>
                  {calcMetrics.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {calcMetrics.slice(0, 6).map((metric) => (
                        <button
                          key={metric.metric_code}
                          type="button"
                          onClick={() => insertCalcMetric(metric)}
                          className="bb-grid-chip text-[11px] hover:bg-[var(--bb-primary-soft)]"
                          title={metric.expression}
                        >
                          {metric.metric_name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <textarea
                  value={templateContent}
                  onChange={(e) => setTemplateContent(e.target.value)}
                  placeholder={"输入报告正文，例如：\\n本期经营情况如下：\\n然后从上方选择机构及产品指标公式插入。"}
                  className="bb-textarea col-span-2 h-32 resize-none"
                />
                <button
                  type="button"
                  onClick={() => void handleSaveTextTemplate()}
                  disabled={uploading}
                  className="bb-btn bb-btn-primary col-span-2"
                >
                  {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  保存为模板
                </button>
              </>
            )}
          </div>

          <div className="flex-1 overflow-auto">
            <table className="bb-table bb-table-dense w-full">
              <thead className="bg-gray-100 sticky top-0">
                <tr>
                  <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">模板</th>
                  <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-20">版本</th>
                  <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-20">变量</th>
                </tr>
              </thead>
              <tbody>
                {filteredTemplates.map((item) => (
                  <tr
                    key={item.template_id}
                    onClick={() => setSelectedTemplateId(item.template_id)}
                    className={`cursor-pointer ${selectedTemplateId === item.template_id ? "bg-blue-50" : "hover:bg-gray-50"}`}
                  >
                    <td className="border-b border-gray-200 px-2 py-2">
                      <div className="font-medium text-gray-800">{item.template_name}</div>
                      <div className="text-gray-500 mt-0.5">{item.template_code}</div>
                    </td>
                    <td className="border-b border-gray-200 px-2 py-2 text-gray-700">v{item.version_no}</td>
                    <td className="border-b border-gray-200 px-2 py-2 text-gray-700">{item.variable_count}</td>
                  </tr>
                ))}
                {filteredTemplates.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-3 py-8 text-center text-gray-400">
                      暂无模板
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="min-h-0 flex flex-col gap-3">
          <div className="bb-panel min-h-0 flex flex-col flex-[1.2]">
            <div className="bb-panel-header">
              <div className="bb-panel-title">
                报告预览{selectedTemplate ? `：${selectedTemplate.template_name}` : ""}
              </div>
              <button
                type="button"
                onClick={() => void handlePreview()}
                disabled={!selectedTemplateId || previewing}
                className="bb-btn bb-btn-secondary h-7 px-2"
              >
                {previewing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                预览报告
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {aiInspection && (
                <div className="bb-status-banner bb-status-banner-success mb-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="font-medium">AI 解析结果：{aiInspection.filename}</div>
                    <div className="text-[11px] text-emerald-700">{aiInspection.model || "DeepSeek"}</div>
                  </div>
                  <div className="mb-2 text-emerald-800">{aiInspection.summary || "已完成报告结构识别"}</div>
                  <div className="grid grid-cols-3 gap-2 mb-2">
                    <div className="rounded bg-white/70 p-2">结构块：{aiInspection.blocks.length}</div>
                    <div className="rounded bg-white/70 p-2">待确认：{aiInspection.issues.length}</div>
                    <div className="rounded bg-white/70 p-2">假设：{aiInspection.assumptions.length}</div>
                  </div>
                  <div className="mb-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void handleSaveBlueprint()}
                      disabled={savingBlueprint}
                      className="bb-btn bb-btn-success h-7 px-2"
                    >
                      {savingBlueprint ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      保存蓝图
                    </button>
                    <button
                      type="button"
                      onClick={() => void handlePreviewBlueprint()}
                      disabled={!savedBlueprint || previewingBlueprint}
                      className="bb-btn bb-btn-secondary h-7 px-2"
                    >
                      {previewingBlueprint ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                      生成指标预览
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleGenerateBlueprint()}
                      disabled={!savedBlueprint || generatingBlueprint}
                      className="bb-btn bb-btn-secondary h-7 px-2"
                    >
                      {generatingBlueprint ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                      保存并生成 Word
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDownloadBlueprint()}
                      disabled={!blueprintGenerated}
                      className="bb-btn bb-btn-secondary h-7 px-2"
                    >
                      <Download className="w-3.5 h-3.5" />
                      下载
                    </button>
                  </div>
                  {savedBlueprint && (
                    <div className="mb-2 rounded bg-white/70 p-2 text-[11px] text-emerald-800">
                      已保存蓝图 #{savedBlueprint.blueprint_id}：{savedBlueprint.blueprint_name}
                    </div>
                  )}
                  {blueprintPreviewText && (
                    <div className="mb-2 max-h-52 overflow-auto whitespace-pre-wrap rounded border border-emerald-200 bg-white p-2 text-[11px] leading-5 text-slate-700">
                      {blueprintPreviewText}
                    </div>
                  )}
                  {aiInspection.issues.length > 0 && (
                    <div className="space-y-2">
                      {aiInspection.issues.slice(0, 4).map((issue, index) => (
                        <div key={`${issue.issue_type}-${index}`} className="rounded border border-emerald-200 bg-white p-2">
                          <div className="font-medium text-emerald-900">{issue.issue_type}</div>
                          <div className="mt-1 text-slate-700">{issue.text}</div>
                          {issue.rule_preview && <div className="mt-1 text-slate-500">计划：{issue.rule_preview}</div>}
                          {issue.suggested_action && <div className="mt-1 text-emerald-700">{issue.suggested_action}</div>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {previewText ? (
                <div className="bb-card whitespace-pre-wrap bg-[var(--bb-bg-subtle)] text-sm leading-7">
                  {previewText}
                </div>
              ) : (
                <div className="bb-empty-state h-full min-h-44 flex-col gap-2 border border-dashed border-[var(--bb-border)]">
                  <FileText className="w-8 h-8 text-slate-300" />
                  <div>选择模板并填写参数后，点击“预览报告”查看替换后的正文。</div>
                  <div>这里会直接展示公式、参数和文本替换结果，不再要求手工维护变量绑定。</div>
                </div>
              )}
              {previewWarnings.length > 0 && (
                <div className="bb-status-banner bb-status-banner-warning mt-3">
                  {previewWarnings.map((item) => (
                    <div key={item}>{item}</div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-[minmax(320px,1fr)_minmax(320px,1fr)] gap-3 min-h-0 flex-1">
            <div className="bb-panel min-h-0 flex flex-col">
              <div className="bb-panel-header">
                <div className="bb-panel-title">生成参数</div>
                <button
                  type="button"
                  onClick={() => void handleGenerate()}
                  disabled={!selectedTemplateId || generating}
                  className="bb-btn bb-btn-success h-7 px-3"
                >
                  {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                  生成 Word
                </button>
              </div>
              <div className="p-3 overflow-auto space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  {["year", "start_month", "end_month", "version_id", "budget_actual"].map((key) => (
                    <label key={key} className="block">
                      <span className="block text-[11px] text-gray-500 mb-1">
                        {key === "year"
                          ? "年度"
                          : key === "start_month"
                            ? "开始月份"
                            : key === "end_month"
                              ? "结束月份"
                              : key === "version_id"
                                ? "版本ID"
                                : "数据口径（0预算/1实际）"}
                      </span>
                      <input
                        value={paramValues[key] ?? ""}
                        onChange={(e) => setParamValues((current) => ({ ...current, [key]: e.target.value }))}
                        className={`bb-input w-full ${
                          key === "budget_actual" ? "hidden" : ""
                        }`}
                      />
                      {key === "budget_actual" && (
                        <select
                          value={paramValues[key] ?? "0"}
                          onChange={(e) => setParamValues((current) => ({ ...current, [key]: e.target.value }))}
                          className="bb-select w-full"
                        >
                          <option value="0">预算</option>
                          <option value="1">实际</option>
                        </select>
                      )}
                    </label>
                  ))}
                </div>
                {parameterVariables
                  .map(paramKeyOf)
                  .filter((key) => !["year", "month", "start_month", "end_month", "version_id", "budget_actual"].includes(key))
                  .map((key) => (
                    <label key={key} className="block">
                      <span className="block text-[11px] text-gray-500 mb-1">{key}</span>
                      <input
                        value={paramValues[key] ?? ""}
                        onChange={(e) => setParamValues((current) => ({ ...current, [key]: e.target.value }))}
                        className="bb-input w-full"
                      />
                    </label>
                  ))}
                {textVariables.map((item) => {
                  const key = textKeyOf(item);
                  return (
                    <label key={item.variable_key} className="block">
                      <span className="block text-[11px] text-gray-500 mb-1">{item.variable_name}</span>
                      <input
                        value={textValues[key] ?? ""}
                        onChange={(e) => setTextValues((current) => ({ ...current, [key]: e.target.value }))}
                        className="bb-input w-full"
                      />
                    </label>
                  );
                })}
                {metricVariables.length > 0 && (
                  <div className="bb-card bg-[var(--bb-bg-subtle)]">
                    <div className="text-[11px] text-gray-500 mb-1">本次会计算的指标</div>
                    <div className="flex flex-wrap gap-1">
                      {metricVariables.map((item) => (
                        <span key={item.variable_key} className="bb-grid-chip text-[11px]">
                          {item.variable_name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {chartVariables.length > 0 && (
                  <div className="bb-ai-card">
                    <div className="mb-1 flex items-center gap-1 text-[11px] text-sky-700">
                      <ChartNoAxesColumn className="h-3.5 w-3.5" />
                      本次会自动渲染的图表
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {chartVariables.map((item) => (
                        <span
                          key={item.variable_key}
                          className="inline-flex items-center gap-1 rounded border border-sky-200 bg-white px-1.5 py-0.5 text-[11px] text-sky-700"
                        >
                          <ChartNoAxesColumn className="h-3 w-3" />
                          <span className="rounded bg-sky-100 px-1 text-[10px] font-medium text-sky-700">图表</span>
                          <span>{item.variable_name || chartCodeOf(item)}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {lastGenerated && (
                  <div className="bb-status-banner bb-status-banner-success">
                    最近生成：{lastGenerated.output_filename}
                  </div>
                )}
              </div>
            </div>

            <div className="bb-panel min-h-0 flex flex-col">
              <div className="bb-panel-header"><div className="bb-panel-title">报告实例</div></div>
              <div className="flex-1 overflow-auto">
                <table className="bb-table bb-table-dense w-full">
                  <thead className="bg-gray-100 sticky top-0">
                    <tr>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">实例</th>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-24">状态</th>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-20">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {instances.map((item) => (
                      <tr key={item.instance_id} className="hover:bg-gray-50">
                        <td className="border-b border-gray-200 px-2 py-2">
                          <div className="font-medium text-gray-800">{item.instance_name}</div>
                          <div className="text-gray-500 mt-0.5">生成：{fmtTime(item.last_generated_at ?? item.created_at)}</div>
                          {item.last_refresh_at && <div className="text-gray-500 mt-0.5">刷新：{fmtTime(item.last_refresh_at)}</div>}
                          {item.error_message && <div className="text-red-500 mt-0.5">{item.error_message}</div>}
                        </td>
                        <td className="border-b border-gray-200 px-2 py-2 text-gray-700">{item.generation_status}</td>
                        <td className="border-b border-gray-200 px-2 py-2">
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() => void handleRefreshInstance(item)}
                              disabled={refreshingInstanceId === item.instance_id}
                              className="bb-icon-btn border border-[var(--bb-border)] bg-[var(--bb-bg-surface)]"
                              title="按原参数刷新"
                            >
                              {refreshingInstanceId === item.instance_id ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <RefreshCw className="w-3.5 h-3.5" />
                              )}
                            </button>
                          <button
                            type="button"
                            onClick={() => void handleDownloadInstance(item)}
                            disabled={item.generation_status !== "success"}
                            className="bb-icon-btn border border-[var(--bb-border)] bg-[var(--bb-bg-surface)]"
                            title="下载 Word"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {instances.length === 0 && (
                      <tr>
                        <td colSpan={3} className="px-3 py-8 text-center text-gray-400">
                          暂无生成记录
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>
      </div>

      {showCalcMetricDialog && (
        <div className="bb-modal-backdrop z-40">
          <div className="bb-modal w-[760px] max-w-[calc(100vw-48px)] max-h-[calc(100vh-48px)]">
            <div className="bb-modal-header">
              <div className="bb-panel-title">报告计算指标</div>
              <button
                type="button"
                onClick={() => setShowCalcMetricDialog(false)}
                className="bb-icon-btn border border-[var(--bb-border)] bg-[var(--bb-bg-surface)]"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="p-4 space-y-3 overflow-auto">
              <div className="grid grid-cols-2 gap-2">
                <label className="block">
                  <span className="block text-[11px] text-gray-500 mb-1">指标编码</span>
                  <input
                    value={calcMetricCode}
                    onChange={(e) => setCalcMetricCode(e.target.value)}
                    placeholder="如 net_interest_margin"
                    className="bb-input w-full"
                  />
                </label>
                <label className="block">
                  <span className="block text-[11px] text-gray-500 mb-1">指标名称</span>
                  <input
                    value={calcMetricName}
                    onChange={(e) => setCalcMetricName(e.target.value)}
                    placeholder="如 净息差"
                    className="bb-input w-full"
                  />
                </label>
              </div>
              <div className="grid grid-cols-[1fr_120px] gap-2">
                <label className="block">
                  <span className="block text-[11px] text-gray-500 mb-1">计算表达式</span>
                  <input
                    value={calcMetricExpression}
                    onChange={(e) => setCalcMetricExpression(e.target.value)}
                    placeholder="使用 M1、M2 组合，例如 (M1 - M2) / M3"
                    className="bb-input w-full font-mono"
                  />
                </label>
                <label className="block">
                  <span className="block text-[11px] text-gray-500 mb-1">展示格式</span>
                  <select
                    value={calcMetricFormatType}
                    onChange={(e) => setCalcMetricFormatType(e.target.value as "number" | "percent")}
                    className="bb-select w-full"
                  >
                    <option value="number">数值</option>
                    <option value="percent">百分比</option>
                  </select>
                </label>
              </div>
              <div className="bb-panel">
                <div className="bb-panel-header">
                  <div className="bb-panel-title">基础指标项</div>
                  <button
                    type="button"
                    onClick={() => {
                      setMetricPickerMode("calc");
                      setShowCalcMetricDialog(false);
                      setShowMetricPicker(true);
                    }}
                    className="bb-btn bb-btn-secondary h-7 px-2"
                  >
                    <Search className="w-3.5 h-3.5" />
                    从指标树添加
                  </button>
                </div>
                <div className="max-h-44 overflow-auto">
                  <table className="bb-table bb-table-dense w-full">
                    <thead className="bg-gray-100 sticky top-0">
                      <tr>
                        <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-20">别名</th>
                        <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">机构及产品指标编码</th>
                        <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-16">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {calcMetricComponents.map((component, index) => (
                        <tr key={`${component.alias}-${component.data_acct_code}`} className="hover:bg-gray-50">
                          <td className="border-b border-gray-200 px-2 py-1">
                            <input
                              value={component.alias}
                              onChange={(e) =>
                                setCalcMetricComponents((current) =>
                                  current.map((item, itemIndex) =>
                                    itemIndex === index ? { ...item, alias: e.target.value.trim() } : item,
                                  ),
                                )
                              }
                              className="bb-input w-full font-mono"
                            />
                          </td>
                          <td className="border-b border-gray-200 px-2 py-2">
                            <div className="font-mono text-[11px] text-slate-500">{calcComponentMetricCode(component)}</div>
                            <div className="text-gray-700">{calcComponentMetricName(component)}</div>
                          </td>
                          <td className="border-b border-gray-200 px-2 py-1">
                            <button
                              type="button"
                              onClick={() =>
                                setCalcMetricComponents((current) => current.filter((_, itemIndex) => itemIndex !== index))
                              }
                              className="bb-btn bb-btn-secondary h-7 px-2"
                            >
                              移除
                            </button>
                          </td>
                        </tr>
                      ))}
                      {calcMetricComponents.length === 0 && (
                        <tr>
                          <td colSpan={3} className="px-3 py-6 text-center text-gray-400">
                            先从指标树添加基础项，系统会给它们生成 M1、M2 这样的表达式别名
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
              {calcMetrics.length > 0 && (
                <div className="bb-card bg-[var(--bb-bg-subtle)]">
                  <div className="text-[11px] text-gray-500 mb-1">已有计算指标，点击可插入模板</div>
                  <div className="flex flex-wrap gap-1">
                    {calcMetrics.map((metric) => (
                      <button
                        key={metric.metric_code}
                        type="button"
                        onClick={() => {
                          insertCalcMetric(metric);
                          setShowCalcMetricDialog(false);
                        }}
                        className="bb-grid-chip text-[11px] hover:bg-[var(--bb-primary-soft)]"
                        title={metric.expression}
                      >
                        {metric.metric_name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="border-t border-[var(--bb-border-soft)] px-4 py-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowCalcMetricDialog(false)}
                className="bb-btn bb-btn-secondary"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleSaveCalcMetric()}
                disabled={savingCalcMetric}
                className="bb-btn bb-btn-success"
              >
                {savingCalcMetric ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                保存并插入
              </button>
            </div>
          </div>
        </div>
      )}

      {showMetricPicker && (
        <div className="bb-modal-backdrop z-50">
          <div className="bb-modal w-[920px] max-w-[calc(100vw-48px)] h-[620px] max-h-[calc(100vh-48px)]">
            <div className="bb-modal-header">
              <div className="bb-panel-title">
                {metricPickerMode === "calc" ? "选择计算指标的基础项" : "选择机构及产品指标"}
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowMetricPicker(false);
                  if (metricPickerMode === "calc") setShowCalcMetricDialog(true);
                }}
                className="bb-icon-btn border border-[var(--bb-border)] bg-[var(--bb-bg-surface)]"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="p-3 border-b border-gray-200">
              <input
                value={metricSearchText}
                onChange={(e) => setMetricSearchText(e.target.value)}
                placeholder="搜索机构及产品指标编码、名称或公式"
                className="bb-input w-full"
              />
            </div>
            <div className="flex-1 min-h-0 grid grid-cols-[320px_minmax(0,1fr)]">
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
              <div className="min-h-0 overflow-auto">
                <table className="bb-table bb-table-dense w-full">
                  <thead className="sticky top-0 bg-gray-100 z-10">
                    <tr>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">指标/绑定</th>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">机构及产品指标</th>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">公式口径</th>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-20">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedMetricBindings.map((binding) => {
                      const formula = binding.formula_text || "";
                      return (
                        <tr key={binding.candidate_key} className="hover:bg-blue-50/50">
                          <td className="border-b border-gray-200 px-2 py-2">
                            <div className="font-mono text-[11px] text-slate-600">{bindingMetricCode(binding)}</div>
                            <div className="flex items-center gap-1.5 text-gray-700">
                              <span>{bindingMetricName(binding)}</span>
                              <span
                                className={`shrink-0 rounded border px-1 py-0.5 text-[10px] ${
                                  "border-blue-200 bg-blue-50 text-blue-700"
                                }`}
                              >
                                {binding.source_label}
                              </span>
                            </div>
                            {binding.source_ref ? (
                              <div className="mt-0.5 font-mono text-[10px] text-blue-500">{binding.source_ref}</div>
                            ) : null}
                          </td>
                          <td className="border-b border-gray-200 px-2 py-2">
                            <div className="font-mono text-[11px] text-slate-600">{bindingMetricCode(binding)}</div>
                            <div className="text-gray-700">{bindingMetricName(binding)}</div>
                          </td>
                          <td className="border-b border-gray-200 px-2 py-2 text-gray-600 max-w-[280px]">
                            <div className="line-clamp-2">{formula || "未配置公式，生成时按指标当前值口径处理"}</div>
                          </td>
                          <td className="border-b border-gray-200 px-2 py-2">
                            <button
                              type="button"
                              onClick={() => insertMetricBinding(binding)}
                              className="bb-btn bb-btn-primary h-7 px-2"
                            >
                              {metricPickerMode === "calc" ? "加入" : "插入"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                    {selectedMetricBindings.length === 0 && (
                      <tr>
                        <td colSpan={4} className="px-3 py-8 text-center text-gray-400">
                          当前条件下暂无可选指标
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
