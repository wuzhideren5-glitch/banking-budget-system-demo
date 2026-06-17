"""
End-to-end backend verification for the current metric/data-account model.

The test dynamically selects one product-scoped or all-product calculated
data account instead of relying on historical Z0001/A1200/C1200 seed data.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

API_ROOT = Path(__file__).resolve().parent
REPO_ROOT = API_ROOT.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.db_paths import budget_db_path, common_db_path  # noqa: E402
from app.formula_refs import extract_formula_codes  # noqa: E402
from app.services.budget_actual_batch import recalculate_budget_actual_batch_formula_account  # noqa: E402
from app.services.budget_summary_rebuild import rebuild_budget_summary_for_version  # noqa: E402
from app.services.formula_engine import calculate_formula_value  # noqa: E402
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte  # noqa: E402


def _scope_applies(scope_code: str | None, scope_codes: set[str]) -> bool:
    return str(scope_code or "").strip().upper() in scope_codes


async def main() -> int:
    os.chdir(REPO_ROOT)
    common_path = common_db_path()
    budget_path = budget_db_path(settings.budget_year)
    print(f"Common DB: {common_path}")
    print(f"Budget DB: {budget_path}\n")

    async with aiosqlite.connect(common_path) as cdb:
        cdb.row_factory = aiosqlite.Row
        await cdb.execute("PRAGMA foreign_keys = ON")

        cur = await cdb.execute(
            f"""
            {org_product_runtime_products_cte()}
            SELECT product_code, product_name, parent_code
            FROM org_product_runtime_products
            WHERE product_name LIKE '%贷%'
              AND product_code <> ''
              AND product_name <> ''
            ORDER BY product_code
            LIMIT 1
            """
        )
        product = await cur.fetchone()
        if not product:
            print("SKIP: No loan product found in org-product runtime catalog")
            return 0
        product_code = str(product["product_code"])
        product_name = str(product["product_name"])
        scope_codes = {"CORP", product_code.upper()}
        parent_code = str(product["parent_code"] or "").upper() if "parent_code" in product.keys() else ""
        while parent_code:
            scope_codes.add(parent_code)
            cur_parent = await cdb.execute(
                f"""
                {org_product_runtime_products_cte()}
                SELECT parent_code
                FROM org_product_runtime_products
                WHERE product_code = ?
                """,
                (parent_code,),
            )
            parent = await cur_parent.fetchone()
            parent_code = str(parent["parent_code"] or "").upper() if parent else ""
        print(f"[Step 1] Test product: {product_code} - {product_name}")

        cur = await cdb.execute(
            """
            SELECT da.data_acct_code, da.data_acct_name, da.value_type, b.scope_code, da.budget_formula
            FROM data_account da
            JOIN data_account_metric_binding b ON b.data_acct_code = da.data_acct_code
            WHERE da.budget_formula IS NOT NULL AND TRIM(da.budget_formula) <> ''
              AND b.is_active = 1
            ORDER BY da.data_acct_code
            """
        )
        calc_accounts = await cur.fetchall()
        selected = None
        ref_rows: list[aiosqlite.Row] = []
        for row in calc_accounts:
            if not _scope_applies(row["scope_code"], scope_codes):
                continue
            refs = sorted(extract_formula_codes(str(row["budget_formula"] or "")))
            if not refs:
                continue
            placeholders = ",".join("?" for _ in refs)
            cur_refs = await cdb.execute(
                f"""
                SELECT data_acct_code, data_acct_name, value_type
                FROM data_account
                WHERE data_acct_code IN ({placeholders})
                ORDER BY data_acct_code
                """,
                tuple(refs),
            )
            ref_rows = await cur_refs.fetchall()
            if len(ref_rows) == len(refs):
                selected = row
                break
        if selected is None:
            print("SKIP: No calculated data account with resolvable refs found")
            return 0

        target_code = str(selected["data_acct_code"])
        target_name = str(selected["data_acct_name"])
        formula = str(selected["budget_formula"] or "")
        print(f"  Target: {target_code} - {target_name}")
        print(f"  Formula: {formula}")
        for ref in ref_rows:
            print(f"  Ref: {ref['data_acct_code']} - {ref['data_acct_name']} ({ref['value_type']})")

        cur = await cdb.execute(
            "SELECT period_id FROM period WHERE month = 'M04' AND year = ?",
            (f"Y{settings.budget_year}",),
        )
        period = await cur.fetchone()
        if not period:
            raise SystemExit(f"ERROR: No M04 period for Y{settings.budget_year}")
        period_id = int(period["period_id"])

    async with aiosqlite.connect(budget_path) as bdb:
        await bdb.execute("PRAGMA foreign_keys = ON")
        cur = await bdb.execute("SELECT version_id, version_name FROM version ORDER BY version_id DESC LIMIT 1")
        version = await cur.fetchone()
        if not version:
            raise SystemExit("ERROR: No budget version found")
        version_id = int(version[0])
        version_name = str(version[1])
        print(f"\n[Step 2] Version: v{version_id} ({version_name}); period_id={period_id}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    values: dict[str, float] = {}
    async with aiosqlite.connect(budget_path) as bdb:
        await bdb.execute("PRAGMA foreign_keys = ON")
        print("\n[Step 3] Writing formula reference values")
        for idx, ref in enumerate(ref_rows, start=1):
            code = str(ref["data_acct_code"])
            value_type = str(ref["value_type"] or "")
            value = 0.045 if value_type == "百分比" else float(1000 * idx)
            values[code] = value
            await bdb.execute(
                """
                INSERT INTO budget_data (data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc, create_time, update_time)
                VALUES (?, ?, ?, 0, ?, ?, 0, ?, ?)
                ON CONFLICT(data_acct_code, product_code, period_id, version_id, budget_actual)
                DO UPDATE SET value = excluded.value, need_calc = 0, update_time = excluded.update_time
                """,
                (code, product_code, period_id, version_id, value, now, now),
            )
            print(f"  {code} = {value}")
        await bdb.commit()

    expected = calculate_formula_value(formula, values)
    print(f"\n[Step 4] Expected {target_code} = {expected:,.10f}")

    count = await recalculate_budget_actual_batch_formula_account(
        data_acct_code=target_code,
        formula=formula,
        version_id=version_id,
        budget_actual=0,
        product_code=product_code,
        budget_path=budget_path,
        budget_year=settings.budget_year,
        common_path=common_path,
    )
    print(f"  Recalculated {count} period(s)")

    async with aiosqlite.connect(budget_path) as bdb:
        await bdb.execute("PRAGMA foreign_keys = ON")
        cur = await bdb.execute(
            """
            SELECT value
            FROM budget_data
            WHERE data_acct_code = ? AND product_code = ? AND period_id = ? AND version_id = ? AND budget_actual = 0
            """,
            (target_code, product_code, period_id, version_id),
        )
        row = await cur.fetchone()
        if not row:
            raise SystemExit(f"ERROR: {target_code} not written to budget_data")
        actual = float(row[0])
        diff = abs(actual - expected)
        print(f"  Actual {target_code} = {actual:,.10f}; diff={diff:,.10f}")
        if diff >= 0.01:
            raise SystemExit(f"ERROR: Formula result mismatch for {target_code}")

    rebuilt = await rebuild_budget_summary_for_version(version_id, budget_path)
    print(f"\n[Step 5] Rebuilt budget_summary rows: {rebuilt}")
    if rebuilt <= 0:
        raise SystemExit("ERROR: budget_summary rebuild produced no rows")

    print("\n============================================================")
    print("  END-TO-END TEST PASS")
    print(f"  Product: {product_code} - {product_name}")
    print(f"  Target:  {target_code} - {target_name}")
    print("============================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
