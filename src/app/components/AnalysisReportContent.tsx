import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
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
  apiGet,
  apiPost,
  apiPostForm,
  apiPut,
  downloadFile,
  type DataAccountDto,
  type DataAccountMetricBindingDto,
  type DataAccountMetricNodeDto,
  type DataAccountMetricTreeDto,
  type SmartReportCalcMetricComponentDto,
  type SmartReportCalcMetricDto,
  type SmartReportCalcMetricUpsertDto,
  type SmartReportGenerateResponseDto,
  type SmartReportInstanceDto,
  type SmartReportPreviewResponseDto,
  type SmartReportTemplateCreateResponseDto,
  type SmartReportTemplateDto,
  type SmartReportTextTemplateCreateDto,
  type SmartReportTemplateVariableDto,
} from "@/lib/api";

type MetricTreeNode = DataAccountMetricNodeDto & {
  children: MetricTreeNode[];
};

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

export function AnalysisReportContent() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [templates, setTemplates] = useState<SmartReportTemplateDto[]>([]);
  const [instances, setInstances] = useState<SmartReportInstanceDto[]>([]);
  const [variables, setVariables] = useState<SmartReportTemplateVariableDto[]>([]);
  const [calcMetrics, setCalcMetrics] = useState<SmartReportCalcMetricDto[]>([]);
  const [dataAccounts, setDataAccounts] = useState<DataAccountDto[]>([]);
  const [metricNodes, setMetricNodes] = useState<DataAccountMetricNodeDto[]>([]);
  const [metricBindings, setMetricBindings] = useState<DataAccountMetricBindingDto[]>([]);
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
  const [uploading, setUploading] = useState(false);
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

  const dataAccountByCode = useMemo(() => new Map(dataAccounts.map((item) => [item.data_acct_code, item])), [dataAccounts]);

  const metricTreeRoots = useMemo(() => {
    const byCode = new Map<string, MetricTreeNode>();
    metricNodes.forEach((node) => byCode.set(node.node_code, { ...node, children: [] }));
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
    const q = metricSearchText.trim().toLowerCase();
    const descendantCodes = selectedMetricNode
      ? metricDescendantsByNode.get(selectedMetricNode) ?? new Set([selectedMetricNode])
      : null;
    return metricBindings.filter((binding) => {
      if (descendantCodes && !descendantCodes.has(binding.metric_node_code)) return false;
      const account = dataAccountByCode.get(binding.data_acct_code);
      if (!q) return true;
      return (
        binding.binding_code.toLowerCase().includes(q) ||
        binding.data_acct_code.toLowerCase().includes(q) ||
        (binding.data_acct_name ?? "").toLowerCase().includes(q) ||
        (binding.metric_node_name ?? "").toLowerCase().includes(q) ||
        (account?.budget_formula ?? "").toLowerCase().includes(q) ||
        (account?.actual_formula ?? "").toLowerCase().includes(q)
      );
    });
  }, [dataAccountByCode, metricBindings, metricDescendantsByNode, metricSearchText, selectedMetricNode]);

  const parameterVariables = variables.filter((item) => item.variable_type === "parameter");
  const textVariables = variables.filter((item) => item.variable_type === "text");
  const metricVariables = variables.filter((item) => item.variable_type === "metric");

  const loadTemplates = async (keepSelected = true) => {
    const rows = await apiGet<SmartReportTemplateDto[]>("/api/smart-reports/templates");
    setTemplates(rows);
    setSelectedTemplateId((current) => {
      if (keepSelected && current && rows.some((item) => item.template_id === current)) return current;
      return rows[0]?.template_id ?? null;
    });
  };

  const loadInstances = async () => {
    const rows = await apiGet<SmartReportInstanceDto[]>("/api/smart-reports/instances");
    setInstances(rows);
  };

  const loadCalcMetrics = async () => {
    const rows = await apiGet<SmartReportCalcMetricDto[]>("/api/smart-reports/calc-metrics");
    setCalcMetrics(rows);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      loadTemplates(false),
      loadInstances(),
      loadCalcMetrics(),
      apiGet<DataAccountDto[]>("/api/data-accounts").then(setDataAccounts),
      apiGet<DataAccountMetricTreeDto>("/api/data-account-metric-tree").then((tree) => {
        setMetricNodes(tree.nodes ?? []);
        setMetricBindings(tree.bindings ?? []);
        setSelectedMetricNode((current) => current ?? tree.nodes?.[0]?.node_code ?? null);
      }),
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
    if (!selectedTemplateId) {
      setVariables([]);
      setPreviewText("");
      setPreviewWarnings([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    apiGet<SmartReportTemplateVariableDto[]>(`/api/smart-reports/templates/${selectedTemplateId}/variables`)
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
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("template_code", code);
    form.append("template_name", name);
    form.append("template_type", "analysis");
    setUploading(true);
    setError("");
    setMessage("");
    try {
      const result = await apiPostForm<SmartReportTemplateCreateResponseDto>("/api/smart-reports/templates", form);
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
      const result = await apiPost<SmartReportTemplateCreateResponseDto>("/api/smart-reports/templates/text", payload);
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

  const insertMetricBinding = (binding: DataAccountMetricBindingDto) => {
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
            data_acct_name: binding.data_acct_name ?? binding.metric_node_name ?? "",
          },
        ];
      });
      if (insertedAlias) setCalcMetricExpression((current) => (current.trim() ? current : insertedAlias));
      setShowMetricPicker(false);
      setShowCalcMetricDialog(true);
      return;
    }
    const token = `{{formula:${binding.data_acct_code}:auto}}`;
    const label = `${binding.binding_code} ${binding.metric_node_name ?? binding.data_acct_name ?? binding.data_acct_code}`;
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
      const saved = await apiPut<SmartReportCalcMetricDto>(`/api/smart-reports/calc-metrics/${encodeURIComponent(code)}`, payload);
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
      const result = await apiPost<SmartReportPreviewResponseDto>("/api/smart-reports/preview", {
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
      const result = await apiPost<SmartReportGenerateResponseDto>("/api/smart-reports/generate", {
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
    await downloadFile(`/api/smart-reports/instances/${instance.instance_id}/download`, `${instance.instance_name}.docx`);
  };

  const handleRefreshInstance = async (instance: SmartReportInstanceDto) => {
    setRefreshingInstanceId(instance.instance_id);
    setError("");
    setMessage("");
    try {
      const result = await apiPost<SmartReportGenerateResponseDto>(
        `/api/smart-reports/instances/${instance.instance_id}/refresh`,
        {},
      );
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
    const directBindingCount = metricBindings.filter((binding) => binding.metric_node_code === node.node_code).length;
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
    <div className="h-full flex flex-col p-4 bg-slate-50/40">
      <div className="flex items-center justify-between mb-3 gap-3">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-slate-700" />
          <h3 className="text-sm font-medium text-gray-800">智能分析报告</h3>
          {loading && <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />}
        </div>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索模板编码或名称"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-3 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 w-64 bg-white"
          />
        </div>
      </div>

      {(error || message) && (
        <div
          className={`mb-3 flex items-center gap-2 border px-3 py-2 text-xs rounded ${
            error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
          }`}
        >
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{error || message}</span>
        </div>
      )}

      <div className="grid grid-cols-[minmax(360px,0.9fr)_minmax(520px,1.4fr)] gap-3 min-h-0 flex-1">
        <section className="min-h-0 flex flex-col border border-gray-300 rounded bg-white">
          <div className="border-b border-gray-200 px-3 py-2 flex items-center justify-between">
            <div className="text-xs font-medium text-gray-700">报告模板</div>
            <button
              type="button"
              onClick={() => void loadTemplates(true)}
              className="inline-flex items-center gap-1 px-2 py-1 border border-gray-300 rounded text-xs hover:bg-gray-50"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              刷新
            </button>
          </div>

          <div className="p-3 border-b border-gray-200 grid grid-cols-2 gap-2">
            <div className="col-span-2 grid grid-cols-2 gap-1 bg-gray-100 border border-gray-200 rounded p-1">
              <button
                type="button"
                onClick={() => setTemplateInputMode("upload")}
                className={`px-2 py-1 text-xs rounded ${
                  templateInputMode === "upload" ? "bg-white text-blue-700 shadow-sm" : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                上传 Word
              </button>
              <button
                type="button"
                onClick={() => setTemplateInputMode("text")}
                className={`px-2 py-1 text-xs rounded ${
                  templateInputMode === "text" ? "bg-white text-blue-700 shadow-sm" : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                手工录入
              </button>
            </div>
            <input
              value={templateCode}
              onChange={(e) => setTemplateCode(e.target.value)}
              placeholder="模板编码"
              className="border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <input
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="模板名称"
              className="border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
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
                  className="col-span-2 inline-flex justify-center items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-60"
                >
                  {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                  上传并识别占位符
                </button>
              </>
            ) : (
              <>
                <div className="col-span-2 grid grid-cols-5 gap-2 border border-gray-200 rounded bg-gray-50 p-2">
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
                          className="w-full border border-gray-300 rounded px-2 py-1 text-xs bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                        >
                          <option value="0">预算</option>
                          <option value="1">实际</option>
                        </select>
                      ) : (
                        <input
                          value={paramValues[key] ?? ""}
                          onChange={(e) => setParamValues((current) => ({ ...current, [key]: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                      )}
                    </label>
                  ))}
                </div>
                <div className="col-span-2 border border-gray-200 rounded p-2 space-y-2">
                  <div className="text-[11px] text-gray-500">
                    从数据科目指标树选择指标，系统会按上方报告口径自动使用预算或实际公式。
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setMetricPickerMode("template");
                      setShowMetricPicker(true);
                    }}
                    className="w-full inline-flex justify-center items-center gap-1 px-2 py-1 border border-gray-300 rounded text-xs hover:bg-gray-50"
                  >
                    <Search className="w-3.5 h-3.5" />
                    打开指标树选择
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCalcMetricDialog(true)}
                    className="w-full inline-flex justify-center items-center gap-1 px-2 py-1 border border-emerald-300 text-emerald-700 rounded text-xs hover:bg-emerald-50"
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
                          className="rounded border border-gray-300 bg-white px-1.5 py-0.5 text-[11px] text-gray-600 hover:bg-blue-50"
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
                  placeholder={"输入报告正文，例如：\\n本期经营情况如下：\\n然后从上方选择数据科目公式插入。"}
                  className="col-span-2 h-32 border border-gray-300 rounded px-2 py-1.5 text-xs resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <button
                  type="button"
                  onClick={() => void handleSaveTextTemplate()}
                  disabled={uploading}
                  className="col-span-2 inline-flex justify-center items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-60"
                >
                  {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  保存为模板
                </button>
              </>
            )}
          </div>

          <div className="flex-1 overflow-auto">
            <table className="w-full text-xs border-collapse">
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
          <div className="border border-gray-300 rounded bg-white min-h-0 flex flex-col flex-[1.2]">
            <div className="border-b border-gray-200 px-3 py-2 flex items-center justify-between">
              <div className="text-xs font-medium text-gray-700">
                报告预览{selectedTemplate ? `：${selectedTemplate.template_name}` : ""}
              </div>
              <button
                type="button"
                onClick={() => void handlePreview()}
                disabled={!selectedTemplateId || previewing}
                className="inline-flex items-center gap-1 px-2 py-1 border border-gray-300 rounded text-xs hover:bg-gray-50 disabled:opacity-60"
              >
                {previewing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                预览报告
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {previewText ? (
                <div className="whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-4 text-sm leading-7 text-slate-800">
                  {previewText}
                </div>
              ) : (
                <div className="h-full min-h-44 rounded border border-dashed border-slate-300 bg-slate-50/70 p-6 text-center text-xs text-slate-500 flex flex-col items-center justify-center gap-2">
                  <FileText className="w-8 h-8 text-slate-300" />
                  <div>选择模板并填写参数后，点击“预览报告”查看替换后的正文。</div>
                  <div>这里会直接展示公式、参数和文本替换结果，不再要求手工维护变量绑定。</div>
                </div>
              )}
              {previewWarnings.length > 0 && (
                <div className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  {previewWarnings.map((item) => (
                    <div key={item}>{item}</div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-[minmax(320px,1fr)_minmax(320px,1fr)] gap-3 min-h-0 flex-1">
            <div className="border border-gray-300 rounded bg-white min-h-0 flex flex-col">
              <div className="border-b border-gray-200 px-3 py-2 flex items-center justify-between">
                <div className="text-xs font-medium text-gray-700">生成参数</div>
                <button
                  type="button"
                  onClick={() => void handleGenerate()}
                  disabled={!selectedTemplateId || generating}
                  className="inline-flex items-center gap-1 px-3 py-1 bg-emerald-600 text-white rounded text-xs hover:bg-emerald-700 disabled:opacity-60"
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
                        className={`w-full border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 ${
                          key === "budget_actual" ? "hidden" : ""
                        }`}
                      />
                      {key === "budget_actual" && (
                        <select
                          value={paramValues[key] ?? "0"}
                          onChange={(e) => setParamValues((current) => ({ ...current, [key]: e.target.value }))}
                          className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
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
                        className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
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
                        className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </label>
                  );
                })}
                {metricVariables.length > 0 && (
                  <div className="border border-gray-200 rounded p-2 bg-gray-50">
                    <div className="text-[11px] text-gray-500 mb-1">本次会计算的指标</div>
                    <div className="flex flex-wrap gap-1">
                      {metricVariables.map((item) => (
                        <span key={item.variable_key} className="px-1.5 py-0.5 rounded border border-gray-300 bg-white text-[11px]">
                          {item.variable_name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {lastGenerated && (
                  <div className="border border-emerald-200 rounded p-2 bg-emerald-50 text-xs text-emerald-700">
                    最近生成：{lastGenerated.output_filename}
                  </div>
                )}
              </div>
            </div>

            <div className="border border-gray-300 rounded bg-white min-h-0 flex flex-col">
              <div className="border-b border-gray-200 px-3 py-2 text-xs font-medium text-gray-700">报告实例</div>
              <div className="flex-1 overflow-auto">
                <table className="w-full text-xs border-collapse">
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
                              className="inline-flex items-center justify-center w-7 h-7 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
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
                            className="inline-flex items-center justify-center w-7 h-7 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
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
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30">
          <div className="w-[760px] max-w-[calc(100vw-48px)] max-h-[calc(100vh-48px)] bg-white border border-gray-300 rounded shadow-xl flex flex-col">
            <div className="h-10 px-3 border-b border-gray-200 flex items-center justify-between">
              <div className="text-sm font-medium text-gray-800">报告计算指标</div>
              <button
                type="button"
                onClick={() => setShowCalcMetricDialog(false)}
                className="inline-flex items-center justify-center w-7 h-7 border border-gray-300 rounded hover:bg-gray-50"
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
                    className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </label>
                <label className="block">
                  <span className="block text-[11px] text-gray-500 mb-1">指标名称</span>
                  <input
                    value={calcMetricName}
                    onChange={(e) => setCalcMetricName(e.target.value)}
                    placeholder="如 净息差"
                    className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
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
                    className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </label>
                <label className="block">
                  <span className="block text-[11px] text-gray-500 mb-1">展示格式</span>
                  <select
                    value={calcMetricFormatType}
                    onChange={(e) => setCalcMetricFormatType(e.target.value as "number" | "percent")}
                    className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                  >
                    <option value="number">数值</option>
                    <option value="percent">百分比</option>
                  </select>
                </label>
              </div>
              <div className="border border-gray-200 rounded">
                <div className="px-3 py-2 border-b border-gray-200 flex items-center justify-between bg-gray-50">
                  <div className="text-xs font-medium text-gray-700">基础指标项</div>
                  <button
                    type="button"
                    onClick={() => {
                      setMetricPickerMode("calc");
                      setShowCalcMetricDialog(false);
                      setShowMetricPicker(true);
                    }}
                    className="inline-flex items-center gap-1 px-2 py-1 border border-gray-300 rounded text-xs hover:bg-white"
                  >
                    <Search className="w-3.5 h-3.5" />
                    从指标树添加
                  </button>
                </div>
                <div className="max-h-44 overflow-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead className="bg-gray-100 sticky top-0">
                      <tr>
                        <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-20">别名</th>
                        <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">数据科目</th>
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
                              className="w-full border border-gray-300 rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                          </td>
                          <td className="border-b border-gray-200 px-2 py-2">
                            <div className="font-mono text-[11px] text-slate-500">{component.data_acct_code}</div>
                            <div className="text-gray-700">{component.data_acct_name ?? "-"}</div>
                          </td>
                          <td className="border-b border-gray-200 px-2 py-1">
                            <button
                              type="button"
                              onClick={() =>
                                setCalcMetricComponents((current) => current.filter((_, itemIndex) => itemIndex !== index))
                              }
                              className="px-2 py-1 border border-gray-300 rounded text-xs hover:bg-gray-50"
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
                <div className="border border-gray-200 rounded p-2 bg-slate-50">
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
                        className="rounded border border-gray-300 bg-white px-1.5 py-0.5 text-[11px] text-gray-600 hover:bg-blue-50"
                        title={metric.expression}
                      >
                        {metric.metric_name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="border-t border-gray-200 px-4 py-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowCalcMetricDialog(false)}
                className="px-3 py-1.5 border border-gray-300 rounded text-xs hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleSaveCalcMetric()}
                disabled={savingCalcMetric}
                className="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-white rounded text-xs hover:bg-emerald-700 disabled:opacity-60"
              >
                {savingCalcMetric ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                保存并插入
              </button>
            </div>
          </div>
        </div>
      )}

      {showMetricPicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-[920px] max-w-[calc(100vw-48px)] h-[620px] max-h-[calc(100vh-48px)] bg-white border border-gray-300 rounded shadow-xl flex flex-col">
            <div className="h-10 px-3 border-b border-gray-200 flex items-center justify-between">
              <div className="text-sm font-medium text-gray-800">
                {metricPickerMode === "calc" ? "选择计算指标的基础项" : "选择数据科目指标"}
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowMetricPicker(false);
                  if (metricPickerMode === "calc") setShowCalcMetricDialog(true);
                }}
                className="inline-flex items-center justify-center w-7 h-7 border border-gray-300 rounded hover:bg-gray-50"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="p-3 border-b border-gray-200">
              <input
                value={metricSearchText}
                onChange={(e) => setMetricSearchText(e.target.value)}
                placeholder="搜索指标、数据科目编码、名称或公式"
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
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
                <table className="w-full text-xs border-collapse">
                  <thead className="sticky top-0 bg-gray-100 z-10">
                    <tr>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">指标/绑定</th>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">数据科目</th>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700">公式口径</th>
                      <th className="border-b border-gray-300 px-2 py-2 text-left text-gray-700 w-20">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedMetricBindings.map((binding) => {
                      const account = dataAccountByCode.get(binding.data_acct_code);
                      const formula = account?.budget_formula || account?.actual_formula || "";
                      return (
                        <tr key={binding.binding_code} className="hover:bg-blue-50/50">
                          <td className="border-b border-gray-200 px-2 py-2">
                            <div className="font-mono text-[11px] text-slate-600">{binding.binding_code}</div>
                            <div className="text-gray-700">{binding.metric_node_name ?? "-"}</div>
                          </td>
                          <td className="border-b border-gray-200 px-2 py-2">
                            <div className="font-mono text-[11px] text-slate-600">{binding.data_acct_code}</div>
                            <div className="text-gray-700">{binding.data_acct_name ?? "-"}</div>
                          </td>
                          <td className="border-b border-gray-200 px-2 py-2 text-gray-600 max-w-[280px]">
                            <div className="line-clamp-2">{formula || "未配置公式，生成时按指标当前值口径处理"}</div>
                          </td>
                          <td className="border-b border-gray-200 px-2 py-2">
                            <button
                              type="button"
                              onClick={() => insertMetricBinding(binding)}
                              className="px-2 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700"
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
