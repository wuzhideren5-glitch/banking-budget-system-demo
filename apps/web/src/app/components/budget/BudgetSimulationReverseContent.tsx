import { useEffect, useMemo, useState } from "react";
import { Calculator, ChevronDown, Database, Search, SlidersHorizontal } from "lucide-react";
import { listOrgProductRuntimeProducts, type OrgProductRuntimeProductDto } from "@/lib/expense/masterDataApi";
import {
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

type ReverseTargetType = "NET_PROFIT" | "PROVISION_COVERAGE";
type ReverseOutputKey = SimulationParamKey | "PROFIT_NET" | "RISK_NPL_RATE" | "PROVISION_COVERAGE";

type OutputMeta = {
  key: ReverseOutputKey;
  label: string;
  productSelectable: boolean;
};

const SIMULATION_FACTOR_OUTPUTS: OutputMeta[] = [
  { key: "MGMT_LOAN_EOY", label: "管理贷款时点规模", productSelectable: true },
  { key: "LOAN_YIELD_RATE", label: "贷款收益率", productSelectable: true },
  { key: "UNION_LOAN_YIELD_RATE", label: "联合贷款收益率", productSelectable: true },
  { key: "RISK_COST_RATE", label: "风险成本率", productSelectable: true },
];

const NET_PROFIT_OUTPUTS: OutputMeta[] = [
  ...SIMULATION_FACTOR_OUTPUTS,
  { key: "PROVISION_COVERAGE", label: "拨备覆盖率", productSelectable: false },
];

const COVERAGE_OUTPUTS: OutputMeta[] = [
  { key: "PROFIT_NET", label: "净利润", productSelectable: false },
  { key: "RISK_NPL_RATE", label: "不良贷款率", productSelectable: false },
];

const PERCENT_OUTPUT_KEYS = new Set<ReverseOutputKey>([
  "LOAN_YIELD_RATE",
  "UNION_LOAN_YIELD_RATE",
  "RISK_COST_RATE",
  "RISK_NPL_RATE",
  "PROVISION_COVERAGE",
]);

const SIM_INTEREST_NET = "03.02.01.01.001";
const SIM_INTEREST_INCOME = "03.01.01.01.025";
const SIM_INTEREST_EXPENSE = "04.01.06.01.012";
const SIM_FEE_NET = "03.04.01.01.003";
const SIM_FEE_INCOME = "03.04.01.01.001";
const SIM_FEE_EXPENSE = "04.03.01.01.004";
const SIM_OTHER_REVENUE = "03.09.05";
const SIM_IMPAIRMENT = "06.01.01.01.001";
const SIM_LOAN_RISK_COST = "06.01.01.02.007";
const SIM_RISK_COST_BASE = "06.01.01.01.008";
const SIM_RISK_COST_GAP = "06.01.01.01.004";
const SIM_RISK_COST_PEER = "06.01.01.02.009";
const SIM_RISK_COST_OTHER = "06.01.01.02.003";

const REVENUE_COMPONENT_CODES = new Set([SIM_INTEREST_NET, SIM_FEE_NET, SIM_OTHER_REVENUE]);
const INTEREST_INCOME_COMPONENT_PREFIX = `${SIM_INTEREST_INCOME}::`;
const RISK_COST_BASE_PRODUCT_COMPONENT_PREFIX = `${SIM_RISK_COST_BASE}::`;
const DEEP_COMPONENT_CODES = new Set([SIM_INTEREST_INCOME, SIM_INTEREST_EXPENSE, SIM_FEE_INCOME, SIM_FEE_EXPENSE]);
const IMPAIRMENT_COMPONENT_CODES = new Set([SIM_LOAN_RISK_COST, SIM_RISK_COST_PEER, SIM_RISK_COST_OTHER]);
const LOAN_RISK_COST_COMPONENT_CODES = new Set([SIM_RISK_COST_BASE, SIM_RISK_COST_GAP]);

function isSimulationFactorOutputKey(key: ReverseOutputKey): key is SimulationParamKey {
  return key === "MGMT_LOAN_EOY" || key === "LOAN_YIELD_RATE" || key === "UNION_LOAN_YIELD_RATE" || key === "RISK_COST_RATE";
}

export function BudgetSimulationReverseContent() {
  const [loanProducts, setLoanProducts] = useState<OrgProductRuntimeProductDto[]>([]);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [selectorKeyword, setSelectorKeyword] = useState("");
  const [targetType, setTargetType] = useState<ReverseTargetType>("NET_PROFIT");
  const [targetNetProfit, setTargetNetProfit] = useState("");
  const [targetProvisionCoverage, setTargetProvisionCoverage] = useState("");
  const [selectedOutputs, setSelectedOutputs] = useState<Set<ReverseOutputKey>>(
    new Set<ReverseOutputKey>(["MGMT_LOAN_EOY", "RISK_COST_RATE"]),
  );
  const [selectedOutputProducts, setSelectedOutputProducts] = useState<Record<SimulationParamKey, Set<string>>>({
    MGMT_LOAN_EOY: new Set(),
    LOAN_YIELD_RATE: new Set(),
    UNION_LOAN_YIELD_RATE: new Set(),
    RISK_COST_RATE: new Set(),
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [baselineByRowKey, setBaselineByRowKey] = useState<Record<string, SimulationBaselineRowDto>>({});
  const [reverseValueByRowKey, setReverseValueByRowKey] = useState<Record<string, number>>({});
  const [resultLoading, setResultLoading] = useState(false);
  const [resultRows, setResultRows] = useState<SimulationResultRowDto[]>([]);
  const [resultError, setResultError] = useState("");
  const [reverseHint, setReverseHint] = useState("");

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError("");
      try {
        const [allProducts, baselineResult] = await Promise.all([
          listOrgProductRuntimeProducts(),
          fetchSimulationResult([]),
        ]);
        const loans = allProducts
          .filter((p) => String(p.product_name || "").includes("贷"))
          .sort((a, b) => a.product_code.localeCompare(b.product_code, "zh-CN"));
        setLoanProducts(loans);
        setResultRows(baselineResult);
      } catch (e) {
        setError(e instanceof Error ? e.message : "初始化倒算数据失败");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    setSelectedOutputs(
      targetType === "NET_PROFIT"
        ? new Set<ReverseOutputKey>(["MGMT_LOAN_EOY", "RISK_COST_RATE"])
        : new Set<ReverseOutputKey>(["PROFIT_NET", "RISK_NPL_RATE"]),
    );
    setReverseValueByRowKey({});
    setReverseHint("");
    setResultError("");
  }, [targetType]);

  const options = targetType === "NET_PROFIT" ? NET_PROFIT_OUTPUTS : COVERAGE_OUTPUTS;

  const selectedSummary = useMemo(() => {
    const chunks: string[] = [];
    for (const opt of options) {
      if (!selectedOutputs.has(opt.key)) continue;
      if (opt.productSelectable && isSimulationFactorOutputKey(opt.key)) {
        const factorKey = opt.key;
        const names = loanProducts
          .filter((prod) => selectedOutputProducts[factorKey].has(prod.product_code))
          .map((prod) => prod.product_name);
        chunks.push(names.length > 0 ? `${opt.label}（${names.join("、")}）` : opt.label);
      } else {
        chunks.push(opt.label);
      }
    }
    return chunks;
  }, [loanProducts, options, selectedOutputProducts, selectedOutputs]);

  const selectedFactorRows = useMemo(() => {
    const rows: Array<{
      rowKey: string;
      indicator_code: SimulationParamKey;
      indicator_label: string;
      product_code: string | null;
      product_label: string | null;
    }> = [];
    if (targetType !== "NET_PROFIT") return rows;
    for (const opt of SIMULATION_FACTOR_OUTPUTS) {
      if (!selectedOutputs.has(opt.key)) continue;
      const key = opt.key as SimulationParamKey;
      const productCodes = Array.from(selectedOutputProducts[key]);
      if (productCodes.length === 0) {
        rows.push({
          rowKey: `${key}|`,
          indicator_code: key,
          indicator_label: opt.label,
          product_code: null,
          product_label: null,
        });
        continue;
      }
      for (const pc of productCodes) {
        const product = loanProducts.find((p) => p.product_code === pc);
        rows.push({
          rowKey: `${key}|${pc}`,
          indicator_code: key,
          indicator_label: opt.label,
          product_code: pc,
          product_label: product ? `${product.product_code} ${product.product_name}` : pc,
        });
      }
    }
    return rows;
  }, [loanProducts, selectedOutputProducts, selectedOutputs, targetType]);

  useEffect(() => {
    const loadBaseline = async () => {
      if (selectedFactorRows.length === 0) {
        setBaselineByRowKey({});
        return;
      }
      setBaselineLoading(true);
      try {
        const resp = await fetchSimulationBaseline(
          selectedFactorRows.map((row) => ({
            indicator_code: row.indicator_code,
            product_code: row.product_code,
          })),
        );
        const next: Record<string, SimulationBaselineRowDto> = {};
        for (const row of selectedFactorRows) {
          const hit = resp.find(
            (item) => item.indicator_code === row.indicator_code && (item.product_code ?? null) === (row.product_code ?? null),
          );
          if (hit) next[row.rowKey] = hit;
        }
        setBaselineByRowKey(next);
      } catch {
        setBaselineByRowKey({});
      } finally {
        setBaselineLoading(false);
      }
    };
    void loadBaseline();
  }, [selectedFactorRows]);

  const groupedResult = useMemo(() => {
    const profit = resultRows.filter((r) => r.metric_group === "盈利性指标");
    const risk = resultRows.filter((r) => r.metric_group === "风险指标");
    return { profit, risk };
  }, [resultRows]);

  const baselineNetProfit = groupedResult.profit.find((r) => r.indicator_code === "PROFIT_NET")?.baseline_2026 ?? 0;
  const baselineNplBalance = groupedResult.risk.find((r) => r.indicator_code === "RISK_NPL_BALANCE")?.baseline_2026 ?? 0;
  const baselineProvision = groupedResult.risk.find((r) => r.indicator_code === "RISK_PROVISION_BALANCE")?.baseline_2026 ?? 0;
  const baselineCoverage = Math.abs(baselineNplBalance) > 1e-9 ? baselineProvision / baselineNplBalance : null;
  const simulationCoverage = useMemo(() => {
    const npl = groupedResult.risk.find((r) => r.indicator_code === "RISK_NPL_BALANCE")?.simulation_2026 ?? 0;
    const provision = groupedResult.risk.find((r) => r.indicator_code === "RISK_PROVISION_BALANCE")?.simulation_2026 ?? 0;
    return Math.abs(npl) > 1e-9 ? provision / npl : null;
  }, [groupedResult.risk]);

  const parseNumeric = (raw: string): number | null => {
    const value = Number.parseFloat(String(raw || "").replace(/[%％,\s]/g, ""));
    return Number.isFinite(value) ? value : null;
  };

  const formatValue = (value: number, valueType: string): string => {
    if (valueType === "百分比") return `${(value * 100).toFixed(2)}%`;
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  };

  const outputValueType = (key: ReverseOutputKey): string => (PERCENT_OUTPUT_KEYS.has(key) ? "百分比" : "金额");

  const runReverse = async () => {
    setResultLoading(true);
    setResultError("");
    setReverseHint("");
    try {
      const payload: SimulationInputItemDto[] = [];
      const nextReverseValues: Record<string, number> = {};
      if (targetType === "NET_PROFIT") {
        const target = parseNumeric(targetNetProfit);
        if (target === null) {
          throw new Error("请输入有效的净利润目标值");
        }
        const ratio = Math.abs(baselineNetProfit) > 1e-9 ? target / baselineNetProfit : 1;
        for (const row of selectedFactorRows) {
          const base = baselineByRowKey[row.rowKey]?.baseline_value ?? 0;
          let next = base;
          if (row.indicator_code === "MGMT_LOAN_EOY") {
            next = Math.max(0, base * ratio);
          } else if (row.indicator_code === "LOAN_YIELD_RATE" || row.indicator_code === "UNION_LOAN_YIELD_RATE") {
            next = Math.max(0, Math.min(1, base * (1 + (ratio - 1) * 0.5)));
          } else if (row.indicator_code === "RISK_COST_RATE") {
            next = Math.max(0, Math.min(1, base * Math.max(0.2, Math.min(1.8, 1 - (ratio - 1) * 0.25))));
          }
          nextReverseValues[row.rowKey] = next;
          payload.push({
            indicator_code: row.indicator_code,
            product_code: row.product_code,
            simulate_value: next,
          });
        }
        payload.push({ indicator_code: "PROFIT_NET", product_code: null, simulate_value: target });
        setReverseHint("已按净利润目标倒算并输出所选变量建议值。");
      } else {
        const targetPct = parseNumeric(targetProvisionCoverage);
        if (targetPct === null || targetPct <= 0) {
          throw new Error("请输入有效且大于 0 的拨备覆盖率目标");
        }
        const targetRate = targetPct > 1 ? targetPct / 100 : targetPct;
        if (Math.abs(baselineNplBalance) <= 1e-9) {
          throw new Error("当前基准不良余额为 0，无法按覆盖率倒算");
        }
        const targetProvision = baselineNplBalance * targetRate;
        const baseLoanRiskCost = groupedResult.profit.find((r) => r.indicator_code === SIM_LOAN_RISK_COST)?.baseline_2026 ?? 0;
        const baseImpairment = groupedResult.profit.find((r) => r.indicator_code === SIM_IMPAIRMENT)?.baseline_2026 ?? 0;
        const delta = targetProvision - baselineProvision;
        payload.push({ indicator_code: "RISK_PROVISION_BALANCE", product_code: null, simulate_value: targetProvision });
        payload.push({ indicator_code: SIM_LOAN_RISK_COST, product_code: null, simulate_value: baseLoanRiskCost + delta });
        payload.push({ indicator_code: SIM_IMPAIRMENT, product_code: null, simulate_value: baseImpairment + delta });
        setReverseHint("已按拨备覆盖率目标倒算，并联动风险成本与拨备余额口径。");
      }
      const resp = await fetchSimulationResult(payload);
      setReverseValueByRowKey(nextReverseValues);
      setResultRows(resp);
    } catch (e) {
      setResultError(e instanceof Error ? e.message : "倒算失败");
    } finally {
      setResultLoading(false);
    }
  };

  const toggleOutput = (key: ReverseOutputKey, checked: boolean) => {
    setSelectedOutputs((prev) => {
      const next = new Set(prev);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
    if (!checked && isSimulationFactorOutputKey(key)) {
      setSelectedOutputProducts((prev) => ({ ...prev, [key]: new Set() }));
    }
  };

  const toggleProduct = (key: SimulationParamKey, productCode: string, checked: boolean) => {
    setSelectedOutputs((prev) => new Set(prev).add(key));
    setSelectedOutputProducts((prev) => {
      const next = new Set(prev[key]);
      if (checked) next.add(productCode);
      else next.delete(productCode);
      return { ...prev, [key]: next };
    });
  };

  const normalizedKeyword = selectorKeyword.trim().toLowerCase();

  const fixedOutputRows = options.filter((opt) => selectedOutputs.has(opt.key) && !opt.productSelectable);

  return (
    <div className="bb-page overflow-auto">
      <div className="bb-page-header">
        <div className="bb-page-title">
          <SlidersHorizontal className="w-4 h-4 text-[var(--bb-primary)]" />
          模拟测算（倒算）
        </div>
        <div className="flex items-center gap-2">
          <select
            className="bb-select h-10"
            value={targetType}
            onChange={(e) => setTargetType(e.target.value as ReverseTargetType)}
          >
            <option value="NET_PROFIT">净利润目标</option>
            <option value="PROVISION_COVERAGE">拨备覆盖率目标</option>
          </select>
          <input
            className="bb-input h-10 w-48"
            value={targetType === "NET_PROFIT" ? targetNetProfit : targetProvisionCoverage}
            onChange={(e) => (targetType === "NET_PROFIT" ? setTargetNetProfit(e.target.value) : setTargetProvisionCoverage(e.target.value))}
            placeholder={targetType === "NET_PROFIT" ? "输入净利润目标" : "输入覆盖率，如150%"}
          />
          <button type="button" onClick={() => setSelectorOpen((v) => !v)} className="bb-btn bb-btn-secondary h-10 min-w-[320px] max-w-[520px]">
            <Search className="w-4 h-4 text-[var(--bb-text-muted)]" />
            <span className="truncate text-left flex-1">{selectedSummary.length > 0 ? selectedSummary.join("、") : "请选择倒算输出变量"}</span>
            <ChevronDown className={`w-3.5 h-3.5 text-[var(--bb-text-muted)] transition-transform ${selectorOpen ? "rotate-180" : ""}`} />
          </button>
          <button type="button" onClick={runReverse} disabled={resultLoading} className="bb-btn bb-btn-primary h-10">
            <Calculator className="w-4 h-4" />
            {resultLoading ? "倒算中..." : "开始倒算"}
          </button>
        </div>
      </div>

      {selectorOpen && (
        <div className="bb-panel w-[720px] max-w-full shadow-sm">
          <div className="bb-panel-header">
            <span className="bb-panel-title">选择倒算输出变量</span>
            <div className="ml-auto w-[320px] max-w-full flex items-center gap-2">
              <Search className="w-4 h-4 text-[var(--bb-text-muted)]" />
              <input value={selectorKeyword} onChange={(e) => setSelectorKeyword(e.target.value)} placeholder="搜索变量..." className="bb-input w-full" />
            </div>
          </div>
          <div className="h-[360px] overflow-auto p-2 space-y-2">
            {options.map((opt) => {
              const isFactor = opt.productSelectable && isSimulationFactorOutputKey(opt.key);
              const childSet = isFactor ? selectedOutputProducts[opt.key as SimulationParamKey] : new Set<string>();
              const filteredProducts = loanProducts.filter((prod) => {
                if (!normalizedKeyword) return true;
                return (
                  opt.label.toLowerCase().includes(normalizedKeyword) ||
                  prod.product_code.toLowerCase().includes(normalizedKeyword) ||
                  String(prod.product_name || "").toLowerCase().includes(normalizedKeyword)
                );
              });
              if (normalizedKeyword && !opt.label.toLowerCase().includes(normalizedKeyword) && isFactor && filteredProducts.length === 0) return null;
              return (
                <div key={opt.key} className="bb-card p-0">
                  <div className="px-2 py-1.5 bg-[var(--bb-primary-soft)] flex items-center gap-2">
                    <label className="flex items-center gap-2 text-xs text-[var(--bb-text)]">
                      <input type="checkbox" checked={selectedOutputs.has(opt.key)} onChange={(e) => toggleOutput(opt.key, e.target.checked)} />
                      <span className="font-medium">{opt.label}</span>
                    </label>
                  </div>
                  {isFactor ? (
                    <div className="p-2 border-t border-[var(--bb-border-soft)]">
                      <div className="text-[11px] text-[var(--bb-text-muted)] mb-1">二级变量：贷款产品</div>
                      <div className="grid grid-cols-2 gap-1">
                        {filteredProducts.map((prod) => (
                          <label key={`${opt.key}-${prod.product_code}`} className="flex items-center gap-2 text-xs text-[var(--bb-text)] px-1 py-1 rounded hover:bg-[var(--bb-bg-subtle)]">
                            <input type="checkbox" checked={childSet.has(prod.product_code)} onChange={(e) => toggleProduct(opt.key as SimulationParamKey, prod.product_code, e.target.checked)} />
                            <Database className="w-3.5 h-3.5 text-[var(--bb-success)] shrink-0" />
                            <span className="font-mono text-[11px] text-[var(--bb-text-muted)]">{prod.product_code}</span>
                            <span className="truncate">{prod.product_name}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {loading ? <div className="bb-status-banner m-3">正在初始化倒算数据...</div> : null}
      {error ? <div className="bb-status-banner bb-status-banner-danger m-3">加载失败：{error}</div> : null}
      {reverseHint ? <div className="bb-status-banner bb-status-banner-info">{reverseHint}</div> : null}
      {resultError ? <div className="bb-status-banner bb-status-banner-danger">倒算失败：{resultError}</div> : null}

      <div className="bb-panel">
        <div className="bb-panel-header">
          <span className="bb-panel-title">倒算输出变量</span>
        </div>
        <div className="p-3">
          <table className="bb-table bb-table-dense">
            <colgroup>
              <col className="w-[46%]" />
              <col className="w-[27%]" />
              <col className="w-[27%]" />
            </colgroup>
            <thead>
              <tr>
                <th>输出变量</th>
                <th className="bb-cell-number">26年基准</th>
                <th className="bb-cell-number">倒算结果</th>
              </tr>
            </thead>
            <tbody>
              {selectedFactorRows.length === 0 && fixedOutputRows.length === 0 ? (
                <tr>
                  <td colSpan={3} className="py-6 text-center text-[var(--bb-text-muted)]">请选择倒算输出变量</td>
                </tr>
              ) : (
                <>
                  {selectedFactorRows.map((row) => {
                    const baseline = baselineByRowKey[row.rowKey];
                    const valueType = baseline?.value_type ?? outputValueType(row.indicator_code);
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
                        <td className="bb-cell-number">{baselineLoading ? "加载中..." : baseline ? formatValue(baseline.baseline_value, valueType) : "--"}</td>
                        <td className="bb-cell-number">{reverseValueByRowKey[row.rowKey] !== undefined ? formatValue(reverseValueByRowKey[row.rowKey], valueType) : "--"}</td>
                      </tr>
                    );
                  })}
                  {fixedOutputRows.map((opt) => {
                    const row =
                      opt.key === "PROFIT_NET"
                        ? groupedResult.profit.find((r) => r.indicator_code === "PROFIT_NET")
                        : opt.key === "RISK_NPL_RATE"
                          ? groupedResult.risk.find((r) => r.indicator_code === "RISK_NPL_RATE")
                          : null;
                    const baseline = opt.key === "PROVISION_COVERAGE" ? baselineCoverage : row?.baseline_2026;
                    const simulation = opt.key === "PROVISION_COVERAGE" ? simulationCoverage : row?.simulation_2026;
                    const valueType = outputValueType(opt.key);
                    return (
                      <tr key={opt.key}>
                        <td>{opt.label}</td>
                        <td className="bb-cell-number">{baseline === null || baseline === undefined ? "--" : formatValue(baseline, valueType)}</td>
                        <td className="bb-cell-number">{simulation === null || simulation === undefined ? "--" : formatValue(simulation, valueType)}</td>
                      </tr>
                    );
                  })}
                </>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bb-panel">
        <div className="bb-panel-header">
          <span className="bb-panel-title">倒算结果</span>
        </div>
        <div className="p-3">
          <table className="bb-table bb-table-dense">
            <colgroup>
              <col className="w-[46%]" />
              <col className="w-[27%]" />
              <col className="w-[27%]" />
            </colgroup>
            <thead>
              <tr>
                <th>指标分类 / 指标</th>
                <th className="bb-cell-number">26年基准</th>
                <th className="bb-cell-number">倒算结果</th>
              </tr>
            </thead>
            <tbody>
              {groupedResult.profit.length === 0 && groupedResult.risk.length === 0 ? (
                <tr>
                  <td colSpan={3} className="py-6 text-center text-[var(--bb-text-muted)]">暂无结果，请输入目标并点击“开始倒算”</td>
                </tr>
              ) : (
                <>
                  <tr className="bg-[var(--bb-primary-soft)]">
                    <td className="font-medium text-[var(--bb-text-strong)]">盈利指标</td>
                    <td />
                    <td />
                  </tr>
                  {groupedResult.profit.map((row) => {
                    const isSummary = row.indicator_code.startsWith("PROFIT_");
                    const isInterestProduct = row.indicator_code.startsWith(INTEREST_INCOME_COMPONENT_PREFIX);
                    const isInterestFactor = isInterestProduct && row.indicator_code.includes("::FACTOR_");
                    const isRiskProduct = row.indicator_code.startsWith(RISK_COST_BASE_PRODUCT_COMPONENT_PREFIX);
                    const isRiskFactor = isRiskProduct && row.indicator_code.includes("::FACTOR_");
                    const isDeep = DEEP_COMPONENT_CODES.has(row.indicator_code);
                    const isSub = REVENUE_COMPONENT_CODES.has(row.indicator_code) || IMPAIRMENT_COMPONENT_CODES.has(row.indicator_code) || LOAN_RISK_COST_COMPONENT_CODES.has(row.indicator_code);
                    const cellClass = isSummary
                      ? "text-gray-700 font-semibold pl-3"
                      : isInterestFactor || isRiskFactor
                        ? "text-gray-600 pl-24"
                        : isInterestProduct || isRiskProduct
                          ? "text-gray-700 font-medium pl-20"
                          : isDeep
                            ? "text-gray-700 pl-14"
                            : isSub
                              ? "text-gray-700 pl-10"
                              : "text-gray-700 pl-6";
                    return (
                      <tr key={`p-${row.indicator_code}`}>
                        <td className={cellClass}>- {row.indicator_name}</td>
                        <td className="bb-cell-number">{formatValue(row.baseline_2026, row.value_type)}</td>
                        <td className="bb-cell-number">{formatValue(row.simulation_2026, row.value_type)}</td>
                      </tr>
                    );
                  })}
                  <tr className="bg-[var(--bb-danger-soft)]">
                    <td className="font-medium text-[var(--bb-text-strong)]">风险指标</td>
                    <td />
                    <td />
                  </tr>
                  {groupedResult.risk.map((row) => (
                    <tr key={`r-${row.indicator_code}`}>
                      <td className="pl-6">- {row.indicator_name}</td>
                      <td className="bb-cell-number">{formatValue(row.baseline_2026, row.value_type)}</td>
                      <td className="bb-cell-number">{formatValue(row.simulation_2026, row.value_type)}</td>
                    </tr>
                  ))}
                </>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
