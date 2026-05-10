import { useEffect, useMemo, useState } from "react";
import { Download, FileText, Loader2, RefreshCw, Search, Wand2 } from "lucide-react";

import {
  apiGet,
  apiPost,
  downloadFile,
  type SmartReportGenerateResponseDto,
  type SmartReportTemplateDto,
  type SmartReportTemplateVariableDto,
} from "@/lib/api";

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

export function AnalysisPPTContent() {
  const [templates, setTemplates] = useState<SmartReportTemplateDto[]>([]);
  const [variables, setVariables] = useState<SmartReportTemplateVariableDto[]>([]);
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
  const [lastGenerated, setLastGenerated] = useState<SmartReportGenerateResponseDto | null>(null);

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

  const selectedTemplate = pptTemplates.find((item) => item.template_id === selectedTemplateId) ?? null;
  const parameterVariables = variables.filter((item) => item.variable_type === "parameter");
  const textVariableRows = variables.filter((item) => item.variable_type === "text");
  const dataVariables = variables.filter((item) => item.variable_type !== "parameter" && item.variable_type !== "text");

  const loadTemplates = async () => {
    setLoadingTemplates(true);
    try {
      const rows = await apiGet<SmartReportTemplateDto[]>("/api/smart-reports/templates");
      setTemplates(rows);
      const pptRows = rows.filter((item) => item.template_type === "ppt");
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
    if (!selectedTemplateId) {
      setVariables([]);
      setLastGenerated(null);
      return;
    }
    let cancelled = false;
    setLoadingVariables(true);
    setError("");
    void apiGet<SmartReportTemplateVariableDto[]>(`/api/smart-reports/templates/${selectedTemplateId}/variables`)
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
      const result = await apiPost<SmartReportGenerateResponseDto>("/api/smart-reports/generate", {
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
    await downloadFile(lastGenerated.download_url, lastGenerated.output_filename || "smart-report.pptx");
  };

  return (
    <div className="h-full flex flex-col p-4 gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-gray-800">智能演示PPT</h3>
          <div className="text-xs text-gray-500 mt-1">复用智能报告模板与变量配置，模板类型为 `ppt`。</div>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索模板编码或名称"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              className="pl-8 pr-3 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 w-64"
            />
          </div>
          <button
            type="button"
            onClick={() => void loadTemplates()}
            className="inline-flex items-center gap-1 rounded border border-gray-300 px-2.5 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingTemplates ? "animate-spin" : ""}`} />
            刷新
          </button>
        </div>
      </div>

      {error ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}
      {message ? <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{message}</div> : null}

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(360px,42%)_1fr] gap-4">
        <div className="min-h-0 overflow-hidden rounded border border-gray-300 bg-white">
          <div className="border-b border-gray-200 px-3 py-2 text-xs font-medium text-gray-700">
            PPT 模板列表
          </div>
          <div className="h-full overflow-auto">
            <table className="w-full text-xs border-collapse">
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

        <div className="min-h-0 overflow-auto rounded border border-gray-300 bg-white">
          {!selectedTemplate ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-500">请选择一个 PPT 模板</div>
          ) : (
            <div className="p-4 space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-blue-600" />
                    <h4 className="text-sm font-medium text-gray-800">{selectedTemplate.template_name}</h4>
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
                    className="inline-flex items-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
                  >
                    {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
                    生成 PPT
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDownload()}
                    disabled={!lastGenerated}
                    className="inline-flex items-center gap-1 rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:text-gray-400"
                  >
                    <Download className="h-3.5 w-3.5" />
                    下载
                  </button>
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded border border-gray-200">
                  <div className="border-b border-gray-200 px-3 py-2 text-xs font-medium text-gray-700">参数变量</div>
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
                              className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                            <div className="text-[11px] text-gray-500">{item.variable_key}</div>
                          </label>
                        );
                      })
                    )}
                  </div>
                </div>

                <div className="rounded border border-gray-200">
                  <div className="border-b border-gray-200 px-3 py-2 text-xs font-medium text-gray-700">文本变量</div>
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
                              className="w-full rounded border border-gray-300 px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                            <div className="text-[11px] text-gray-500">{item.variable_key}</div>
                          </label>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>

              <div className="rounded border border-gray-200">
                <div className="border-b border-gray-200 px-3 py-2 text-xs font-medium text-gray-700">模板概览</div>
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
                <div className="rounded border border-blue-200 bg-blue-50 px-3 py-3 text-xs text-blue-900">
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
    </div>
  );
}
