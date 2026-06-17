import { useEffect, useMemo, useState } from "react";
import { BarChart3, Download, FileText, Loader2, RefreshCw, Search, Table2, Wand2 } from "lucide-react";

import {
  downloadSmartPptGeneratedFile,
  generateSmartPptFromReportTemplate,
  generateSmartPptScene,
  generateSmartPptTemplateDeck,
  listSmartPptInstances,
  listSmartPptReportTemplateVariables,
  listSmartPptReportTemplates,
  listSmartPptScenes,
  loadSmartPptTemplateStudio,
  previewSmartPptScene,
  saveSmartPptTemplateBindings,
  suggestSmartPptTemplateChartBlocks,
  type SmartPptReportTemplateGenerateResponseDto,
  type SmartPptReportTemplateDto,
  type SmartPptReportTemplateVariableDto,
  type SmartPptSceneDto,
  type SmartPptSceneDetailResponseDto,
  type SmartPptSlidePreviewDto,
  type SmartPptGenerateResponseDto,
  type SmartPptInstanceDto,
  type SmartPptChartConfigDto,
  type SmartPptTemplateBindingConfigDto,
  type SmartPptTemplateChartBlockDto,
  type SmartPptTemplateGenerateResponseDto,
  type SmartPptTemplateInspectResponseDto,
  type SmartPptTemplateObjectDto,
} from "@/lib/system/smartPptApi";
import { getOrgProductMetricSnapshot } from "@/lib/org-product/orgProductMetricApi";
import { deriveRuntimeRefFromOrgProductMetricCode } from "@/lib/org-product/orgProductMetricCode";

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

type SmartPptMetricCandidate = {
  candidate_key: string;
  metric_code: string;
  display_name: string;
  org_product_metric_ref: string;
  org_product_metric_name: string;
  org_product_data_acct_code: string;
};

function fmtTime(value?: string | null): string {
  if (!value) return "-";
  return value.replace("T", " ").replace("Z", "");
}

function orgProductMetricCodeFromRef(ref?: string | null): string {
  const parts = String(ref || "").split(":");
  return parts.length >= 3 ? parts[2] : "";
}

function paramKeyOf(variable: SmartPptReportTemplateVariableDto): string {
  const raw = variable.binding_config?.param_key;
  if (typeof raw === "string" && raw.trim()) return raw.trim();
  return variable.variable_key.includes(":") ? variable.variable_key.split(":").slice(1).join(":") : variable.variable_key;
}

function textKeyOf(variable: SmartPptReportTemplateVariableDto): string {
  const raw = variable.binding_config?.text_key;
  if (typeof raw === "string" && raw.trim()) return raw.trim();
  return variable.variable_key.includes(":") ? variable.variable_key.split(":").slice(1).join(":") : variable.variable_key;
}

const sceneParamFields = [
  { key: "year", label: "年度", placeholder: "2026" },
  { key: "quarter", label: "季度", placeholder: "Q1" },
  { key: "start_month", label: "开始月", placeholder: "1" },
  { key: "end_month", label: "结束月", placeholder: "3" },
  { key: "version_id", label: "预算版本", placeholder: "1" },
  { key: "actual_version_id", label: "实际版本", placeholder: "3" },
];

const defaultTemplateStudioFileName = "26年一季度全行经营简报_脱敏版.pptx";

const templateObjectLabels: Record<string, string> = {
  chart: "图表",
  table: "表格",
  text: "文本",
  picture: "图片",
  group: "组合",
  other: "其他",
};

const bindingTypeLabels: Record<string, string> = {
  ignore: "不绑定",
  text: "文本替换",
  chart: "图表数据",
  table: "表格数据",
  kpi: "指标卡",
};

