from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.budget_data_writer import IMPORT_INPUT_POLICY, write_budget_data_items
from app.services.org_product_budget_sync import (
    OrgProductBudgetSyncPlan,
    apply_org_product_budget_sync_plan,
    plan_org_product_budget_sync,
)


class OrgProductBudgetSyncTests(unittest.TestCase):
    def test_plan_and_writer_sync_rows_derived_from_org_product_metric_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common_path = root / "common.db"
            budget_path = root / "budget_2026.db"
            with sqlite3.connect(common_path) as conn:
                conn.execute("CREATE TABLE period(period_id INTEGER PRIMARY KEY, year TEXT, month TEXT)")
                conn.executemany(
                    "INSERT INTO period(period_id, year, month) VALUES (?, ?, ?)",
                    [(idx, "Y2026", f"M{idx:02d}") for idx in range(1, 13)],
                )
                conn.execute(
                    """
                    CREATE TABLE data_account(
                      data_acct_code TEXT PRIMARY KEY,
                      budget_formula TEXT,
                      actual_formula TEXT,
                      allow_manual_entry INTEGER
                    )
                    """
                )
                conn.executemany(
                    """
                    INSERT INTO data_account(data_acct_code, budget_formula, actual_formula, allow_manual_entry)
                    VALUES (?, '', '', 1)
                    """,
                    [("A01.01.01",), ("A01.05.03",)],
                )
                conn.commit()

            with sqlite3.connect(budget_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE version(
                      version_id INTEGER PRIMARY KEY,
                      version_name TEXT,
                      version_date_time TEXT,
                      current_month INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO version(version_id, version_name, version_date_time, current_month) VALUES (1, 'v1', '', 3)"
                )
                conn.execute(
                    """
                    CREATE TABLE budget_data(
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      data_acct_code TEXT NOT NULL,
                      product_code TEXT NOT NULL,
                      period_id INTEGER NOT NULL,
                      budget_actual INTEGER NOT NULL,
                      version_id INTEGER NOT NULL,
                      value REAL NOT NULL,
                      formula_value REAL,
                      manual_value REAL,
                      value_source TEXT NOT NULL DEFAULT 'none',
                      need_calc INTEGER NOT NULL DEFAULT 0,
                      create_time TEXT,
                      update_time TEXT,
                      UNIQUE(data_acct_code, product_code, period_id, version_id, budget_actual)
                    )
                    """
                )
                conn.commit()

            payload = {
                "metrics": [
                    {
                        "metric_code": "A010101",
                        "metric_name": "营业收入",
                        "values": {"months": {"a1": "100", "f4": "200", "f2": "300", "a3": "400"}},
                    },
                    {
                        "metric_code": "A010503",
                        "metric_name": "05费用保护",
                        "values": {"months": {"a1": "999"}},
                    },
                    {
                        "metric_code": "LEGACY",
                        "metric_name": "无法派生行",
                        "values": {"months": {"a1": "888"}},
                    },
                ]
            }
            plan = plan_org_product_budget_sync(
                payload=payload,
                entity_code="A01",
                table_name="业务状况表",
                year=2026,
                budget_version_id=1,
                current_month=3,
                period_month_map={idx: idx for idx in range(1, 13)},
            )

            self.assertEqual(plan.candidate_rows, 2)
            self.assertEqual(plan.non_confirmed_rows, 0)
            self.assertEqual(plan.unbound_rows, 1)
            self.assertEqual(len(plan.write_items), 3)
            self.assertEqual(plan.skipped_cells, 2)

            result = asyncio.run(
                write_budget_data_items(
                    budget_path=budget_path,
                    common_path=common_path,
                    items=plan.write_items,
                    policy=IMPORT_INPUT_POLICY,
                )
            )

            self.assertEqual(result.saved_cells, 3)
            with sqlite3.connect(budget_path) as conn:
                rows = conn.execute(
                    """
                    SELECT data_acct_code, product_code, period_id, budget_actual, version_id, value, value_source
                    FROM budget_data
                    ORDER BY period_id, budget_actual
                    """
                ).fetchall()

            self.assertEqual(
                rows,
                [
                    ("A01.01.01", "A01", 1, 1, 1, 100.0, "manual"),
                    ("A01.05.03", "A01", 1, 1, 1, 999.0, "manual"),
                    ("A01.01.01", "A01", 4, 0, 1, 200.0, "manual"),
                ],
            )

    def test_apply_refreshes_summary_and_pivot_after_successful_write(self) -> None:
        calls: list[tuple[str, object]] = []

        async def fake_write_items(**kwargs):
            calls.append(("write", len(kwargs["items"])))
            return type(
                "WriteResult",
                (),
                {
                    "saved_cells": 1,
                    "skipped_cells": 0,
                    "affected_products": {"A01"},
                    "written_data_accts": {"A01.01.01"},
                    "warnings": [],
                    "errors": [],
                },
            )()

        async def fake_rebuild_summary(version_id: int, budget_path: Path | None) -> int:
            calls.append(("summary", (version_id, budget_path)))
            return 3

        async def fake_rebuild_aggregate(version_id: int, budget_path: Path) -> int:
            calls.append(("aggregate", (version_id, budget_path)))
            return 9

        async def fake_set_refresh_time(budget_path: Path, timestamp: str) -> None:
            calls.append(("refresh", (budget_path, timestamp)))

        plan = OrgProductBudgetSyncPlan(
            write_items=[
                next(
                    iter(
                        plan_org_product_budget_sync(
                            payload={
                                "metrics": [
                                    {
                                        "metric_code": "A010101",
                                        "values": {"months": {"a1": "1"}},
                                    }
                                ]
                            },
                            entity_code="A01",
                            table_name="业务状况表",
                            year=2026,
                            budget_version_id=1,
                            current_month=3,
                            period_month_map={1: 1},
                        ).write_items
                    )
                )
            ]
        )

        result = asyncio.run(
            apply_org_product_budget_sync_plan(
                plan=plan,
                common_path=Path("common.db"),
                budget_path=Path("budget_2026.db"),
                budget_version_id=1,
                timestamp="2026-06-05T16:40:00Z",
                write_items=fake_write_items,
                rebuild_summary=fake_rebuild_summary,
                rebuild_aggregate=fake_rebuild_aggregate,
                set_refresh_time=fake_set_refresh_time,
            )
        )

        self.assertEqual(result.summary_rows, 3)
        self.assertEqual(result.budget_aggregate_rows, 9)
        self.assertEqual(
            calls,
            [
                ("write", 1),
                ("summary", (1, Path("budget_2026.db"))),
                ("refresh", (Path("budget_2026.db"), "2026-06-05T16:40:00Z")),
                ("aggregate", (1, Path("budget_2026.db"))),
            ],
        )

    def test_apply_skips_downstream_refresh_when_nothing_was_written(self) -> None:
        calls: list[str] = []

        async def fake_write_items(**kwargs):
            calls.append("write")
            return type(
                "WriteResult",
                (),
                {
                    "saved_cells": 0,
                    "skipped_cells": 0,
                    "affected_products": set(),
                    "written_data_accts": set(),
                    "warnings": [],
                    "errors": [],
                },
            )()

        async def fail_rebuild_summary(version_id: int, budget_path: Path | None) -> int:
            raise AssertionError("summary should not refresh without written cells")

        result = asyncio.run(
            apply_org_product_budget_sync_plan(
                plan=OrgProductBudgetSyncPlan(),
                common_path=Path("common.db"),
                budget_path=Path("budget_2026.db"),
                budget_version_id=1,
                timestamp="2026-06-05T16:40:00Z",
                write_items=fake_write_items,
                rebuild_summary=fail_rebuild_summary,
            )
        )

        self.assertEqual(result.summary_rows, 0)
        self.assertEqual(result.budget_aggregate_rows, 0)
        self.assertEqual(calls, ["write"])
