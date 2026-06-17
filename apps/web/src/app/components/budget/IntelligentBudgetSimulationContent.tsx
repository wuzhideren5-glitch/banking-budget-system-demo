import { useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  ChevronDown,
  Download,
  Eye,
  Play,
  RefreshCw,
  Target,
  X,
} from "lucide-react";
import { downloadBlob } from "@/lib/shared/api";
import {
  createIntelligentBudgetTask,
  exportIntelligentBudgetTask,
  parseIntelligentBudgetTarget,
  type IntelligentBudgetSolutionDto,
  type IntelligentBudgetTaskDto,
  type ParsedIntelligentBudgetTargetDto,
} from "@/lib/budget/intelligentBudgetSimulationApi";

const DEFAULT_TARGET = "净利润增长10%，不良率控制在1.2%以内，规模不要太冒进，风险不要明显上升";

const BALANCE_ROWS = [
  ["loan_balance", "贷款余额", "amount"],
  ["interest_earning_assets", "生息资产", "amount"],
  ["provision_balance", "拨备余额", "amount"],
  ["excess_provision", "超额拨备", "amount"],
] as const;

const INCOME_ROWS = [
  ["operating_income", "营业收入", "amount"],
  ["net_interest_income", "净利息收入", "amount"],
  ["operating_expense", "费用", "amount"],
  ["impairment_loss", "拨备/减值", "amount"],
  ["net_profit", "净利润", "amount"],
] as const;

const RISK_ROWS = [
  ["npl_balance", "不良余额", "amount"],
  ["npl_ratio", "不良率", "percent"],
  ["risk_cost_rate", "风险成本率", "percent"],
] as const;

function formatPercent(value: number, digits = 2): string {
  return `${(Number(value || 0) * 100).toFixed(digits)}%`;
}

function formatSignedPercent(value: number, digits = 1): string {
  const n = Number(value || 0) * 100;
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

function formatBp(value: number): string {
  const n = Number(value || 0);
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}bp`;
}

function formatAmount(value: number): string {
  return `${Number(value || 0).toFixed(2)}亿`;
}

function formatValue(value: number, kind: "amount" | "percent"): string {
  return kind === "percent" ? formatPercent(value) : formatAmount(value);
}

function formatChange(current: number, baseline: number, kind: "amount" | "percent"): string {
  const delta = Number(current || 0) - Number(baseline || 0);
  if (kind === "percent") return `${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(2)}pct`;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}亿`;
}

function statusLabel(status: IntelligentBudgetTaskDto["status"] | null): string {
  if (status === "completed") return "已形成预算结果";
  if (status === "negotiation_required") return "需要协商";
  return "待确认";
}

function roleLabel(solution: IntelligentBudgetSolutionDto): string {
  if (solution.display_role === "baseline") return "基础方案";
  if (solution.display_role === "recommended") return "综合推荐";
  if (solution.display_role === "risk_first") return "风险优先";
  if (solution.display_role === "profit_first") return "利润/结构优先";
  return "备选方案";
}

function coreActionText(solution: IntelligentBudgetSolutionDto): Array<[string, string]> {
  const factors = solution.factor_movements || {};
  return [
    ["规模", formatSignedPercent(Number(factors.scale_growth || 0))],
    ["收益率", formatBp(Number(factors.yield_bp || 0))],
    ["费用", formatSignedPercent(Number(factors.expense_growth || 0))],
    ["风险", String(solution.core_actions?.["风险"] || "-")],
  ];
}

function pickFeaturedSolutions(task: IntelligentBudgetTaskDto | null): IntelligentBudgetSolutionDto[] {
  if (!task) return [];
  const picked: IntelligentBudgetSolutionDto[] = [task.baseline_solution];
  const roles = ["recommended", "risk_first", "profit_first"] as const;
  for (const role of roles) {
    const item = task.solutions.find((solution) => solution.display_role === role);
    if (item && !picked.some((solution) => solution.solution_id === item.solution_id)) picked.push(item);
  }
  for (const item of task.solutions) {
    if (picked.length >= 4) break;
    if (!picked.some((solution) => solution.solution_id === item.solution_id)) picked.push(item);
  }
  return picked;
}

function MetricCard({ label, value, muted = false }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-[var(--bb-text-muted)]">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold ${muted ? "text-[var(--bb-text)]" : "text-[var(--bb-text-strong)]"}`}>{value}</div>
    </div>
  );
}

