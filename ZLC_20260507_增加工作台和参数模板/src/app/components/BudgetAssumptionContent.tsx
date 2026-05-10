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
  const [productScopeKey, setProductScopeKey] = useState("");
  const [selectedYear, setSelectedYear] = useState<number>(new Date().getFullYear());
  const [forecastStartMonth, setForecastStartMonth] = useState<number>(1);
  const [fillValue, setFillValue] = useState("");
  const [valueMap, setValueMap] = useState<Record<number, string>>({});
  const [impact, setImpact] = useState<AssumptionImpactResponseDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingParameter, setEditingParameter] = useState<AssumptionParameterDto | null>(null);
  const [editingParameterDraft, setEditingParameterDraft] = useState({
    parameter_code: "",
    parameter_name: "",
    category: "",
    value_type: "百分比",
    scope_type: "product",
    time_granularity: "monthly",
    apply_products: "",
    input_mode: "manual",
    source_data_code: "",
    value_formula: "",
    default_unit: "",
    remark: "",
  });
  const [editingTemplate, setEditingTemplate] = useState<AssumptionRuleTemplateDto | null>(null);
  const [editingTemplateDraft, setEditingTemplateDraft] = useState({
    rule_name: "",
    remark: "",
    formula_expression: "",
    raw_config_json: "{}",
  });
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
      const currentSession = await apiGet<SessionInfo>("/api/session");
      const versionSnapshot = await apiGet<VersionSnapshotResponseDto>("/api/version-snapshot");
      setSession(currentSession);
      setSelectedYear(currentSession.budget_year);
      const currentVersion = versionSnapshot.items.find((item) => item.version_id === currentSession.version_id);
      setForecastStartMonth(Math.min(12, Math.max(1, currentVersion?.current_month || 1)));
      const [parameterRows, templateRows] = await Promise.all([
        apiGet<AssumptionParameterDto[]>("/api/budget-assumptions/parameters"),
        apiGet<AssumptionRuleTemplateDto[]>("/api/budget-assumptions/rule-templates"),
      ]);
      setParameters(parameterRows);
      setTemplates(templateRows);
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
      setCreateDraft({
        parameter_code: "",
        parameter_name: "",
        category: createDraft.category,
        value_type: createDraft.value_type,
        scope_type: createDraft.scope_type,
        time_granularity: createDraft.time_granularity,
        apply_products: createDraft.apply_products,
        input_mode: createDraft.input_mode,
        value_formula: "",
        source_data_code: "",
        default_unit: createDraft.default_unit,
        remark: "",
      });
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

  const handleSaveValues = async () => {
    if (!session || !selectedCode) return;
    const items: AssumptionValueUpsertItemDto[] =
      selectedParameter?.time_granularity === "annual"
        ? [
            {
              parameter_code: selectedCode,
              month_index: 0,
              value: Number(valueMap[0] || 0),
              product_scope_key: productScopeKey,
              scenario_code: "BASE",
            },
          ]
        : MONTH_OPTIONS.filter((item) => item.key > 0).map((item) => ({
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

  const handleFillFutureMonths = () => {
    if (!fillValue.trim()) {
      alert("请先输入要批量填充的数值。");
      return;
    }
    const nextMap = { ...valueMap };
    for (let month = forecastStartMonth; month <= 12; month += 1) {
      nextMap[month] = fillValue;
    }
    setValueMap(nextMap);
  };

  const handleEditParameter = async (row: AssumptionParameterDto) => {
    setEditingParameter(row);
    setEditingParameterDraft({
      parameter_code: row.parameter_code,
      parameter_name: row.parameter_name,
      category: row.category,
      value_type: row.value_type,
      scope_type: row.scope_type,
      time_granularity: row.time_granularity,
      apply_products: row.apply_products || "",
      input_mode: row.input_mode || "manual",
      source_data_code: row.source_data_code || "",
      value_formula: row.value_formula || "",
      default_unit: row.default_unit || "",
      remark: row.remark || "",
    });
  };

  const handleSaveEditedParameter = async () => {
    if (!editingParameter) return;
    if (!editingParameterDraft.parameter_code.trim() || !editingParameterDraft.parameter_name.trim()) {
      alert("参数编码和参数名称不能为空。");
      return;
    }
    try {
      await apiPatch<AssumptionParameterDto>(
        `/api/budget-assumptions/parameters/${encodeURIComponent(editingParameter.parameter_code)}`,
        {
          parameter_code: editingParameterDraft.parameter_code.toUpperCase(),
          parameter_name: editingParameterDraft.parameter_name,
          category: editingParameterDraft.category,
          value_type: editingParameterDraft.value_type,
          scope_type: editingParameterDraft.scope_type,
          time_granularity: editingParameterDraft.time_granularity,
          apply_products: editingParameterDraft.apply_products,
          input_mode: editingParameterDraft.input_mode,
          source_data_code: editingParameterDraft.source_data_code.toUpperCase(),
          value_formula: editingParameterDraft.value_formula,
          default_unit: editingParameterDraft.default_unit,
          remark: editingParameterDraft.remark,
        },
      );
      setEditingParameter(null);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "更新参数失败");
    }
  };

  const handleEditTemplate = async (template: AssumptionRuleTemplateDto) => {
    try {
      const parsed = JSON.parse(template.config_json || "{}");
      setEditingTemplate(template);
      setEditingTemplateDraft({
        rule_name: template.rule_name,
        remark: template.remark || "",
        formula_expression: String(parsed.formula_expression || ""),
        raw_config_json: JSON.stringify(parsed, null, 2),
      });
    } catch {
      alert("当前模板配置 JSON 格式不正确，请先修复底层配置。");
    }
  };

  const handleSaveEditedTemplate = async () => {
    if (!editingTemplate) return;
    if (!editingTemplateDraft.rule_name.trim()) {
      alert("模板名称不能为空。");
      return;
    }
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(editingTemplateDraft.raw_config_json || "{}");
    } catch {
      alert("模板底层配置 JSON 格式不正确。");
      return;
    }
    parsed.formula_expression = editingTemplateDraft.formula_expression;
    const nextConfigJson = JSON.stringify(parsed, null, 2);
    try {
      await apiPatch<AssumptionRuleTemplateDto>(
        `/api/budget-assumptions/rule-templates/${encodeURIComponent(editingTemplate.rule_code)}`,
        {
          rule_name: editingTemplateDraft.rule_name,
          remark: editingTemplateDraft.remark,
          config_json: nextConfigJson,
        },
      );
      setEditingTemplate(null);
      await refresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : "更新模板失败");
    }
  };

  if (loading) {
    return <div className="p-4 text-xs text-gray-600">加载预算基本假设…</div>;
  }

  return (
    <div className="p-4 h-full overflow-auto bg-white">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-gray-800">预算基本假设</h3>
          <p className="mt-1 text-xs text-gray-500">
            先维护参数目录和参数取值方式，再在数据科目里绑定存款/贷款/费用模板。预算数计算公式与预算预测模板互斥，最后保存的那个生效。
          </p>
        </div>
        {session && (
          <div className="text-xs text-gray-500">
            年度：{session.budget_year} | 版本：{session.version_name} | 预测起始月：{forecastStartMonth}月
          </div>
        )}
      </div>

      {error && <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_1fr]">
        <div className="rounded border border-gray-200">
          <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-700">
            假设参数目录
          </div>
          <div className="overflow-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-2 py-2 text-left">编码</th>
                  <th className="px-2 py-2 text-left">名称</th>
                  <th className="px-2 py-2 text-left">分类</th>
                  <th className="px-2 py-2 text-left">适用产品</th>
                  <th className="px-2 py-2 text-left">取值方式</th>
                  <th className="px-2 py-2 text-left">来源/公式</th>
                  <th className="px-2 py-2 text-center">启用</th>
                  <th className="px-2 py-2 text-center">操作</th>
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
                    <td className="px-2 py-2 text-gray-600">{row.apply_products || row.scope_type}</td>
                    <td className="px-2 py-2 text-gray-600">{inputModeLabel(row.input_mode)}</td>
                    <td className="px-2 py-2 text-gray-600">
                      {row.source_data_code || row.value_formula || "-"}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={row.is_enabled}
                        onChange={() => void handleToggleEnabled(row)}
                      />
                    </td>
                    <td className="px-2 py-2 text-center">
                      <button
                        type="button"
                        onClick={() => void handleEditParameter(row)}
                        className="rounded border border-blue-300 px-2 py-0.5 text-[11px] text-blue-700 hover:bg-blue-50"
                      >
                        编辑
                      </button>
                    </td>
                  </tr>
                ))}
                {parameters.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-2 py-6 text-center text-gray-400">
                      暂无参数
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="border-t border-gray-200 bg-gray-50 px-3 py-3">
            <div className="mb-2 text-xs font-medium text-gray-700">新增参数</div>
            <div className="grid grid-cols-2 gap-2 xl:grid-cols-5">
              <input
                value={createDraft.parameter_code}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, parameter_code: e.target.value.toUpperCase() }))}
                placeholder="参数编码"
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              />
              <input
                value={createDraft.parameter_name}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, parameter_name: e.target.value }))}
                placeholder="参数名称"
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              />
              <input
                value={createDraft.category}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, category: e.target.value }))}
                placeholder="参数分类"
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              />
              <select
                value={createDraft.scope_type}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, scope_type: e.target.value }))}
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              >
                <option value="global">global</option>
                <option value="product">product</option>
                <option value="product_group">product_group</option>
              </select>
              <input
                value={createDraft.apply_products}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, apply_products: e.target.value }))}
                placeholder="适用产品"
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              />
              <select
                value={createDraft.value_type}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, value_type: e.target.value }))}
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              >
                <option value="金额">金额</option>
                <option value="百分比">百分比</option>
                <option value="户数">户数</option>
              </select>
              <select
                value={createDraft.time_granularity}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, time_granularity: e.target.value }))}
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              >
                <option value="monthly">monthly</option>
                <option value="annual">annual</option>
              </select>
              <select
                value={createDraft.input_mode}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, input_mode: e.target.value }))}
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              >
                <option value="manual">manual</option>
                <option value="source_prev_actual">source_prev_actual</option>
                <option value="source_ytd_avg_actual">source_ytd_avg_actual</option>
                <option value="formula">formula</option>
              </select>
              <input
                value={createDraft.source_data_code}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, source_data_code: e.target.value.toUpperCase() }))}
                placeholder="来源科目编码"
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              />
              <input
                value={createDraft.value_formula}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, value_formula: e.target.value }))}
                placeholder='参数公式，如 PREV_ACTUAL("L3163")'
                className="rounded border border-gray-300 px-2 py-1 text-xs xl:col-span-2"
              />
              <input
                value={createDraft.default_unit}
                onChange={(e) => setCreateDraft((prev) => ({ ...prev, default_unit: e.target.value }))}
                placeholder="单位"
                className="rounded border border-gray-300 px-2 py-1 text-xs"
              />
              <button
                type="button"
                onClick={() => void handleCreateParameter()}
                className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
              >
                新增参数
              </button>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded border border-gray-200">
            <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-700">
              参数值维护
            </div>
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
                  <input
                    type="number"
                    value={selectedYear}
                    onChange={(e) => setSelectedYear(Number(e.target.value || session?.budget_year || new Date().getFullYear()))}
                    className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                  />
                </div>
                <div>
                  <div className="mb-1 text-[11px] text-gray-500">产品范围键</div>
                  <input
                    value={productScopeKey}
                    onChange={(e) => setProductScopeKey(e.target.value.toUpperCase())}
                    placeholder="留空=默认产品范围"
                    className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                  />
                </div>
                <div className="flex items-end">
                  <button
                    type="button"
                    onClick={() => void handleSaveValues()}
                    disabled={!selectedCode || saving}
                    className="rounded bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {saving ? "保存中..." : "保存参数值"}
                  </button>
                </div>
              </div>

              {selectedParameter?.input_mode === "manual" ? (
                <>
                  <div className="rounded border border-blue-100 bg-blue-50 p-3">
                    <div className="mb-2 text-xs font-medium text-blue-800">快捷填充</div>
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
                      <div>
                        <div className="mb-1 text-[11px] text-blue-700">预测起始月</div>
                        <input
                          type="number"
                          min={1}
                          max={12}
                          value={forecastStartMonth}
                          onChange={(e) => setForecastStartMonth(Math.min(12, Math.max(1, Number(e.target.value || 1))))}
                          className="w-full rounded border border-blue-200 px-2 py-1 text-xs"
                        />
                      </div>
                      <div>
                        <div className="mb-1 text-[11px] text-blue-700">
                          {selectedParameter.time_granularity === "annual" ? "年值" : "统一数值"}
                        </div>
                        <input
                          value={fillValue}
                          onChange={(e) => setFillValue(e.target.value)}
                          className="w-full rounded border border-blue-200 px-2 py-1 text-xs"
                        />
                      </div>
                      <div className="md:col-span-2 flex items-end gap-2">
                        {selectedParameter.time_granularity === "annual" ? (
                          <button
                            type="button"
                            onClick={() => setValueMap((prev) => ({ ...prev, 0: fillValue }))}
                            className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
                          >
                            应用为年度统一值
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={handleFillFutureMonths}
                            className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
                          >
                            从{forecastStartMonth}月批量填充到12月
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="mt-2 text-[11px] text-blue-700">
                      建议做法：对大多数参数只维护“产品 + 预测起始月到年末”的统一值；如需 2027 年预算，可切换预算年度后录一个年值或统一值。
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                    {(selectedParameter.time_granularity === "annual" ? MONTH_OPTIONS.filter((item) => item.key === 0) : MONTH_OPTIONS.filter((item) => item.key > 0)).map((item) => (
                      <label key={item.key} className="rounded border border-gray-200 p-2">
                        <div className="mb-1 text-[11px] text-gray-500">{item.label}</div>
                        <input
                          value={valueMap[item.key] ?? ""}
                          onChange={(e) =>
                            setValueMap((prev) => ({
                              ...prev,
                              [item.key]: e.target.value,
                            }))
                          }
                          className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                        />
                      </label>
                    ))}
                  </div>
                </>
              ) : (
                <div className="rounded border border-amber-200 bg-amber-50 px-3 py-3 text-xs text-amber-800">
                  当前参数取值方式为“{inputModeLabel(selectedParameter?.input_mode || "")}”，不需要逐月录值。
                  {selectedParameter?.source_data_code && ` 来源数据科目：${selectedParameter.source_data_code}。`}
                  {selectedParameter?.value_formula && ` 公式：${selectedParameter.value_formula}`}
                </div>
              )}
            </div>
          </div>

          <div className="rounded border border-gray-200">
            <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-700">
              预置预测模板
            </div>
            <div className="divide-y divide-gray-100">
              {templates.map((template) => (
                <div key={template.rule_code} className="px-3 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-medium text-gray-800">{template.rule_name}</div>
                    <div className="flex items-center gap-2">
                      <div className="font-mono text-[11px] text-gray-500">{template.rule_code}</div>
                      <button
                        type="button"
                        onClick={() => void handleEditTemplate(template)}
                        className="rounded border border-blue-300 px-2 py-0.5 text-[11px] text-blue-700 hover:bg-blue-50"
                      >
                        编辑模板
                      </button>
                    </div>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500">{template.rule_type}</div>
                  <div className="mt-2 whitespace-pre-wrap rounded bg-gray-50 px-2 py-2 font-mono text-[11px] text-gray-600">
                    {template.config_json}
                  </div>
                  {template.remark && <div className="mt-2 text-xs text-gray-600">{template.remark}</div>}
                </div>
              ))}
              {templates.length === 0 && (
                <div className="px-3 py-6 text-center text-xs text-gray-400">暂无模板</div>
              )}
            </div>
          </div>

          <div className="rounded border border-gray-200">
            <div className="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-700">
              参数引用关系
            </div>
            <div className="p-3 text-xs">
              <div className="mb-3 rounded border border-blue-100 bg-blue-50 px-3 py-2 text-[11px] leading-5 text-blue-800">
                这里显示的是“这个参数当前被哪些模板、哪些数据科目模板绑定引用了”，不是金额测算结果。
                用途是排查：如果你修改了当前参数，哪些模板和预测科目会受到影响。
              </div>
              {!selectedCode ? (
                <div className="text-gray-400">请选择参数后查看它的引用关系。</div>
              ) : !impact || impact.items.length === 0 ? (
                <div className="text-gray-500">当前参数暂未在模板或数据科目模板绑定中被引用，可以理解为它目前还没有参与预测链路。</div>
              ) : (
                <div className="space-y-2">
                  {impact.items.map((item, idx) => (
                    <div key={`${item.match_source}-${item.rule_code || ""}-${item.data_acct_code || ""}-${idx}`} className="rounded border border-gray-100 bg-gray-50 px-2 py-2">
                      <div className="font-medium text-gray-700">{item.match_source}</div>
                      {item.rule_code && (
                        <div className="mt-1 text-gray-600">
                          模板：<span className="font-mono">{item.rule_code}</span>
                          {item.rule_name ? ` - ${item.rule_name}` : ""}
                        </div>
                      )}
                      {item.data_acct_code && (
                        <div className="mt-1 text-gray-600">
                          数据科目：<span className="font-mono">{item.data_acct_code}</span>
                          {item.data_acct_name ? ` - ${item.data_acct_name}` : ""}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      {editingParameter && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-[760px] max-w-[94vw] max-h-[88vh] overflow-auto rounded bg-white shadow-lg border border-gray-200">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-800">编辑假设参数</div>
                <div className="text-xs text-gray-500 mt-1">{editingParameter.parameter_code}</div>
              </div>
              <button
                type="button"
                onClick={() => setEditingParameter(null)}
                className="px-2 py-1 text-xs rounded border border-gray-200 hover:bg-gray-50"
              >
                关闭
              </button>
            </div>
            <div className="p-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">参数编码</div>
                <input
                  value={editingParameterDraft.parameter_code}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, parameter_code: e.target.value.toUpperCase() }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">参数名称</div>
                <input
                  value={editingParameterDraft.parameter_name}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, parameter_name: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">参数分类</div>
                <input
                  value={editingParameterDraft.category}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, category: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">适用粒度</div>
                <select
                  value={editingParameterDraft.scope_type}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, scope_type: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                >
                  <option value="global">global</option>
                  <option value="product">product</option>
                  <option value="product_group">product_group</option>
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">适用产品</div>
                <input
                  value={editingParameterDraft.apply_products}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, apply_products: e.target.value }))}
                  placeholder="如：按产品 / 全部产品 / 指定产品组"
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">数值类型</div>
                <select
                  value={editingParameterDraft.value_type}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, value_type: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                >
                  <option value="金额">金额</option>
                  <option value="百分比">百分比</option>
                  <option value="户数">户数</option>
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">时间粒度</div>
                <select
                  value={editingParameterDraft.time_granularity}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, time_granularity: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                >
                  <option value="monthly">monthly</option>
                  <option value="annual">annual</option>
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">取值方式</div>
                <select
                  value={editingParameterDraft.input_mode}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, input_mode: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                >
                  <option value="manual">manual</option>
                  <option value="source_prev_actual">source_prev_actual</option>
                  <option value="source_ytd_avg_actual">source_ytd_avg_actual</option>
                  <option value="formula">formula</option>
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">取值来源科目</div>
                <input
                  value={editingParameterDraft.source_data_code}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, source_data_code: e.target.value.toUpperCase() }))}
                  placeholder="如：L3163"
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono"
                />
              </label>
              <label className="block md:col-span-2">
                <div className="mb-1 text-xs text-gray-600">参数公式</div>
                <input
                  value={editingParameterDraft.value_formula}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, value_formula: e.target.value }))}
                  placeholder='如：PREV_ACTUAL("L3163") 或 YTD_AVG_ACTUAL("L3163")'
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">单位</div>
                <input
                  value={editingParameterDraft.default_unit}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, default_unit: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                />
              </label>
              <label className="block md:col-span-2">
                <div className="mb-1 text-xs text-gray-600">备注</div>
                <textarea
                  value={editingParameterDraft.remark}
                  onChange={(e) => setEditingParameterDraft((prev) => ({ ...prev, remark: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs min-h-[72px]"
                />
              </label>
            </div>
            <div className="px-4 py-3 border-t border-gray-100 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingParameter(null)}
                className="px-3 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleSaveEditedParameter()}
                className="px-3 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-700"
              >
                保存参数
              </button>
            </div>
          </div>
        </div>
      )}
      {editingTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-[860px] max-w-[94vw] max-h-[88vh] overflow-auto rounded bg-white shadow-lg border border-gray-200">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-800">编辑预置预测模板</div>
                <div className="text-xs text-gray-500 mt-1">{editingTemplate.rule_code}</div>
              </div>
              <button
                type="button"
                onClick={() => setEditingTemplate(null)}
                className="px-2 py-1 text-xs rounded border border-gray-200 hover:bg-gray-50"
              >
                关闭
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <label className="block">
                  <div className="mb-1 text-xs text-gray-600">模板名称</div>
                  <input
                    value={editingTemplateDraft.rule_name}
                    onChange={(e) => setEditingTemplateDraft((prev) => ({ ...prev, rule_name: e.target.value }))}
                    className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
                  />
                </label>
                <label className="block">
                  <div className="mb-1 text-xs text-gray-600">模板类型</div>
                  <input
                    value={editingTemplate.rule_type}
                    disabled
                    className="w-full rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-500"
                  />
                </label>
              </div>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">模板说明</div>
                <textarea
                  value={editingTemplateDraft.remark}
                  onChange={(e) => setEditingTemplateDraft((prev) => ({ ...prev, remark: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs min-h-[72px]"
                />
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">公式表达式</div>
                <textarea
                  value={editingTemplateDraft.formula_expression}
                  onChange={(e) => setEditingTemplateDraft((prev) => ({ ...prev, formula_expression: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono min-h-[88px]"
                  placeholder='如：A("AVG_BALANCE") * PREV_ACTUAL("ACTUAL_CUSTOMER_RATE") * DAYS() / 360'
                />
                <div className="mt-1 text-[11px] text-gray-500">
                  公式可引用 `A("...")`、`P("...")`、`PREV_ACTUAL("...")`、`YTD_AVG_ACTUAL("...")`、`DAYS()`、`MAX/MIN`
                </div>
              </label>
              <label className="block">
                <div className="mb-1 text-xs text-gray-600">模板底层配置 JSON</div>
                <textarea
                  value={editingTemplateDraft.raw_config_json}
                  onChange={(e) => setEditingTemplateDraft((prev) => ({ ...prev, raw_config_json: e.target.value }))}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono min-h-[220px]"
                />
                <div className="mt-1 text-[11px] text-gray-500">
                  除名称、说明、公式外，其他绑定字段也可以在这里继续调整。
                </div>
              </label>
            </div>
            <div className="px-4 py-3 border-t border-gray-100 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingTemplate(null)}
                className="px-3 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleSaveEditedTemplate()}
                className="px-3 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-700"
              >
                保存模板
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
