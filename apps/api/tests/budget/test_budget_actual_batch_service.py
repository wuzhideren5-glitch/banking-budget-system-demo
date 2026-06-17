from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.services.budget_actual_batch import (
    BUDGET_FACT_REFRESH_ACTION_DESC,
    LEGACY_BUDGET_ACTUAL_BATCH_ACTION_DESC,
    BudgetActualBatchCommandResult,
    BudgetActualBatchPlanRequest,
    BudgetActualBatchPreviewContext,
    formula_rows_for_budget_actual_batch_product,
    list_budget_actual_batch_history,
    recalculate_budget_actual_batch_formula_account,
    run_budget_actual_batch_command,
    preview_budget_actual_batch_command,
)


class BudgetActualBatchFormulaRowsTests(unittest.IsolatedAsyncioTestCase):
    async def test_formula_rows_filter_scope_normalize_formula_and_order_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            with sqlite3.connect(common_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY,
                      budget_formula TEXT,
                      actual_formula TEXT
                    );
                    CREATE TABLE data_account_metric_binding (
                      data_acct_code TEXT NOT NULL,
                      scope_code TEXT NOT NULL,
                      sort_order INTEGER NOT NULL,
                      is_active INTEGER NOT NULL
                    );
                    INSERT INTO data_account(data_acct_code, budget_formula, actual_formula)
                    VALUES
                      ('A01.01.01.001', 'A01.01.01.002 + A01.01.01.003', 'A01.01.01.004 + 1'),
                      ('A01.01.01.002', 'A01.01.01.003 * 2', ''),
                      ('A01.01.01.003', '', ''),
                      ('A01.01.01.004', '', 'A01.01.01.005 + 2'),
                      ('A01.01.01.005', '', '3'),
                      ('A02.01.01.001', '9', '9'),
                      ('A01.01.01.006', '8', '8');
                    INSERT INTO data_account_metric_binding(data_acct_code, scope_code, sort_order, is_active)
                    VALUES
                      ('A01.01.01.001', 'A01', 1, 1),
                      ('A01.01.01.002', 'A01', 2, 1),
                      ('A01.01.01.003', 'A01', 3, 1),
                      ('A01.01.01.004', 'A01', 4, 1),
                      ('A01.01.01.005', 'A01', 5, 1),
                      ('A02.01.01.001', 'A02', 1, 1),
                      ('A01.01.01.006', 'A01', 6, 0);
                    """
                )

            budget_rows = await formula_rows_for_budget_actual_batch_product(
                "a01",
                0,
                common_path=common_path,
            )
            actual_rows = await formula_rows_for_budget_actual_batch_product(
                "A01",
                1,
                common_path=common_path,
            )

        self.assertEqual(
            budget_rows,
            [
                ("A01.01.01.002", "A01.01.01.003 * 2"),
                ("A01.01.01.001", "A01.01.01.002 + A01.01.01.003"),
            ],
        )
        self.assertEqual(
            actual_rows,
            [
                ("A01.01.01.005", "3"),
                ("A01.01.01.004", "A01.01.01.005 + 2"),
                ("A01.01.01.001", "A01.01.01.004 + 1"),
            ],
        )

    async def test_main_does_not_keep_formula_row_sql_or_dependency_sorting(self) -> None:
        main_source = (Path(__file__).parent / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("def _formula_rows_for_product", main_source)
        self.assertNotIn("def _order_formula_rows_by_dependency", main_source)
        self.assertNotIn("def _recalculate_data_account_formula", main_source)
        self.assertNotIn("BudgetDataWriteItem", main_source)
        self.assertNotIn("write_budget_data_items", main_source)
        self.assertNotIn("SELECT d.data_acct_code, d.", main_source)
        self.assertIn("formula_rows_for_budget_actual_batch_product", main_source)
        self.assertIn("recalculate_budget_actual_batch_product_formula_rows", main_source)

    async def test_router_does_not_keep_history_operation_log_sql(self) -> None:
        router_source = (
            Path(__file__).parent / "app" / "routers" / "budget_actual_batch.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("FROM operation_log", router_source)
        self.assertNotIn("action_type = 'BATCH_RUN'", router_source)
        self.assertNotIn("action_desc = '预算/实际数据跑批'", router_source)
        self.assertNotIn("action_desc = '预算事实刷新跑批'", router_source)
        self.assertNotIn("json.loads", router_source)
        self.assertNotIn("aiosqlite.connect", router_source)
        self.assertNotIn("common_db_path", router_source)

    async def test_router_does_not_import_aggregate_rebuild_services(self) -> None:
        router_source = (
            Path(__file__).parent / "app" / "routers" / "budget_actual_batch.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("from app.services.pivot_aggregate", router_source)
        self.assertNotIn("rebuild_budget_pivot_aggregate_for_version=", router_source)
        self.assertNotIn("rebuild_compare_pivot_aggregate=", router_source)

    async def test_history_read_model_filters_batch_logs_and_parses_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            with sqlite3.connect(common_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE operation_log (
                      log_id INTEGER PRIMARY KEY,
                      user_id TEXT,
                      affected_rows INTEGER,
                      after_data TEXT,
                      create_time TEXT,
                      action_type TEXT,
                      action_desc TEXT
                    );
                    INSERT INTO operation_log(
                      log_id, user_id, affected_rows, after_data, create_time, action_type, action_desc
                    )
                    VALUES
                      (
                        1,
                        'u1',
                        5,
                        '{"version_id": 7, "budget_year": 2026, "product_code": "A01", "product_count": 2, "budget_actuals": [0, 1], "run_formula": true, "rebuild_summary": true, "sync_compare": false, "rebuild_aggregate": true, "formula_task_count": 3, "formula_cell_count": 36, "summary_rows_rebuilt": 12}',
                        '2026-06-04T10:00:00Z',
                        'BATCH_RUN',
                        '预算事实刷新跑批'
                      ),
                      (
                        2,
                        'u2',
                        9,
                        '{broken',
                        '2026-06-04T11:00:00Z',
                        'BATCH_RUN',
                        '预算/实际数据跑批'
                      ),
                      (
                        3,
                        'ignored',
                        99,
                        '{"version_id": 99}',
                        '2026-06-04T12:00:00Z',
                        'OTHER',
                        '预算/实际数据跑批'
                      );
                    """
                )

            rows = await list_budget_actual_batch_history(common_path=common_path, limit=10)

        self.assertEqual([row.log_id for row in rows], [2, 1])
        self.assertEqual(rows[0].user_id, "u2")
        self.assertEqual(rows[0].affected_rows, 9)
        self.assertIsNone(rows[0].version_id)
        self.assertEqual(rows[0].budget_actuals, [])
        self.assertEqual(rows[1].version_id, 7)
        self.assertEqual(rows[1].budget_year, 2026)
        self.assertEqual(rows[1].product_code, "A01")
        self.assertEqual(rows[1].product_count, 2)
        self.assertEqual(rows[1].budget_actuals, [0, 1])
        self.assertTrue(rows[1].run_formula)
        self.assertTrue(rows[1].rebuild_summary)
        self.assertFalse(rows[1].sync_compare)
        self.assertTrue(rows[1].rebuild_aggregate)
        self.assertEqual(rows[1].formula_task_count, 3)
        self.assertEqual(rows[1].formula_cell_count, 36)
        self.assertEqual(rows[1].summary_rows_rebuilt, 12)
        self.assertEqual(rows[1].affected_rows, 5)

    async def test_formula_account_recalculation_reads_refs_and_writes_formula_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2026.db"
            with sqlite3.connect(common_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE period (
                      period_id INTEGER PRIMARY KEY,
                      year TEXT NOT NULL,
                      month TEXT NOT NULL
                    );
                    INSERT INTO period(period_id, year, month)
                    VALUES (1, 'Y2026', 'M01'), (2, 'Y2026', 'M02');
                    """
                )
            with sqlite3.connect(budget_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE version (
                      version_id INTEGER PRIMARY KEY,
                      version_name TEXT,
                      version_date_time TEXT,
                      current_month INTEGER NOT NULL
                    );
                    CREATE TABLE budget_data (
                      data_acct_code TEXT NOT NULL,
                      product_code TEXT NOT NULL,
                      period_id INTEGER NOT NULL,
                      budget_actual INTEGER NOT NULL,
                      version_id INTEGER NOT NULL,
                      value REAL NOT NULL DEFAULT 0,
                      formula_value REAL,
                      manual_value REAL,
                      value_source TEXT NOT NULL DEFAULT 'manual'
                        CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
                      need_calc INTEGER NOT NULL DEFAULT 0,
                      create_time TEXT,
                      update_time TEXT,
                      PRIMARY KEY(data_acct_code, product_code, period_id, version_id, budget_actual)
                    );
                    INSERT INTO version(version_id, version_name, version_date_time, current_month)
                    VALUES (7, 'V7', '2026-06-04T00:00:00Z', 1);
                    INSERT INTO budget_data(
                      data_acct_code, product_code, period_id, budget_actual, version_id,
                      value, formula_value, manual_value, value_source, need_calc
                    )
                    VALUES
                      ('A01.01.01.002', 'A01', 1, 0, 7, 10, NULL, 10, 'manual', 0),
                      ('A01.01.01.003', 'A01', 1, 0, 7, 5, NULL, 5, 'manual', 0),
                      ('A01.01.01.002', 'A01', 2, 0, 7, 20, NULL, 20, 'manual', 0),
                      ('A01.01.01.003', 'A01', 2, 0, 7, 7, NULL, 7, 'manual', 0);
                    """
                )

            count = await recalculate_budget_actual_batch_formula_account(
                data_acct_code="A01.01.01.001",
                formula="A01.01.01.002 + A01.01.01.003 * 2",
                version_id=7,
                budget_actual=0,
                product_code="A01",
                budget_path=budget_path,
                budget_year=2026,
                common_path=common_path,
            )

            with sqlite3.connect(budget_path) as conn:
                rows = conn.execute(
                    """
                    SELECT period_id, value, formula_value, manual_value, value_source, need_calc
                    FROM budget_data
                    WHERE data_acct_code = 'A01.01.01.001'
                    ORDER BY period_id
                    """
                ).fetchall()

        self.assertEqual(count, 2)
        self.assertEqual(
            rows,
            [
                (1, 20.0, 20.0, None, "formula", 0),
                (2, 34.0, 34.0, None, "formula", 0),
            ],
        )


class BudgetActualBatchPreviewCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_selects_context_counts_formula_tasks_and_builds_rollup_warnings(self) -> None:
        calls: list[tuple[str, object]] = []
        formula_rows = {
            ("A01", 0): [("D1", "A+B"), ("D2", "C+D")],
            ("A01", 1): [("D1", "actual")],
            ("A0101", 0): [("D3", "leaf")],
            ("A0101", 1): [],
        }

        async def editable_context_provider() -> tuple[Path, int, int]:
            calls.append(("context", None))
            return Path("budget_2026.db"), 2026, 9

        async def ensure_version_exists(budget_path: Path, version_id: int) -> None:
            calls.append(("ensure_version", (budget_path, version_id)))

        async def sync_rollup_accounts() -> None:
            calls.append(("sync_rollup_accounts", None))

        async def resolve_product_selection(product_code: str) -> list[str]:
            calls.append(("resolve_products", product_code))
            return ["A01", "A0101"]

        async def period_count_for_year(budget_year: int) -> int:
            calls.append(("period_count", budget_year))
            return 12

        async def formula_rows_for_product(product_code: str, budget_actual: int) -> list[tuple[str, str]]:
            calls.append(("formula_rows", (product_code, budget_actual)))
            return formula_rows[(product_code, budget_actual)]

        async def manual_override_count(**kwargs) -> int:
            calls.append(("manual_override_count", kwargs))
            self.assertEqual(kwargs["budget_path"], Path("budget_2026.db"))
            self.assertEqual(kwargs["version_id"], 9)
            self.assertEqual(kwargs["product_codes"], ["A01", "A0101"])
            self.assertEqual(kwargs["data_acct_codes"], ["D1", "D2", "D3"])
            self.assertEqual(kwargs["budget_actuals"], [0, 1])
            return 3

        async def estimate_metric_tree_rollups(**kwargs):
            calls.append(("estimate_rollups", kwargs))
            self.assertEqual(kwargs["budget_year"], 2026)
            self.assertEqual(kwargs["product_codes"], ["A01", "A0101"])
            self.assertEqual(kwargs["budget_actuals"], [0, 1])
            return SimpleNamespace(
                rollup_task_count=2,
                rollup_cell_count=24,
                audit_items=[{"node_code": "A01.01", "target_data_acct_code": "A01.01"}],
                audit_truncated=True,
                warnings=["rollup warning"],
            )

        result = await preview_budget_actual_batch_command(
            BudgetActualBatchPlanRequest(
                product_code="A01",
                version_id=None,
                budget_actuals=[0, 1],
            ),
            editable_context_provider=editable_context_provider,
            ensure_version_exists=ensure_version_exists,
            sync_rollup_accounts=sync_rollup_accounts,
            resolve_product_selection=resolve_product_selection,
            period_count_for_year=period_count_for_year,
            formula_rows_for_product=formula_rows_for_product,
            manual_override_count=manual_override_count,
            estimate_metric_tree_rollups=estimate_metric_tree_rollups,
        )

        self.assertEqual(result.mode, "preview")
        self.assertEqual(result.budget_year, 2026)
        self.assertEqual(result.version_id, 9)
        self.assertEqual(result.product_code, "A01")
        self.assertEqual(result.product_count, 2)
        self.assertEqual(result.data_account_count, 3)
        self.assertEqual(result.formula_task_count, 4)
        self.assertEqual(result.formula_cell_count, 48)
        self.assertEqual(result.manual_override_cell_count, 3)
        self.assertEqual(result.metric_rollup_task_count, 2)
        self.assertEqual(result.metric_rollup_cell_count, 24)
        self.assertEqual(result.metric_rollup_audit_items, [{"node_code": "A01.01", "target_data_acct_code": "A01.01"}])
        self.assertTrue(result.metric_rollup_audit_truncated)
        self.assertEqual(
            result.warnings,
            [
                "存在 3 个手工补录单元格；跑批会刷新公式值，但最终展示仍以手工值优先。",
                "指标树父节点汇总任务 2 个，预计写入 24 个 rollup 单元格。",
                "rollup warning",
            ],
        )
        self.assertEqual(result.message, "preview ok")
        self.assertEqual(
            [name for name, _value in calls[:4]],
            ["context", "ensure_version", "sync_rollup_accounts", "resolve_products"],
        )


class BudgetActualBatchRunCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_reuses_preview_context_rebuilds_outputs_and_logs_affected_rows(self) -> None:
        calls: list[tuple[str, object]] = []
        request = BudgetActualBatchPlanRequest(
            product_code="A01",
            version_id=9,
            budget_actuals=[0, 1],
            run_formula=True,
            rebuild_summary=True,
            sync_compare=True,
            rebuild_aggregate=True,
        )
        preview_context = BudgetActualBatchPreviewContext(
            response=BudgetActualBatchCommandResult(
                mode="preview",
                budget_year=2026,
                version_id=9,
                product_code="A01",
                product_count=2,
                data_account_count=3,
                formula_task_count=4,
                formula_cell_count=48,
                manual_override_cell_count=1,
                metric_rollup_task_count=2,
                metric_rollup_cell_count=24,
                metric_rollup_audit_items=[{"node_code": "PREVIEW"}],
                metric_rollup_audit_truncated=True,
                warnings=["preview warning"],
                message="preview ok",
            ),
            budget_path=Path("budget_2026.db"),
            budget_year=2026,
            product_codes=["A01", "A0101"],
        )

        async def preview_context_provider(inner_request: BudgetActualBatchPlanRequest) -> BudgetActualBatchPreviewContext:
            calls.append(("preview", inner_request))
            return preview_context

        async def recalculate_product_formula_rows(**kwargs) -> int:
            calls.append(("recalculate", kwargs))
            return {
                ("A01", 0): 5,
                ("A01", 1): 7,
                ("A0101", 0): 3,
                ("A0101", 1): 0,
            }[(kwargs["product_code"], kwargs["budget_actual"])]

        async def rebuild_metric_tree_rollups(**kwargs):
            calls.append(("rebuild_rollups", kwargs))
            return SimpleNamespace(
                written_cells=4,
                audit_items=[{"node_code": "RUN"}],
                audit_truncated=False,
                warnings=["run warning"],
            )

        async def rebuild_budget_summary_for_version(version_id: int, budget_path: Path) -> int:
            calls.append(("rebuild_summary", (version_id, budget_path)))
            return 6

        async def rebuild_budget_pivot_aggregate_for_version(version_id: int, budget_path: Path) -> int:
            calls.append(("rebuild_budget_aggregate", (version_id, budget_path)))
            return 8

        async def sync_compare_budget_summary(**kwargs):
            calls.append(("sync_compare", kwargs))
            return SimpleNamespace(inserted_rows=10, selected_versions=2)

        async def rebuild_compare_pivot_aggregate() -> int:
            calls.append(("rebuild_compare_aggregate", None))
            return 12

        async def set_budget_refresh_time(budget_path: Path, timestamp: str) -> None:
            calls.append(("refresh_time", (budget_path, timestamp)))

        async def write_operation_log(**kwargs) -> None:
            calls.append(("log", kwargs))

        result = await run_budget_actual_batch_command(
            request,
            preview_context_provider=preview_context_provider,
            recalculate_product_formula_rows=recalculate_product_formula_rows,
            rebuild_metric_tree_rollups=rebuild_metric_tree_rollups,
            rebuild_budget_summary_for_version=rebuild_budget_summary_for_version,
            rebuild_budget_pivot_aggregate_for_version=rebuild_budget_pivot_aggregate_for_version,
            sync_compare_budget_summary=sync_compare_budget_summary,
            rebuild_compare_pivot_aggregate=rebuild_compare_pivot_aggregate,
            set_budget_refresh_time=set_budget_refresh_time,
            iso_now=lambda: "2026-06-04T12:00:00",
            write_operation_log=write_operation_log,
        )

        self.assertEqual(result.mode, "run")
        self.assertEqual(result.formula_rows_recalculated, 15)
        self.assertEqual(result.metric_rollup_cells_written, 4)
        self.assertEqual(result.metric_rollup_audit_items, [{"node_code": "RUN"}])
        self.assertFalse(result.metric_rollup_audit_truncated)
        self.assertEqual(result.summary_rows_rebuilt, 6)
        self.assertEqual(result.budget_aggregate_rows_rebuilt, 8)
        self.assertEqual(result.compare_rows_inserted, 10)
        self.assertEqual(result.compare_aggregate_rows_rebuilt, 12)
        self.assertEqual(result.selected_compare_versions, 2)
        self.assertEqual(result.warnings, ["preview warning", "run warning"])
        self.assertEqual(result.message, "run ok")

        self.assertEqual(calls[0], ("preview", request))
        self.assertEqual(
            [call[1]["product_code"] for call in calls if call[0] == "recalculate"],
            ["A01", "A01", "A0101", "A0101"],
        )
        self.assertIn(("refresh_time", (Path("budget_2026.db"), "2026-06-04T12:00:00")), calls)
        log_payload = next(value for name, value in calls if name == "log")
        self.assertEqual(log_payload["action_type"], "BATCH_RUN")
        self.assertEqual(log_payload["action_desc"], BUDGET_FACT_REFRESH_ACTION_DESC)
        self.assertNotEqual(log_payload["action_desc"], LEGACY_BUDGET_ACTUAL_BATCH_ACTION_DESC)
        self.assertEqual(log_payload["affected_rows"], 55)
        self.assertEqual(log_payload["after_data"]["version_id"], 9)
        self.assertEqual(log_payload["after_data"]["product_count"], 2)
        self.assertEqual(log_payload["after_data"]["metric_rollup_cells_written"], 4)
        self.assertEqual(log_payload["after_data"]["compare_aggregate_rows_rebuilt"], 12)


if __name__ == "__main__":
    unittest.main()
