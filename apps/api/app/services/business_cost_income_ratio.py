"""Business cost-income ratio read model and calculation service."""
from __future__ import annotations

from typing import Any

import aiosqlite

from app.db_bootstrap.business_cost_income import ensure_business_cost_income_schema_async
from app.core.db_paths import budget_db_path, common_db_path
from app.services.business_cost_income_derived import (
    apply_bcir_input_derived_values,
    effective_bcir_item_entry_mode,
    uses_derived_input_amount,
)
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte


AMOUNT_UNIT_DIVISORS: dict[str, tuple[str, float]] = {
    "yuan": ("元", 1.0),
    "thousand": ("千元", 1_000.0),
    "ten_thousand": ("万元", 10_000.0),
    "million": ("百万元", 1_000_000.0),
    "hundred_million": ("亿元", 100_000_000.0),
}


def amount_unit_meta(amount_unit: str | None) -> tuple[str, float]:
    normalized = str(amount_unit or "").strip().lower()
    return AMOUNT_UNIT_DIVISORS.get(normalized, AMOUNT_UNIT_DIVISORS["yuan"])


def amount_unit_options() -> list[dict[str, str]]:
    return [{"value": key, "label": value[0]} for key, value in AMOUNT_UNIT_DIVISORS.items()]


def parse_year_month(value: str) -> tuple[int, int]:
    text = str(value or "").strip()
    parts = text.split("-")
    if len(parts) != 2:
        raise ValueError("月份格式应为 YYYY-MM")
    year = int(parts[0])
    month = int(parts[1])
    if year < 2000 or year > 2100:
        raise ValueError("年份超出范围")
    if month < 1 or month > 12:
        raise ValueError("月份超出范围")
    return year, month


def norm_dim(value: str | None) -> str:
    return str(value or "").strip()


def _scale_amount(value: float | int | None, divisor: float) -> float:
    return round(float(value or 0.0) / divisor, 2)


async def ensure_business_cost_income_tables(year: int) -> None:
    path = budget_db_path(year)
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_business_cost_income_schema_async(db)
        await db.commit()


async def load_business_cost_income_items(
    db: aiosqlite.Connection,
    *,
    product_code: str | None = None,
) -> list[dict[str, Any]]:
    normalized_product = str(product_code or "").strip().upper()
    cur = await db.execute(
        """
        SELECT id, product_code, section, name, parent_id, display_group, data_acct_code,
               org_product_ref, org_product_entity_code, org_product_table_name,
               org_product_metric_code, org_product_metric_name,
               manual_entry_mode, value_mode, sort_order, enabled
        FROM business_cost_income_item
        WHERE product_code = ?
        ORDER BY section, sort_order, id
        """,
        (normalized_product,),
    )
    rows = await cur.fetchall()
    return [
        {
            "id": int(row[0]),
            "product_code": str(row[1] or ""),
            "section": str(row[2]),
            "name": str(row[3]),
            "parent_id": int(row[4]) if row[4] is not None else None,
            "display_group": int(row[5] or 0),
            "data_acct_code": str(row[6] or ""),
            "org_product_ref": str(row[7] or ""),
            "org_product_entity_code": str(row[8] or ""),
            "org_product_table_name": str(row[9] or ""),
            "org_product_metric_code": str(row[10] or ""),
            "org_product_metric_name": str(row[11] or ""),
            "manual_entry_mode": str(row[12] or "disabled"),
            "value_mode": str(row[13] or "tree"),
            "sort_order": int(row[14] or 0),
            "enabled": int(row[15] or 0),
        }
        for row in rows
    ]


async def load_business_cost_income_indicators(
    db: aiosqlite.Connection,
    *,
    product_code: str | None = None,
) -> list[dict[str, Any]]:
    normalized_product = str(product_code or "").strip().upper()
    cur = await db.execute(
        """
        SELECT id, product_code, name, parent_id, display_group, topic_metric_node_code,
               numerator_section, numerator_item_id, numerator_value_mode,
               denominator_section, denominator_item_id, denominator_value_mode,
               format, annualize, sort_order, enabled
        FROM business_cost_income_indicator
        WHERE product_code = ?
        ORDER BY sort_order, id
        """,
        (normalized_product,),
    )
    rows = await cur.fetchall()
    return [
        {
            "id": int(row[0]),
            "product_code": str(row[1] or ""),
            "name": str(row[2]),
            "parent_id": int(row[3]) if row[3] is not None else None,
            "display_group": int(row[4] or 0),
            "topic_metric_node_code": str(row[5] or "") or None,
            "numerator_section": str(row[6]),
            "numerator_item_id": int(row[7]),
            "numerator_value_mode": str(row[8] or "tree"),
            "denominator_section": str(row[9]),
            "denominator_item_id": int(row[10]),
            "denominator_value_mode": str(row[11] or "tree"),
            "format": str(row[12]),
            "annualize": int(row[13] or 0),
            "sort_order": int(row[14] or 0),
            "enabled": int(row[15] or 0),
        }
        for row in rows
    ]


