"""Budget summary read-model rebuild service."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app.core.aiosqlite_compat as aiosqlite
from fastapi import HTTPException

from app.core.config import settings
from app.db_bootstrap.budget_version import ensure_budget_version_schema
from app.db_bootstrap.derived_read_models import ensure_budget_summary_read_model_schema_async
from app.core.db_paths import budget_db_path, common_db_path
from app.metric_tree_paths import build_metric_path
from app.core.months import parse_month_index
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fixed_levels(path: list[str], max_levels: int) -> list[str | None]:
    levels: list[str | None] = [None] * max_levels
    for idx, token in enumerate(path[:max_levels]):
        levels[idx] = token
    return levels


async def rebuild_budget_summary_for_version(
    version_id: int,
    budget_path: Path | None = None,
) -> int:
    common_path = common_db_path()
    resolved_budget_path = budget_path if budget_path is not None else budget_db_path(settings.budget_year)
    async with aiosqlite.connect(common_path) as cdb, aiosqlite.connect(resolved_budget_path) as bdb:
        await cdb.execute("PRAGMA foreign_keys = ON")
        await bdb.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_version_schema(bdb)
        await ensure_budget_summary_read_model_schema_async(bdb)

        cur_ver = await bdb.execute(
            "SELECT version_name, current_month FROM version WHERE version_id = ?",
            (version_id,),
        )
        vrow = await cur_ver.fetchone()
        if not vrow:
            raise HTTPException(status_code=400, detail=f"版本 {version_id} 不存在")
        version_name = str(vrow[0])
        current_month = int(vrow[1])

        cur_data_accounts = await cdb.execute(
            """
            SELECT data_acct_code, data_acct_name, value_type
            FROM data_account
            """
        )
        data_account_rows = await cur_data_accounts.fetchall()
        data_account_map = {
            str(r[0]): {
                "name": str(r[1]),
                "value_type": str(r[2]),
            }
            for r in data_account_rows
        }

        cur_product = await cdb.execute(
            f"""
            {org_product_runtime_products_cte()}
            SELECT product_code, product_name
            FROM org_product_runtime_products
            WHERE product_code <> '' AND product_name <> ''
            """
        )
        product_name_map = {
            str(r[0]): str(r[1]) for r in await cur_product.fetchall()
        }

        cur_period = await cdb.execute("SELECT period_id, year, month, quarter FROM period")
        period_map = {
            int(r[0]): {
                "year": str(r[1]),
                "month": str(r[2]),
                "quarter": str(r[3]),
            }
            for r in await cur_period.fetchall()
        }

        cur_metric_nodes = await cdb.execute(
            """
            SELECT node_code, node_name, parent_code, level, sort_order
            FROM data_account_metric_node
            WHERE is_active = 1
            """
        )
        metric_node_map = {
            str(r[0]).strip().upper(): {
                "name": str(r[1] or "").strip(),
                "parent": str(r[2]).strip().upper() if r[2] is not None else None,
                "level": int(r[3] or 0),
                "sort_order": int(r[4] or 0),
            }
            for r in await cur_metric_nodes.fetchall()
        }

        cur_metric_bindings = await cdb.execute(
            """
            SELECT b.metric_node_code, b.data_acct_code, b.scope_code,
                   COALESCE(n.sort_order, 999999) AS node_sort_order,
                   COALESCE(b.sort_order, 999999) AS binding_sort_order,
                   COALESCE(n.level, 999999) AS node_level
            FROM data_account_metric_binding b
            LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
            WHERE b.is_active = 1
              AND COALESCE(n.is_active, 1) = 1
            ORDER BY node_sort_order, binding_sort_order, node_level,
                     b.metric_node_code, b.scope_code, b.data_acct_code
            """
        )
        metric_paths_by_data_scope: dict[tuple[str, str], list[list[str]]] = {}
        seen_metric_bindings: set[tuple[str, str, str]] = set()
        for metric_code_raw, data_code_raw, scope_code_raw, *_ in await cur_metric_bindings.fetchall():
            metric_code = str(metric_code_raw or "").strip().upper()
            data_code = str(data_code_raw or "").strip().upper()
            scope_code = str(scope_code_raw or "").strip().upper()
            if not metric_code or not data_code:
                continue
            binding_key = (data_code, scope_code, metric_code)
            if binding_key in seen_metric_bindings:
                continue
            seen_metric_bindings.add(binding_key)
            metric_path = [
                part for part in build_metric_path(metric_code, metric_node_map)
                if not part.startswith("00 ")
            ]
            metric_paths_by_data_scope.setdefault((data_code, scope_code), []).append(metric_path)

        cur_budget_cols = await bdb.execute("PRAGMA table_info(budget_data)")
        budget_data_cols = {str(r[1]) for r in await cur_budget_cols.fetchall()}
        if "value_source" not in budget_data_cols:
            raise RuntimeError("budget_data 缺少当前 value_source 字段，不能按旧事实表重建预算汇总")
        cur_budget_data = await bdb.execute(
            """
            SELECT data_acct_code, product_code, period_id, budget_actual, value,
                   value_source
            FROM budget_data
            WHERE version_id = ?
            """,
            (version_id,),
        )
        budget_rows = await cur_budget_data.fetchall()

        rows_to_insert: list[tuple[Any, ...]] = []
        update_time = _iso_now()
        for data_code_raw, product_code_raw, period_id_raw, budget_actual_raw, value_raw, value_source_raw in budget_rows:
            data_code = str(data_code_raw)
            row_product_code = str(product_code_raw) if product_code_raw else ""
            period_id = int(period_id_raw)
            budget_actual = int(budget_actual_raw)
            value = float(value_raw or 0.0)
            value_source = str(value_source_raw).strip().lower()
            acct = data_account_map.get(data_code)
            period = period_map.get(period_id)
            if not acct or not period:
                continue
            month_idx = parse_month_index(period["month"])
            expected_budget_actual = 1 if month_idx < current_month else 0
            if budget_actual != expected_budget_actual:
                continue

            product_code = row_product_code or acct.get("product_code") or ""
            product_name = product_name_map.get(product_code, "") if product_code else ""
            product_code_name = (
                f"{product_code} {product_name}".strip() if product_code else None
            )
            data_code_name = f"{data_code} {acct['name']}".strip()

            metric_scope_candidates = []
            if product_code:
                metric_scope_candidates.append(product_code.strip().upper())
            metric_scope_candidates.append("CORP")
            metric_paths: list[list[str]] = []
            for metric_scope in metric_scope_candidates:
                metric_paths = metric_paths_by_data_scope.get((data_code.strip().upper(), metric_scope), [])
                if metric_paths:
                    break
            if not metric_paths:
                metric_paths = [[]]

            dept_levels = _fixed_levels([], 3)
            for metric_path in metric_paths:
                metric_levels = _fixed_levels(metric_path, 5)
                rows_to_insert.append(
                    (
                        metric_levels[0],
                        metric_levels[1],
                        metric_levels[2],
                        metric_levels[3],
                        metric_levels[4],
                        dept_levels[0],
                        dept_levels[1],
                        dept_levels[2],
                        data_code_name,
                        product_code_name,
                        period["year"],
                        period["month"],
                        period["quarter"],
                        budget_actual,
                        version_id,
                        version_name,
                        value,
                        acct["value_type"],
                        value_source,
                        update_time,
                    )
                )

        await bdb.execute("DELETE FROM budget_summary WHERE version_id = ?", (version_id,))
        if rows_to_insert:
            await bdb.executemany(
                """
                INSERT INTO budget_summary (
                  metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
                  dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
                  year, month, quarter, budget_actual, version_id, version_name,
                  value, value_type, value_source, update_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
        await bdb.commit()
    return len(rows_to_insert)
