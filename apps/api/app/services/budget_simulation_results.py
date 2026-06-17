"""Result-row builder for budget simulation."""
from __future__ import annotations

from pathlib import Path

import aiosqlite

from app.schemas import SimulationInputItem, SimulationResultRow
from app.services.budget_simulation_metrics import (
    DATA_METRIC_VALUE_HINTS,
    load_runtime_metric_bindings,
    load_product_name_map,
    simulation_factor_metric_baseline,
    sum_runtime_metric_refs,
)


SIM_REVENUE = "03.09.05.01.039"
SIM_INTEREST_NET = "03.02.01.01.001"
SIM_INTEREST_INCOME = "03.01.01.01.025"
SIM_INTEREST_EXPENSE = "04.01.06.01.012"
SIM_FEE_NET = "03.04.01.01.003"
SIM_FEE_INCOME = "03.04.01.01.001"
SIM_FEE_EXPENSE = "04.03.01.01.004"
SIM_OTHER_REVENUE = "03.09.05"
SIM_IMPAIRMENT = "06.01.01.01.001"
SIM_LOAN_RISK_COST = "06.01.01.02.007"
SIM_RISK_COST_BASE = "06.01.01.01.008"
SIM_RISK_COST_GAP = "06.01.01.01.004"
SIM_RISK_COST_PEER = "06.01.01.02.009"
SIM_RISK_COST_OTHER = "06.01.01.02.003"
SIM_TAX_SURCHARGE = "07.01.01.01.001"
SIM_OTHER_BUSINESS_NET = "03.03.04"
SIM_NON_OPERATING_NET = "03.06.01.01.001"
SIM_INCOME_TAX = "07.02.01.01.001"

ProductFactorRow = tuple[str, str, float, float, float, float, float, float, float, float, float]


async def _latest_version_id(path: Path) -> int:
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1")
        row = await cur.fetchone()
    return int(row[0]) if row else 0


def _build_simulation_overrides(
    body: list[SimulationInputItem],
) -> tuple[dict[tuple[str, str], float], dict[str, list[float]], set[str]]:
    override_by_key: dict[tuple[str, str], float] = {}
    override_by_code: dict[str, list[float]] = {}
    requested_products: set[str] = set()
    for item in body:
        code = str(item.indicator_code or "").strip().upper()
        if not code:
            continue
        product_code = str(item.product_code or "").strip().upper()
        value = float(item.simulate_value)
        override_by_key[(code, product_code)] = value
        override_by_code.setdefault(code, []).append(value)
        if product_code:
            requested_products.add(product_code)
    return override_by_key, override_by_code, requested_products


def _loan_products(product_name_map: dict[str, str], requested_products: set[str]) -> list[tuple[str, str]]:
    products = [(code, name) for code, name in product_name_map.items() if "贷" in name and code != "CORP"]
    product_codes = {code for code, _ in products}
    for product_code in sorted(requested_products):
        if product_code not in product_codes:
            products.append((product_code, product_name_map.get(product_code, product_code)))
    products.sort(key=lambda item: item[0])
    return products


def _append_result_row(
    result: list[SimulationResultRow],
    group: str,
    code: str,
    name: str,
    b25: float,
    b26: float,
    sim26: float,
    value_type: str = "金额",
) -> None:
    result.append(
        SimulationResultRow(
            metric_group=group,
            indicator_code=code,
            indicator_name=name,
            value_type=value_type,
            baseline_2025=float(b25),
            baseline_2026=float(b26),
            simulation_2026=float(sim26),
        )
    )


