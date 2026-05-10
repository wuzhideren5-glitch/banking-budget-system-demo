import { useEffect, useMemo, useState } from "react";
import {
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  type AssumptionImpactResponseDto,
  type AssumptionParameterDto,
  type AssumptionRuleTemplateDto,
  type AssumptionValueDto,
  type AssumptionValueUpsertItemDto,
  type SessionInfo,
  type VersionSnapshotResponseDto,
} from "@/lib/api";

const MONTH_OPTIONS = [
  { key: 0, label: "年值" },
  { key: 1, label: "1月" },
  { key: 2, label: "2月" },
  { key: 3, label: "3月" },
  { key: 4, label: "4月" },
  { key: 5, label: "5月" },
  { key: 6, label: "6月" },
  { key: 7, label: "7月" },
  { key: 8, label: "8月" },
  { key: 9, label: "9月" },
  { key: 10, label: "10月" },
  { key: 11, label: "11月" },
  { key: 12, label: "12月" },
];

export function BudgetAssumptionContent() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [parameters, setParameters] = useState<AssumptionParameterDto[]>([]);
  const [templates, setTemplates] = useState<AssumptionRuleTemplateDto[]>([]);
  const [selectedCode, setSelectedCode] = useState("");
  const [selectedYear, setSelectedYear] = useState<number>(new Date().getFullYear());
  const [productScopeKey, setProductScopeKey] = useState("");
  const [forecastStartMonth, setForecastStartMonth] = useState(1);
  const [fillValue, setFillValue] = useState("");
  const [valueMap, setValueMap] = useState<Record<number, string>>({});
  const [impact, setImpact] = useState<AssumptionImpactResponseDto | null>(null);
  const [editingTemplate, setEditingTemplate] = useState<AssumptionRuleTemplateDto | null>(null);
  const [templateConfig, setTemplateConfig] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createDraft, setCreateDraft] = useState({
    parameter_code: "",
    parameter_name: "",
    category: "产品利率",
    value_type: "百分比",
    scope_type: "product",
    time_granularity: "monthly",
    apply_products: "按产品",
    input_mode: "manual",
    value_formula: "",
    source_data_code: "",
    default_unit: "%",
    remark: "",
  });

  const selectedParameter = useMemo(
    () => parameters.find((item) => item.parameter_code === selectedCode) ?? null,
    [parameters, selectedCode],
  );

  const inputModeLabel = (mode: string) => {
    switch (mode) {
      case "source_prev_actual":
        return "按上月实际";
      case "source_ytd_avg_actual":
        return "按截至上月累计平均";
      case "formula":
        return "公式";
      default:
        return "手工";
    }
  };

  const loadValues = async (parameterCode: string, budgetYear: number, versionId: number, scopeKey: string) => {
    const rows = await apiGet<AssumptionValueDto[]>(
      `/api/budget-assumptions/values?budget_year=${encodeURIComponent(String(budgetYear))}&version_id=${encodeURIComponent(String(versionId))}&parameter_code=${encodeURIComponent(parameterCode)}&scenario_code=BASE`,
    );
    const nextMap: Record<number, string> = {};
    rows
      .filter((row) => (row.product_scope_key || "") === scopeKey)
      .forEach((row) => {
        nextMap[row.month_index] = String(row.value ?? "");
      });
    setValueMap(nextMap);
  };

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [currentSession, versionSnapshot, parameterRows, templateRows] = await Promise.all([
        apiGet<SessionInfo>("/api/session"),
        apiGet<VersionSnapshotResponseDto>("/api/version-snapshot"),
        apiGet<AssumptionParameterDto[]>("/api/budget-assumptions/parameters"),
        apiGet<AssumptionRuleTemplateDto[]>("/api/budget-assumptions/rule-templates"),
      ]);
      setSession(currentSession);
      setSelectedYear(currentSession.budget_year);
      setParameters(parameterRows);
      setTemplates(templateRows);
      const currentVersion = versionSnapshot.items.find((item) => item.version_id === currentSession.version_id);
      setForecastStartMonth(Math.min(12, Math.max(1, currentVersion?.current_month || currentSession.version_id || 1)));
      const nextSelected = selectedCode || parameterRows[0]?.parameter_code || "";
      setSelectedCode(nextSelected);
      if (nextSelected) {
        await loadValues(nextSelected, currentSession.budget_year, currentSession.version_id, productScopeKey);
      } else {
        setValueMap({});
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载预算基本假设失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedCode || !session) return;
    void loadValues(selectedCode, selectedYear, session.version_id, productScopeKey);
  }, [selectedCode, selectedYear, session, productScopeKey]);

  useEffect(() => {
    if (!selectedCode) {
      setImpact(null);
      return;
    }
    void (async () => {
      try {
        const result = await apiGet<AssumptionImpactResponseDto>(
          `/api/budget-assumptions/impact/${encodeURIComponent(selectedCode)}`,
        );
        setImpact(result);
      } catch {
        setImpact(null);
      }
    })();
  }, [selectedCode]);

  const handleCreateParameter = async () => {
    if (!createDraft.parameter_code.trim() || !createDraft.parameter_name.trim()) {
      alert("请先填写参数编码和参数名称。");
      return;
    }
    try {
      await apiPost<AssumptionParameterDto>("/api/budget-assumptions/parameters", createDraft);
      setCreateDraft((prev) => ({
        ...prev,
        parameter_code: "",
        parameter_name: "",
        value_formula: "",
        source_data_code: "",
        remark: "",
      }));
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "新增参数失败");
    }
  };

  const handleToggleEnabled = async (row: AssumptionParameterDto) => {
    try {
      await apiPatch<AssumptionParameterDto>(
        `/api/budget-assumptions/parameters/${encodeURIComponent(row.parameter_code)}`,
        { is_enabled: !row.is_enabled },
      );
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "更新参数状态失败");
    }
  };

  const handleFillFutureMonths = () => {
    if (!fillValue.trim()) {
      alert("请先输入要批量填充的数值。");
      return;
    }
    const nextMap = { ...valueMap };
    const start = selectedParameter?.time_granularity === "annual" ? 0 : forecastStartMonth;
    const end = selectedParameter?.time_granularity === "annual" ? 0 : 12;
    for (let month = start; month <= end; month += 1) {
      nextMap[month] = fillValue;
    }
    setValueMap(nextMap);
  };

  const handleSaveValues = async () => {
    if (!session || !selectedCode) return;
    const months = selectedParameter?.time_granularity === "annual"
      ? MONTH_OPTIONS.filter((item) => item.key === 0)
      : MONTH_OPTIONS.filter((item) => item.key > 0);
    const items: AssumptionValueUpsertItemDto[] = months.map((item) => ({
      parameter_code: selectedCode,
      month_index: item.key,
      value: Number(valueMap[item.key] || 0),
      product_scope_key: productScopeKey,
      scenario_code: "BASE",
    }));
    setSaving(true);
    try {
      await apiPut<AssumptionValueDto[]>("/api/budget-assumptions/values", {
        budget_year: selectedYear,
        version_id: session.version_id,
        items,
      });
      await loadValues(selectedCode, selectedYear, session.version_id, productScopeKey);
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存参数值失败");
    } finally {
      setSaving(false);
    }
  };

  const handleOpenTemplate = (template: AssumptionRuleTemplateDto) => {
    setEditingTemplate(template);
    try {
      setTemplateConfig(JSON.stringify(JSON.parse(template.config_json || "{}"), null, 2));
    } catch {
      setTemplateConfig(template.config_json || "{}");
    }
  };

  const handleSaveTemplate = async () => {
    if (!editingTemplate) return;
    try {
      JSON.parse(templateConfig || "{}");
      await apiPatch<AssumptionRuleTemplateDto>(
        `/api/budget-assumptions/rule-templates/${encodeURIComponent(editingTemplate.rule_code)}`,
        { config_json: templateConfig },
      );
      setEditingTemplate(null);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "模板 JSON 格式不正确或保存失败");
    }
  };

  if (loading) {
    return <div className="p-4 text-xs text-gray-600">加载预算基本假设...</div>;
  }

  return (
    <div className="h-full overflow-auto bg-white p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-gray-800">预算基本假设</h3>
          <p className="mt-1 text-xs text-gray-500">
            维护预测参数、参数值和预置模板。当前版本先提供模板骨架和参数沉淀能力，便于后续接入自动测算。
          </p>
        </div>
        {session && (
          <div className="whitespace-nowrap text-xs text-gray-500">
            年度：{session.budget_year} | 版本：{session.version_name} | 预测起始月：{forecastStartMonth}月
          </div>
        )}
      </div>

      {error && <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_1fr]">
        <div className="rounded border border-gray-200">
          <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-700">假设参数目录</div>
          <div className="overflow-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-2 py-2 text-left">编码</th>
                  <th className="px-2 py-2 text-left">名称</th>
                  <th className="px-2 py-2 text-left">分类</th>
                  <th className="px-2 py-2 text-left">取值方式</th>
                  <th className="px-2 py-2 text-left">单位</th>
                  <th className="px-2 py-2 text-center">启用</th>
                </tr>
              </thead>
              <tbody>
                {parameters.map((row) => (
                  <tr
                    key={row.parameter_code}
                    className={`border-t border-gray-100 ${selectedCode === row.parameter_code ? "bg-blue-50" : "hover:bg-gray-50"}`}
                  >
                    <td className="px-2 py-2 font-mono text-gray-700">
                      <button type="button" onClick={() => setSelectedCode(row.parameter_code)} className="text-left hover:text-blue-700">
                        {row.parameter_code}
                      </button>
                    </td>
                    <td className="px-2 py-2 text-gray-700">{row.parameter_name}</td>
                    <td className="px-2 py-2 text-gray-600">{row.category}</td>
                    <td className="px-2 py-2 text-gray-600">{inputModeLabel(row.input_mode)}</td>
                    <td className="px-2 py-2 text-gray-600">{row.default_unit || "-"}</td>
                    <td className="px-2 py-2 text-center">
                      <input type="checkbox" checked={row.is_enabled} onChange={() => void handleToggleEnabled(row)} />
                    </td>
                  </tr>
                ))}
                {parameters.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-2 py-6 text-center text-gray-400">暂无参数</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="border-t border-gray-200 bg-gray-50 px-3 py-3">
            <div className="mb-2 text-xs font-medium text-gray-700">新增参数</div>
            <div className="grid grid-cols-2 gap-2 xl:grid-cols-5">
              <input value={createDraft.parameter_code} onChange={(e) => setCreateDraft((prev) => ({ ...prev, parameter_code: e.target.value.toUpperCase() }))} placeholder="参数编码" className="rounded border border-gray-300 px-2 py-1 text-xs" />
              <input value={createDraft.parameter_name} onChange={(e) => setCreateDraft((prev) => ({ ...prev, parameter_name: e.target.value }))} placeholder="参数名称" className="rounded border border-gray-300 px-2 py-1 text-xs" />
              <input value={createDraft.category} onChange={(e) => setCreateDraft((prev) => ({ ...prev, category: e.target.value }))} placeholder="参数分类" className="rounded border border-gray-300 px-2 py-1 text-xs" />
              <select value={createDraft.value_type} onChange={(e) => setCreateDraft((prev) => ({ ...prev, value_type: e.target.value }))} className="rounded border border-gray-300 px-2 py-1 text-xs">
                <option value="金额">金额</option>
                <option value="百分比">百分比</option>
                <option value="户数">户数</option>
              </select>
              <select value={createDraft.time_granularity} onChange={(e) => setCreateDraft((prev) => ({ ...prev, time_granularity: e.target.value }))} className="rounded border border-gray-300 px-2 py-1 text-xs">
                <option value="monthly">monthly</option>
                <option value="annual">annual</option>
              </select>
              <input value={createDraft.default_unit} onChange={(e) => setCreateDraft((prev) => ({ ...prev, default_unit: e.target.value }))} placeholder="单位" className="rounded border border-gray-300 px-2 py-1 text-xs" />
              <input value={createDraft.apply_products} onChange={(e) => setCreateDraft((prev) => ({ ...prev, apply_products: e.target.value }))} placeholder="适用产品" className="rounded border border-gray-300 px-2 py-1 text-xs" />
              <input value={createDraft.source_data_code} onChange={(e) => setCreateDraft((prev) => ({ ...prev, source_data_code: e.target.value.toUpperCase() }))} placeholder="来源科目编码" className="rounded border border-gray-300 px-2 py-1 text-xs" />
              <input value={createDraft.remark} onChange={(e) => setCreateDraft((prev) => ({ ...prev, remark: e.target.value }))} placeholder="备注" className="rounded border border-gray-300 px-2 py-1 text-xs" />
              <button type="button" onClick={() => void handleCreateParameter()} className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700">新增参数</button>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded border border-gray-200">
            <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-700">参数值维护</div>
            <div className="space-y-3 p-3">
              <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                <div>
                  <div className="mb-1 text-[11px] text-gray-500">当前参数</div>
                  <div className="rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-700">
                    {selectedParameter ? `${selectedParameter.parameter_code} - ${selectedParameter.parameter_name}` : "请选择参数"}
                  </div>
                </div>
                <div>
                  <div className="mb-1 text-[11px] text-gray-500">预算年度</div>
                  <input type="number" value={selectedYear} onChange={(e) => setSelectedYear(Number(e.target.value || session?.budget_year || new Date().getFullYear()))} className="w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                </div>
                <div>
                  <div className="mb-1 text-[11px] text-gray-500">产品范围键</div>
                  <input value={productScopeKey} onChange={(e) => setProductScopeKey(e.target.value.toUpperCase())} placeholder="留空=默认产品范围" className="w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                </div>
              </div>
              <div className="rounded border border-blue-100 bg-blue-50 p-3">
                <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
                  <input type="number" min={1} max={12} value={forecastStartMonth} onChange={(e) => setForecastStartMonth(Math.min(12, Math.max(1, Number(e.target.value || 1))))} className="rounded border border-blue-200 px-2 py-1 text-xs" />
                  <input value={fillValue} onChange={(e) => setFillValue(e.target.value)} placeholder="批量填充值" className="rounded border border-blue-200 px-2 py-1 text-xs" />
                  <button type="button" onClick={handleFillFutureMonths} className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700">批量填充</button>
                  <button type="button" onClick={() => void handleSaveValues()} disabled={!selectedCode || saving} className="rounded bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-700 disabled:opacity-50">{saving ? "保存中..." : "保存参数值"}</button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {(selectedParameter?.time_granularity === "annual" ? MONTH_OPTIONS.filter((item) => item.key === 0) : MONTH_OPTIONS.filter((item) => item.key > 0)).map((item) => (
                  <label key={item.key} className="rounded border border-gray-200 p-2">
                    <div className="mb-1 text-[11px] text-gray-500">{item.label}</div>
                    <input value={valueMap[item.key] ?? ""} onChange={(e) => setValueMap((prev) => ({ ...prev, [item.key]: e.target.value }))} className="w-full rounded border border-gray-300 px-2 py-1 text-xs" />
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded border border-gray-200">
            <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-700">预置预测模板</div>
            <div className="divide-y divide-gray-100">
              {templates.map((template) => (
                <div key={template.rule_code} className="px-3 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-medium text-gray-800">{template.rule_name}</div>
                      <div className="mt-1 font-mono text-[11px] text-gray-500">{template.rule_code} / {template.rule_type}</div>
                    </div>
                    <button type="button" onClick={() => handleOpenTemplate(template)} className="rounded border border-blue-300 px-2 py-0.5 text-[11px] text-blue-700 hover:bg-blue-50">编辑 JSON</button>
                  </div>
                  {template.remark && <div className="mt-2 text-xs text-gray-600">{template.remark}</div>}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded border border-gray-200">
            <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-700">参数引用关系</div>
            <div className="p-3 text-xs">
              {!selectedCode ? (
                <div className="text-gray-400">请选择参数后查看引用关系。</div>
              ) : !impact || impact.items.length === 0 ? (
                <div className="text-gray-500">当前参数暂未在模板或数据科目模板绑定中被引用。</div>
              ) : (
                <div className="space-y-2">
                  {impact.items.map((item, idx) => (
                    <div key={`${item.match_source}-${item.rule_code || ""}-${item.data_acct_code || ""}-${idx}`} className="rounded border border-gray-100 bg-gray-50 px-2 py-2">
                      <div className="font-medium text-gray-700">{item.match_source}</div>
                      {item.rule_code && <div className="mt-1 text-gray-600">模板：<span className="font-mono">{item.rule_code}</span>{item.rule_name ? ` - ${item.rule_name}` : ""}</div>}
                      {item.data_acct_code && <div className="mt-1 text-gray-600">数据科目：<span className="font-mono">{item.data_acct_code}</span>{item.data_acct_name ? ` - ${item.data_acct_name}` : ""}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {editingTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-[820px] max-w-[94vw] rounded border border-gray-200 bg-white shadow-lg">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
              <div>
                <div className="text-sm font-medium text-gray-800">编辑模板配置</div>
                <div className="mt-1 text-xs text-gray-500">{editingTemplate.rule_code}</div>
              </div>
              <button type="button" onClick={() => setEditingTemplate(null)} className="rounded border border-gray-200 px-2 py-1 text-xs hover:bg-gray-50">关闭</button>
            </div>
            <div className="p-4">
              <textarea value={templateConfig} onChange={(e) => setTemplateConfig(e.target.value)} className="min-h-[340px] w-full rounded border border-gray-300 px-2 py-2 font-mono text-xs" />
            </div>
            <div className="flex justify-end gap-2 border-t border-gray-100 px-4 py-3">
              <button type="button" onClick={() => setEditingTemplate(null)} className="rounded border border-gray-300 px-3 py-1 text-xs hover:bg-gray-50">取消</button>
              <button type="button" onClick={() => void handleSaveTemplate()} className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700">保存模板</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