export function AnalysisPPTContent() {
  const [templates, setTemplates] = useState<SmartPptReportTemplateDto[]>([]);
  const [variables, setVariables] = useState<SmartPptReportTemplateVariableDto[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [searchText, setSearchText] = useState("");
  const [paramValues, setParamValues] = useState<Record<string, string>>({
    year: "2026",
    start_month: "1",
    end_month: "12",
    version_id: "1",
    budget_actual: "0",
  });
  const [textValues, setTextValues] = useState<Record<string, string>>({});
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [loadingVariables, setLoadingVariables] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [lastGenerated, setLastGenerated] = useState<SmartPptReportTemplateGenerateResponseDto | null>(null);

  // ── 场景模式状态 ──
  const [activeTab, setActiveTab] = useState<"scene" | "template" | "studio">("scene");
  const [scenes, setScenes] = useState<SmartPptSceneDto[]>([]);
  const [selectedSceneId, setSelectedSceneId] = useState<number | null>(null);
  const [sceneDetail, setSceneDetail] = useState<SmartPptSceneDetailResponseDto | null>(null);
  const [loadingScenes, setLoadingScenes] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [generatingScene, setGeneratingScene] = useState(false);
  const [sceneInstance, setSceneInstance] = useState<SmartPptGenerateResponseDto | null>(null);
  const [sceneInstances, setSceneInstances] = useState<SmartPptInstanceDto[]>([]);
  const [templateReport, setTemplateReport] = useState<SmartPptTemplateInspectResponseDto | null>(null);
  const [templateBindings, setTemplateBindings] = useState<SmartPptTemplateBindingConfigDto[]>([]);
  const [chartBlocks, setChartBlocks] = useState<SmartPptTemplateChartBlockDto[]>([]);
  const [chartConfigs, setChartConfigs] = useState<SmartPptChartConfigDto[]>([]);
  const [orgProductMetricSnapshot, setOrgProductMetricSnapshot] = useState<OrgProductMetricSnapshotDto | null>(null);
  const [selectedTemplateObjectId, setSelectedTemplateObjectId] = useState<string | null>(null);
  const [templateGenerated, setTemplateGenerated] = useState<SmartPptTemplateGenerateResponseDto | null>(null);
  const [loadingTemplateReport, setLoadingTemplateReport] = useState(false);
  const [savingTemplateBindings, setSavingTemplateBindings] = useState(false);
  const [suggestingTemplateBindings, setSuggestingTemplateBindings] = useState(false);
  const [generatingTemplateDeck, setGeneratingTemplateDeck] = useState(false);
  const [sceneParams, setSceneParams] = useState<Record<string, string>>({
    year: "2026",
    quarter: "Q1",
    start_month: "1",
    end_month: "3",
    version_id: "1",
    actual_version_id: "3",
  });

  const pptTemplates = useMemo(
    () => templates.filter((item) => item.template_type === "ppt"),
    [templates],
  );

  const filteredTemplates = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return pptTemplates;
    return pptTemplates.filter(
      (item) =>
        item.template_code.toLowerCase().includes(q) ||
        item.template_name.toLowerCase().includes(q) ||
        (item.remark ?? "").toLowerCase().includes(q),
    );
  }, [pptTemplates, searchText]);

  const selectedTemplate = useMemo(
    () => pptTemplates.find((item) => item.template_id === selectedTemplateId) ?? null,
    [pptTemplates, selectedTemplateId],
  );
  const parameterVariables = useMemo(
    () => variables.filter((item) => item.variable_type === "parameter"),
    [variables],
  );
  const textVariableRows = useMemo(
    () => variables.filter((item) => item.variable_type === "text"),
    [variables],
  );
  const dataVariables = useMemo(
    () => variables.filter((item) => item.variable_type !== "parameter" && item.variable_type !== "text"),
    [variables],
  );
  const templateObjectRows = useMemo(
    () =>
      templateReport?.slides.flatMap((slide) =>
        slide.objects.map((object) => ({
          slideIndex: slide.slide_index,
          slideTitle: slide.title,
          object,
        })),
      ) ?? [],
    [templateReport],
  );
  const selectedTemplateObjectRow =
    templateObjectRows.find((item) => item.object.object_id === selectedTemplateObjectId) ?? null;
  const selectedTemplateBinding =
    templateBindings.find((item) => item.object_id === selectedTemplateObjectId) ?? null;

  const orgProductMetricCandidates = useMemo<SmartPptMetricCandidate[]>(() => {
    const candidates: SmartPptMetricCandidate[] = [];
    const seen = new Set<string>();
    for (const entity of orgProductMetricSnapshot?.entities ?? []) {
      const entityCode = String(entity.entity_code || "").trim().toUpperCase();
      for (const table of entity.tables ?? []) {
        const walk = (metrics: OrgProductMetricNodeDto[]) => {
          for (const metric of metrics) {
            const metricCode = String(metric.code || "").trim().toUpperCase();
            const dataAcctCode = deriveRuntimeRefFromOrgProductMetricCode(entityCode, metricCode);
            const metricNodeCode = dataAcctCode;
            if (metricCode && dataAcctCode && metricNodeCode) {
              const orgRef = `${entityCode}:${table.table_name}:${metricCode}`;
              const key = `${orgRef}:${metricNodeCode}:${dataAcctCode}`;
              if (!seen.has(key)) {
                seen.add(key);
                const name = String(metric.name || dataAcctCode);
                candidates.push({
                  candidate_key: key,
                  metric_code: metricNodeCode,
                  display_name: `${name} · ${metricCode}`,
                  org_product_metric_ref: orgRef,
                  org_product_metric_name: name,
                  org_product_data_acct_code: dataAcctCode,
                });
              }
            }
            if (metric.children?.length) walk(metric.children);
          }
        };
        walk(table.metrics ?? []);
      }
    }
    return candidates;
  }, [orgProductMetricSnapshot]);

  const loadTemplates = async () => {
    setLoadingTemplates(true);
    try {
      const pptRows = await listSmartPptReportTemplates();
      setTemplates(pptRows);
      setSelectedTemplateId((current) => {
        if (current && pptRows.some((item) => item.template_id === current)) return current;
        return pptRows[0]?.template_id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 PPT 模板失败");
    } finally {
      setLoadingTemplates(false);
    }
  };

  useEffect(() => {
    void loadTemplates();
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (getOrgProductMetricSnapshot() as Promise<OrgProductMetricSnapshotDto>)
      .then((snapshot) => {
        if (!cancelled) setOrgProductMetricSnapshot(snapshot);
      })
      .catch(() => {
        if (!cancelled) setOrgProductMetricSnapshot({ entities: [] });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedTemplateId) {
      setVariables([]);
      setLastGenerated(null);
      return;
    }
    let cancelled = false;
    setLoadingVariables(true);
    setError("");
    void listSmartPptReportTemplateVariables(selectedTemplateId)
      .then((rows) => {
        if (cancelled) return;
        setVariables(rows);
        setLastGenerated(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载模板变量失败");
      })
      .finally(() => {
        if (!cancelled) setLoadingVariables(false);
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
      for (const item of textVariableRows) {
        const key = textKeyOf(item);
        if (next[key] === undefined) next[key] = "";
      }
      return next;
    });
  }, [parameterVariables, textVariableRows]);

  const handleGenerate = async () => {
    if (!selectedTemplate) {
      setError("请选择 PPT 模板");
      return;
    }
    setGenerating(true);
    setError("");
    setMessage("");
    try {
      const result = await generateSmartPptFromReportTemplate({
        template_id: selectedTemplate.template_id,
        instance_name: `${selectedTemplate.template_name} ${new Date().toLocaleString()}`,
        parameters: paramValues,
        text_values: textValues,
      });
      setLastGenerated(result);
      setMessage(`PPT 已生成：${result.output_filename}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成 PPT 失败");
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async () => {
    if (!lastGenerated) return;
    await downloadSmartPptGeneratedFile(lastGenerated.download_url, lastGenerated.output_filename || "smart-ppt.pptx");
  };

  // ── 场景模式：加载场景列表 ──
  const loadScenes = async () => {
    setLoadingScenes(true);
    setError("");
    try {
      const rows = await listSmartPptScenes();
      setScenes(rows);
      if (rows.length === 0) {
        setSelectedSceneId(null);
        setSceneDetail(null);
        return;
      }
      const preferredSceneId = rows.some((item) => item.scene_id === selectedSceneId)
        ? selectedSceneId
        : rows[0].scene_id;
      setSelectedSceneId(preferredSceneId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载场景列表失败");
    } finally {
      setLoadingScenes(false);
    }
  };

  // ── 场景模式：选中场景后预览 ──
  const handleSelectScene = async (sceneId: number) => {
    setSelectedSceneId(sceneId);
    setSceneDetail(null);
    setSceneInstance(null);
    setLoadingPreview(true);
    setError("");
    try {
      const result = await previewSmartPptScene({
        scene_id: sceneId,
        params: sceneParams,
      });
      setSceneDetail(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载场景预览失败");
    } finally {
      setLoadingPreview(false);
    }
  };

  // ── 场景模式：生成 PPT ──
  const handleGenerateScene = async () => {
    if (!selectedSceneId) {
      setError("请选择一个场景");
      return;
    }
    setGeneratingScene(true);
    setError("");
    setMessage("");
    try {
      const result = await generateSmartPptScene({
        scene_id: selectedSceneId,
        params: sceneParams,
        instance_name: `${scenes.find((s) => s.scene_id === selectedSceneId)?.scene_name ?? "PPT"} ${new Date().toLocaleString()}`,
      });
      setSceneInstance(result);
      setMessage(`PPT 已生成：${result.output_filename}`);
      void loadInstances();
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成 PPT 失败");
    } finally {
      setGeneratingScene(false);
    }
  };

  // ── 场景模式：下载最近生成的 PPT ──
  const handleDownloadScene = async () => {
    if (!sceneInstance) return;
    await downloadSmartPptGeneratedFile(sceneInstance.download_url, sceneInstance.output_filename || "smart-ppt.pptx");
  };

  // ── 加载场景实例列表 ──
  const loadInstances = async () => {
    try {
      const rows = await listSmartPptInstances();
      setSceneInstances(rows);
    } catch {
      // 静默失败
    }
  };

  const handleInspectTemplate = async () => {
    setLoadingTemplateReport(true);
    setError("");
    setMessage("");
    try {
      const result = await loadSmartPptTemplateStudio(defaultTemplateStudioFileName);
      setTemplateReport(result.report);
      setTemplateBindings(result.bindings);
      setChartBlocks([]);
      setChartConfigs(result.chart_configs);
      setTemplateGenerated(null);
      const firstObject = result.report.slides.flatMap((slide) => slide.objects).find((object) => object.object_type !== "other");
      setSelectedTemplateObjectId(firstObject?.object_id ?? null);
      setMessage(`模板已解析：${result.report.template_file_name}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "解析 PPT 模板失败");
    } finally {
      setLoadingTemplateReport(false);
    }
  };

  const handleSuggestTemplateBindings = async () => {
    setSuggestingTemplateBindings(true);
    setError("");
    setMessage("");
    try {
      const result = await suggestSmartPptTemplateChartBlocks(defaultTemplateStudioFileName, 10);
      setChartBlocks(result.blocks);
      setTemplateBindings(result.blocks.map((block) => block.binding));
      setTemplateGenerated(null);
      setSelectedTemplateObjectId(result.blocks[0]?.chart_object_id ?? selectedTemplateObjectId);
      setMessage(`已生成图表区块草案：${result.blocks.length} 个`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成绑定草案失败");
    } finally {
      setSuggestingTemplateBindings(false);
    }
  };

  const buildDefaultBinding = (
    object: SmartPptTemplateObjectDto,
    slideIndex: number,
  ): SmartPptTemplateBindingConfigDto => ({
    object_id: object.object_id,
    slide_index: slideIndex,
    object_type: object.object_type,
    binding_type: object.object_type === "chart" || object.object_type === "table" || object.object_type === "text" ? object.object_type : "ignore",
    target_key: object.shape_name ?? object.object_id,
    data_source: "",
    chart_config_code: "",
    metric_code: "",
    org_product_metric_ref: "",
    org_product_metric_name: "",
    org_product_data_acct_code: "",
    prompt: "",
    enabled: true,
    notes: "",
  });

  const updateSelectedBinding = (patch: Partial<SmartPptTemplateBindingConfigDto>) => {
    if (!selectedTemplateObjectRow) return;
    const base = selectedTemplateBinding ?? buildDefaultBinding(selectedTemplateObjectRow.object, selectedTemplateObjectRow.slideIndex);
    const next = { ...base, ...patch };
    setTemplateBindings((current) => {
      const existingIndex = current.findIndex((item) => item.object_id === next.object_id);
      if (existingIndex < 0) return [...current, next];
      return current.map((item, index) => (index === existingIndex ? next : item));
    });
  };

  const handleSelectOrgProductMetricCandidate = (candidateKey: string) => {
    if (!candidateKey) {
      updateSelectedBinding({
        org_product_metric_ref: "",
        org_product_metric_name: "",
        org_product_data_acct_code: "",
      });
      return;
    }
    const candidate = orgProductMetricCandidates.find((item) => item.candidate_key === candidateKey);
    if (!candidate) return;
    updateSelectedBinding({
      metric_code: candidate.metric_code,
      org_product_metric_ref: candidate.org_product_metric_ref,
      org_product_metric_name: candidate.org_product_metric_name,
      org_product_data_acct_code: candidate.org_product_data_acct_code,
    });
  };

  const handleSaveTemplateBindings = async () => {
    if (!templateReport) return;
    setSavingTemplateBindings(true);
    setError("");
    setMessage("");
    try {
      const result = await saveSmartPptTemplateBindings(templateReport.template_file_name, templateBindings);
      setTemplateBindings(result.bindings);
      setMessage(`绑定配置已保存：${result.bindings.length} 项`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存绑定配置失败");
    } finally {
      setSavingTemplateBindings(false);
    }
  };

  const handleGenerateTemplateDeck = async () => {
    if (!templateReport) return;
    setGeneratingTemplateDeck(true);
    setError("");
    setMessage("");
    try {
      const result = await generateSmartPptTemplateDeck({
        template_file_name: templateReport.template_file_name,
        bindings: templateBindings,
        max_slides: 10,
        params: {
          year: "2026",
          quarter: "Q1",
          start_month: "1",
          end_month: "3",
          version_id: "1",
          actual_version_id: "3",
          report_title: "2026年一季度经营简报",
        },
      });
      setTemplateGenerated(result);
      setMessage(`模板 PPT 已生成：${result.output_filename}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成模板 PPT 失败");
    } finally {
      setGeneratingTemplateDeck(false);
    }
  };

  const handleDownloadTemplateDeck = async () => {
    if (!templateGenerated) return;
    await downloadSmartPptGeneratedFile(templateGenerated.download_url, templateGenerated.output_filename || "template-studio.pptx");
  };

  // 初始化加载场景列表
  useEffect(() => {
    void loadScenes();
    void loadInstances();
  }, []);

  useEffect(() => {
    if (!selectedSceneId || sceneDetail || loadingPreview || scenes.length === 0) return;
    void handleSelectScene(selectedSceneId);
  }, [selectedSceneId, sceneDetail, loadingPreview, scenes.length]);

  const renderSlidePreview = (slide: SmartPptSlidePreviewDto) => (
    <div key={slide.slide_index} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-blue-600">
            第 {slide.slide_index} 页 · {slide.slide_type}
          </div>
          <h4 className="mt-1 text-sm font-semibold text-gray-900">{slide.title}</h4>
          {slide.subtitle ? <div className="mt-1 text-xs text-gray-500">{slide.subtitle}</div> : null}
        </div>
        {slide.chart_type ? (
          <span className="rounded-full bg-blue-50 px-2 py-1 text-[11px] font-medium text-blue-700">
            {slide.chart_type}
          </span>
        ) : null}
      </div>

      {slide.narrative ? <div className="mt-3 text-xs leading-5 text-gray-600">{slide.narrative}</div> : null}

      {slide.metric_cards.length > 0 ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {slide.metric_cards.map((card, index) => (
            <div key={`${slide.slide_index}-metric-${index}`} className="rounded-lg bg-gray-50 px-3 py-2">
              {Object.entries(card).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-gray-500">{key}</span>
                  <span className="font-medium text-gray-800">{String(value)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : null}

      {slide.table_headers.length > 0 ? (
        <div className="mt-3 overflow-hidden rounded-lg border border-gray-200">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                {slide.table_headers.map((header) => (
                  <th key={header} className="px-3 py-2 font-medium">
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {slide.table_rows.slice(0, 4).map((row, rowIndex) => (
                <tr key={`${slide.slide_index}-row-${rowIndex}`} className="border-t border-gray-100">
                  {row.map((cell, cellIndex) => (
                    <td key={`${slide.slide_index}-cell-${rowIndex}-${cellIndex}`} className="px-3 py-2 text-gray-600">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );

  const renderTemplateStudio = () => {
    const bindableObjects = templateObjectRows.filter((item) => item.object.object_type !== "other");
    const effectiveBinding =
      selectedTemplateObjectRow && selectedTemplateObjectRow.object.object_type !== "other"
        ? selectedTemplateBinding ?? buildDefaultBinding(selectedTemplateObjectRow.object, selectedTemplateObjectRow.slideIndex)
        : null;
    const summaryItems = templateReport
      ? [
          { label: "页数", value: templateReport.slide_count, icon: FileText },
          { label: "图表", value: templateReport.chart_count, icon: BarChart3 },
          { label: "表格", value: templateReport.table_count, icon: Table2 },
          { label: "已配置", value: templateBindings.length, icon: FileText },
        ]
      : [];

    return (
      <div className="min-h-0 flex-1 overflow-auto rounded border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-medium text-gray-800">模板绑定配置工作台</h4>
            <div className="mt-1 text-xs text-gray-500">先解析经营简报模板的页面、图表、表格和文本对象，再进入字段绑定。</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleInspectTemplate()}
              disabled={loadingTemplateReport}
              className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:text-gray-400"
            >
              {loadingTemplateReport ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              解析经营简报模板
            </button>
            <button
              type="button"
              onClick={() => void handleSuggestTemplateBindings()}
              disabled={!templateReport || suggestingTemplateBindings}
              className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:text-gray-400"
            >
              {suggestingTemplateBindings ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
              生成草案
            </button>
            <button
              type="button"
              onClick={() => void handleSaveTemplateBindings()}
              disabled={!templateReport || savingTemplateBindings}
              className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
            >
              {savingTemplateBindings ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
              保存绑定
            </button>
            <button
              type="button"
              onClick={() => void handleGenerateTemplateDeck()}
              disabled={!templateReport || generatingTemplateDeck}
              className="inline-flex items-center gap-1 rounded bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
            >
              {generatingTemplateDeck ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
              生成模板 PPT
            </button>
            <button
              type="button"
              onClick={() => void handleDownloadTemplateDeck()}
              disabled={!templateGenerated}
              className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:text-gray-400"
            >
              <Download className="h-3.5 w-3.5" />
              下载
            </button>
          </div>
        </div>

        {!templateReport ? (
          <div className="mt-4 rounded border border-dashed border-gray-300 bg-white px-4 py-8 text-center text-xs text-gray-500">
            目标模板：{defaultTemplateStudioFileName}
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            <div className="rounded border border-gray-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-gray-900">{templateReport.template_file_name}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    画布 {templateReport.slide_width} × {templateReport.slide_height} EMU
                  </div>
                </div>
                <div className="grid min-w-[360px] flex-1 grid-cols-2 gap-2 lg:grid-cols-4">
                  {summaryItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <div key={item.label} className="rounded bg-gray-50 px-3 py-2">
                        <div className="flex items-center gap-1 text-[11px] text-gray-500">
                          <Icon className="h-3.5 w-3.5" />
                          {item.label}
                        </div>
                        <div className="mt-1 text-lg font-semibold text-gray-900">{item.value}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="rounded border border-gray-200 bg-white">
              <div className="border-b border-gray-200 px-4 py-3 text-sm font-medium text-gray-800">页面结构</div>
              <div className="overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">页码</th>
                      <th className="px-3 py-2 font-medium">标题识别</th>
                      <th className="px-3 py-2 font-medium">图表</th>
                      <th className="px-3 py-2 font-medium">表格</th>
                      <th className="px-3 py-2 font-medium">文本</th>
                      <th className="px-3 py-2 font-medium">对象</th>
                    </tr>
                  </thead>
                  <tbody>
                    {templateReport.slides.map((slide) => (
                      <tr key={slide.slide_index} className="border-t border-gray-100 align-top">
                        <td className="px-3 py-2 font-mono text-gray-700">#{slide.slide_index}</td>
                        <td className="max-w-[360px] px-3 py-2 text-gray-700">{slide.title || "-"}</td>
                        <td className="px-3 py-2 text-gray-600">{slide.chart_count}</td>
                        <td className="px-3 py-2 text-gray-600">{slide.table_count}</td>
                        <td className="px-3 py-2 text-gray-600">{slide.text_count}</td>
                        <td className="px-3 py-2 text-gray-500">
                          {slide.objects.slice(0, 5).map((item) => templateObjectLabels[item.object_type] ?? item.object_type).join(" / ")}
                          {slide.objects.length > 5 ? " ..." : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {chartBlocks.length > 0 ? (
              <div className="rounded border border-gray-200 bg-white">
                <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
                  <div className="text-sm font-medium text-gray-800">图表语义区块</div>
                  <div className="text-xs text-gray-500">{chartBlocks.length} 个区块</div>
                </div>
                <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
                  {chartBlocks.map((block) => {
                    const active = block.chart_object_id === selectedTemplateObjectId;
                    return (
                      <button
                        key={block.block_id}
                        type="button"
                        onClick={() => setSelectedTemplateObjectId(block.chart_object_id)}
                        className={`rounded border p-3 text-left text-xs transition hover:shadow-sm ${
                          active ? "border-blue-500 bg-blue-50" : "border-gray-200 bg-white"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-gray-900">{block.block_name}</div>
                            <div className="mt-1 text-[11px] text-gray-500">
                              第 {block.slide_index} 页 · {block.section || "未命名章节"}
                            </div>
                          </div>
                          <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600">
                            {block.default_chart_config_code || "未绑定"}
                          </span>
                        </div>
                        <div className="mt-2 font-mono text-[11px] text-gray-400">{block.chart_object_id}</div>
                        {block.nearby_title ? (
                          <div className="mt-1 truncate text-[11px] text-gray-500">邻近标题：{block.nearby_title}</div>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}

            <div className="grid gap-4 xl:grid-cols-[minmax(420px,1fr)_380px]">
              <div className="rounded border border-gray-200 bg-white">
                <div className="border-b border-gray-200 px-4 py-3 text-sm font-medium text-gray-800">可绑定对象</div>
                <div className="max-h-[420px] overflow-auto">
                  {bindableObjects.map((item) => {
                    const object = item.object;
                    const active = object.object_id === selectedTemplateObjectId;
                    const configured = templateBindings.some((binding) => binding.object_id === object.object_id);
                    return (
                      <button
                        key={object.object_id}
                        type="button"
                        onClick={() => setSelectedTemplateObjectId(object.object_id)}
                        className={`flex w-full items-start justify-between gap-3 border-b border-gray-100 px-4 py-3 text-left text-xs hover:bg-gray-50 ${
                          active ? "bg-blue-50" : "bg-white"
                        }`}
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[11px] text-gray-500">#{item.slideIndex}</span>
                            <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600">
                              {templateObjectLabels[object.object_type] ?? object.object_type}
                            </span>
                            {configured ? <span className="text-[11px] text-blue-600">已配置</span> : null}
                          </div>
                          <div className="mt-1 truncate font-medium text-gray-800">
                            {object.text_excerpt || object.shape_name || object.object_id}
                          </div>
                          <div className="mt-1 font-mono text-[11px] text-gray-400">{object.object_id}</div>
                        </div>
                        <div className="shrink-0 text-right text-[11px] text-gray-400">
                          {object.row_count && object.column_count ? `${object.row_count}×${object.column_count}` : object.chart_type || ""}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="rounded border border-gray-200 bg-white">
                <div className="border-b border-gray-200 px-4 py-3 text-sm font-medium text-gray-800">绑定配置</div>
                {!selectedTemplateObjectRow || !effectiveBinding ? (
                  <div className="px-4 py-8 text-center text-xs text-gray-500">请选择一个图表、表格或文本对象。</div>
                ) : (
                  <div className="space-y-3 p-4 text-xs">
                    <div>
                      <div className="font-medium text-gray-800">{selectedTemplateObjectRow.object.text_excerpt || selectedTemplateObjectRow.object.shape_name}</div>
                      <div className="mt-1 font-mono text-[11px] text-gray-400">{selectedTemplateObjectRow.object.object_id}</div>
                    </div>

                    <label className="block space-y-1">
                      <span className="font-medium text-gray-700">绑定类型</span>
                      <select
                        value={effectiveBinding.binding_type}
                        onChange={(event) => updateSelectedBinding({ binding_type: event.target.value })}
                        className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        {Object.entries(bindingTypeLabels).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="block space-y-1">
                      <span className="font-medium text-gray-700">目标字段</span>
                      <input
                        value={effectiveBinding.target_key ?? ""}
                        onChange={(event) => updateSelectedBinding({ target_key: event.target.value })}
                        placeholder="例如 customer_growth_chart"
                        className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </label>

                    <label className="block space-y-1">
                      <span className="font-medium text-gray-700">数据来源</span>
                      <input
                        value={effectiveBinding.data_source ?? ""}
                        onChange={(event) => updateSelectedBinding({ data_source: event.target.value })}
                        placeholder="例如 budget_fact / metric_binding"
                        className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </label>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block space-y-1">
                        <span className="font-medium text-gray-700">图表规则</span>
                        <select
                          value={effectiveBinding.chart_config_code ?? ""}
                          onChange={(event) => updateSelectedBinding({ chart_config_code: event.target.value })}
                          className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        >
                          <option value="">不替换图表数据</option>
                          {chartConfigs.map((item) => (
                            <option key={item.config_code} value={item.config_code}>
                              {item.config_code} · {item.chart_type}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="space-y-1">
                        <span className="font-medium text-gray-700">指标编码</span>
                        <select
                          value={
                            orgProductMetricCandidates.find(
                              (item) => item.org_product_metric_ref === effectiveBinding.org_product_metric_ref,
                            )?.candidate_key ?? ""
                          }
                          onChange={(event) => handleSelectOrgProductMetricCandidate(event.target.value)}
                          className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        >
                          <option value="">手动填写或使用原编码</option>
                          {orgProductMetricCandidates.map((item) => (
                            <option key={item.candidate_key} value={item.candidate_key}>
                              {item.display_name}
                            </option>
                          ))}
                        </select>
                        <input
                          value={effectiveBinding.metric_code ?? ""}
                          onChange={(event) =>
                            updateSelectedBinding({
                              metric_code: event.target.value,
                              org_product_metric_ref: "",
                              org_product_metric_name: "",
                              org_product_data_acct_code: "",
                            })
                          }
                          placeholder="metric_code"
                          className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                        {effectiveBinding.org_product_metric_ref ? (
                          <div className="rounded border border-blue-100 bg-blue-50 px-2 py-1 text-[11px] text-blue-700">
                            <div>{effectiveBinding.org_product_metric_name || "机构产品指标"}</div>
                            <div className="font-mono text-blue-500">
                              {orgProductMetricCodeFromRef(effectiveBinding.org_product_metric_ref) || effectiveBinding.org_product_metric_ref}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>

                    <label className="block space-y-1">
                      <span className="font-medium text-gray-700">生成提示</span>
                      <textarea
                        value={effectiveBinding.prompt ?? ""}
                        onChange={(event) => updateSelectedBinding({ prompt: event.target.value })}
                        rows={3}
                        placeholder="描述这个对象应该表达的业务含义"
                        className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </label>

                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={effectiveBinding.enabled}
                        onChange={(event) => updateSelectedBinding({ enabled: event.target.checked })}
                        className="h-3.5 w-3.5 rounded border-gray-300"
                      />
                      <span className="text-gray-700">启用此绑定</span>
                    </label>
                  </div>
                )}
              </div>
            </div>

            {templateReport.warnings.length > 0 ? (
              <div className="rounded border border-amber-200 bg-amber-50 px-3 py-3 text-xs text-amber-800">
                {templateReport.warnings.slice(0, 5).map((warning) => (
                  <div key={warning}>{warning}</div>
                ))}
              </div>
            ) : null}

            {templateGenerated ? (
              <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-3 text-xs text-emerald-900">
                <div className="font-medium">最近一次模板生成</div>
                <div className="mt-1">文件：{templateGenerated.output_filename}</div>
                <div className="mt-1">页数：{templateGenerated.slide_count || 10} 页</div>
                <div className="mt-1">应用绑定：{templateGenerated.applied_count} 项</div>
                {templateGenerated.warnings.length > 0 ? (
                  <div className="mt-2 space-y-1 text-amber-700">
                    {templateGenerated.warnings.slice(0, 5).map((warning) => (
                      <div key={warning}>{warning}</div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="bb-page">
      <div className="bb-page-header">
        <div>
          <h3 className="bb-page-title">智能演示PPT</h3>
          <div className="bb-page-subtitle mt-1">支持场景驱动生成与模板驱动生成两种模式。</div>
        </div>
        <div className="bb-tabs">
          <button
            type="button"
            onClick={() => setActiveTab("scene")}
            className={`bb-tab ${
              activeTab === "scene" ? "bb-tab-active" : ""
            }`}
          >
            Scene
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("studio")}
            className={`bb-tab ${
              activeTab === "studio" ? "bb-tab-active" : ""
            }`}
          >
            Studio
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("template")}
            className={`bb-tab ${
              activeTab === "template" ? "bb-tab-active" : ""
            }`}
          >
            Template
          </button>
        </div>
      </div>

      {error ? <div className="bb-status-banner bb-status-banner-danger">{error}</div> : null}
      {message ? <div className="bb-status-banner bb-status-banner-success">{message}</div> : null}

      {activeTab === "studio" ? (
        renderTemplateStudio()
      ) : activeTab === "scene" ? (
        <div className="bb-panel min-h-0 flex-1 overflow-auto p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h4 className="bb-page-title">场景选择</h4>
              <div className="bb-page-subtitle mt-1">选择业务场景后自动加载幻灯片预览，再直接生成 PPT。</div>
            </div>
            <button
              type="button"
              onClick={() => void loadScenes()}
              className="bb-btn bb-btn-secondary"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingScenes ? "animate-spin" : ""}`} />
              刷新场景
            </button>
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {loadingScenes ? (
              <div className="bb-card col-span-full flex items-center gap-2 px-4 py-6 text-xs text-[var(--bb-text-muted)]">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                正在加载场景
              </div>
            ) : scenes.length === 0 ? (
              <div className="bb-empty-state col-span-full border border-dashed border-[var(--bb-border)]">
                当前没有可用场景
              </div>
            ) : (
              scenes.map((scene) => {
                const active = scene.scene_id === selectedSceneId;
                return (
                  <button
                    key={scene.scene_id}
                    type="button"
                    onClick={() => void handleSelectScene(scene.scene_id)}
                    className={`bb-card text-left transition hover:border-[var(--bb-primary)] ${
                      active ? "border-[var(--bb-primary)] bg-[var(--bb-primary-soft)]" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-gray-900">{scene.scene_name}</div>
                        <div className="mt-1 font-mono text-[11px] text-gray-500">{scene.scene_code}</div>
                      </div>
                      <span className="bb-grid-chip text-[11px] font-medium">
                        {scene.scene_type}
                      </span>
                    </div>
                    <div className="mt-3 text-xs leading-5 text-gray-600">{scene.description || "暂无场景说明"}</div>
                  </button>
                );
              })
            )}
          </div>

          <div className="bb-panel mt-6 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h4 className="bb-panel-title">生成参数</h4>
                <div className="bb-page-subtitle mt-1">调整参数后刷新预览，生成时会使用同一组参数。</div>
              </div>
              <button
                type="button"
                onClick={() => selectedSceneId && void handleSelectScene(selectedSceneId)}
                disabled={!selectedSceneId || loadingPreview}
                className="bb-btn bb-btn-secondary"
              >
                {loadingPreview ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                刷新预览
              </button>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {sceneParamFields.map((field) => (
                <label key={field.key} className="block space-y-1">
                  <div className="text-xs font-medium text-gray-700">{field.label}</div>
                  <input
                    value={sceneParams[field.key] ?? ""}
                    onChange={(event) =>
                      setSceneParams((current) => ({ ...current, [field.key]: event.target.value }))
                    }
                    placeholder={field.placeholder}
                    className="bb-input w-full"
                  />
                </label>
              ))}
            </div>
          </div>

          <div className="bb-panel mt-6">
            <div className="bb-panel-header items-start">
              <div>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-[var(--bb-primary)]" />
                  <h4 className="bb-panel-title">
                    {sceneDetail?.scene.scene_name ?? "场景预览"}
                  </h4>
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  {sceneDetail?.scene.description ?? "选择场景后查看 slide_previews 预览。"}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleGenerateScene()}
                  disabled={!selectedSceneId || generatingScene || loadingPreview}
                  className="bb-btn bb-btn-primary"
                >
                  {generatingScene ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Wand2 className="h-3.5 w-3.5" />
                  )}
                  生成 PPT
                </button>
                <button
                  type="button"
                  onClick={() => void handleDownloadScene()}
                  disabled={!sceneInstance}
                  className="bb-btn bb-btn-secondary"
                >
                  <Download className="h-3.5 w-3.5" />
                  下载
                </button>
              </div>
            </div>

            <div className="p-4">
              {loadingPreview ? (
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  正在加载场景预览
                </div>
              ) : !sceneDetail ? (
                <div className="text-xs text-gray-500">请选择一个场景查看预览。</div>
              ) : sceneDetail.slide_previews.length === 0 ? (
                <div className="text-xs text-gray-500">当前场景暂无预览页。</div>
              ) : (
                <div className="grid gap-4 lg:grid-cols-2">
                  {sceneDetail.slide_previews.map((slide) => renderSlidePreview(slide))}
                </div>
              )}
            </div>

            {sceneInstance ? (
              <div className="bb-status-banner border-x-0 border-b-0 border-[var(--bb-border-soft)] bg-[var(--bb-primary-soft)] px-4 py-3 text-xs text-[var(--bb-primary)]">
                <div className="font-medium">最近一次生成</div>
                <div className="mt-1">文件：{sceneInstance.output_filename}</div>
                <div className="mt-1">时间：{fmtTime(sceneInstance.generated_at)}</div>
                {sceneInstance.warnings.length > 0 ? (
                  <div className="mt-2 space-y-1 text-amber-700">
                    {sceneInstance.warnings.map((warning) => (
                      <div key={warning}>{warning}</div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="bb-panel mt-6">
            <div className="bb-panel-header"><div className="bb-panel-title">生成记录</div></div>
            {sceneInstances.length === 0 ? (
              <div className="px-4 py-6 text-xs text-gray-500">暂无智能 PPT 生成记录。</div>
            ) : (
              <div className="overflow-auto">
                <table className="bb-table bb-table-dense w-full text-left">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-3 py-2 font-medium">实例</th>
                      <th className="px-3 py-2 font-medium">场景</th>
                      <th className="px-3 py-2 font-medium">状态</th>
                      <th className="px-3 py-2 font-medium">生成时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sceneInstances.slice(0, 8).map((item) => (
                      <tr key={item.instance_id} className="border-t border-gray-100">
                        <td className="px-3 py-2 text-gray-700">{item.instance_name}</td>
                        <td className="px-3 py-2 text-gray-600">{item.scene_name ?? `#${item.scene_id}`}</td>
                        <td className="px-3 py-2 text-gray-600">{item.generation_status}</td>
                        <td className="px-3 py-2 text-gray-500">{fmtTime(item.last_generated_at ?? item.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(360px,42%)_1fr] gap-4">
          <div className="bb-panel min-h-0 overflow-hidden">
            <div className="bb-panel-header">
              <div className="bb-panel-title">PPT 模板列表</div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="搜索模板编码或名称"
                    value={searchText}
                    onChange={(event) => setSearchText(event.target.value)}
                    className="bb-input w-64 pl-8"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => void loadTemplates()}
                  className="bb-btn bb-btn-secondary"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loadingTemplates ? "animate-spin" : ""}`} />
                  刷新
                </button>
              </div>
            </div>
            <div className="h-full overflow-auto">
                <table className="bb-table bb-table-dense w-full">
                <thead className="sticky top-0 bg-gray-100">
                  <tr>
                    <th className="border-b border-gray-200 px-3 py-2 text-left text-gray-700">模板编码</th>
                    <th className="border-b border-gray-200 px-3 py-2 text-left text-gray-700">模板名称</th>
                    <th className="border-b border-gray-200 px-3 py-2 text-left text-gray-700">占位符</th>
                    <th className="border-b border-gray-200 px-3 py-2 text-left text-gray-700">版本</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTemplates.map((item) => {
                    const active = item.template_id === selectedTemplateId;
                    return (
                      <tr
                        key={item.template_id}
                        className={active ? "bg-blue-50" : "hover:bg-gray-50"}
                        onClick={() => setSelectedTemplateId(item.template_id)}
                      >
                        <td className="border-b border-gray-100 px-3 py-2 font-mono text-gray-700">{item.template_code}</td>
                        <td className="border-b border-gray-100 px-3 py-2 text-gray-700">
                          <div className="font-medium">{item.template_name}</div>
                          <div className="text-[11px] text-gray-500">{item.remark || "无备注"}</div>
                        </td>
                        <td className="border-b border-gray-100 px-3 py-2 text-gray-700">{item.variable_count}</td>
                        <td className="border-b border-gray-100 px-3 py-2 text-gray-500">v{item.version_no}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {!loadingTemplates && filteredTemplates.length === 0 ? (
                <div className="px-4 py-8 text-center text-xs text-gray-500">当前没有可用的 PPT 模板</div>
              ) : null}
            </div>
          </div>

          <div className="bb-panel min-h-0 overflow-auto">
            {!selectedTemplate ? (
              <div className="flex h-full items-center justify-center text-sm text-gray-500">请选择一个 PPT 模板</div>
            ) : (
              <div className="p-4 space-y-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-[var(--bb-primary)]" />
                      <h4 className="bb-panel-title">{selectedTemplate.template_name}</h4>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      编码 {selectedTemplate.template_code} · 更新时间 {fmtTime(selectedTemplate.updated_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void handleGenerate()}
                      disabled={generating || loadingVariables}
                      className="bb-btn bb-btn-primary"
                    >
                      {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                      生成 PPT
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDownload()}
                      disabled={!lastGenerated}
                      className="bb-btn bb-btn-secondary"
                    >
                      <Download className="h-3.5 w-3.5" />
                      下载
                    </button>
                  </div>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="bb-panel">
                    <div className="bb-panel-header"><div className="bb-panel-title">参数变量</div></div>
                    <div className="space-y-3 p-3">
                      {loadingVariables ? (
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          正在加载模板变量
                        </div>
                      ) : parameterVariables.length === 0 ? (
                        <div className="text-xs text-gray-500">当前模板没有参数变量，可直接生成。</div>
                      ) : (
                        parameterVariables.map((item) => {
                          const key = paramKeyOf(item);
                          return (
                            <label key={item.variable_id} className="block space-y-1">
                              <div className="text-xs font-medium text-gray-700">{item.variable_name}</div>
                              <input
                                value={paramValues[key] ?? ""}
                                onChange={(event) =>
                                  setParamValues((current) => ({ ...current, [key]: event.target.value }))
                                }
                                placeholder={key}
                                className="bb-input w-full"
                              />
                              <div className="text-[11px] text-gray-500">{item.variable_key}</div>
                            </label>
                          );
                        })
                      )}
                    </div>
                  </div>

                  <div className="bb-panel">
                    <div className="bb-panel-header"><div className="bb-panel-title">文本变量</div></div>
                    <div className="space-y-3 p-3">
                      {loadingVariables ? (
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          正在加载模板变量
                        </div>
                      ) : textVariableRows.length === 0 ? (
                        <div className="text-xs text-gray-500">当前模板没有文本变量。</div>
                      ) : (
                        textVariableRows.map((item) => {
                          const key = textKeyOf(item);
                          return (
                            <label key={item.variable_id} className="block space-y-1">
                              <div className="text-xs font-medium text-gray-700">{item.variable_name}</div>
                              <textarea
                                value={textValues[key] ?? ""}
                                onChange={(event) =>
                                  setTextValues((current) => ({ ...current, [key]: event.target.value }))
                                }
                                placeholder={key}
                                rows={3}
                                className="bb-textarea w-full"
                              />
                              <div className="text-[11px] text-gray-500">{item.variable_key}</div>
                            </label>
                          );
                        })
                      )}
                    </div>
                  </div>
                </div>

                <div className="bb-panel">
                  <div className="bb-panel-header"><div className="bb-panel-title">模板概览</div></div>
                  <div className="grid gap-3 p-3 text-xs text-gray-600 md:grid-cols-3">
                    <div className="rounded bg-gray-50 px-3 py-2">
                      <div className="text-[11px] text-gray-500">参数变量</div>
                      <div className="mt-1 text-sm font-medium text-gray-800">{parameterVariables.length}</div>
                    </div>
                    <div className="rounded bg-gray-50 px-3 py-2">
                      <div className="text-[11px] text-gray-500">文本变量</div>
                      <div className="mt-1 text-sm font-medium text-gray-800">{textVariableRows.length}</div>
                    </div>
                    <div className="rounded bg-gray-50 px-3 py-2">
                      <div className="text-[11px] text-gray-500">数据占位符</div>
                      <div className="mt-1 text-sm font-medium text-gray-800">{dataVariables.length}</div>
                    </div>
                  </div>
                </div>

                {lastGenerated ? (
                  <div className="bb-status-banner bg-[var(--bb-primary-soft)] text-[var(--bb-primary)]">
                    <div className="font-medium">最近一次生成</div>
                    <div className="mt-1">文件：{lastGenerated.output_filename}</div>
                    <div className="mt-1">时间：{fmtTime(lastGenerated.generated_at)}</div>
                    {lastGenerated.warnings.length > 0 ? (
                      <div className="mt-2 space-y-1 text-amber-700">
                        {lastGenerated.warnings.map((warning) => (
                          <div key={warning}>{warning}</div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
