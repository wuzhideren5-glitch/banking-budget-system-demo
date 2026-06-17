"""Metric-tree reads for budget simulation baselines and results."""
from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any

import aiosqlite

from app.schemas import SimulationBaselineRequestItem, SimulationBaselineRow
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte


DATA_METRIC_VALUE_HINTS: dict[str, dict[str, Any]] = {
    "INTEREST_INCOME": {
        "codes": ["03.01.03", "03.01.04", "03.01.20"],
        "prefixes": ["03.01"],
        "keywords": ["利息收入"],
    },
    "INTEREST_EXPENSE": {
        "codes": ["04.01.06"],
        "prefixes": ["04.01", "04.02"],
        "keywords": ["利息支出"],
    },
    "FEE_INCOME": {
        "codes": ["03.03.02"],
        "keywords": ["手续费收入"],
    },
    "FEE_EXPENSE": {
        "codes": ["09.01.53"],
        "keywords": ["手续费支出"],
    },
    "OTHER_REVENUE": {
        "codes": ["03.03.05"],
        "keywords": ["其他营业收入", "营业收入"],
    },
    "RISK_BASE": {
        "codes": ["04.03.01", "04.03.05"],
        "keywords": ["基础拨备", "表内风险成本"],
    },
    "RISK_GAP": {
        "codes": ["04.03.02"],
        "keywords": ["超额拨备", "差额拨备"],
    },
    "RISK_PEER": {
        "codes": ["04.03.03"],
        "keywords": ["同业风险成本"],
    },
    "RISK_OTHER": {
        "codes": ["04.03.04"],
        "keywords": ["其他风险成本"],
    },
    "TAX_SURCHARGE": {
        "codes": ["09.01.57"],
        "keywords": ["营业税金及附加"],
    },
    "OTHER_BUSINESS_INCOME": {
        "codes": ["03.03.06"],
        "keywords": ["其他业务收入"],
    },
    "OTHER_BUSINESS_EXPENSE": {
        "codes": ["09.01.60"],
        "keywords": ["其他业务支出"],
    },
    "NON_OPERATING_INCOME": {
        "codes": ["03.03.07"],
        "keywords": ["营业外收入"],
    },
    "NON_OPERATING_EXPENSE": {
        "codes": ["09.01.61"],
        "keywords": ["营业外支出"],
    },
    "INCOME_TAX": {
        "codes": ["05.02.16", "05.02.17"],
        "keywords": ["企业所得税费用"],
    },
    "NPL_BALANCE": {
        "codes": [],
        "keywords": ["不良余额", "不良贷款余额"],
    },
    "NPL_RATE": {
        "codes": ["01.02.08"],
        "keywords": ["逾期90+规模占比", "不良率"],
    },
    "PROVISION_BALANCE": {
        "codes": ["04.03.01", "04.03.02", "04.03.05"],
        "keywords": ["拨备", "风险成本"],
    },
}


SIMULATION_FACTOR_METRIC_HINTS: dict[str, dict[str, Any]] = {
    "MGMT_LOAN_DAILY": {
        "name": "管理贷款日均规模",
        "value_type": "金额",
        "codes": ["01.01.017", "01.01.17", "01.01.18", "01.01.36"],
        "keywords": ["管理贷款日均", "贷款资产_表内日均", "管理资产_日均", "纯自营贷款表内_日均"],
    },
    "MGMT_LOAN_EOY": {
        "name": "管理贷款时点规模",
        "value_type": "金额",
        "codes": ["01.03.06", "01.02.015", "01.02.016", "01.01.18"],
        "keywords": ["管理贷款时点", "管理贷款余额", "表内贷款时点余额", "贷款资产_表内日均"],
    },
    "LOAN_YIELD_RATE": {
        "name": "贷款收益率",
        "value_type": "百分比",
        "codes": ["02.01.05", "02.01.06", "02.01.10"],
        "keywords": ["贷款收益率", "一般性贷款收益率", "收益率_年化", "存放同业其他资产收益率"],
    },
    "UNION_LOAN_YIELD_RATE": {
        "name": "联合贷款收益率",
        "value_type": "百分比",
        "codes": ["02.01.05", "02.01.06", "02.01.10"],
        "keywords": ["联合贷款收益率", "收益率_年化", "存放同业其他资产收益率"],
    },
    "RISK_COST_RATE": {
        "name": "风险成本率",
        "value_type": "百分比",
        "codes": ["01.02.08"],
        "keywords": ["风险成本率", "逾期90+规模占比"],
    },
    "NPL_RATIO": {
        "name": "不良率",
        "value_type": "百分比",
        "codes": ["01.02.08"],
        "keywords": ["不良率", "逾期90+规模占比"],
    },
}


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().upper()


