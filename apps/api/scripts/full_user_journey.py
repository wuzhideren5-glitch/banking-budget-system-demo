#!/usr/bin/env python3
"""Run a full user journey against a copied DATA_DIR.

The script is intentionally destructive only inside var/test-runs/<timestamp>/data.
It exercises upload, CRUD, budget write, batch rebuild, pivot export, expense export,
smart report/PPT generation, and the retired-table deletion gate.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.runtime_metric_refs import derive_runtime_ref_from_org_product_metric_code  # noqa: E402


class Journey:
    def __init__(self, *, data_dir: Path, report_path: Path) -> None:
        self.data_dir = data_dir
        self.report_path = report_path
        self.results: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []

    def step(self, name: str, func: Callable[[], Any], *, optional: bool = False) -> Any:
        started = datetime.now().isoformat(timespec="seconds")
        try:
            value = func()
            self.results.append({"name": name, "status": "passed", "optional": optional, "started_at": started})
            return value
        except Exception as exc:
            status = "skipped" if optional else "failed"
            self.results.append(
                {
                    "name": name,
                    "status": status,
                    "optional": optional,
                    "started_at": started,
                    "error": str(exc),
                }
            )
            if optional:
                return None
            raise

    def record_artifact(self, name: str, response: Any) -> None:
        self.artifacts.append(
            {
                "name": name,
                "content_type": response.headers.get("content-type", ""),
                "content_disposition": response.headers.get("content-disposition", ""),
                "bytes": len(response.content),
            }
        )

    def write_report(self) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "data_dir": str(self.data_dir),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "results": self.results,
            "artifacts": self.artifacts,
        }
        self.report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sqlite_backup(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
        source.backup(target)


def prepare_data_dir(explicit_data_dir: Path | None) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = REPO_ROOT / "var" / "test-runs" / timestamp
    data_dir = explicit_data_dir or (run_root / "data")
    source_dir = REPO_ROOT / "var" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if explicit_data_dir is None:
        for item in source_dir.iterdir():
            target = data_dir / item.name
            if item.is_file() and item.suffix == ".db":
                sqlite_backup(item, target)
            elif item.is_file() and item.suffix not in {".db-wal", ".db-shm", ".db-journal"}:
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
    return data_dir, run_root


def assert_ok(resp: Any, *, context: str = "") -> Any:
    if resp.status_code >= 400:
        raise AssertionError(f"{context or resp.request.url.path} -> {resp.status_code}: {resp.text[:500]}")
    return resp


def assert_retired_endpoint(resp: Any, *, context: str = "") -> Any:
    if resp.status_code not in {404, 405}:
        raise AssertionError(f"{context or resp.request.url.path} should be retired, got {resp.status_code}: {resp.text[:500]}")
    return resp


def assert_file(journey: Journey, resp: Any, name: str, *, min_bytes: int = 100) -> Any:
    assert_ok(resp, context=name)
    if len(resp.content) < min_bytes:
        raise AssertionError(f"{name} returned only {len(resp.content)} bytes")
    journey.record_artifact(name, resp)
    return resp


def choose_test_product(products: list[dict[str, Any]]) -> str:
    existing = {str(p.get("product_code") or "").upper() for p in products}
    for idx in range(99, 70, -1):
        code = f"Z{idx}"
        if code not in existing:
            return code
    raise AssertionError("No free Zxx product code available for full journey test")


def create_test_metric_tree(client: Any, product_code: str) -> str:
    """Return an existing product-prefixed metric node from the org-product master."""
    payload = assert_ok(client.get("/api/org-product-metrics/db-snapshot"), context="org-product metric snapshot").json()
    nodes: list[str] = []
    for entity in payload.get("entities") or []:
        entity_code = str(entity.get("entity_code") or "").strip().upper()
        for table in entity.get("tables") or []:
            stack = list(table.get("metrics") or [])
            while stack:
                metric = stack.pop(0)
                stack[0:0] = list(metric.get("children") or [])
                runtime_ref = derive_runtime_ref_from_org_product_metric_code(
                    entity_code=entity_code,
                    metric_code=metric.get("code"),
                )
                if not runtime_ref:
                    for legacy_key in ("metric_node_code", "data_acct_code"):
                        candidate = str(metric.get(legacy_key) or "").strip().upper()
                        if candidate.startswith(f"{entity_code}."):
                            runtime_ref = candidate
                            break
                if runtime_ref:
                    nodes.append(runtime_ref)
    preferred_prefix = f"{str(product_code or '').upper()}."
    for code in nodes:
        if code.startswith(preferred_prefix):
            return code
    for code in nodes:
        if "." in code:
            return code
    raise AssertionError("No existing product-prefixed metric node available for full journey test")


def ensure_retired_tables_absent(data_dir: Path) -> None:
    with sqlite3.connect(data_dir / "common.db") as conn:
        for table_name in ("pivot_aggregate_rule", "smart_report_definition"):
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            if row:
                raise AssertionError(f"Retired table still exists in test DB: {table_name}")


def find_budget_input_cell(client: Any, version_id: int, products: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    product_codes = [
        str(item.get("product_code") or "").upper()
        for item in products
        if str(item.get("product_code") or "").upper() not in {"", "CORP"} and not str(item.get("product_code") or "").upper().startswith("Z")
    ]
    for product_code in product_codes[:25]:
        for budget_actual in (0, 1):
            resp = assert_ok(
                client.get(
                    "/api/budget-input",
                    params={"product_code": product_code, "version_id": version_id, "budget_actual": budget_actual},
                ),
                context=f"budget input {product_code}",
            )
            payload = resp.json()
            editable_periods = [p for p in payload.get("periods", []) if p.get("editable")]
            if not editable_periods:
                continue
            for row in payload.get("rows", []):
                if row.get("formula_locked") or row.get("allow_manual_entry") is False:
                    continue
                period = editable_periods[0]
                return product_code, {
                    "data_acct_code": row["data_acct_code"],
                    "product_code": row["product_code"],
                    "period_id": period["period_id"],
                    "version_id": version_id,
                    "budget_actual": budget_actual,
                    "value": 12345.67,
                }
    raise AssertionError("No editable budget input cell found")


def run_journey(journey: Journey) -> None:
    os.environ["DATA_DIR"] = str(journey.data_dir)
    os.environ["FEISHU_ENABLED"] = "false"
    os.chdir(API_ROOT)

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        journey.step("retired DB tables are absent after bootstrap", lambda: ensure_retired_tables_absent(journey.data_dir))
        journey.step("health check", lambda: assert_ok(client.get("/api/health"), context="health"))
        journey.step(
            "login as admin",
            lambda: assert_ok(
                client.post("/api/login", json={"user_name": "Arthur", "password": "Arthur2026"}),
                context="login",
            ),
        )
        journey.step("session is authenticated", lambda: assert_ok(client.get("/api/session"), context="session"))

        products = journey.step(
            "list org-product runtime products",
            lambda: assert_ok(
                client.get("/api/org-product-runtime-products"),
                context="org-product runtime products",
            ).json(),
        )
        test_product = choose_test_product(products)

        metric_node = journey.step("current metric-tree node select", lambda: create_test_metric_tree(client, test_product))
        test_data_code = metric_node

        def data_account_crud() -> None:
            body = {
                "data_acct_code": test_data_code,
                "data_acct_name": "Full Journey Metric",
                "metric_node_code": metric_node,
                "scope_code": test_product,
                "allow_manual_entry": 1,
                "value_type": "金额",
                "remark": "full-user-journey",
            }
            assert_retired_endpoint(client.post("/api/data-accounts", json=body), context="data account create")
            assert_retired_endpoint(
                client.patch(f"/api/data-accounts/{test_data_code}", json={"remark": "full-user-journey-updated"}),
                context="data account patch",
            )
            assert_retired_endpoint(client.delete(f"/api/data-accounts/{test_data_code}"), context="data account delete")

        journey.step("data-account direct write APIs retired", data_account_crud)

        def product_write_apis_retired() -> None:
            base_path = "/api/org-product-runtime-products"
            assert_retired_endpoint(
                client.post(
                    base_path,
                    json={"product_code": "ZZ99", "product_name": "Retired Product Write"},
                ),
                context=f"product create {base_path}",
            )
            assert_retired_endpoint(
                client.patch(f"{base_path}/{test_product}", json={"product_name": "Retired Product Patch"}),
                context=f"product patch {base_path}",
            )
            assert_retired_endpoint(client.delete(f"{base_path}/{test_product}"), context=f"product delete {base_path}")
            assert_retired_endpoint(client.get("/api/product-types"), context="legacy product-types endpoint")

        journey.step("product write APIs retired", product_write_apis_retired)

        def dept_crud() -> None:
            parent = next((d for d in assert_ok(client.get("/api/dept-accounts"), context="departments").json() if int(d.get("level") or 0) == 1), None)
            parent_code = parent["dept_code"] if parent else None
            body = {
                "dept_code": "Y990001",
                "dept_name": "Full Journey Department",
                "entity_name": "微众银行",
                "parent_code": parent_code,
                "level": 2 if parent_code else 1,
                "is_leaf": True,
            }
            assert_ok(client.post("/api/dept-accounts", json=body), context="department create")
            assert_ok(client.patch("/api/dept-accounts/Y990001", json={"dept_name": "Full Journey Department Updated"}), context="department patch")
            assert_ok(client.delete("/api/dept-accounts/Y990001"), context="department delete")

        journey.step("department create/update/delete", dept_crud)

        def budget_subject_crud() -> None:
            created = assert_ok(
                client.post(
                    "/api/budget-subject-catalog",
                    json={"subject_name": "Full Journey Subject", "manage_department": "Full Journey", "formula_text": ""},
                ),
                context="budget subject create",
            ).json()
            row_id = created["id"]
            assert_ok(
                client.patch(f"/api/budget-subject-catalog/{row_id}", json={"subject_name": "Full Journey Subject Updated"}),
                context="budget subject patch",
            )
            assert_ok(client.delete(f"/api/budget-subject-catalog/{row_id}"), context="budget subject delete")

        journey.step("budget subject create/update/delete", budget_subject_crud)

        file_gets = [
            ("template interface product org tree", "/api/templates/product_org_tree_import_template"),
            ("department tree export", "/api/dept-tree/export"),
            ("budget subject export", "/api/budget-subject-catalog/export"),
            ("budget input template", "/api/budget-input/template"),
            ("budget display export", "/api/budget-output/display-report/export-full"),
        ]
        for name, path in file_gets:
            journey.step(f"download {name}", lambda p=path, n=name: assert_file(journey, client.get(p), n))

        versions = journey.step("list budget input versions", lambda: assert_ok(client.get("/api/budget-input/versions"), context="versions").json())
        if not versions:
            raise AssertionError("No budget version available")
        version_id = int(versions[0]["version_id"])
        products = assert_ok(
            client.get("/api/org-product-runtime-products"),
            context="org-product runtime products refreshed",
        ).json()
        product_code, budget_item = find_budget_input_cell(client, version_id, products)

        journey.step(
            "budget input workbook export",
            lambda: assert_file(
                journey,
                client.get("/api/budget-input/export", params={"product_code": product_code, "version_id": version_id}),
                "budget input export",
            ),
        )
        journey.step(
            "budget input batch write via BudgetDataWriter",
            lambda: assert_ok(client.post("/api/budget-input/batch", json={"items": [budget_item]}), context="budget input batch"),
        )

        batch_body = {
            "product_code": product_code,
            "version_id": version_id,
            "budget_actuals": [0, 1],
            "run_formula": True,
            "rebuild_summary": True,
            "sync_compare": True,
            "rebuild_aggregate": True,
        }
        journey.step("budget/actual batch preview", lambda: assert_ok(client.post("/api/budget-actual-batch/preview", json=batch_body), context="batch preview"))
        journey.step("budget/actual batch run", lambda: assert_ok(client.post("/api/budget-actual-batch/run", json=batch_body), context="batch run"))
        journey.step("compare sync latest", lambda: assert_ok(client.get("/api/compare-summary/sync/latest"), context="compare sync latest"))

        pivot_body = {
            "row_field_ids": ["data_code_name"],
            "column_field_ids": ["month"],
            "page_field_ids": ["version_name"],
            "page_selections": {},
            "pivot_search_text": "",
        }
        export_pivot_body = {**pivot_body, "show_row_total": True, "show_column_total": True}
        journey.step("budget aggregate pivot query", lambda: assert_ok(client.post("/api/budget-summary/aggregate", json=pivot_body), context="budget aggregate"))
        journey.step("compare aggregate pivot query", lambda: assert_ok(client.post("/api/compare-summary/aggregate", json=pivot_body), context="compare aggregate"))
        journey.step("budget aggregate pivot export", lambda: assert_file(journey, client.post("/api/budget-summary/export-aggregate-pivot", json=export_pivot_body), "budget pivot export"))
        journey.step("compare aggregate pivot export", lambda: assert_file(journey, client.post("/api/compare-summary/export-aggregate-pivot", json=export_pivot_body), "compare pivot export"))

        journey.step("chart report tree", lambda: assert_ok(client.get("/api/chart/report-tree"), context="chart tree"))
        journey.step("chart version options", lambda: assert_ok(client.get("/api/chart/version-options"), context="chart versions"))
        chart_ppt_body = {
            "chart_type": "bar",
            "title": "Full Journey Pivot Chart",
            "subtitle": "Copied database validation",
            "categories": ["M01", "M02"],
            "series": [{"name": "value", "values": [1.0, 2.0]}],
            "matrix_headers": ["M01", "M02"],
            "matrix_rows": [{"label": "value", "values": ["1.0", "2.0"]}],
        }
        journey.step("pivot chart PPT export", lambda: assert_file(journey, client.post("/api/chart/export-ppt", json=chart_ppt_body), "pivot chart PPT", min_bytes=1000))

        def expense_forecast_export() -> None:
            meta = assert_ok(client.get("/api/expense-forecast/meta"), context="expense forecast meta").json()
            scope_value = (meta.get("entity_options") or [{"value": "微众银行"}])[0]["value"]
            body = {
                "year": int(meta.get("default_year") or 2026),
                "forecast_version": meta.get("default_version") or "baseline",
                "scope_type": "entity",
                "scope_value": scope_value,
                "compile_mode": "scope",
                "amount_unit": "yuan",
                "exclude_fields": [],
            }
            assert_ok(client.get("/api/expense-forecast/view", params={k: body[k] for k in ("year", "forecast_version", "scope_type", "scope_value")}), context="expense forecast view")
            assert_file(journey, client.post("/api/expense-forecast/export", json=body), "expense forecast export")

        journey.step("expense forecast view/export", expense_forecast_export)
        journey.step("expense execution status", lambda: assert_ok(client.get("/api/expense-budget-execution/status"), context="expense execution status"))
        journey.step("expense execution export", lambda: assert_file(journey, client.post("/api/expense-budget-execution/export", json={"mode": "query", "perspective": "group", "amount_unit": "yuan"}), "expense execution export"))

        def smart_report_flow() -> None:
            templates = assert_ok(client.get("/api/smart-reports/templates"), context="smart report templates").json()
            if not templates:
                raise AssertionError("No smart report templates available")
            template = next((t for t in templates if t.get("status") == "active"), templates[0])
            template_id = int(template["template_id"])
            assert_ok(client.get(f"/api/smart-reports/templates/{template_id}/variables"), context="smart report variables")
            assert_ok(client.post("/api/smart-reports/preview", json={"template_id": template_id, "parameters": {}, "text_values": {}}), context="smart report preview")
            generated = assert_ok(
                client.post(
                    "/api/smart-reports/generate",
                    json={"template_id": template_id, "instance_name": "Full Journey Smart Report", "parameters": {}, "text_values": {}},
                ),
                context="smart report generate",
            ).json()
            assert_file(journey, client.get(generated["download_url"]), "smart report download", min_bytes=1000)

        journey.step("smart report template/preview/generate/download", smart_report_flow)
        journey.step("smart report blueprints list", lambda: assert_ok(client.get("/api/smart-reports/blueprints"), context="smart report blueprints"))
        journey.step("smart report calc metrics list", lambda: assert_ok(client.get("/api/smart-reports/calc-metrics"), context="smart report calc metrics"))

        def smart_ppt_flow() -> None:
            scenes = assert_ok(client.get("/api/smart-ppt/scenes"), context="smart ppt scenes").json()
            if not scenes:
                raise AssertionError("No smart PPT scenes available")
            scene_id = int(scenes[0]["scene_id"])
            params = scenes[0].get("default_params_json") or {}
            assert_ok(client.post("/api/smart-ppt/preview", json={"scene_id": scene_id, "params": params}), context="smart ppt preview")
            generated = assert_ok(
                client.post("/api/smart-ppt/generate", json={"scene_id": scene_id, "instance_name": "Full Journey Smart PPT", "params": params}),
                context="smart ppt generate",
            ).json()
            assert_file(journey, client.get(generated["download_url"]), "smart ppt download", min_bytes=1000)
            assert_ok(client.get("/api/smart-ppt/chart-configs"), context="smart ppt chart configs")

        journey.step("smart PPT scenes/preview/generate/download", smart_ppt_flow)

        journey.step("system databases list", lambda: assert_ok(client.get("/api/system/databases"), context="system databases"))
        state = journey.step("system edit/show read", lambda: assert_ok(client.get("/api/system/edit-show-version"), context="edit show read").json())
        journey.step("system edit/show save", lambda: assert_ok(client.put("/api/system/edit-show-version", json=state), context="edit show save"))
        journey.step("version snapshot", lambda: assert_ok(client.get("/api/version-snapshot"), context="version snapshot"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=None, help="Use an existing copied DATA_DIR instead of creating one.")
    args = parser.parse_args()

    data_dir, run_root = prepare_data_dir(args.data_dir)
    report_path = run_root / "full_user_journey_report.json"
    journey = Journey(data_dir=data_dir, report_path=report_path)
    try:
        run_journey(journey)
    finally:
        journey.write_report()

    failed = [r for r in journey.results if r["status"] == "failed"]
    print(f"DATA_DIR={data_dir}")
    print(f"REPORT={report_path}")
    print(f"PASSED={len([r for r in journey.results if r['status'] == 'passed'])}")
    print(f"FAILED={len(failed)}")
    if failed:
        for item in failed:
            print(f"- {item['name']}: {item.get('error', '')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