async def load_business_cost_income_meta_options(
    *,
    entity_name: str | None,
    report_month: str | None,
    product_code: str | None,
) -> dict[str, Any]:
    async with aiosqlite.connect(common_db_path()) as cdb:
        await cdb.execute("PRAGMA foreign_keys = ON")
        cur = await cdb.execute(
            """
            SELECT DISTINCT entity_name
            FROM dept_account
            WHERE entity_name IS NOT NULL AND TRIM(entity_name) != ''
            ORDER BY entity_name
            """
        )
        entities = [str(row[0]) for row in await cur.fetchall()]
        cur = await cdb.execute(
            f"""
            {org_product_runtime_products_cte()}
            SELECT product_code, product_name
            FROM org_product_runtime_products
            WHERE product_code <> '' AND product_name <> ''
            ORDER BY product_code
            """
        )
        products = [
            {"product_code": str(row[0]), "product_name": str(row[1])}
            for row in await cur.fetchall()
        ]

    groups: list[str] = []
    if report_month:
        try:
            year, _month = parse_year_month(report_month)
            await ensure_business_cost_income_tables(year)
            async with aiosqlite.connect(budget_db_path(year)) as db:
                await db.execute("PRAGMA foreign_keys = ON")
                cur = await db.execute(
                    """
                    SELECT DISTINCT group_name
                    FROM business_cost_income_value
                    WHERE year = ?
                      AND entity_name = ?
                      AND product_code = ?
                      AND TRIM(group_name) != ''
                    ORDER BY group_name
                    """,
                    (year, norm_dim(entity_name), norm_dim(product_code)),
                )
                groups = [str(row[0]) for row in await cur.fetchall()]
        except Exception:
            groups = []

    return {
        "entity_options": entities,
        "product_options": products,
        "group_options": groups,
        "amount_unit_options": amount_unit_options(),
    }


async def _load_aggregates(
    db: aiosqlite.Connection,
    *,
    year: int,
    month: int,
    entity_name: str,
    group_name: str,
    product_code: str,
) -> dict[tuple[str, int, str], float]:
    cur = await db.execute(
        """
        SELECT item_section, item_id, field, SUM(value) AS total
        FROM business_cost_income_value
        WHERE year = ?
          AND entity_name = ?
          AND group_name = ?
          AND product_code = ?
          AND (
            (field = 'actual' AND month BETWEEN 1 AND ?)
            OR (field IN ('budget', 'forecast') AND month BETWEEN 1 AND 12)
          )
        GROUP BY item_section, item_id, field
        """,
        (year, entity_name, group_name, product_code, month),
    )
    rows = await cur.fetchall()
    return {(str(row[0]), int(row[1]), str(row[2])): float(row[3] or 0.0) for row in rows}


async def _load_last_year_actuals(
    db: aiosqlite.Connection,
    *,
    year: int,
    month: int,
    entity_name: str,
    group_name: str,
    product_code: str,
) -> dict[tuple[str, int], float]:
    cur = await db.execute(
        """
        SELECT item_section, item_id, SUM(value) AS total
        FROM business_cost_income_value
        WHERE year = ?
          AND entity_name = ?
          AND group_name = ?
          AND product_code = ?
          AND field = 'actual'
          AND month BETWEEN 1 AND ?
        GROUP BY item_section, item_id
        """,
        (year - 1, entity_name, group_name, product_code, month),
    )
    rows = await cur.fetchall()
    return {(str(row[0]), int(row[1])): float(row[2] or 0.0) for row in rows}


async def _load_month_cells(
    db: aiosqlite.Connection,
    *,
    year: int,
    month: int,
    entity_name: str,
    group_name: str,
    product_code: str,
) -> dict[tuple[str, int, str], float]:
    cur = await db.execute(
        """
        SELECT item_section, item_id, field, value
        FROM business_cost_income_value
        WHERE year = ?
          AND month = ?
          AND entity_name = ?
          AND group_name = ?
          AND product_code = ?
        """,
        (year, month, entity_name, group_name, product_code),
    )
    rows = await cur.fetchall()
    return {(str(row[0]), int(row[1]), str(row[2])): float(row[3] or 0.0) for row in rows}


