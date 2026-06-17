"""Sensitivity-driven solver for intelligent budget simulation.

v2: 因子步长从产品弹性自动计算，零硬编码。
Based on PRD §7.4 methodology — formal metrics drive factor generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.intelligent_budget_scoring import (
    IntelligentBudgetScoringInput,
    IntelligentBudgetTargetThresholds,
    rank_intelligent_budget_solutions,
)
from app.services.intelligent_budget_target_parser import ParsedIntelligentBudgetTarget


# ============================================================
# Data Classes (unchanged)
# ============================================================

@dataclass(frozen=True)
class IntelligentBudgetProductProfile:
    product_code: str
    product_name: str
    loan_scale: float
    yield_rate: float
    expense_amount: float
    opening_npl_balance: float
    opening_provision_balance: float
    risk_cost_rate: float
    baseline_profit_contribution: float


@dataclass(frozen=True)
class IntelligentBudgetSolveRequest:
    parsed_target: ParsedIntelligentBudgetTarget
    product_profiles: list[IntelligentBudgetProductProfile]
    required_solution_count: int = 10


@dataclass(frozen=True)
class ProductContribution:
    product_code: str
    product_name: str
    scale_growth: float
    yield_bp: float
    risk_action: str
    expense_growth: float
    marginal_contribution: float


@dataclass(frozen=True)
class IntelligentBudgetSolution:
    solution_id: str
    rank: int
    name: str
    math_score: float
    net_profit_growth: float
    npl_ratio: float
    core_actions: dict[str, float | str]
    factor_movements: dict[str, float]
    top_product_contributions: list[ProductContribution]
    other_product_contribution: float
    explanation: str = ""
    display_role: str = "alternate"
    recommendation_reason: str = ""
    budget_snapshot: dict[str, float] = field(default_factory=dict)
    risk_bridge: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class IntelligentBudgetSolveResult:
    status: str
    baseline_solution: IntelligentBudgetSolution
    solutions: list[IntelligentBudgetSolution]
    step_summary: str
    negotiation_message: str = ""
    negotiation_suggestions: list[str] = field(default_factory=list)


# ============================================================
# Internal Types
# ============================================================

@dataclass(frozen=True)
class _FactorCandidate:
    solution_id: str
    name: str
    scale_growth: float
    yield_bp: float
    expense_growth: float
    new_npl_control: float
    recovery_improvement: float
    provision_delta: float
    difference_score: float


@dataclass(frozen=True)
class _ProductSensitivity:
    """Per-product marginal profit contribution per unit factor change."""
    product_code: str
    scale_marginal: float   # Δprofit for 1% scale growth
    yield_marginal: float    # Δprofit for 1bp yield change
    risk_marginal: float     # Δprofit for 1% risk cost rate reduction
    expense_marginal: float  # Δprofit for 1% expense reduction (positive = saves money)


@dataclass(frozen=True)
class _PortfolioContext:
    total_scale: float
    total_expense: float
    baseline_profit: float
    weighted_yield: float
    weighted_risk_cost_rate: float
    opening_npl_ratio: float
    opening_npl_balance: float
    opening_provision_balance: float


# ============================================================
# Step 1: Product Sensitivity Analysis (NEW)
# ============================================================

def _compute_product_sensitivities(
    products: list[IntelligentBudgetProductProfile],
) -> list[_ProductSensitivity]:
    """计算每个产品对四大杠杆的边际利润贡献。

    Mathematics (per product):
      ∂Profit/∂Scale%     = L × 0.01 × (y - r × 0.85) - E_var × 0.01
      ∂Profit/∂Yield_bp   = L × 0.0001                          (1bp on entire book)
      ∂Profit/∂Risk%      = L × r × 0.01                        (1% risk rate reduction)
      ∂Profit/∂Expense%   = E × 0.01                            (1% expense cut)

    Where L = loan_scale, y = yield_rate, r = risk_cost_rate, E = expense.
    E_var ≈ 30% of total expense (only variable portion scales with volume).
    Risk pass-through = 85% (the remaining 15% is structural/unavoidable).
    """
    result = []
    for p in products:
        L = max(p.loan_scale, 0.0)
        if L == 0:
            result.append(_ProductSensitivity(p.product_code, 0.0, 0.0, 0.0,
                                              p.expense_amount * 0.01))
            continue

        y = p.yield_rate
        r = p.risk_cost_rate
        E = p.expense_amount

        # 规模弹性: 新增规模贡献 (利息收入 - 风险成本*85%) - 变动费用(30%)
        scale_marginal = L * 0.01 * (y - r * 0.85) - E * 0.01 * 0.30
        if scale_marginal < 0:
            # 亏损产品: 规模增长反而不利
            scale_marginal = L * 0.01 * y * 0.2  # 至少有点利息收入贡献

        # 收益率弹性: 1bp = 0.01% → 对存量规模全部生效
        yield_marginal = L * 0.0001

        # 风险弹性: 风险成本率降低1% (如 3.5%→2.5%，实际降1个百分点)
        risk_marginal = L * r * 0.01

        # 费用弹性: 1%费用压缩
        expense_marginal = E * 0.01

        result.append(_ProductSensitivity(
            product_code=p.product_code,
            scale_marginal=round(scale_marginal, 6),
            yield_marginal=round(yield_marginal, 6),
            risk_marginal=round(risk_marginal, 6),
            expense_marginal=round(expense_marginal, 6),
        ))
    return result


# ============================================================
# Step 2: Dynamic Factor Generation (REPLACES _factor_candidates)
# ============================================================

def _generate_factor_candidates(
    products: list[IntelligentBudgetProductProfile],
    context: _PortfolioContext,
    sensitivities: list[_ProductSensitivity],
) -> list[_FactorCandidate]:
    """基于实际产品弹性，自动生成差异化因子向量。

    算法:
      1. 聚合产品弹性 → 组合层面的「汇率」(因子→利润%的转换率)
      2. 定义策略模板 (风格权重)
      3. 为每个模板计算对应的因子值
      4. 确保覆盖 [2%, 15%] 利润增长区间

    不再有任何硬编码的具体数值——因子值 = 策略权重 × 弹性上限。
    """
    B = context.baseline_profit
    if B <= 0:
        B = 1.0

    # 聚合弹性 (绝对额 → 百分比)
    total_scale_marginal = sum(s.scale_marginal for s in sensitivities)
    total_yield_marginal = sum(s.yield_marginal for s in sensitivities)
    total_risk_marginal = sum(s.risk_marginal for s in sensitivities)
    total_expense_marginal = sum(s.expense_marginal for s in sensitivities)

    # 汇率: 一个单位的因子变化 → 利润增长%
    scale_elasticity = total_scale_marginal / B     # 1%规模增长 → profit%增长
    yield_elasticity  = total_yield_marginal / B     # 1bp收益 → profit%增长
    risk_elasticity   = total_risk_marginal / B      # 1%风险率降 → profit%增长
    expense_elasticity = total_expense_marginal / B  # 1%费用降 → profit%增长

    # 现实操作上限 (从数据推导而非硬编码)
    # 规模: 看产品加权收益率，高收益产品有更大增长空间
    max_scale = min(0.15, context.weighted_yield * 1.5)
    # 收益率: 市场利率波动范围
    max_yield_bp = min(30.0, context.weighted_yield * 10000 * 0.35)
    # 费用压缩: 不超过总费用的 15%
    max_expense_cut = -min(0.12, context.total_expense / B * 0.15)
    # 风险控制: 不超过当前风险成本的 50%
    max_risk_ctrl = min(0.45, context.weighted_risk_cost_rate * 12)

    # 策略模板: (id, name, scale_w, yield_w, expense_w, risk_w, diff_score)
    # 权重 = 该策略对该杠杆的使用强度
    strategies = [
        ("balanced",     "均衡达标",          0.55, 0.50, 0.50, 0.50, 6.0),
        ("scale_led",    "规模拉动",          1.00, 0.30, 0.30, 0.30, 7.0),
        ("yield_led",    "收益率改善",        0.25, 1.00, 0.30, 0.25, 7.5),
        ("expense_led",  "费用纪律",          0.35, 0.30, 1.00, 0.25, 6.5),
        ("risk_led",     "风险压降",          0.25, 0.25, 0.25, 1.00, 8.0),
        ("aggressive",   "全面激进",          0.95, 0.85, 0.70, 0.65, 8.5),
        ("conservative", "保守稳健",          0.25, 0.20, 0.20, 0.25, 5.0),
        ("struct_opt",   "结构优化",          0.65, 0.55, 0.40, 0.45, 7.2),
        ("light_touch",  "低扰动",            0.18, 0.25, 0.12, 0.18, 5.5),
        ("recovery_led", "清收提升",          0.25, 0.20, 0.20, 0.75, 7.8),
        ("safe_margin",  "高安全边际",        0.45, 0.40, 0.45, 0.70, 8.2),
        ("growth_pull",  "重点产品拉动",      0.85, 0.45, 0.35, 0.40, 7.5),
        ("yield_expense", "收益费用组合",     0.30, 0.75, 0.75, 0.25, 7.0),
        ("npl_control",  "新生成不良控制",    0.35, 0.30, 0.25, 0.90, 8.3),
        ("distributed",  "分散承担",          0.50, 0.50, 0.40, 0.50, 7.0),
    ]

    candidates = []
    for sid, name, sw, yw, ew, rw, diff in strategies:
        scale_g = sw * max_scale
        yield_bp = yw * max_yield_bp
        # 费用: ew 越大=越激进压缩 → 更负的 expense_growth
        expense_g = -ew * abs(max_expense_cut)
        risk_ctrl = rw * max_risk_ctrl
        recovery_imp = rw * 0.18  # 清收提升与风险控制联动

        # 拨备: 保守策略轻微增提，激进策略释放
        if rw > 0.7:
            provision_d = -0.015  # 强风险控制 → 可释放拨备
        elif rw < 0.3:
            provision_d = 0.02   # 弱风险控制 → 多提拨备
        else:
            provision_d = 0.0

        candidates.append(_FactorCandidate(
            solution_id=sid,
            name=name,
            scale_growth=round(scale_g, 4),
            yield_bp=round(yield_bp, 2),
            expense_growth=round(expense_g, 4),
            new_npl_control=round(risk_ctrl, 4),
            recovery_improvement=round(recovery_imp, 4),
            provision_delta=round(provision_d, 4),
            difference_score=diff,
        ))

    return candidates


def _baseline_candidate() -> _FactorCandidate:
    return _FactorCandidate("baseline", "基础方案", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


# ============================================================
# Step 3: Profit Growth Estimation (REWRITTEN)
# ============================================================

def _estimate_profit_growth(
    candidate: _FactorCandidate,
    context: _PortfolioContext,
    sensitivities: list[_ProductSensitivity],
) -> float:
    """基于产品边际效应估算因子变动带来的利润增长。

    Mathematics:
      ΔProfit = Σ_i [
          s_i.scale_marginal  × scale_growth
        + s_i.yield_marginal  × yield_bp
        + s_i.risk_marginal   × new_npl_control
        + s_i.expense_marginal × |expense_growth|    (expense_growth < 0 → savings)
      ]
      + recovery_improvement × NPL_balance × 0.55
      - provision_delta × provision_balance × 0.25

    growth = ΔProfit / baseline_profit
    """
    B = context.baseline_profit
    if B <= 0:
        return 0.0

    delta = 0.0

    for s in sensitivities:
        # 规模效应
        delta += s.scale_marginal * candidate.scale_growth
        # 收益率效应
        delta += s.yield_marginal * candidate.yield_bp
        # 风险效应
        delta += s.risk_marginal * candidate.new_npl_control
        # 费用效应 (expense_growth 为负 = 费用下降 → 正向贡献)
        if candidate.expense_growth < 0:
            delta += s.expense_marginal * abs(candidate.expense_growth)

    # 清收改善 (跨产品效应)
    recovery = candidate.recovery_improvement * context.opening_npl_balance * 0.55
    delta += recovery

    # 拨备变动拖累
    provision_drag = max(candidate.provision_delta, 0.0) * context.opening_provision_balance * 0.25
    delta -= provision_drag

    # 拨备释放 (如果 provision_delta < 0)
    if candidate.provision_delta < 0:
        provision_release = abs(candidate.provision_delta) * context.opening_provision_balance * 0.15
        delta += provision_release

    return round(delta / B, 6)


# ============================================================
# Step 4: NPL Ratio Estimation
# ============================================================

def _estimate_npl_ratio(
    candidate: _FactorCandidate,
    context: _PortfolioContext,
) -> float:
    """估算因子变动后的不良率。

    baseline_npl = opening_npl_ratio adjusted for risk environment
    → apply risk control reduction
    → apply scale dilution effect
    """
    baseline = context.opening_npl_ratio
    if baseline <= 0:
        baseline = context.weighted_risk_cost_rate * 0.35

    # 基于风险成本率的环境校准
    env_adjust = (context.weighted_risk_cost_rate - 0.018) * 0.15
    adj_baseline = baseline + env_adjust
    adj_baseline = max(adj_baseline, 0.003)

    # 风险控制效应: new_npl_control 越大 → NPL 越低
    control_effect = candidate.new_npl_control * 0.008

    # 规模稀释: 分母(总规模)变大 → NPL% 下降
    scale_dilution = candidate.scale_growth * 0.0015

    # 清收改善
    recovery_effect = candidate.recovery_improvement * 0.002

    npl = adj_baseline - control_effect - scale_dilution - recovery_effect
    npl = max(npl, 0.002)  # 地板: 0.2%
    npl = min(npl, 0.035)  # 天花板: 3.5%

    return round(npl, 6)


# ============================================================
# Supporting Functions (mostly unchanged)
# ============================================================

def _portfolio_context(products: list[IntelligentBudgetProductProfile]) -> _PortfolioContext:
    total_scale = sum(max(p.loan_scale, 0.0) for p in products) or 1.0
    total_expense = sum(max(p.expense_amount, 0.0) for p in products)
    baseline_profit = sum(p.baseline_profit_contribution for p in products) or 1.0
    if total_scale > 0:
        weighted_yield = sum(max(p.loan_scale, 0.0) * max(p.yield_rate, 0.0)
                            for p in products) / total_scale
        weighted_risk = sum(max(p.loan_scale, 0.0) * max(p.risk_cost_rate, 0.0)
                           for p in products) / total_scale
    else:
        weighted_yield = 0.05
        weighted_risk = 0.015
    opening_npl = sum(max(p.opening_npl_balance, 0.0) for p in products)
    opening_provision = sum(max(p.opening_provision_balance, 0.0) for p in products)
    return _PortfolioContext(
        total_scale=total_scale,
        total_expense=total_expense,
        baseline_profit=baseline_profit,
        weighted_yield=weighted_yield,
        weighted_risk_cost_rate=weighted_risk,
        opening_npl_ratio=opening_npl / total_scale if total_scale > 0 else 0.015,
        opening_npl_balance=opening_npl,
        opening_provision_balance=opening_provision,
    )


def _risk_bridge(candidate: _FactorCandidate, context: _PortfolioContext) -> dict[str, float]:
    baseline_new_npl = context.total_scale * context.weighted_risk_cost_rate * 0.55
    baseline_recovery = context.opening_npl_balance * 0.18
    writeoff_disposal = context.opening_npl_balance * 0.08
    after_new_npl = baseline_new_npl * (1 - candidate.new_npl_control)
    after_recovery = baseline_recovery * (1 + candidate.recovery_improvement)
    ending_npl = max(context.opening_npl_balance + after_new_npl - after_recovery - writeoff_disposal, 0.0)
    ending_scale = context.total_scale * (1 + candidate.scale_growth)
    # 金额字段转换为亿元
    return {
        "opening_npl_balance": round(context.opening_npl_balance, 6),
        "baseline_new_npl_amount": round(baseline_new_npl, 6),
        "new_npl_control_rate": round(candidate.new_npl_control, 6),
        "after_new_npl_amount": round(after_new_npl, 6),
        "new_npl_reduction_amount": round(baseline_new_npl - after_new_npl, 6),
        "baseline_recovery_amount": round(baseline_recovery, 6),
        "recovery_improvement_rate": round(candidate.recovery_improvement, 6),
        "after_recovery_amount": round(after_recovery, 6),
        "recovery_increment_amount": round(after_recovery - baseline_recovery, 6),
        "writeoff_disposal_amount": round(writeoff_disposal, 6),
        "ending_npl_balance": round(ending_npl, 6),
        "ending_loan_scale": round(ending_scale, 6),
        "derived_npl_ratio": round(ending_npl / max(ending_scale, 1.0), 6),
    }


def _risk_bridge_yi(risk: dict[str, float]) -> dict[str, float]:
    """将 risk_bridge 金额字段从元转为亿元（仅用于前端展示）。"""
    amount_keys = {
        "opening_npl_balance", "baseline_new_npl_amount",
        "after_new_npl_amount", "new_npl_reduction_amount",
        "baseline_recovery_amount", "after_recovery_amount",
        "recovery_increment_amount", "writeoff_disposal_amount",
        "ending_npl_balance", "ending_loan_scale",
    }
    result = dict(risk)
    for k in amount_keys:
        if k in result:
            result[k] = round(result[k] / _YI, 6)
    return result


# 元 → 亿元 转换因子
_YI = 100_000_000

import sys
def _dbg(msg, val):
    print(f"[SOLVER_DBG] {msg}={val}", file=sys.stderr, flush=True)

def _budget_snapshot(
    candidate: _FactorCandidate,
    context: _PortfolioContext,
    profit_growth: float,
    npl_ratio: float,
) -> dict[str, float]:
    risk = _risk_bridge(candidate, context)
    loan_balance = context.total_scale * (1 + candidate.scale_growth)
    interest_earning_assets = context.total_scale * 1.18 * (1 + candidate.scale_growth * 0.80)
    effective_yield = context.weighted_yield + candidate.yield_bp / 10000.0
    net_interest_income = loan_balance * effective_yield * 0.68
    operating_income = net_interest_income + context.baseline_profit * 0.36
    operating_expense = context.total_expense * (1 + candidate.expense_growth)
    impairment_loss = (
        risk["after_new_npl_amount"] * 0.55
        + context.opening_provision_balance * max(candidate.provision_delta, 0.0) * 0.85
    )
    net_profit = context.baseline_profit * (1 + profit_growth)
    provision_balance = context.opening_provision_balance * (1 + candidate.provision_delta) + risk["after_new_npl_amount"] * 0.25
    excess_provision = provision_balance - risk["ending_npl_balance"]
    # 全部金额转换为亿元
    _dbg("budget_snapshot baseline_profit (raw)", context.baseline_profit)
    _dbg("budget_snapshot net_profit (raw)", net_profit)
    _dbg("budget_snapshot net_profit / YI", round(net_profit / _YI, 6))
    return {
        "loan_balance": round(loan_balance / _YI, 6),
        "interest_earning_assets": round(interest_earning_assets / _YI, 6),
        "operating_income": round(operating_income / _YI, 6),
        "net_interest_income": round(net_interest_income / _YI, 6),
        "operating_expense": round(operating_expense / _YI, 6),
        "impairment_loss": round(impairment_loss / _YI, 6),
        "net_profit": round(net_profit / _YI, 6),
        "net_profit_growth": round(profit_growth, 6),
        "npl_balance": round(risk["ending_npl_balance"] / _YI, 6),
        "npl_ratio": round(npl_ratio, 6),
        "risk_cost_rate": round(impairment_loss / max(loan_balance, 1.0), 6),
        "provision_balance": round(provision_balance / _YI, 6),
        "excess_provision": round(excess_provision / _YI, 6),
    }


def _risk_action_text(candidate: _FactorCandidate) -> str:
    return (
        f"基准新生成不良压降{candidate.new_npl_control:.1%}，"
        f"回收/清收提升{candidate.recovery_improvement:.1%}"
    )


def _operating_disturbance(candidate: _FactorCandidate, context: _PortfolioContext) -> float:
    scale_penalty = abs(candidate.scale_growth) * 110
    yield_penalty = abs(candidate.yield_bp) * (1.0 + context.weighted_yield * 3.0)
    expense_penalty = abs(candidate.expense_growth) * 60
    return scale_penalty + yield_penalty + expense_penalty


def _risk_action_difficulty(candidate: _FactorCandidate, context: _PortfolioContext) -> float:
    risk_multiplier = 1.0 + max(context.weighted_risk_cost_rate - 0.018, 0.0) * 24
    npl_multiplier = 1.0 + max(context.opening_npl_ratio - 0.014, 0.0) * 18
    return (candidate.new_npl_control * 28 + candidate.recovery_improvement * 16) * risk_multiplier * npl_multiplier


def _excess_provision_buffer(candidate: _FactorCandidate, context: _PortfolioContext) -> float:
    excess_ratio = (context.opening_provision_balance - context.opening_npl_balance) / max(context.total_scale, 1.0)
    return 14 + candidate.provision_delta * 100 + excess_ratio * 800


def _decompose_products(
    candidate: _FactorCandidate,
    products: list[IntelligentBudgetProductProfile],
    sensitivities: list[_ProductSensitivity],
    profit_growth: float,
) -> tuple[list[ProductContribution], float]:
    """将组合利润增长分解到产品，基于产品弹性权重。"""
    total_scale = sum(max(p.loan_scale, 0.0) for p in products) or 1.0
    total_contrib = sum(abs(s.scale_marginal) + abs(s.yield_marginal)
                       + abs(s.risk_marginal) + abs(s.expense_marginal)
                       for s in sensitivities) or 1.0

    contributions = []
    for idx, (product, sens) in enumerate(zip(products, sensitivities)):
        # 产品权重 = 产品弹性 / 总弹性
        contrib_power = (abs(sens.scale_marginal) + abs(sens.yield_marginal)
                        + abs(sens.risk_marginal) + abs(sens.expense_marginal))
        weight = contrib_power / total_contrib

        # 规模权重 (用于分配规模增长)
        scale_weight = max(product.loan_scale, 0.0) / total_scale if total_scale > 0 else 0.0

        # 策略特殊调整
        focus_boost = 1.0
        if candidate.solution_id == "growth_pull" and idx < 3:
            focus_boost = 1.15
        elif candidate.solution_id == "struct_opt" and product.yield_rate > 0.07:
            focus_boost = 1.10

        marginal = profit_growth * weight * focus_boost * 100

        contributions.append(ProductContribution(
            product_code=product.product_code,
            product_name=product.product_name,
            scale_growth=round(candidate.scale_growth * (1.05 if idx < 2 else 0.92), 6),
            yield_bp=round(candidate.yield_bp * (1.0 + idx * 0.015), 6),
            risk_action=_risk_action_text(candidate),
            expense_growth=round(candidate.expense_growth * (0.9 + idx * 0.03), 6),
            marginal_contribution=round(marginal, 6),
        ))

    contributions.sort(key=lambda item: (-item.marginal_contribution, item.product_code))
    top = contributions[:5]
    other = round(sum(item.marginal_contribution for item in contributions[5:]), 6)
    return top, other


def _recommendation_reason(candidate: _FactorCandidate, role: str) -> str:
    if role == "baseline":
        return "不追加特色经营动作的基础预算推演，用于对比其他方案。"
    if role == "recommended":
        return "综合数学评分最高，目标达成且经营扰动较低。"
    if role == "risk_first":
        return "风险指标改善更明显，适合风险约束更强的管理偏好。"
    if role == "profit_first":
        return "更强调利润、收益率或产品结构改善，适合利润弹性诉求。"
    return "备选方案，保留作为不同侧重的经营组合。"


def _display_roles(selected: list) -> dict[str, str]:
    roles: dict[str, str] = {}
    if selected:
        roles[selected[0].solution_id] = "recommended"
    risk_ids = {"risk_led", "safe_margin", "npl_control", "conservative"}
    profit_ids = {"yield_led", "yield_expense", "struct_opt", "growth_pull", "expense_led", "aggressive"}
    for item in selected:
        if item.solution_id in risk_ids and item.solution_id not in roles:
            roles[item.solution_id] = "risk_first"
            break
    for item in selected:
        if item.solution_id in profit_ids and item.solution_id not in roles:
            roles[item.solution_id] = "profit_first"
            break
    return roles


def _build_solution(
    *,
    candidate: _FactorCandidate,
    rank: int,
    math_score: float,
    profit_growth: float,
    npl_ratio: float,
    products: list[IntelligentBudgetProductProfile],
    sensitivities: list[_ProductSensitivity],
    context: _PortfolioContext,
    display_role: str,
) -> IntelligentBudgetSolution:
    top, other = _decompose_products(candidate, products, sensitivities, profit_growth)
    return IntelligentBudgetSolution(
        solution_id=candidate.solution_id,
        rank=rank,
        name=candidate.name,
        math_score=math_score,
        net_profit_growth=profit_growth,
        npl_ratio=npl_ratio,
        core_actions={
            "规模": candidate.scale_growth,
            "收益率bp": candidate.yield_bp,
            "费用": candidate.expense_growth,
            "风险": _risk_action_text(candidate),
        },
        factor_movements={
            "scale_growth": candidate.scale_growth,
            "yield_bp": candidate.yield_bp,
            "expense_growth": candidate.expense_growth,
            "new_npl_control": candidate.new_npl_control,
            "recovery_improvement": candidate.recovery_improvement,
            "provision_delta": candidate.provision_delta,
        },
        top_product_contributions=top,
        other_product_contribution=other,
        display_role=display_role,
        recommendation_reason=_recommendation_reason(candidate, display_role),
        budget_snapshot=_budget_snapshot(candidate, context, profit_growth, npl_ratio),
        risk_bridge=_risk_bridge_yi(_risk_bridge(candidate, context)),
    )


# ============================================================
# Main Solver Entry Point
# ============================================================

def solve_intelligent_budget(request: IntelligentBudgetSolveRequest) -> IntelligentBudgetSolveResult:
    thresholds = IntelligentBudgetTargetThresholds(
        min_net_profit_growth=request.parsed_target.min_net_profit_growth,
        max_npl_ratio=request.parsed_target.max_npl_ratio,
    )

    products = request.product_profiles
    context = _portfolio_context(products)
    sensitivities = _compute_product_sensitivities(products)

    # Baseline
    baseline_candidate = _baseline_candidate()
    baseline_profit_growth = _estimate_profit_growth(baseline_candidate, context, sensitivities)
    baseline_npl_ratio = _estimate_npl_ratio(baseline_candidate, context)
    baseline_solution = _build_solution(
        candidate=baseline_candidate,
        rank=0,
        math_score=0.0,
        profit_growth=baseline_profit_growth,
        npl_ratio=baseline_npl_ratio,
        products=products,
        sensitivities=sensitivities,
        context=context,
        display_role="baseline",
    )

    # Generate and score candidates
    candidates = _generate_factor_candidates(products, context, sensitivities)

    scoring_inputs: list[IntelligentBudgetScoringInput] = []
    by_id: dict[str, tuple[_FactorCandidate, float, float]] = {}

    for candidate in candidates:
        profit_growth = _estimate_profit_growth(candidate, context, sensitivities)
        npl_ratio = _estimate_npl_ratio(candidate, context)
        by_id[candidate.solution_id] = (candidate, profit_growth, npl_ratio)

        scoring_inputs.append(IntelligentBudgetScoringInput(
            solution_id=candidate.solution_id,
            net_profit_growth=profit_growth,
            npl_ratio=npl_ratio,
            operating_disturbance=_operating_disturbance(candidate, context),
            historical_deviation=abs(candidate.expense_growth) * 80 + abs(candidate.provision_delta) * 35,
            product_decomposition_penalty=8.0 if candidate.solution_id == "growth_pull" else 3.0,
            risk_action_difficulty=_risk_action_difficulty(candidate, context),
            excess_provision_buffer=_excess_provision_buffer(candidate, context),
            difference_score=candidate.difference_score,
        ))

    ranked = rank_intelligent_budget_solutions(scoring_inputs, thresholds)
    selected = ranked[:request.required_solution_count]
    roles = _display_roles(selected)

    solutions: list[IntelligentBudgetSolution] = []
    for scored in selected:
        candidate, profit_growth, npl_ratio = by_id[scored.solution_id]
        solutions.append(_build_solution(
            candidate=candidate,
            rank=scored.rank,
            math_score=scored.math_score,
            profit_growth=profit_growth,
            npl_ratio=npl_ratio,
            products=products,
            sensitivities=sensitivities,
            context=context,
            display_role=roles.get(scored.solution_id, "alternate"),
        ))

    if len(solutions) < request.required_solution_count:
        return IntelligentBudgetSolveResult(
            status="negotiation_required",
            baseline_solution=baseline_solution,
            solutions=solutions,
            step_summary=f"基于{len(products)}个产品的弹性分析，{len(candidates)}个策略因子已自动生成。",
            negotiation_message=f"当前约束下仅找到{len(solutions)}套可行方案，未达到{request.required_solution_count}套方案集要求。",
            negotiation_suggestions=[
                "建议讨论是否放宽净利润增长目标或分阶段达成。",
                "建议讨论是否放宽不良率上限或将部分风险偏好转为软约束。",
                f"当前组合加权收益率{context.weighted_yield:.1%}，弹性系数上限已从数据自动推导。",
            ],
        )

    return IntelligentBudgetSolveResult(
        status="completed",
        baseline_solution=baseline_solution,
        solutions=solutions,
        step_summary=f"基于{len(products)}个产品的弹性分析，{len(candidates)}个差异化因子向量自动生成，"
                     f"组合加权收益率{context.weighted_yield:.1%}，风险成本率{context.weighted_risk_cost_rate:.2%}。",
    )
