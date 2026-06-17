"""端到端测试 v3：通过 FastAPI TestClient 完成模拟测算模块测试。

这个脚本专门给沙箱/Agent 环境使用：不启动 uvicorn，不监听 localhost 端口，
因此不会触发 "Network binding is blocked in this sandbox"。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parent
REPO_ROOT = API_ROOT.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
os.chdir(REPO_ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


TEST_USER = os.getenv("HERMES_TEST_USER", "Arthur")
TEST_PASSWORD = os.getenv("HERMES_TEST_PASSWORD", "Arthur2026")


def api(client: TestClient, method: str, path: str, body: Any | None = None) -> tuple[int, Any]:
    response = client.request(method, path, json=body)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:500]}
    return response.status_code, payload


def require(status: int, expected: int, label: str, payload: Any) -> None:
    if status != expected:
        raise SystemExit(f"{label} failed: expected {expected}, got {status}: {payload}")


def main() -> int:
    with TestClient(app) as client:
        print("=== Step 0: Health ===")
        status, resp = api(client, "GET", "/api/health")
        print(f"  {status} {resp}")
        require(status, 200, "health check", resp)

        print("\n=== Step 1: Login ===")
        status, resp = api(
            client,
            "POST",
            "/api/login",
            {"user_name": TEST_USER, "password": TEST_PASSWORD},
        )
        print(f"  {status} user={TEST_USER} need_change_password={resp.get('need_change_password')}")
        require(status, 200, "login", resp)
        if resp.get("need_change_password"):
            raise SystemExit(f"Test user {TEST_USER!r} must change password before API verification.")

        print("\n=== Step 2: Get products ===")
        status, products = api(client, "GET", "/api/org-product-runtime-products")
        require(status, 200, "org-product runtime product list", products)
        loan_products = [p for p in products if "贷" in (p.get("product_name") or "")]
        if not loan_products:
            raise SystemExit("No loan products found.")
        prod = loan_products[0]
        product_by_code = {str(p.get("product_code") or "").upper(): p for p in products}
        scope_codes = {"CORP", str(prod["product_code"]).upper()}
        parent_code = str(prod.get("parent_code") or "").upper()
        while parent_code and parent_code in product_by_code:
            scope_codes.add(parent_code)
            parent_code = str(product_by_code[parent_code].get("parent_code") or "").upper()
        print(f"  Using: {prod['product_code']} - {prod['product_name']}")

        print("\n=== Step 3: Get org-product metrics ===")
        status, metric_snapshot = api(client, "GET", "/api/org-product-metrics/db-snapshot")
        require(status, 200, "org-product metric snapshot", metric_snapshot)
        accounts = []
        for entity in metric_snapshot.get("entities", []):
            entity_code = str(entity.get("entity_code") or "").upper()
            for table in entity.get("tables", []):
                stack = list(table.get("metrics", []))
                while stack:
                    metric = stack.pop(0)
                    stack[0:0] = list(metric.get("children", []) or [])
                    if str(metric.get("mapping_status") or "").upper() != "MANUAL_CONFIRMED":
                        continue
                    data_code = str(metric.get("data_acct_code") or "").upper()
                    if not data_code:
                        continue
                    accounts.append(
                        {
                            "data_acct_code": data_code,
                            "data_acct_name": metric.get("name") or data_code,
                            "budget_formula": metric.get("formula_forecast") or metric.get("formula") or "",
                            "scope_code": entity_code,
                        }
                    )
        require(200 if accounts else 500, 200, "org-product confirmed metric list", accounts)

        daily_acct = rate_acct = formula_acct = formula_text = None
        for row in accounts:
            code = row.get("data_acct_code", "")
            name = row.get("data_acct_name", "")
            budget_formula = row.get("budget_formula") or ""
            applies = str(row.get("scope_code") or "").upper() in scope_codes
            if not applies:
                continue
            if "日均" in name and daily_acct is None:
                daily_acct = code
                print(f"  日均: {code} - {name}")
            elif "收益率" in name and rate_acct is None:
                rate_acct = code
                print(f"  收益率: {code} - {name}")
            elif budget_formula and formula_acct is None:
                formula_acct = code
                formula_text = budget_formula
                print(f"  公式科目: {code} - {name} (formula: {budget_formula[:80]})")

        if daily_acct is None or rate_acct is None:
            for row in accounts:
                code = row.get("data_acct_code", "")
                name = row.get("data_acct_name", "")
                if daily_acct is None and "日均" in name:
                    daily_acct = code
                    print(f"  Fallback 日均: {daily_acct} - {name}")
                if rate_acct is None and "收益率" in name:
                    rate_acct = code
                    print(f"  Fallback 收益率: {rate_acct} - {name}")
                if daily_acct and rate_acct:
                    break

        print("\n=== Step 4: Get simulation baseline result ===")
        status, simulation_rows = api(client, "POST", "/api/budget-simulation/result", [])
        require(status, 200, "simulation result", simulation_rows)
        print(f"  Rows: {len(simulation_rows)}")

        print("\n=== Step 5: Get version snapshot ===")
        status, version_snapshot = api(client, "GET", "/api/version-snapshot")
        require(status, 200, "version snapshot", version_snapshot)
        print(f"  Items: {len(version_snapshot.get('items', []))}")

        print()
        print("=" * 60)
        print("  SUMMARY")
        print("=" * 60)
        print("  Backend verification: PASS (FastAPI TestClient, no network binding)")
        print(f"  Product: {prod['product_code']} - {prod['product_name']}")
        print(f"  Daily account: {daily_acct}")
        print(f"  Rate account: {rate_acct}")
        print(f"  Formula account: {formula_acct}")
        print(f"  Formula: {formula_text or 'NONE'}")

        if daily_acct and rate_acct:
            a_value = 100_000_000.0
            k_pct = 4.5
            c_expected = a_value * (k_pct / 100) / 12 / 1.06
            print("\n  Formula verification (manual):")
            print("    formula = daily average x rate / 12 / 1.06")
            print(f"    C = {a_value:,.0f} x {k_pct / 100} / 12 / 1.06")
            print(f"    C = {c_expected:,.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