def _metrics_from_amounts(
    *,
    current_actual: float,
    annual_budget: float,
    annual_forecast: float,
    last_year_actual: float,
) -> dict[str, Any]:
    current_actual = round(float(current_actual or 0.0), 2)
    annual_budget = round(float(annual_budget or 0.0), 2)
    annual_forecast = round(float(annual_forecast or 0.0), 2)
    last_year_actual = round(float(last_year_actual or 0.0), 2)
    forecast_budget_gap = round(annual_forecast - annual_budget, 2)
    yoy_change = round(current_actual - last_year_actual, 2)
    return {
        "current_actual": current_actual,
        "annual_budget": annual_budget,
        "budget_progress": round(current_actual / annual_budget, 6) if annual_budget else None,
        "annual_forecast": annual_forecast,
        "forecast_budget_gap": forecast_budget_gap,
        "gap_rate": round(forecast_budget_gap / annual_budget, 6) if annual_budget else None,
        "yoy_change": yoy_change,
        "yoy_rate": round(yoy_change / last_year_actual, 6) if last_year_actual else None,
        "last_year_actual": last_year_actual,
    }


def _ratio(a: float, b: float) -> float | None:
    if not b:
        return None
    return a / b


async def build_business_cost_income_ratio_report(
    *,
    entity_name: str,
    report_month: str,
    group_name: str | None,
    product_code: str | None,
    amount_unit: str,
) -> dict[str, Any]:
    year, month = parse_year_month(report_month)
    entity = norm_dim(entity_name)
    if not entity:
        raise ValueError("主体不能为空")

    amount_unit_label, divisor = amount_unit_meta(amount_unit)
    group = norm_dim(group_name)
    product = norm_dim(product_code)
    await ensure_business_cost_income_tables(year)

    async with aiosqlite.connect(budget_db_path(year)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        items = await load_business_cost_income_items(db, product_code=product)
        indicators = await load_business_cost_income_indicators(db, product_code=product)
        aggregates = await _load_aggregates(
            db,
            year=year,
            month=month,
            entity_name=entity,
            group_name=group,
            product_code=product,
        )
        last_year_actuals = await _load_last_year_actuals(
            db,
            year=year,
            month=month,
            entity_name=entity,
            group_name=group,
            product_code=product,
        )
        month_cells = await _load_month_cells(
            db,
            year=year,
            month=month,
            entity_name=entity,
            group_name=group,
            product_code=product,
        )

    apply_bcir_input_derived_values(
        items,
        aggregates,
        month_cells=month_cells,
        last_year_actuals=last_year_actuals,
        report_month=month,
    )

    item_by_key: dict[tuple[str, int], dict[str, Any]] = {
        (item["section"], item["id"]): item for item in items
    }
    children_by_key: dict[tuple[str, int | None], list[dict[str, Any]]] = {}
    for item in items:
        children_by_key.setdefault((str(item["section"]), item.get("parent_id")), []).append(item)
    for children in children_by_key.values():
        children.sort(key=lambda item: (int(item.get("sort_order", 0)), int(item["id"])))

    def has_children(section: str, item_id: int) -> bool:
        return bool(children_by_key.get((section, item_id)))

    def leaf_ids(section: str, item_id: int) -> list[int]:
        children = children_by_key.get((section, item_id), [])
        if not children:
            return [item_id]
        leaves: list[int] = []
        for child in children:
            leaves.extend(leaf_ids(section, int(child["id"])))
        return leaves

    def item_metrics(section: str, item_id: int) -> dict[str, Any]:
        item = item_by_key.get((section, item_id), {})
        item_name = str(item.get("name") or "")
        if has_children(section, item_id) and not (
            section == "input" and uses_derived_input_amount(item_name)
        ):
            leaves = leaf_ids(section, item_id)
            cur_actual = sum(aggregates.get((section, leaf_id, "actual"), 0.0) for leaf_id in leaves)
            annual_budget = sum(aggregates.get((section, leaf_id, "budget"), 0.0) for leaf_id in leaves)
            annual_forecast = sum(aggregates.get((section, leaf_id, "forecast"), 0.0) for leaf_id in leaves)
            last_year_actual = sum(last_year_actuals.get((section, leaf_id), 0.0) for leaf_id in leaves)
        else:
            cur_actual = aggregates.get((section, item_id, "actual"), 0.0)
            annual_budget = aggregates.get((section, item_id, "budget"), 0.0)
            annual_forecast = aggregates.get((section, item_id, "forecast"), 0.0)
            last_year_actual = last_year_actuals.get((section, item_id), 0.0)
        raw = _metrics_from_amounts(
            current_actual=cur_actual,
            annual_budget=annual_budget,
            annual_forecast=annual_forecast,
            last_year_actual=last_year_actual,
        )
        return {
            **raw,
            "current_actual": _scale_amount(raw["current_actual"], divisor),
            "annual_budget": _scale_amount(raw["annual_budget"], divisor),
            "annual_forecast": _scale_amount(raw["annual_forecast"], divisor),
            "forecast_budget_gap": _scale_amount(raw["forecast_budget_gap"], divisor),
            "yoy_change": _scale_amount(raw["yoy_change"], divisor),
            "last_year_actual": _scale_amount(raw["last_year_actual"], divisor),
        }

    def month_entry(section: str, item_id: int) -> dict[str, Any]:
        item = item_by_key.get((section, item_id), {})
        item_name = str(item.get("name") or "")
        if has_children(section, item_id) and not (
            section == "input" and uses_derived_input_amount(item_name)
        ):
            leaves = leaf_ids(section, item_id)
            actual = sum(month_cells.get((section, leaf_id, "actual"), 0.0) for leaf_id in leaves)
            budget = sum(month_cells.get((section, leaf_id, "budget"), 0.0) for leaf_id in leaves)
            forecast = sum(month_cells.get((section, leaf_id, "forecast"), 0.0) for leaf_id in leaves)
        else:
            actual = month_cells.get((section, item_id, "actual"), 0.0)
            budget = month_cells.get((section, item_id, "budget"), 0.0)
            forecast = month_cells.get((section, item_id, "forecast"), 0.0)
        return {
            "month_actual": _scale_amount(actual, divisor),
            "month_budget": _scale_amount(budget, divisor),
            "month_forecast": _scale_amount(forecast, divisor),
        }

    def aggregate_for_item(section: str, item_id: int, field: str) -> float:
        item = item_by_key.get((section, item_id), {})
        item_name = str(item.get("name") or "")
        if has_children(section, item_id) and not (
            section == "input" and uses_derived_input_amount(item_name)
        ):
            return sum(aggregates.get((section, leaf_id, field), 0.0) for leaf_id in leaf_ids(section, item_id))
        return aggregates.get((section, item_id, field), 0.0)

    def last_year_for_item(section: str, item_id: int) -> float:
        item = item_by_key.get((section, item_id), {})
        item_name = str(item.get("name") or "")
        if has_children(section, item_id) and not (
            section == "input" and uses_derived_input_amount(item_name)
        ):
            return sum(last_year_actuals.get((section, leaf_id), 0.0) for leaf_id in leaf_ids(section, item_id))
        return last_year_actuals.get((section, item_id), 0.0)

    def tree_order(section: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []

        def walk(node: dict[str, Any]) -> None:
            result.append(node)
            for child in children_by_key.get((section, int(node["id"])), []):
                walk(child)

        for root in children_by_key.get((section, None), []):
            walk(root)
        return result

    rows: list[dict[str, Any]] = []
    for section_name in ("input", "output"):
        for item in tree_order(section_name):
            if item["enabled"] != 1:
                continue
            section = str(item["section"])
            item_id = int(item["id"])
            rows.append(
                {
                    "section": section,
                    "id": item_id,
                    "name": str(item["name"]),
                    "parent_id": item.get("parent_id"),
                    "is_leaf": not has_children(section, item_id),
                    "entry_mode": effective_bcir_item_entry_mode(
                        section,
                        str(item["name"]),
                        has_children=has_children(section, item_id),
                        manual_entry_mode=str(item.get("manual_entry_mode") or "disabled"),
                    ),
                    "data_acct_code": str(item.get("data_acct_code") or ""),
                    "org_product_ref": str(item.get("org_product_ref") or ""),
                    "org_product_entity_code": str(item.get("org_product_entity_code") or ""),
                    "org_product_table_name": str(item.get("org_product_table_name") or ""),
                    "org_product_metric_code": str(item.get("org_product_metric_code") or ""),
                    "org_product_metric_name": str(item.get("org_product_metric_name") or ""),
                    "sort_order": int(item["sort_order"]),
                    "enabled": True,
                    "metrics": item_metrics(section, item_id),
                    "monthly_entry": month_entry(section, item_id),
                }
            )

    indicator_children: dict[int | None, list[dict[str, Any]]] = {}
    for indicator in indicators:
        indicator_children.setdefault(indicator.get("parent_id"), []).append(indicator)
    for children in indicator_children.values():
        children.sort(key=lambda ind: (int(ind.get("sort_order", 0)), int(ind["id"])))

    def indicator_tree_order() -> list[dict[str, Any]]:
        ordered: list[dict[str, Any]] = []

        def walk(node: dict[str, Any]) -> None:
            ordered.append(node)
            for child in indicator_children.get(int(node["id"]), []):
                walk(child)

        for root in indicator_children.get(None, []):
            walk(root)
        return ordered

    empty_indicator_metrics = _metrics_from_amounts(
        current_actual=0.0,
        annual_budget=0.0,
        annual_forecast=0.0,
        last_year_actual=0.0,
    )
    empty_indicator_monthly = {"month_actual": 0.0, "month_budget": 0.0, "month_forecast": 0.0}

    for indicator in indicator_tree_order():
        if indicator["enabled"] != 1:
            continue
        indicator_id = int(indicator["id"])
        if int(indicator.get("display_group") or 0) == 1:
            rows.append(
                {
                    "section": "indicator",
                    "id": indicator_id,
                    "name": str(indicator["name"]),
                    "parent_id": indicator.get("parent_id"),
                    "is_leaf": False,
                    "entry_mode": "indicator",
                    "topic_metric_node_code": indicator.get("topic_metric_node_code"),
                    "sort_order": int(indicator["sort_order"]),
                    "enabled": True,
                    "metrics": empty_indicator_metrics,
                    "monthly_entry": empty_indicator_monthly,
                }
            )
            continue

        n_key = (indicator["numerator_section"], indicator["numerator_item_id"])
        d_key = (indicator["denominator_section"], indicator["denominator_item_id"])
        if n_key not in item_by_key or d_key not in item_by_key:
            continue

        n_agg_actual = aggregate_for_item(n_key[0], n_key[1], "actual")
        n_agg_budget = aggregate_for_item(n_key[0], n_key[1], "budget")
        n_agg_forecast = aggregate_for_item(n_key[0], n_key[1], "forecast")
        n_last = last_year_for_item(n_key[0], n_key[1])

        d_agg_actual = aggregate_for_item(d_key[0], d_key[1], "actual")
        d_agg_budget = aggregate_for_item(d_key[0], d_key[1], "budget")
        d_agg_forecast = aggregate_for_item(d_key[0], d_key[1], "forecast")
        d_last = last_year_for_item(d_key[0], d_key[1])

        metrics = _metrics_from_amounts(
            current_actual=_ratio(n_agg_actual, d_agg_actual) or 0.0,
            annual_budget=_ratio(n_agg_budget, d_agg_budget) or 0.0,
            annual_forecast=_ratio(n_agg_forecast, d_agg_forecast) or 0.0,
            last_year_actual=_ratio(n_last, d_last) or 0.0,
        )
        if indicator["format"] == "percent":
            metrics = {
                **metrics,
                "current_actual": round(metrics["current_actual"] * 100, 4),
                "annual_budget": round(metrics["annual_budget"] * 100, 4),
                "annual_forecast": round(metrics["annual_forecast"] * 100, 4),
                "forecast_budget_gap": round(metrics["forecast_budget_gap"] * 100, 4),
                "yoy_change": round(metrics["yoy_change"] * 100, 4),
                "last_year_actual": round(metrics["last_year_actual"] * 100, 4),
            }
        rows.append(
            {
                "section": "indicator",
                "id": indicator_id,
                "name": str(indicator["name"]),
                "parent_id": indicator.get("parent_id"),
                "is_leaf": True,
                "entry_mode": "indicator",
                "topic_metric_node_code": indicator.get("topic_metric_node_code"),
                "sort_order": int(indicator["sort_order"]),
                "enabled": True,
                "metrics": metrics,
                "monthly_entry": empty_indicator_monthly,
            }
        )

    rows.sort(
        key=lambda row: (
            {"indicator": 0, "input": 1, "output": 2}.get(str(row["section"]), 9),
            int(row["sort_order"]),
            int(row["id"]),
        )
    )
    return {
        "report_month": report_month,
        "entity_name": entity,
        "group_name": group or None,
        "product_code": product or None,
        "amount_unit": amount_unit,
        "amount_unit_label": amount_unit_label,
        "rows": rows,
        "note": "",
    }