async def build_budget_simulation_result_rows(
    common_path: Path,
    body: list[SimulationInputItem],
) -> list[SimulationResultRow]:
    """Build simulation result rows from the current metric tree and annual budget facts."""
    year_2025_path = common_path.parent / "budget_2025.db"
    year_2026_path = common_path.parent / "budget_2026.db"
    v25 = await _latest_version_id(year_2025_path) if year_2025_path.exists() else 0
    v26 = await _latest_version_id(year_2026_path) if year_2026_path.exists() else 0
    metric_bindings = await load_runtime_metric_bindings(common_path)
    product_name_map = await load_product_name_map(common_path)

    override_by_key, override_by_code, requested_products = _build_simulation_overrides(body)
    loan_products = _loan_products(product_name_map, requested_products)

    def input_value(indicator_code: str, product_code: str | None, default: float) -> float:
        code = indicator_code.strip().upper()
        pc = str(product_code or "").strip().upper()
        if (code, pc) in override_by_key:
            return float(override_by_key[(code, pc)])
        if (code, "") in override_by_key:
            return float(override_by_key[(code, "")])
        return float(default)

    def direct_override(code: str, default: float) -> float:
        values = override_by_code.get(code.strip().upper())
        return float(sum(values)) if values else float(default)

    async def metric_value(key: str, path: Path, version_id: int, value_type: str = "金额") -> float:
        return await sum_runtime_metric_refs(
            path,
            version_id,
            metric_bindings,
            DATA_METRIC_VALUE_HINTS[key],
            value_type=value_type,
        )

    result: list[SimulationResultRow] = []

    interest_income_b25 = await metric_value("INTEREST_INCOME", year_2025_path, v25)
    interest_income_b26 = await metric_value("INTEREST_INCOME", year_2026_path, v26)
    interest_expense_b25 = await metric_value("INTEREST_EXPENSE", year_2025_path, v25)
    interest_expense_b26 = await metric_value("INTEREST_EXPENSE", year_2026_path, v26)
    fee_income_b25 = await metric_value("FEE_INCOME", year_2025_path, v25)
    fee_income_b26 = await metric_value("FEE_INCOME", year_2026_path, v26)
    fee_expense_b25 = await metric_value("FEE_EXPENSE", year_2025_path, v25)
    fee_expense_b26 = await metric_value("FEE_EXPENSE", year_2026_path, v26)
    other_revenue_b25 = await metric_value("OTHER_REVENUE", year_2025_path, v25)
    other_revenue_b26 = await metric_value("OTHER_REVENUE", year_2026_path, v26)
    risk_base_b25_data = await metric_value("RISK_BASE", year_2025_path, v25)
    risk_base_b26_data = await metric_value("RISK_BASE", year_2026_path, v26)
    risk_gap_b25 = await metric_value("RISK_GAP", year_2025_path, v25)
    risk_gap_b26 = await metric_value("RISK_GAP", year_2026_path, v26)
    risk_peer_b25 = await metric_value("RISK_PEER", year_2025_path, v25)
    risk_peer_b26 = await metric_value("RISK_PEER", year_2026_path, v26)
    risk_other_b25 = await metric_value("RISK_OTHER", year_2025_path, v25)
    risk_other_b26 = await metric_value("RISK_OTHER", year_2026_path, v26)
    tax_surcharge_b25 = await metric_value("TAX_SURCHARGE", year_2025_path, v25)
    tax_surcharge_b26 = await metric_value("TAX_SURCHARGE", year_2026_path, v26)
    other_business_income_b25 = await metric_value("OTHER_BUSINESS_INCOME", year_2025_path, v25)
    other_business_income_b26 = await metric_value("OTHER_BUSINESS_INCOME", year_2026_path, v26)
    other_business_expense_b25 = await metric_value("OTHER_BUSINESS_EXPENSE", year_2025_path, v25)
    other_business_expense_b26 = await metric_value("OTHER_BUSINESS_EXPENSE", year_2026_path, v26)
    non_operating_income_b25 = await metric_value("NON_OPERATING_INCOME", year_2025_path, v25)
    non_operating_income_b26 = await metric_value("NON_OPERATING_INCOME", year_2026_path, v26)
    non_operating_expense_b25 = await metric_value("NON_OPERATING_EXPENSE", year_2025_path, v25)
    non_operating_expense_b26 = await metric_value("NON_OPERATING_EXPENSE", year_2026_path, v26)
    income_tax_b25 = await metric_value("INCOME_TAX", year_2025_path, v25)
    income_tax_b26 = await metric_value("INCOME_TAX", year_2026_path, v26)

    interest_product_rows: list[ProductFactorRow] = []
    risk_product_rows: list[ProductFactorRow] = []
    for product_code, product_name in loan_products:
        daily_b25 = await simulation_factor_metric_baseline(
            year_2025_path, v25, metric_bindings, "MGMT_LOAN_DAILY", product_code
        )
        daily_b26 = await simulation_factor_metric_baseline(
            year_2026_path, v26, metric_bindings, "MGMT_LOAN_DAILY", product_code
        )
        eoy_b26 = await simulation_factor_metric_baseline(
            year_2026_path, v26, metric_bindings, "MGMT_LOAN_EOY", product_code
        )
        if abs(daily_b26) <= 1e-12 and abs(eoy_b26) > 1e-12:
            daily_b26 = eoy_b26
        rate_b25 = await simulation_factor_metric_baseline(
            year_2025_path, v25, metric_bindings, "LOAN_YIELD_RATE", product_code
        )
        rate_b26 = await simulation_factor_metric_baseline(
            year_2026_path, v26, metric_bindings, "LOAN_YIELD_RATE", product_code
        )
        union_rate_b26 = await simulation_factor_metric_baseline(
            year_2026_path, v26, metric_bindings, "UNION_LOAN_YIELD_RATE", product_code
        )
        if abs(rate_b26) <= 1e-12 and abs(union_rate_b26) > 1e-12:
            rate_b26 = union_rate_b26
        daily_sim = input_value("MGMT_LOAN_DAILY", product_code, daily_b26)
        daily_sim = input_value("MGMT_LOAN_EOY", product_code, daily_sim)
        rate_sim = input_value("LOAN_YIELD_RATE", product_code, rate_b26)
        rate_sim = input_value("UNION_LOAN_YIELD_RATE", product_code, rate_sim)
        interest_product_rows.append(
            (
                product_code,
                product_name,
                daily_b25 * rate_b25,
                daily_b26 * rate_b26,
                daily_sim * rate_sim,
                daily_b25,
                daily_b26,
                daily_sim,
                rate_b25,
                rate_b26,
                rate_sim,
            )
        )

        risk_rate_b25 = await simulation_factor_metric_baseline(
            year_2025_path, v25, metric_bindings, "RISK_COST_RATE", product_code
        )
        risk_rate_b26 = await simulation_factor_metric_baseline(
            year_2026_path, v26, metric_bindings, "RISK_COST_RATE", product_code
        )
        risk_rate_sim = input_value("RISK_COST_RATE", product_code, risk_rate_b26)
        risk_product_rows.append(
            (
                product_code,
                product_name,
                daily_b25 * risk_rate_b25,
                daily_b26 * risk_rate_b26,
                daily_sim * risk_rate_sim,
                daily_b25,
                daily_b26,
                daily_sim,
                risk_rate_b25,
                risk_rate_b26,
                risk_rate_sim,
            )
        )

    product_interest_b25 = sum(row[2] for row in interest_product_rows)
    product_interest_b26 = sum(row[3] for row in interest_product_rows)
    product_interest_sim = sum(row[4] for row in interest_product_rows)
    interest_income_b25 = interest_income_b25 or product_interest_b25
    interest_income_b26 = interest_income_b26 or product_interest_b26
    interest_income_sim = interest_income_b26 + (product_interest_sim - product_interest_b26)
    interest_income_sim = direct_override(SIM_INTEREST_INCOME, interest_income_sim)
    interest_expense_sim = direct_override(SIM_INTEREST_EXPENSE, interest_expense_b26)

    fee_income_sim = direct_override(SIM_FEE_INCOME, fee_income_b26)
    fee_expense_sim = direct_override(SIM_FEE_EXPENSE, fee_expense_b26)
    other_revenue_sim = direct_override(SIM_OTHER_REVENUE, other_revenue_b26)

    interest_net_b25 = interest_income_b25 - interest_expense_b25
    interest_net_b26 = interest_income_b26 - interest_expense_b26
    interest_net_sim = direct_override(SIM_INTEREST_NET, interest_income_sim - interest_expense_sim)
    fee_net_b25 = fee_income_b25 - fee_expense_b25
    fee_net_b26 = fee_income_b26 - fee_expense_b26
    fee_net_sim = direct_override(SIM_FEE_NET, fee_income_sim - fee_expense_sim)
    revenue_b25 = interest_net_b25 + fee_net_b25 + other_revenue_b25
    revenue_b26 = interest_net_b26 + fee_net_b26 + other_revenue_b26
    revenue_sim = direct_override(SIM_REVENUE, interest_net_sim + fee_net_sim + other_revenue_sim)

    product_risk_b25 = sum(row[2] for row in risk_product_rows)
    product_risk_b26 = sum(row[3] for row in risk_product_rows)
    product_risk_sim = sum(row[4] for row in risk_product_rows)
    risk_base_b25 = risk_base_b25_data or product_risk_b25
    risk_base_b26 = risk_base_b26_data or product_risk_b26
    risk_base_sim = risk_base_b26 + (product_risk_sim - product_risk_b26)
    risk_gap_sim = direct_override(SIM_RISK_COST_GAP, risk_gap_b26)
    provision_override = override_by_code.get("RISK_PROVISION_BALANCE")
    if provision_override:
        risk_base_sim = float(sum(provision_override)) - risk_gap_sim
    risk_base_sim = direct_override(SIM_RISK_COST_BASE, risk_base_sim)
    loan_risk_b25 = risk_base_b25 + risk_gap_b25
    loan_risk_b26 = risk_base_b26 + risk_gap_b26
    loan_risk_sim = direct_override(SIM_LOAN_RISK_COST, risk_base_sim + risk_gap_sim)
    risk_peer_sim = direct_override(SIM_RISK_COST_PEER, risk_peer_b26)
    risk_other_sim = direct_override(SIM_RISK_COST_OTHER, risk_other_b26)
    impairment_b25 = loan_risk_b25 + risk_peer_b25 + risk_other_b25
    impairment_b26 = loan_risk_b26 + risk_peer_b26 + risk_other_b26
    impairment_sim = direct_override(SIM_IMPAIRMENT, loan_risk_sim + risk_peer_sim + risk_other_sim)

    tax_surcharge_sim = direct_override(SIM_TAX_SURCHARGE, tax_surcharge_b26)
    other_business_net_b25 = other_business_income_b25 - other_business_expense_b25
    other_business_net_b26 = other_business_income_b26 - other_business_expense_b26
    other_business_net_sim = direct_override(SIM_OTHER_BUSINESS_NET, other_business_net_b26)
    non_operating_net_b25 = non_operating_income_b25 - non_operating_expense_b25
    non_operating_net_b26 = non_operating_income_b26 - non_operating_expense_b26
    non_operating_net_sim = direct_override(SIM_NON_OPERATING_NET, non_operating_net_b26)
    fee_total_b25 = impairment_b25 + tax_surcharge_b25
    fee_total_b26 = impairment_b26 + tax_surcharge_b26
    fee_total_sim = impairment_sim + tax_surcharge_sim
    pre_tax_b25 = revenue_b25 - fee_total_b25 + other_business_net_b25 + non_operating_net_b25
    pre_tax_b26 = revenue_b26 - fee_total_b26 + other_business_net_b26 + non_operating_net_b26
    pre_tax_sim = direct_override("PROFIT_PRETAX", revenue_sim - fee_total_sim + other_business_net_sim + non_operating_net_sim)
    income_tax_sim = direct_override(SIM_INCOME_TAX, income_tax_b26)
    net_profit_b25 = pre_tax_b25 - income_tax_b25
    net_profit_b26 = pre_tax_b26 - income_tax_b26
    net_profit_sim = direct_override("PROFIT_NET", pre_tax_sim - income_tax_sim)

    _append_result_row(result, "盈利性指标", SIM_REVENUE, "营业收入", revenue_b25, revenue_b26, revenue_sim)
    _append_result_row(result, "盈利性指标", SIM_INTEREST_NET, "利息净收入", interest_net_b25, interest_net_b26, interest_net_sim)
    _append_result_row(
        result, "盈利性指标", SIM_INTEREST_INCOME, "利息收入", interest_income_b25, interest_income_b26, interest_income_sim
    )
    for product_code, product_name, b25, b26, sim26, d25, d26, d26_sim, r25, r26, r26_sim in interest_product_rows:
        _append_result_row(result, "盈利性指标", f"{SIM_INTEREST_INCOME}::{product_code}", product_name, b25, b26, sim26)
        _append_result_row(
            result,
            "盈利性指标",
            f"{SIM_INTEREST_INCOME}::{product_code}::FACTOR_DAILY",
            f"{product_name}日均余额",
            d25,
            d26,
            d26_sim,
        )
        _append_result_row(
            result,
            "盈利性指标",
            f"{SIM_INTEREST_INCOME}::{product_code}::FACTOR_RATE",
            f"{product_name}收益率",
            r25,
            r26,
            r26_sim,
            "百分比",
        )
    _append_result_row(
        result, "盈利性指标", SIM_INTEREST_EXPENSE, "利息支出", interest_expense_b25, interest_expense_b26, interest_expense_sim
    )
    _append_result_row(result, "盈利性指标", SIM_FEE_NET, "手续费及佣金净收入", fee_net_b25, fee_net_b26, fee_net_sim)
    _append_result_row(result, "盈利性指标", SIM_FEE_INCOME, "手续费收入", fee_income_b25, fee_income_b26, fee_income_sim)
    _append_result_row(result, "盈利性指标", SIM_FEE_EXPENSE, "手续费支出", fee_expense_b25, fee_expense_b26, fee_expense_sim)
    _append_result_row(
        result, "盈利性指标", SIM_OTHER_REVENUE, "其他营业收入", other_revenue_b25, other_revenue_b26, other_revenue_sim
    )
    _append_result_row(result, "盈利性指标", "PROFIT_FEE_TOTAL", "费用", fee_total_b25, fee_total_b26, fee_total_sim)
    _append_result_row(result, "盈利性指标", SIM_IMPAIRMENT, "资产减值损失", impairment_b25, impairment_b26, impairment_sim)
    _append_result_row(result, "盈利性指标", SIM_LOAN_RISK_COST, "贷款风险成本", loan_risk_b25, loan_risk_b26, loan_risk_sim)
    _append_result_row(
        result, "盈利性指标", SIM_RISK_COST_BASE, "风险成本-基础拨备", risk_base_b25, risk_base_b26, risk_base_sim
    )
    for product_code, product_name, b25, b26, sim26, d25, d26, d26_sim, r25, r26, r26_sim in risk_product_rows:
        _append_result_row(
            result, "盈利性指标", f"{SIM_RISK_COST_BASE}::{product_code}", f"{product_name}产品风险成本", b25, b26, sim26
        )
        _append_result_row(
            result,
            "盈利性指标",
            f"{SIM_RISK_COST_BASE}::{product_code}::FACTOR_DAILY",
            f"{product_name}日均余额",
            d25,
            d26,
            d26_sim,
        )
        _append_result_row(
            result,
            "盈利性指标",
            f"{SIM_RISK_COST_BASE}::{product_code}::FACTOR_RATE",
            f"{product_name}风险成本率",
            r25,
            r26,
            r26_sim,
            "百分比",
        )
    _append_result_row(
        result, "盈利性指标", SIM_RISK_COST_GAP, "风险成本-差额拨备", risk_gap_b25, risk_gap_b26, risk_gap_sim
    )
    _append_result_row(result, "盈利性指标", SIM_RISK_COST_PEER, "同业风险成本", risk_peer_b25, risk_peer_b26, risk_peer_sim)
    _append_result_row(result, "盈利性指标", SIM_RISK_COST_OTHER, "其他风险成本", risk_other_b25, risk_other_b26, risk_other_sim)
    _append_result_row(result, "盈利性指标", SIM_TAX_SURCHARGE, "税金及附加", tax_surcharge_b25, tax_surcharge_b26, tax_surcharge_sim)
    _append_result_row(
        result, "盈利性指标", SIM_OTHER_BUSINESS_NET, "其他业务净收入", other_business_net_b25, other_business_net_b26, other_business_net_sim
    )
    _append_result_row(
        result, "盈利性指标", SIM_NON_OPERATING_NET, "营业外净收支", non_operating_net_b25, non_operating_net_b26, non_operating_net_sim
    )
    _append_result_row(result, "盈利性指标", "PROFIT_PRETAX", "税前利润", pre_tax_b25, pre_tax_b26, pre_tax_sim)
    _append_result_row(result, "盈利性指标", SIM_INCOME_TAX, "所得税费用", income_tax_b25, income_tax_b26, income_tax_sim)
    _append_result_row(result, "盈利性指标", "PROFIT_NET", "净利润", net_profit_b25, net_profit_b26, net_profit_sim)

    npl_balance_b25 = await metric_value("NPL_BALANCE", year_2025_path, v25)
    npl_balance_b26 = await metric_value("NPL_BALANCE", year_2026_path, v26)
    npl_rate_b25 = await simulation_factor_metric_baseline(year_2025_path, v25, metric_bindings, "NPL_RATIO", None)
    npl_rate_b26 = await simulation_factor_metric_baseline(year_2026_path, v26, metric_bindings, "NPL_RATIO", None)
    provision_b25 = risk_base_b25 + risk_gap_b25
    provision_b26 = risk_base_b26 + risk_gap_b26
    provision_sim = risk_base_sim + risk_gap_sim
    _append_result_row(
        result,
        "风险指标",
        "RISK_NPL_BALANCE",
        "不良余额",
        npl_balance_b25,
        npl_balance_b26,
        direct_override("RISK_NPL_BALANCE", npl_balance_b26),
    )
    _append_result_row(
        result,
        "风险指标",
        "RISK_NPL_RATE",
        "不良贷款率",
        npl_rate_b25,
        npl_rate_b26,
        direct_override("RISK_NPL_RATE", npl_rate_b26),
        "百分比",
    )
    _append_result_row(
        result,
        "风险指标",
        "RISK_PROVISION_BALANCE",
        "拨备余额",
        provision_b25,
        provision_b26,
        direct_override("RISK_PROVISION_BALANCE", provision_sim),
    )
    _append_result_row(result, "风险指标", "RISK_EXCESS_PROVISION", "超额拨备", risk_gap_b25, risk_gap_b26, risk_gap_sim)
    return result
