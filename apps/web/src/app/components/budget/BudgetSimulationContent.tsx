import { useEffect, useMemo, useState } from "react";
import { Calculator, ChevronDown, Database, Download, Search, SlidersHorizontal } from "lucide-react";
import { downloadBlob } from "@/lib/shared/api";
import { listOrgProductRuntimeProducts, type OrgProductRuntimeProductDto } from "@/lib/expense/masterDataApi";
import {
  exportSimulationExcel,
  fetchSimulationBaseline,
  fetchSimulationResult,
  type SimulationBaselineRowDto,
  type SimulationInputItemDto,
  type SimulationResultRowDto,
} from "@/lib/budget/simulationApi";

type SimulationParamKey =
  | "MGMT_LOAN_EOY"
  | "LOAN_YIELD_RATE"
  | "UNION_LOAN_YIELD_RATE"
  | "RISK_COST_RATE";

type ParamMeta = {
  key: SimulationParamKey;
  label: string;
};

const PARAMS: ParamMeta[] = [
  { key: "MGMT_LOAN_EOY", label: "管理贷款时点规模" },
  { key: "LOAN_YIELD_RATE", label: "贷款收益率" },
  { key: "UNION_LOAN_YIELD_RATE", label: "联合贷款收益率" },
  { key: "RISK_COST_RATE", label: "风险成本率" },
];

const PERCENT_PARAM_KEYS = new Set<SimulationParamKey>([
  "LOAN_YIELD_RATE",
  "UNION_LOAN_YIELD_RATE",
  "RISK_COST_RATE",
]);
const SIM_INTEREST_NET = "03.02.01.01.001";
const SIM_INTEREST_INCOME = "03.01.01.01.025";
const SIM_INTEREST_EXPENSE = "04.01.06.01.012";
const SIM_FEE_NET = "03.04.01.01.003";
const SIM_FEE_INCOME = "03.04.01.01.001";
const SIM_FEE_EXPENSE = "04.03.01.01.004";
const SIM_OTHER_REVENUE = "03.09.05";
const SIM_LOAN_RISK_COST = "06.01.01.02.007";
const SIM_RISK_COST_BASE = "06.01.01.01.008";
const SIM_RISK_COST_GAP = "06.01.01.01.004";
const SIM_RISK_COST_PEER = "06.01.01.02.009";
const SIM_RISK_COST_OTHER = "06.01.01.02.003";

const REVENUE_COMPONENT_CODES = new Set([SIM_INTEREST_NET, SIM_FEE_NET, SIM_OTHER_REVENUE]);
const INTEREST_INCOME_COMPONENT_CODES = new Set([SIM_INTEREST_INCOME, SIM_INTEREST_EXPENSE]);
const INTEREST_INCOME_PRODUCT_COMPONENT_PREFIX = `${SIM_INTEREST_INCOME}::`;
const RISK_COST_BASE_PRODUCT_COMPONENT_PREFIX = `${SIM_RISK_COST_BASE}::`;
const FEE_INCOME_COMPONENT_CODES = new Set([SIM_FEE_INCOME, SIM_FEE_EXPENSE]);
const IMPAIRMENT_COMPONENT_CODES = new Set([SIM_LOAN_RISK_COST, SIM_RISK_COST_PEER, SIM_RISK_COST_OTHER]);
const LOAN_RISK_COST_COMPONENT_CODES = new Set([SIM_RISK_COST_BASE, SIM_RISK_COST_GAP]);

