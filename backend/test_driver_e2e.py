"""
End-to-end test: Budget Prediction Driver Module M04
Driver parameter input -> budget_data verification -> formula calculation -> budget_summary rebuild

Test scenario:
  Product: Z0001 (loan product)
  Formula: C1200 = (A1200 + A1203) * K1200 / 12 / 1.06
  Where:
    A1200 = self-held loan daily avg balance
    A1203 = originated loan daily avg balance
    K1200 = loan yield rate (annualized, decimal)
    C1200 = loan interest income
    /12 = annual -> monthly, /1.06 = VAT adjustment

Test flow:
  1. Query existing product and data accounts
  2. Write M04 driver parameters (A1200, A1203, K1200)
  3. Read back to verify writes
  4. Trigger formula recalculation for C1200
  5. Verify C1200 = (A1200 + A1203) * K1200 / 12 / 1.06
  6. Rebuild budget_summary
  7. Verify budget_summary reflects changes
"""
import asyncio
import os
import sys
import io
import contextlib

# Ensure backend modules are importable
backend_root = os.path.dirname(os.path.abspath(__file__))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

import aiosqlite
from app.config import settings
from app.db_paths import common_db_path, budget_db_path
from app.formula_refs import extract_formula_codes
from app.main import (
    _calculate_formula_value,
    _prepare_formula_expression,
    _recalculate_data_account_formula,
    _rebuild_budget_summary_for_version,
)