function ResultCard({
  solution,
  selected,
  onSelect,
  onDetail,
}: {
  solution: IntelligentBudgetSolutionDto;
  selected: boolean;
  onSelect: () => void;
  onDetail: () => void;
}) {
  const snap = solution.budget_snapshot || {};
  return (
    <div className={`bb-card p-3 ${selected ? "border-[var(--bb-primary)] bg-sky-50" : ""}`}>
      <button type="button" className="w-full text-left" onClick={onSelect}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[11px] font-medium text-[var(--bb-primary)]">{roleLabel(solution)}</div>
            <div className="mt-1 text-sm font-semibold text-[var(--bb-text-strong)] truncate">{solution.name}</div>
          </div>
          {solution.rank > 0 && <div className="text-[11px] text-[var(--bb-text-muted)]">#{solution.rank}</div>}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <MetricCard label="净利润" value={formatAmount(snap.net_profit)} />
          <MetricCard label="净利润增速" value={formatSignedPercent(solution.net_profit_growth)} />
          <MetricCard label="贷款余额" value={formatAmount(snap.loan_balance)} />
          <MetricCard label="不良率" value={formatPercent(solution.npl_ratio)} />
        </div>
        {solution.display_role !== "baseline" && (
          <div className="mt-3 border-t border-[var(--bb-border-soft)] pt-2 text-[11px] text-[var(--bb-text)] space-y-1">
            {coreActionText(solution).slice(0, 3).map(([label, value]) => (
              <div key={label} className="flex gap-2">
                <span className="w-12 shrink-0 text-[var(--bb-text-muted)]">{label}</span>
                <span className="truncate">{value}</span>
              </div>
            ))}
          </div>
        )}
      </button>
      <button type="button" className="bb-btn bb-btn-secondary h-8 mt-3 w-full" onClick={onDetail}>
        <Eye className="w-3.5 h-3.5" />
        查看传导
      </button>
    </div>
  );
}

function StatementTable({
  title,
  rows,
  baseline,
  current,
}: {
  title: string;
  rows: readonly (readonly [string, string, "amount" | "percent"])[];
  baseline: IntelligentBudgetSolutionDto;
  current: IntelligentBudgetSolutionDto;
}) {
  return (
    <div className="bb-panel min-w-0">
      <div className="bb-panel-header">
        <span className="bb-panel-title">{title}</span>
      </div>
      <div className="p-3 overflow-auto">
        <table className="bb-table bb-table-dense w-full table-fixed text-[11px]">
          <thead>
            <tr>
              <th className="truncate">指标</th>
              <th className="truncate">基础方案</th>
              <th className="truncate">当前方案</th>
              <th className="truncate">变化</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([field, label, kind]) => {
              const baseValue = Number(baseline.budget_snapshot?.[field] || 0);
              const currentValue = Number(current.budget_snapshot?.[field] || 0);
              return (
                <tr key={field}>
                  <td className="truncate" title={label}>{label}</td>
                  <td className="truncate" title={formatValue(baseValue, kind)}>{formatValue(baseValue, kind)}</td>
                  <td className="truncate" title={formatValue(currentValue, kind)}>{formatValue(currentValue, kind)}</td>
                  <td className="truncate" title={formatChange(currentValue, baseValue, kind)}>{formatChange(currentValue, baseValue, kind)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DetailModal({
  solution,
  baseline,
  parsed,
  onClose,
}: {
  solution: IntelligentBudgetSolutionDto;
  baseline: IntelligentBudgetSolutionDto;
  parsed: ParsedIntelligentBudgetTargetDto | null;
  onClose: () => void;
}) {
  const bridge = solution.risk_bridge || {};
  return (
    <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4">
      <div className="bg-white border border-[var(--bb-border)] shadow-xl rounded-lg w-[min(1080px,calc(100vw-32px))] max-h-[88vh] overflow-hidden">
        <div className="h-12 px-4 border-b border-[var(--bb-border)] flex items-center justify-between">
          <div className="font-semibold text-[var(--bb-text-strong)]">{solution.name}：传导拆解</div>
          <button type="button" className="bb-btn bb-btn-secondary h-8" onClick={onClose}>
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4 overflow-auto max-h-[calc(88vh-48px)] space-y-4 text-xs text-[var(--bb-text)]">
          <div className="grid [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))] gap-3">
            <div className="bb-card p-3">
              <div className="font-medium text-[var(--bb-text-strong)] mb-2">领导目标</div>
              <div>净利润：&gt;= {parsed ? formatPercent(parsed.min_net_profit_growth) : "-"}</div>
              <div>不良率：&lt;= {parsed ? formatPercent(parsed.max_npl_ratio) : "-"}</div>
            </div>
            <div className="bb-card p-3">
              <div className="font-medium text-[var(--bb-text-strong)] mb-2">本方案结果</div>
              <div>净利润：{formatAmount(solution.budget_snapshot.net_profit)}</div>
              <div>不良率：{formatPercent(solution.npl_ratio)}</div>
              <div>超额拨备：{formatAmount(solution.budget_snapshot.excess_provision)}</div>
            </div>
            <div className="bb-card p-3">
              <div className="font-medium text-[var(--bb-text-strong)] mb-2">推荐说明</div>
              <div>{solution.recommendation_reason || "备选经营组合。"}</div>
            </div>
          </div>

          <div className="bb-panel">
            <div className="bb-panel-header">
              <span className="bb-panel-title">风险传导：基准 -&gt; 动作 -&gt; 结果</span>
            </div>
            <div className="p-3 grid [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))] gap-3">
              <div className="bb-card p-3">
                <div className="font-medium mb-2">基准风险状态</div>
                <div>期初不良余额：{formatAmount(bridge.opening_npl_balance)}</div>
                <div>基准新生成不良：{formatAmount(bridge.baseline_new_npl_amount)}</div>
                <div>基准回收清收：{formatAmount(bridge.baseline_recovery_amount)}</div>
              </div>
              <div className="bb-card p-3">
                <div className="font-medium mb-2">本方案动作</div>
                <div>新生成不良压降：{formatPercent(bridge.new_npl_control_rate)}</div>
                <div>回收清收提升：{formatPercent(bridge.recovery_improvement_rate)}</div>
                <div>核销处置：{formatAmount(bridge.writeoff_disposal_amount)}</div>
              </div>
              <div className="bb-card p-3">
                <div className="font-medium mb-2">推导结果</div>
                <div>方案后新生成不良：{formatAmount(bridge.after_new_npl_amount)}</div>
                <div>方案后回收清收：{formatAmount(bridge.after_recovery_amount)}</div>
                <div>期末不良率：{formatPercent(solution.npl_ratio)}</div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 min-[1100px]:grid-cols-2 gap-3">
            <div className="bb-panel">
              <div className="bb-panel-header">
                <span className="bb-panel-title">二层动因</span>
              </div>
              <div className="p-3 space-y-2">
                {coreActionText(solution).map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-3">
                    <span className="text-[var(--bb-text-muted)]">{label}</span>
                    <span className="font-medium text-right">{value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bb-panel">
              <div className="bb-panel-header">
                <span className="bb-panel-title">产品拆解 Top 5</span>
              </div>
              <div className="p-3 space-y-2">
                {solution.top_product_contributions.map((product, idx) => (
                  <div key={product.product_code} className="bb-card p-2">
                    <div className="font-medium text-[var(--bb-text-strong)]">
                      {idx + 1}. {product.product_code} {product.product_name}
                    </div>
                    <div className="mt-1 text-[var(--bb-text-muted)]">
                      贡献 {product.marginal_contribution.toFixed(2)}；规模 {formatSignedPercent(product.scale_growth)}；收益率 {formatBp(product.yield_bp)}
                    </div>
                  </div>
                ))}
                <div className="text-[var(--bb-text-muted)]">其他产品合计贡献：{solution.other_product_contribution.toFixed(2)}</div>
              </div>
            </div>
          </div>

          {solution.solution_id !== baseline.solution_id && (
            <div className="text-[var(--bb-text-muted)]">
              注：基础方案用于对比，不代表目标已达成；当前方案的资产负债、利润和风险结果均相对基础方案展示变化。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function IntelligentBudgetSimulationContent() {
  const [targetText, setTargetText] = useState(DEFAULT_TARGET);
  const [parsed, setParsed] = useState<ParsedIntelligentBudgetTargetDto | null>(null);
  const [task, setTask] = useState<IntelligentBudgetTaskDto | null>(null);
  const [selectedSolutionId, setSelectedSolutionId] = useState("");
  const [detailSolutionId, setDetailSolutionId] = useState("");
  const [showAlternates, setShowAlternates] = useState(false);
  const [loadingAction, setLoadingAction] = useState<"parse" | "solve" | "export" | null>(null);
  const [error, setError] = useState("");

  const featuredSolutions = useMemo(() => pickFeaturedSolutions(task), [task]);
  const selectedSolution = useMemo(() => {
    if (!task) return null;
    const all = [task.baseline_solution, ...task.solutions];
    return all.find((solution) => solution.solution_id === selectedSolutionId) ?? featuredSolutions[1] ?? task.baseline_solution;
  }, [featuredSolutions, selectedSolutionId, task]);
  const detailSolution = useMemo(() => {
    if (!task || !detailSolutionId) return null;
    return [task.baseline_solution, ...task.solutions].find((solution) => solution.solution_id === detailSolutionId) ?? null;
  }, [detailSolutionId, task]);
  const alternateSolutions = useMemo(() => {
    if (!task) return [];
    const featuredIds = new Set(featuredSolutions.map((solution) => solution.solution_id));
    return task.solutions.filter((solution) => !featuredIds.has(solution.solution_id));
  }, [featuredSolutions, task]);

  const handleParse = async () => {
    setLoadingAction("parse");
    setError("");
    setTask(null);
    setSelectedSolutionId("");
    setDetailSolutionId("");
    try {
      const next = await parseIntelligentBudgetTarget(targetText);
      setParsed(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI解析目标失败");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleSolve = async () => {
    setLoadingAction("solve");
    setError("");
    try {
      const next = await createIntelligentBudgetTask(targetText, true);
      setTask(next);
      setParsed(next.parsed_target);
      const featured = pickFeaturedSolutions(next);
      setSelectedSolutionId(featured[1]?.solution_id ?? next.baseline_solution.solution_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "智能模拟求解失败");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleExport = async () => {
    if (!task) return;
    setLoadingAction("export");
    setError("");
    try {
      const { blob, filename } = await exportIntelligentBudgetTask(task.task_id);
      downloadBlob(blob, filename || "intelligent_budget_simulation.xlsx");
    } catch (e) {
      setError(e instanceof Error ? e.message : "导出Excel失败");
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div className="bb-page h-full overflow-auto">
      <div className="bb-page-header shrink-0">
        <div className="bb-page-title">
          <BarChart3 className="w-4 h-4 text-[var(--bb-primary)]" />
          智能预算模拟结果
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className="text-xs text-[var(--bb-text-muted)]">状态：{statusLabel(task?.status ?? null)}</span>
          <button type="button" className="bb-btn bb-btn-secondary h-9" onClick={handleParse} disabled={loadingAction !== null}>
            <RefreshCw className="w-4 h-4" />
            {loadingAction === "parse" ? "解析中..." : "解析目标"}
          </button>
          <button type="button" className="bb-btn bb-btn-primary h-9" onClick={handleSolve} disabled={!parsed || loadingAction !== null}>
            <Play className="w-4 h-4" />
            {loadingAction === "solve" ? "推演中..." : "确认并生成结果"}
          </button>
          <button type="button" className="bb-btn bb-btn-secondary h-9" onClick={handleExport} disabled={!task || loadingAction !== null}>
            <Download className="w-4 h-4" />
            {loadingAction === "export" ? "导出中..." : "导出Excel"}
          </button>
        </div>
      </div>

      {error && <div className="bb-status-banner bb-status-banner-danger mb-3">{error}</div>}

      <div className="bb-panel mb-3 shrink-0">
        <div className="bb-panel-header">
          <span className="bb-panel-title flex items-center gap-1">
            <Target className="w-4 h-4 text-[var(--bb-primary)]" />
            领导目标
          </span>
          {parsed?.requires_confirmation && (
            <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-amber-700">
              <AlertTriangle className="w-3.5 h-3.5" />
              需用户确认后推演
            </span>
          )}
        </div>
        <div className="p-3 grid grid-cols-1 min-[1280px]:grid-cols-[minmax(260px,1fr)_minmax(320px,1.2fr)] gap-3">
          <textarea value={targetText} onChange={(e) => setTargetText(e.target.value)} className="bb-input min-h-[96px] resize-none text-sm leading-6" />
          <div className="grid [grid-template-columns:repeat(auto-fit,minmax(128px,1fr))] gap-2 text-xs">
            <div className="bb-card p-2">
              <div className="text-[var(--bb-text-muted)] mb-1">净利润目标</div>
              <div className="font-semibold text-[var(--bb-text-strong)]">{parsed ? `>= ${formatPercent(parsed.min_net_profit_growth)}` : "-"}</div>
            </div>
            <div className="bb-card p-2">
              <div className="text-[var(--bb-text-muted)] mb-1">不良率目标</div>
              <div className="font-semibold text-[var(--bb-text-strong)]">{parsed ? `<= ${formatPercent(parsed.max_npl_ratio)}` : "-"}</div>
            </div>
            <div className="bb-card p-2 min-[860px]:col-span-2">
              <div className="text-[var(--bb-text-muted)] mb-1">关键动因</div>
              <div>{parsed?.adjustable_factors?.join("、") || "规模、收益率、费用、风险"}</div>
            </div>
            <div className="bb-card p-2 min-[860px]:col-span-full">
              <div className="text-[var(--bb-text-muted)] mb-1">步长算法摘要</div>
              <div>{task?.step_summary || "确认目标后生成公式敏感度自适应步长，并形成预算结果方案。"}</div>
            </div>
          </div>
        </div>
      </div>

      {task?.status === "negotiation_required" && (
        <div className="bb-status-banner bb-status-banner-warning mb-3 shrink-0">
          <div className="font-medium mb-1">{task.negotiation_message}</div>
          <div>{task.negotiation_suggestions.join("；")}</div>
        </div>
      )}

      <div className="bb-panel mb-3 shrink-0">
        <div className="bb-panel-header">
          <span className="bb-panel-title">重点预算结果方案</span>
        </div>
        <div className="p-3 grid [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))] gap-3">
          {featuredSolutions.length === 0 ? (
            <div className="col-span-full py-12 text-center text-xs text-[var(--bb-text-muted)]">请先解析目标，确认后生成预算模拟结果。</div>
          ) : (
            featuredSolutions.map((solution) => (
              <ResultCard
                key={solution.solution_id}
                solution={solution}
                selected={selectedSolution?.solution_id === solution.solution_id}
                onSelect={() => setSelectedSolutionId(solution.solution_id)}
                onDetail={() => setDetailSolutionId(solution.solution_id)}
              />
            ))
          )}
        </div>
      </div>

      {task && selectedSolution && (
        <div className="grid grid-cols-1 min-[1500px]:grid-cols-3 gap-3 mb-3 shrink-0">
          <StatementTable title="简版资产负债表" rows={BALANCE_ROWS} baseline={task.baseline_solution} current={selectedSolution} />
          <StatementTable title="简版利润表" rows={INCOME_ROWS} baseline={task.baseline_solution} current={selectedSolution} />
          <StatementTable title="风险关键指标表" rows={RISK_ROWS} baseline={task.baseline_solution} current={selectedSolution} />
        </div>
      )}

      {task && alternateSolutions.length > 0 && (
        <div className="bb-panel shrink-0">
          <button type="button" className="bb-panel-header w-full text-left" onClick={() => setShowAlternates((value) => !value)}>
            <span className="bb-panel-title">其他备选方案（{alternateSolutions.length}套）</span>
            <ChevronDown className={`ml-auto w-4 h-4 transition-transform ${showAlternates ? "rotate-180" : ""}`} />
          </button>
          {showAlternates && (
            <div className="p-3 grid [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))] gap-2">
              {alternateSolutions.map((solution) => (
                <button
                  type="button"
                  key={solution.solution_id}
                  className="bb-card p-3 text-left hover:bg-[var(--bb-bg-subtle)]"
                  onClick={() => {
                    setSelectedSolutionId(solution.solution_id);
                    setDetailSolutionId(solution.solution_id);
                  }}
                >
                  <div className="text-xs text-[var(--bb-primary)]">第{solution.rank}名</div>
                  <div className="mt-1 font-semibold text-[var(--bb-text-strong)]">{solution.name}</div>
                  <div className="mt-2 text-xs text-[var(--bb-text-muted)]">
                    净利润 {formatSignedPercent(solution.net_profit_growth)}；不良率 {formatPercent(solution.npl_ratio)}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {detailSolution && task && (
        <DetailModal solution={detailSolution} baseline={task.baseline_solution} parsed={parsed} onClose={() => setDetailSolutionId("")} />
      )}
    </div>
  );
}