async def load_runtime_metric_bindings(common_path: Path) -> list[dict[str, str]]:
    """Load active runtime metric bindings synced from the org-product master."""
    async with aiosqlite.connect(common_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT
              b.data_acct_code AS binding_code,
              b.metric_node_code,
              COALESCE(n.node_name, ''),
              COALESCE(n.local_metric_code, ''),
              COALESCE(n.functional_group_code, ''),
              b.scope_type,
              b.scope_code,
              b.data_acct_code,
              COALESCE(da.data_acct_name, ''),
              COALESCE(da.value_type, '金额')
            FROM data_account_metric_binding b
            LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
            LEFT JOIN data_account da ON da.data_acct_code = b.data_acct_code
            WHERE COALESCE(b.is_active, 1) = 1
              AND COALESCE(n.is_active, 1) = 1
            ORDER BY b.metric_node_code, b.scope_code, b.data_acct_code
            """
        )
        rows = await cur.fetchall()
    return [
        {
            "binding_code": str(r[0] or "").strip().upper(),
            "metric_node_code": str(r[1] or "").strip().upper(),
            "node_name": str(r[2] or "").strip(),
            "local_metric_code": str(r[3] or "").strip().upper(),
            "functional_group_code": str(r[4] or "").strip().upper(),
            "scope_type": str(r[5] or "").strip().upper(),
            "scope_code": str(r[6] or "").strip().upper(),
            "product_code": str(r[6] or "").strip().upper() if str(r[5] or "").strip().upper() == "PRODUCT" else "",
            "data_acct_code": str(r[7] or "").strip().upper(),
            "data_acct_name": str(r[8] or "").strip(),
            "value_type": str(r[9] or "金额").strip(),
        }
        for r in rows
    ]


async def load_product_name_map(common_path: Path) -> dict[str, str]:
    """Load the current product organization names used by simulation read models."""
    async with aiosqlite.connect(common_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            f"""
            {org_product_runtime_products_cte()}
            SELECT product_code, product_name
            FROM org_product_runtime_products
            WHERE product_code <> '' AND product_name <> ''
            ORDER BY product_code
            """
        )
        rows = await cur.fetchall()
    return {str(r[0]).strip().upper(): str(r[1] or "").strip() for r in rows}


def _org_metric_children(metric: dict[str, Any]) -> list[dict[str, Any]]:
    children = metric.get("children")
    return [item for item in children if isinstance(item, dict)] if isinstance(children, list) else []


async def load_org_product_refs_by_runtime_ref_code(common_path: Path) -> dict[str, list[str]]:
    """Load confirmed org-product metric refs grouped by runtime metric ref code."""
    refs_by_code: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    async with aiosqlite.connect(common_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            cur = await db.execute(
                """
                SELECT node_code, product_code, functional_group_code
                FROM data_account_metric_node
                WHERE is_active = 1
                  AND runtime_account_enabled = 1
                  AND COALESCE(product_code, '') <> ''
                  AND COALESCE(functional_group_code, '') <> ''
                ORDER BY product_code, functional_group_code, node_code
                """
            )
            rows = await cur.fetchall()
        except aiosqlite.Error:
            return {}

    for node_code_raw, entity_code_raw, table_name_raw in rows:
        entity_code = str(entity_code_raw or "").strip().upper()
        table_name = str(table_name_raw or "").strip()
        data_acct_code = str(node_code_raw or "").strip().upper()
        if not data_acct_code or not entity_code or not table_name:
            continue
        source_ref = f"{entity_code}:{table_name}:{data_acct_code}"
        dedupe_key = (data_acct_code, source_ref)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        refs_by_code.setdefault(data_acct_code, []).append(source_ref)

    return {code: sorted(refs) for code, refs in refs_by_code.items()}


def binding_matches_hint(binding: dict[str, str], hint: dict[str, Any]) -> bool:
    exact_codes = {_compact_text(c) for c in hint.get("codes", [])}
    prefixes = tuple(_compact_text(p) for p in hint.get("prefixes", []) if _compact_text(p))
    node_code = _compact_text(binding.get("metric_node_code"))
    local_metric_code = _compact_text(binding.get("local_metric_code"))
    if node_code in exact_codes or local_metric_code in exact_codes:
        return True
    if prefixes and any(node_code.startswith(prefix) or local_metric_code.startswith(prefix) for prefix in prefixes):
        return True
    haystack = _compact_text(
        " ".join(
            [
                binding.get("binding_code", ""),
                binding.get("metric_node_code", ""),
                binding.get("local_metric_code", ""),
                binding.get("functional_group_code", ""),
                binding.get("node_name", ""),
                binding.get("data_acct_code", ""),
                binding.get("data_acct_name", ""),
            ]
        )
    )
    return any(_compact_text(keyword) in haystack for keyword in hint.get("keywords", []))


def _binding_matches_product_scope(binding: dict[str, str], product_code: str | None) -> bool:
    if not product_code:
        return True
    candidates = set(_product_scope_candidates(product_code))
    if not candidates:
        return True
    scope_code = str(binding.get("scope_code") or "").strip().upper()
    data_code = str(binding.get("data_acct_code") or "").strip().upper()
    if scope_code in candidates:
        return True
    return any(data_code.startswith(f"{candidate}.") for candidate in candidates)


def resolve_metric_runtime_ref_codes(
    bindings: list[dict[str, str]],
    hint: dict[str, Any],
    *,
    product_code: str | None = None,
) -> list[str]:
    """Resolve runtime metric ref codes only from current metric-tree bindings."""
    codes: list[str] = []
    for binding in bindings:
        if not _binding_matches_product_scope(binding, product_code):
            continue
        if not binding_matches_hint(binding, hint):
            continue
        data_code = str(binding.get("data_acct_code") or "").strip().upper()
        if data_code and data_code not in codes:
            codes.append(data_code)
    return codes


def _product_scope_candidates(product_code: str | None) -> list[str]:
    pc = str(product_code or "").strip().upper()
    if not pc:
        return []
    candidates = [pc]
    if len(pc) > 2 and pc[-2:].isdigit():
        candidates.append(pc[:-2])
    candidates.append("CORP")
    return list(dict.fromkeys(candidates))


def aggregate_metric_values(values: list[float], value_type: str) -> float:
    if not values:
        return 0.0
    if value_type == "百分比":
        effective = [v for v in values if abs(v) > 1e-12] or values
        avg = float(sum(effective) / len(effective))
        return avg / 100.0 if abs(avg) > 1 else avg
    return float(sum(values))


async def aggregate_budget_values(
    budget_path: Path,
    version_id: int,
    runtime_ref_codes: list[str],
    *,
    value_type: str = "金额",
    product_code: str | None = None,
    period_ids: list[int] | None = None,
) -> float:
    if not budget_path.exists() or version_id <= 0 or not runtime_ref_codes:
        return 0.0
    codes = list(dict.fromkeys(str(c).strip().upper() for c in runtime_ref_codes if str(c).strip()))
    if not codes:
        return 0.0

    async def _fetch(scope_code: str | None) -> list[float]:
        filters = ["version_id = ?", "budget_actual = 0", f"data_acct_code IN ({','.join(['?'] * len(codes))})"]
        args: list[Any] = [version_id, *codes]
        if scope_code is not None:
            filters.append("product_code = ?")
            args.append(scope_code)
        if period_ids:
            filters.append(f"period_id IN ({','.join(['?'] * len(period_ids))})")
            args.extend(period_ids)
        async with aiosqlite.connect(budget_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                f"SELECT value FROM budget_data WHERE {' AND '.join(filters)}",
                tuple(args),
            )
            rows = await cur.fetchall()
        return [float(r[0] or 0.0) for r in rows]

    if product_code:
        first_values: list[float] | None = None
        for scope in _product_scope_candidates(product_code):
            values = await _fetch(scope)
            if first_values is None and values:
                first_values = values
            if any(abs(v) > 1e-12 for v in values):
                return aggregate_metric_values(values, value_type)
        return aggregate_metric_values(first_values or [], value_type)
    return aggregate_metric_values(await _fetch(None), value_type)


async def sum_runtime_metric_refs(
    budget_path: Path,
    version_id: int,
    bindings: list[dict[str, str]],
    hint: dict[str, Any],
    *,
    value_type: str = "金额",
    product_code: str | None = None,
    period_ids: list[int] | None = None,
) -> float:
    runtime_ref_codes = resolve_metric_runtime_ref_codes(bindings, hint, product_code=product_code)
    return await aggregate_budget_values(
        budget_path,
        version_id,
        runtime_ref_codes,
        value_type=value_type,
        product_code=product_code,
        period_ids=period_ids,
    )


async def simulation_factor_metric_baseline(
    budget_path: Path,
    version_id: int,
    bindings: list[dict[str, str]],
    indicator_code: str,
    product_code: str | None,
    *,
    period_ids: list[int] | None = None,
) -> float:
    hint = SIMULATION_FACTOR_METRIC_HINTS.get(indicator_code.strip().upper())
    if not hint:
        return 0.0
    return await sum_runtime_metric_refs(
        budget_path,
        version_id,
        bindings,
        hint,
        value_type=str(hint.get("value_type") or "金额"),
        product_code=product_code,
        period_ids=period_ids,
    )


def month_to_period_id(period_month_map: dict[int, int]) -> dict[int, int]:
    """Convert shared pid->month map into month->pid for simulation baseline reads."""
    return {month: period_id for period_id, month in period_month_map.items()}


async def build_budget_simulation_baseline_rows(
    *,
    common_path: Path,
    budget_path: Path,
    version_id: int,
    period_month_map: dict[int, int],
    body: list[SimulationBaselineRequestItem],
) -> list[SimulationBaselineRow]:
    """Build baseline rows from the current metric-tree binding Interface."""
    if not body:
        return []

    period_ids = sorted(set(month_to_period_id(period_month_map).values()))
    product_name_map = await load_product_name_map(common_path)
    metric_bindings = await load_runtime_metric_bindings(common_path)
    org_product_refs_by_runtime_ref_code = await load_org_product_refs_by_runtime_ref_code(common_path)

    rows: list[SimulationBaselineRow] = []
    for item in body:
        indicator_code = str(item.indicator_code or "").strip().upper()
        hint = SIMULATION_FACTOR_METRIC_HINTS.get(indicator_code)
        if not hint:
            continue
        product_code = str(item.product_code or "").strip().upper()
        baseline_value = await simulation_factor_metric_baseline(
            budget_path,
            version_id,
            metric_bindings,
            indicator_code,
            product_code or None,
            period_ids=period_ids,
        )
        source_data_acct_codes = resolve_metric_runtime_ref_codes(
            metric_bindings,
            hint,
            product_code=product_code or None,
        )
        source_org_product_refs = sorted(
            {
                source_ref
                for data_acct_code in source_data_acct_codes
                for source_ref in org_product_refs_by_runtime_ref_code.get(data_acct_code, [])
            }
        )
        rows.append(
            SimulationBaselineRow(
                indicator_code=indicator_code,
                indicator_name=str(hint.get("name") or indicator_code),
                product_code=product_code or None,
                product_name=product_name_map.get(product_code) if product_code else None,
                value_type=str(hint.get("value_type") or "金额"),
                baseline_value=baseline_value,
                source_data_acct_codes=source_data_acct_codes,
                source_org_product_refs=source_org_product_refs,
            )
        )
    return rows