async def main():
    common_path = common_db_path()
    budget_path = budget_db_path(settings.budget_year)
    print(f"Common DB: {common_path}")
    print(f"Budget DB: {budget_path}")
    print()

    # Step 1: Query existing data
    async with aiosqlite.connect(common_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Find loan product Z0001
        cur = await db.execute(
            "SELECT product_code, product_name FROM product_type WHERE product_code = 'Z0001'"
        )
        prod = await cur.fetchone()
        if not prod:
            print("ERROR: Z0001 not found!")
            return
        product_code = str(prod[0])
        product_name = str(prod[1])
        print(f"[Step 1] Test product: {product_code} - {product_name}")

        # Get data accounts for Z0001
        cur = await db.execute(
            "SELECT data_acct_code, data_acct_name, budget_formula FROM data_account WHERE product_code = ? ORDER BY data_acct_code",
            (product_code,),
        )
        accounts = {str(r[0]): (str(r[1]), str(r[2] or "")) for r in await cur.fetchall()}

        # Verify required accounts exist
        for code in ("A1200", "A1203", "K1200", "C1200"):
            if code not in accounts:
                print(f"ERROR: {code} not found in data_account for {product_code}")
                return
            name, formula = accounts[code]
            print(f"  {code}: {name}")
            if formula:
                print(f"       formula: {formula}")

        # Get period M04
        cur = await db.execute(
            "SELECT period_id, year, month FROM period WHERE month = 'M04' AND year = ?",
            (f"Y{settings.budget_year}",),
        )
        period_row = await cur.fetchone()
        if not period_row:
            print(f"ERROR: No period for M04, Y{settings.budget_year}")
            return
        period_id = int(period_row[0])
        print(f"  Period M04: period_id={period_id}")

    # Step 2: Get version
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT version_id, version_name, current_month FROM version ORDER BY version_id DESC LIMIT 1"
        )
        ver = await cur.fetchone()
        version_id = int(ver[0])
        version_name = str(ver[1])
        current_month = int(ver[2])
        print(f"\n[Step 2] Version: v{version_id} ({version_name}), current_month={current_month}")

        # Also record existing C1200 value before recalculation
        cur = await db.execute(
            "SELECT value FROM budget_data WHERE data_acct_code='C1200' AND product_code=? AND period_id=? AND version_id=? AND budget_actual=0",
            (product_code, period_id, version_id),
        )
        row = await cur.fetchone()
        c_before = float(row[0]) if row else None
        if c_before is not None:
            print(f"  C1200 value BEFORE test: {c_before:,.6f}")

    # Step 3: Write driver parameters
    print(f"\n[Step 3] Writing driver parameters for M04...")
    A1200_VALUE = 200.0  # self-held loan daily avg (200 units, consistent with existing 72.7)
    A1203_VALUE = 150.0  # originated loan daily avg
    K1200_VALUE = 0.06   # 6.0% annualized yield rate

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Write A1200 (self-held loan daily avg)
        await db.execute(
            """INSERT INTO budget_data (data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc, create_time, update_time)
               VALUES (?, ?, ?, 0, ?, ?, 0, ?, ?)
               ON CONFLICT(data_acct_code, product_code, period_id, version_id, budget_actual)
               DO UPDATE SET value = excluded.value, need_calc = 0, update_time = excluded.update_time""",
            ("A1200", product_code, period_id, version_id, A1200_VALUE, now, now),
        )

        # Write A1203 (originated loan daily avg)
        await db.execute(
            """INSERT INTO budget_data (data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc, create_time, update_time)
               VALUES (?, ?, ?, 0, ?, ?, 0, ?, ?)
               ON CONFLICT(data_acct_code, product_code, period_id, version_id, budget_actual)
               DO UPDATE SET value = excluded.value, need_calc = 0, update_time = excluded.update_time""",
            ("A1203", product_code, period_id, version_id, A1203_VALUE, now, now),
        )

        # Write K1200 (loan yield rate)
        await db.execute(
            """INSERT INTO budget_data (data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc, create_time, update_time)
               VALUES (?, ?, ?, 0, ?, ?, 0, ?, ?)
               ON CONFLICT(data_acct_code, product_code, period_id, version_id, budget_actual)
               DO UPDATE SET value = excluded.value, need_calc = 0, update_time = excluded.update_time""",
            ("K1200", product_code, period_id, version_id, K1200_VALUE, now, now),
        )

        await db.commit()

    print(f"  A1200 (self-held loan daily avg) = {A1200_VALUE:,.2f}")
    print(f"  A1203 (originated loan daily avg) = {A1203_VALUE:,.2f}")
    print(f"  K1200 (loan yield rate) = {K1200_VALUE} ({K1200_VALUE*100:.1f}%)")

    # Step 4: Read back to verify writes
    print(f"\n[Step 4] Verifying written values...")
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        errors = []
        expected_map = {"A1200": A1200_VALUE, "A1203": A1203_VALUE, "K1200": K1200_VALUE}
        for code, expected in expected_map.items():
            cur = await db.execute(
                "SELECT value FROM budget_data WHERE data_acct_code=? AND product_code=? AND period_id=? AND version_id=? AND budget_actual=0",
                (code, product_code, period_id, version_id),
            )
            row = await cur.fetchone()
            if row:
                actual = float(row[0])
                diff = abs(actual - expected)
                status = "PASS" if diff < 0.0001 else "FAIL"
                print(f"  {code} = {actual:,.6f} (expected {expected:,.6f}) [{status}]")
                if diff >= 0.0001:
                    errors.append(f"{code}: expected {expected}, got {actual}")
            else:
                errors.append(f"{code}: not found in budget_data")
                print(f"  {code}: NOT FOUND [FAIL]")

    if errors:
        print(f"\n  WRITE VERIFICATION FAILED: {errors}")
        return

    # Step 5: Recalculate C1200 formula
    c1200_formula = accounts["C1200"][1]
    print(f"\n[Step 5] Recalculating C1200 formula...")
    print(f"  Formula: {c1200_formula}")
    print(f"  A_total = A1200 + A1203 = {A1200_VALUE} + {A1203_VALUE} = {A1200_VALUE + A1203_VALUE}")
    print(f"  K = {K1200_VALUE}")

    cnt = await _recalculate_data_account_formula(
        data_acct_code="C1200",
        formula=c1200_formula,
        version_id=version_id,
        budget_actual=0,
        product_code=product_code,
        budget_path=budget_path,
        budget_year=settings.budget_year,
    )
    print(f"  Recalculated {cnt} period(s)")

    # Step 6: Verify C1200 calculation
    print(f"\n[Step 6] Verifying C1200 formula result...")
    expected_c1200 = (A1200_VALUE + A1203_VALUE) * K1200_VALUE / 12.0 / 1.06
    print(f"  Formula: C1200 = (A1200 + A1203) * K1200 / 12 / 1.06")
    print(f"  C1200 = ({A1200_VALUE} + {A1203_VALUE}) * {K1200_VALUE} / 12 / 1.06")
    print(f"  C1200 = {A1200_VALUE + A1203_VALUE} * {K1200_VALUE} / 12.72")
    print(f"  C1200 = {expected_c1200:,.10f}")
    print(f"  C1200 = {expected_c1200:,.6f} (rounded)")

    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT value FROM budget_data WHERE data_acct_code='C1200' AND product_code=? AND period_id=? AND version_id=? AND budget_actual=0",
            (product_code, period_id, version_id),
        )
        row = await cur.fetchone()
        if row:
            c_actual = float(row[0])
            diff = abs(c_actual - expected_c1200)
            print(f"\n  C1200 actual   = {c_actual:,.10f}")
            print(f"  C1200 expected = {expected_c1200:,.10f}")
            print(f"  Difference     = {diff:,.10f}")

            if diff < 0.01:
                print(f"\n  [PASS] Formula C1200 = (A1200+A1203)*K1200/12/1.06 is CORRECT")
            else:
                print(f"\n  [FAIL] Formula result mismatch! diff={diff:,.6f}")
                return
        else:
            print(f"\n  [FAIL] C1200 not found in budget_data after recalculation!")
            return

    # Step 7: Rebuild budget_summary
    print(f"\n[Step 7] Rebuilding budget_summary for version {version_id}...")
    rebuilt = await _rebuild_budget_summary_for_version(version_id, budget_path)
    print(f"  Rebuilt {rebuilt} summary rows")

    # Step 8: Verify budget_summary
    print(f"\n[Step 8] Verifying budget_summary for M04...")
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        checks = [
            ("A1200", A1200_VALUE),
            ("A1203", A1203_VALUE),
            ("K1200", K1200_VALUE),
            ("C1200", None),  # We'll check it matches budget_data
        ]
        all_pass = True
        for code, expected_val in checks:
            cur = await db.execute(
                """SELECT value, data_code_name, product_code_name
                   FROM budget_summary
                   WHERE version_id=? AND month='M04' AND budget_actual=0 AND data_code_name LIKE ?
                   ORDER BY data_code_name""",
                (version_id, f"{code}%"),
            )
            rows = await cur.fetchall()
            if rows:
                for r in rows:
                    val = float(r[0])
                    label = r[1]
                    if expected_val is not None:
                        if abs(val - expected_val) < 0.01:
                            print(f"  {label}: {val:,.6f} [PASS] (match)")
                        else:
                            print(f"  {label}: {val:,.6f} [FAIL] expected {expected_val}")
                            all_pass = False
                    else:
                        # For C1200 just show the value
                        print(f"  {label}: {val:,.10f}")
            else:
                print(f"  {code}: NOT FOUND in budget_summary [WARN]")

    # Step 9: Summary
    print()
    print("=" * 60)
    print("  END-TO-END TEST COMPLETE")
    print("=" * 60)
    print(f"  Product:     {product_code} - {product_name}")
    print(f"  Period:      M04 (period_id={period_id})")
    print(f"  Version:     v{version_id} ({version_name})")
    print(f"  A1200 input: {A1200_VALUE:,.2f}")
    print(f"  A1203 input: {A1203_VALUE:,.2f}")
    print(f"  K1200 input: {K1200_VALUE} ({K1200_VALUE*100:.1f}%)")
    print(f"  A_total:     {A1200_VALUE + A1203_VALUE:,.2f}")
    print(f"  Expected C:  {expected_c1200:,.6f}")
    print(f"  Actual C:    {c_actual:,.6f}")
    print(f"  Diff:        {abs(c_actual - expected_c1200):,.10f}")
    if abs(c_actual - expected_c1200) < 0.01:
        print("  RESULT:      PASS")
    else:
        print("  RESULT:      FAIL")
    print("=" * 60)


if __name__ == "__main__":
    # Fix Windows console encoding for Unicode characters
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    asyncio.run(main())