export function BudgetSimulationContent() {
  const [loanProducts, setLoanProducts] = useState<OrgProductRuntimeProductDto[]>([]);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [selectorKeyword, setSelectorKeyword] = useState("");
  const [selectedTop, setSelectedTop] = useState<Set<SimulationParamKey>>(new Set());
  const [selectedProducts, setSelectedProducts] = useState<Record<SimulationParamKey, Set<string>>>({
    MGMT_LOAN_EOY: new Set(),
    LOAN_YIELD_RATE: new Set(),
    UNION_LOAN_YIELD_RATE: new Set(),
    RISK_COST_RATE: new Set(),
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [baselineByRowKey, setBaselineByRowKey] = useState<Record<string, SimulationBaselineRowDto>>({});
  const [simulateValueByRowKey, setSimulateValueByRowKey] = useState<Record<string, string>>({});
  const [resultLoading, setResultLoading] = useState(false);
  const [resultRows, setResultRows] = useState<SimulationResultRowDto[]>([]);
  const [resultError, setResultError] = useState("");
  const [hasComputed, setHasComputed] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        const all = await listOrgProductRuntimeProducts();
        const loans = all
          .filter((p) => String(p.product_name || "").includes("贷"))
          .sort((a, b) => a.product_code.localeCompare(b.product_code, "zh-CN"));
        setLoanProducts(loans);
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载机构及产品清单失败");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const toggleTopSelected = (key: SimulationParamKey, checked: boolean) => {
    setSelectedTop((prev) => {
      const next = new Set(prev);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
    if (!checked) {
      setSelectedProducts((prev) => ({
        ...prev,
        [key]: new Set(),
      }));
    }
  };

  const toggleProductSelected = (key: SimulationParamKey, productCode: string, checked: boolean) => {
    setSelectedTop((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    setSelectedProducts((prev) => {
      const current = new Set(prev[key]);
      if (checked) current.add(productCode);
      else current.delete(productCode);
      return { ...prev, [key]: current };
    });
  };

  const selectedSummary = useMemo(() => {
    const chunks: string[] = [];
    for (const p of PARAMS) {
      if (!selectedTop.has(p.key)) continue;
      const selectedCodes = selectedProducts[p.key] ?? new Set<string>();
      const names = loanProducts
        .filter((prod) => selectedCodes.has(prod.product_code))
        .map((prod) => prod.product_name);
      chunks.push(names.length > 0 ? `${p.label}（${names.join("、")}）` : p.label);
    }
    return chunks;
  }, [loanProducts, selectedProducts, selectedTop]);

  const normalizedKeyword = selectorKeyword.trim().toLowerCase();

  const selectedRows = useMemo(() => {
    const rows: Array<{
      rowKey: string;
      indicator_code: SimulationParamKey;
      indicator_label: string;
      product_code: string | null;
      product_label: string | null;
    }> = [];
    for (const p of PARAMS) {
      if (!selectedTop.has(p.key)) continue;
      const productCodes = Array.from(selectedProducts[p.key] ?? new Set<string>());
      if (productCodes.length === 0) {
        rows.push({
          rowKey: `${p.key}|`,
          indicator_code: p.key,
          indicator_label: p.label,
          product_code: null,
          product_label: null,
        });
        continue;
      }
      for (const pc of productCodes) {
        const prod = loanProducts.find((x) => x.product_code === pc);
        rows.push({
          rowKey: `${p.key}|${pc}`,
          indicator_code: p.key,
          indicator_label: p.label,
          product_code: pc,
          product_label: prod ? `${prod.product_code} ${prod.product_name}` : pc,
        });
      }
    }
    return rows;
  }, [loanProducts, selectedProducts, selectedTop]);

  useEffect(() => {
    const loadBaseline = async () => {
      if (selectedRows.length === 0) {
        setBaselineByRowKey({});
        return;
      }
      setBaselineLoading(true);
      try {
        const resp = await fetchSimulationBaseline(
          selectedRows.map((r) => ({
            indicator_code: r.indicator_code,
            product_code: r.product_code,
          })),
        );
        const map: Record<string, SimulationBaselineRowDto> = {};
        for (const row of selectedRows) {
          const hit = resp.find(
            (x) => x.indicator_code === row.indicator_code && (x.product_code ?? null) === (row.product_code ?? null),
          );
          if (hit) {
            map[row.rowKey] = hit;
          }
        }
        setBaselineByRowKey(map);
      } catch {
        setBaselineByRowKey({});
      } finally {
        setBaselineLoading(false);
      }
    };
    void loadBaseline();
  }, [selectedRows]);

  const formatBaseline = (rowKey: string): string => {
    const b = baselineByRowKey[rowKey];
    if (!b) return "--";
    if (b.value_type === "百分比") return `${(b.baseline_value * 100).toFixed(2)}%`;
    return b.baseline_value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  };

  const parseNumeric = (raw: string): number | null => {
    const v = Number.parseFloat(String(raw || "").replace(/[%％,\s]/g, ""));
    if (!Number.isFinite(v)) return null;
    return v;
  };

  const normalizeSimulationValue = (row: (typeof selectedRows)[number], raw: string): number | null => {
    const n = parseNumeric(raw);
    if (n === null) return null;
    const baseline = baselineByRowKey[row.rowKey];
    const isPercent = baseline?.value_type === "百分比" || PERCENT_PARAM_KEYS.has(row.indicator_code);
    return isPercent && Math.abs(n) > 1 ? n / 100 : n;
  };

  useEffect(() => {
    setHasComputed(false);
    setResultRows([]);
    setResultError("");
  }, [selectedRows, simulateValueByRowKey]);

  const buildSimulationPayload = (): SimulationInputItemDto[] => {
    const items: SimulationInputItemDto[] = [];
    selectedRows.forEach((r) => {
        const raw = simulateValueByRowKey[r.rowKey];
        const num = normalizeSimulationValue(r, raw);
        if (num === null) return;
        items.push({
          indicator_code: r.indicator_code,
          product_code: r.product_code,
          simulate_value: num,
        });
      });
    return items;
  };

  const runCompute = async () => {
    if (selectedRows.length === 0) {
      setResultRows([]);
      setResultError("请先选择模拟参数");
      return;
    }
    setResultLoading(true);
    setResultError("");
    try {
      const resp = await fetchSimulationResult(buildSimulationPayload());
      setResultRows(resp);
      setHasComputed(true);
    } catch (e) {
      setResultRows([]);
      setHasComputed(false);
      const msg = e instanceof Error ? e.message : "测算结果加载失败";
      setResultError(msg);
    } finally {
      setResultLoading(false);
    }
  };

  const groupedResult = useMemo(() => {
    const profit = resultRows.filter((r) => r.metric_group === "盈利性指标");
    const risk = resultRows.filter((r) => r.metric_group === "风险指标");
    return { profit, risk };
  }, [resultRows]);

  const formatScenarioValue = (value: number, valueType: string): string => {
    if (valueType === "百分比") return `${(value * 100).toFixed(2)}%`;
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  };

  const handleExportExcel = async () => {
    if (!hasComputed) {
      setResultError("请先点击“开始计算”，再导出 Excel");
      return;
    }
    setExporting(true);
    setResultError("");
    try {
      const resp = await exportSimulationExcel(buildSimulationPayload());
      downloadBlob(resp.blob, resp.filename || "budget_simulation.xlsx");
    } catch (e) {
      setResultError(e instanceof Error ? e.message : "导出 Excel 失败");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="bb-page overflow-auto">
      <div className="bb-page-header">
        <div className="bb-page-title">
          <SlidersHorizontal className="w-4 h-4 text-[var(--bb-primary)]" />
          模拟测算（正算）
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSelectorOpen((v) => !v)}
            className="bb-btn bb-btn-secondary h-10 min-w-[360px] max-w-[560px]"
          >
            <Search className="w-4 h-4 text-[var(--bb-text-muted)]" />
            <span className="truncate text-left flex-1">
              {selectedSummary.length > 0 ? selectedSummary.join("、") : "请选择模拟参数（可支持多选）"}
            </span>
            <ChevronDown className={`w-3.5 h-3.5 text-[var(--bb-text-muted)] transition-transform ${selectorOpen ? "rotate-180" : ""}`} />
          </button>
          <button
            type="button"
            onClick={runCompute}
            disabled={resultLoading || selectedRows.length === 0}
            className="bb-btn bb-btn-primary h-10"
            title={selectedRows.length === 0 ? "请先选择模拟参数" : "开始计算"}
          >
            <Calculator className="w-4 h-4" />
            {resultLoading ? "计算中..." : "开始计算"}
          </button>
          <button
            type="button"
            onClick={handleExportExcel}
            disabled={exporting || !hasComputed}
            className="bb-btn bb-btn-secondary h-10"
            title={!hasComputed ? "请先开始计算" : "导出 Excel"}
          >
            <Download className="w-4 h-4" />
            {exporting ? "导出中..." : "导出Excel"}
          </button>
        </div>
      </div>

      {selectorOpen && (
        <div>
          <div className="bb-panel w-[720px] max-w-full shadow-sm">
            <div className="bb-panel-header">
              <span className="bb-panel-title">选择模拟参数</span>
              <div className="ml-auto w-[320px] max-w-full flex items-center gap-2">
                <Search className="w-4 h-4 text-[var(--bb-text-muted)]" />
                <input
                  value={selectorKeyword}
                  onChange={(e) => setSelectorKeyword(e.target.value)}
                  placeholder="搜索参数..."
                  className="bb-input w-full"
                />
              </div>
            </div>
            <div className="h-[360px] overflow-auto p-2 space-y-2">
              {PARAMS.map((meta) => {
                const topChecked = selectedTop.has(meta.key);
                const childSet = selectedProducts[meta.key] ?? new Set<string>();
                const selectedProductNames = loanProducts
                  .filter((p) => childSet.has(p.product_code))
                  .map((p) => p.product_name)
                  .join("、");
                const filteredProducts = loanProducts.filter((prod) => {
                  if (!normalizedKeyword) return true;
                  const kw = normalizedKeyword;
                  return (
                    meta.label.toLowerCase().includes(kw) ||
                    prod.product_code.toLowerCase().includes(kw) ||
                    String(prod.product_name || "").toLowerCase().includes(kw)
                  );
                });
                if (filteredProducts.length === 0 && normalizedKeyword && !meta.label.toLowerCase().includes(normalizedKeyword)) {
                  return null;
                }
                return (
                  <div key={meta.key} className="bb-card p-0">
                    <div className="px-2 py-1.5 bg-[var(--bb-primary-soft)] flex items-center gap-2">
                      <label className="flex items-center gap-2 text-xs text-[var(--bb-text)]">
                        <input
                          type="checkbox"
                          checked={topChecked}
                          onChange={(e) => toggleTopSelected(meta.key, e.target.checked)}
                        />
                        <span className="font-medium">{meta.label}</span>
                      </label>
                      <span className="ml-auto text-[11px] text-[var(--bb-text-muted)] truncate max-w-[360px]" title={selectedProductNames || "未选择产品"}>
                        {selectedProductNames || "未选择产品"}
                      </span>
                    </div>
                    <div className="p-2 border-t border-[var(--bb-border-soft)]">
                      <div className="text-[11px] text-[var(--bb-text-muted)] mb-1">二级参数：贷款产品</div>
                      <div className="grid grid-cols-2 gap-1">
                        {filteredProducts.map((prod) => (
                          <label
                            key={`${meta.key}-${prod.product_code}`}
                            className="flex items-center gap-2 text-xs text-[var(--bb-text)] px-1 py-1 rounded hover:bg-[var(--bb-bg-subtle)]"
                          >
                            <input
                              type="checkbox"
                              checked={childSet.has(prod.product_code)}
                              onChange={(e) => toggleProductSelected(meta.key, prod.product_code, e.target.checked)}
                            />
                            <Database className="w-3.5 h-3.5 text-[var(--bb-success)] shrink-0" />
                            <span className="font-mono text-[11px] text-[var(--bb-text-muted)]">{prod.product_code}</span>
                            <span className="truncate">{prod.product_name}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <div className="bb-panel">
        <div className="bb-panel-header">
          <span className="bb-panel-title">情景参数表</span>
        </div>
        {loading ? (
          <div className="px-3 py-6 text-xs text-[var(--bb-text-muted)]">正在加载贷款产品...</div>
        ) : error ? (
          <div className="bb-status-banner bb-status-banner-danger m-3">加载失败：{error}</div>
        ) : (
          <div className="p-3">
            <table className="bb-table bb-table-dense">
              <colgroup>
                <col className="w-[46%]" />
                <col className="w-[27%]" />
                <col className="w-[27%]" />
              </colgroup>
              <thead>
                <tr>
                  <th>选择项目</th>
                  <th className="bb-cell-number">26年基准情景</th>
                  <th className="bb-cell-number">26年模拟测算（利润变动）</th>
                </tr>
              </thead>
              <tbody>
                {selectedRows.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-6 text-center text-[var(--bb-text-muted)]">
                      请先在上方“模拟参数”中选择项目
                    </td>
                  </tr>
                ) : (
                  selectedRows.map((row) => {
                    const baseline = baselineByRowKey[row.rowKey];
                    const sourceRefs = baseline?.source_org_product_refs ?? [];
                    const sourceCodes = baseline?.source_metric_codes ?? baseline?.source_data_acct_codes ?? [];
                    const sourceTitle = [
                      sourceRefs.length ? `机构产品指标：\n${sourceRefs.join("\n")}` : "",
                      sourceCodes.length ? `指标编码：\n${sourceCodes.join("\n")}` : "",
                    ].filter(Boolean).join("\n\n");
                    return (
                    <tr key={row.rowKey}>
                      <td>
                        <div>
                          <span className="font-medium">{row.indicator_label}</span>
                          {row.product_label ? <span className="ml-1 text-[var(--bb-text-muted)]">/ {row.product_label}</span> : null}
                        </div>
                        {(sourceRefs.length > 0 || sourceCodes.length > 0) && (
                          <div
                            className="mt-1 flex min-w-0 items-center gap-1 text-[10px] text-sky-700"
                            title={sourceTitle}
                          >
                            {sourceRefs.length > 0 ? (
                              <>
                                <span className="shrink-0 rounded bg-sky-50 px-1 py-px text-[9px] font-medium text-sky-700">
                                  机构产品
                                </span>
                                <span className="truncate font-mono">{sourceRefs[0]}</span>
                                {sourceRefs.length > 1 && <span className="shrink-0">+{sourceRefs.length - 1}</span>}
                              </>
                            ) : (
                              <>
                                <span className="shrink-0 rounded bg-slate-50 px-1 py-px text-[9px] font-medium text-slate-500">
                                  指标编码
                                </span>
                                <span className="truncate font-mono text-slate-500">{sourceCodes[0]}</span>
                                {sourceCodes.length > 1 && <span className="shrink-0 text-slate-500">+{sourceCodes.length - 1}</span>}
                              </>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="bb-cell-number">
                        {baselineLoading ? "加载中..." : formatBaseline(row.rowKey)}
                      </td>
                      <td>
                        <input
                          type="text"
                          className="bb-grid-input bb-grid-input-number"
                          placeholder="请输入模拟测算值（利润变动）"
                          value={simulateValueByRowKey[row.rowKey] ?? ""}
                          onChange={(e) =>
                            setSimulateValueByRowKey((prev) => ({
                              ...prev,
                              [row.rowKey]: e.target.value,
                            }))
                          }
                        />
                      </td>
                    </tr>
                    );
                  })
                )}
              </tbody>
            </table>
            <div className="mt-2 text-[11px] text-[var(--bb-text-muted)]">基准情景自动引用前序预测数据；百分比类参数可输入 5 或 5%，系统会按 5% 测算。</div>
          </div>
        )}
      </div>

      <div className="bb-panel">
        <div className="bb-panel-header">
          <span className="bb-panel-title">测算结果</span>
        </div>
        <div className="p-3">
          {resultLoading ? (
            <div className="text-xs text-[var(--bb-text-muted)]">正在计算测算结果...</div>
          ) : resultError ? (
            <div className="bb-status-banner bb-status-banner-danger">测算结果加载失败：{resultError}</div>
          ) : (
            <table className="bb-table bb-table-dense">
              <colgroup>
                <col className="w-[46%]" />
                <col className="w-[27%]" />
                <col className="w-[27%]" />
              </colgroup>
              <thead>
                <tr>
                  <th>指标分类 / 指标</th>
                  <th className="bb-cell-number">26年基准情景</th>
                  <th className="bb-cell-number">26年模拟测算（利润变动）</th>
                </tr>
              </thead>
              <tbody>
                {groupedResult.profit.length === 0 && groupedResult.risk.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-6 text-center text-[var(--bb-text-muted)]">
                      暂无结果，请先选择参数、输入模拟情景值并点击“开始计算”
                    </td>
                  </tr>
                ) : (
                  <>
                    <tr className="bg-[var(--bb-primary-soft)]">
                      <td className="font-medium text-[var(--bb-text-strong)]">盈利指标</td>
                      <td />
                      <td />
                    </tr>
                    {groupedResult.profit.map((r) => (
                      <tr key={`p-${r.indicator_code}`} className="hover:bg-gray-50">
                        {(() => {
                          const isSummary = r.indicator_code.startsWith("PROFIT_");
                          const isRevenueComponent = REVENUE_COMPONENT_CODES.has(r.indicator_code);
                          const isInterestIncomeChild = INTEREST_INCOME_COMPONENT_CODES.has(r.indicator_code);
                          const isInterestIncomeProductChild = r.indicator_code.startsWith(INTEREST_INCOME_PRODUCT_COMPONENT_PREFIX);
                          const isInterestIncomeFactorChild =
                            r.indicator_code.startsWith(INTEREST_INCOME_PRODUCT_COMPONENT_PREFIX) &&
                            r.indicator_code.includes("::FACTOR_");
                          const isRiskCostProductChild = r.indicator_code.startsWith(RISK_COST_BASE_PRODUCT_COMPONENT_PREFIX);
                          const isRiskCostFactorChild =
                            r.indicator_code.startsWith(RISK_COST_BASE_PRODUCT_COMPONENT_PREFIX) &&
                            r.indicator_code.includes("::FACTOR_");
                          const isFeeIncomeChild = FEE_INCOME_COMPONENT_CODES.has(r.indicator_code);
                          const isImpairmentComponent = IMPAIRMENT_COMPONENT_CODES.has(r.indicator_code);
                          const isLoanRiskCostChild = LOAN_RISK_COST_COMPONENT_CODES.has(r.indicator_code);
                          const isRevenueDeepChild = isInterestIncomeChild || isFeeIncomeChild;
                          const isSubComponent = isRevenueComponent || isImpairmentComponent;
                          const cellClass = isSummary
                            ? "text-gray-700 font-semibold pl-3"
                            : isInterestIncomeFactorChild
                              ? "text-gray-600 pl-24"
                            : isRiskCostFactorChild
                              ? "text-gray-600 pl-24"
                            : isInterestIncomeProductChild
                              ? "text-gray-700 font-medium pl-20"
                            : isRiskCostProductChild
                              ? "text-gray-700 font-medium pl-20"
                            : isRevenueDeepChild
                              ? "text-gray-700 pl-14"
                            : isLoanRiskCostChild
                              ? "text-gray-700 pl-14"
                            : isSubComponent
                              ? "text-gray-700 pl-10"
                              : "text-gray-700 pl-6";
                          const displayName =
                            isInterestIncomeProductChild && r.indicator_name.includes("开鑫贷单品")
                              ? `其中：${r.indicator_name}`
                              : r.indicator_name;
                          const label = isSummary
                            ? displayName
                            : isInterestIncomeFactorChild
                              ? `▫ ${displayName}`
                            : isRiskCostFactorChild
                              ? `▫ ${displayName}`
                            : isInterestIncomeProductChild
                              ? `▪ ${displayName}`
                            : isRiskCostProductChild
                              ? `▪ ${displayName}`
                            : isRevenueDeepChild
                              ? `◦ ${displayName}`
                            : isLoanRiskCostChild
                              ? `◦ ${displayName}`
                            : isSubComponent
                              ? `· ${displayName}`
                              : `- ${displayName}`;
                          return <td className={cellClass}>{label}</td>;
                        })()}
                        <td className="bb-cell-number">{formatScenarioValue(r.baseline_2026, r.value_type)}</td>
                        <td className="bb-cell-number">{formatScenarioValue(r.simulation_2026, r.value_type)}</td>
                      </tr>
                    ))}
                    <tr className="bg-[var(--bb-danger-soft)]">
                      <td className="font-medium text-[var(--bb-text-strong)]">风险指标</td>
                      <td />
                      <td />
                    </tr>
                    {groupedResult.risk.map((r) => (
                      <tr key={`r-${r.indicator_code}`}>
                        <td className="pl-6">- {r.indicator_name}</td>
                        <td className="bb-cell-number">{formatScenarioValue(r.baseline_2026, r.value_type)}</td>
                        <td className="bb-cell-number">{formatScenarioValue(r.simulation_2026, r.value_type)}</td>
                      </tr>
                    ))}
                  </>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
