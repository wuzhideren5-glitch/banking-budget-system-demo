from __future__ import annotations

import asyncio
import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.global_refresh_status import (
    collect_global_refresh_status,
    get_budget_refresh_time,
    get_compare_refresh_time,
    last_budget_or_compare_calc_time,
    set_budget_refresh_time,
    set_compare_refresh_time,
)


class GlobalRefreshStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.budget_db = root / "budget_2026.db"
        self.compare_db = root / "compare.db"

        with sqlite3.connect(self.budget_db) as conn:
            conn.execute(
                """
                CREATE TABLE budget_summary(
                    update_time TEXT
                )
                """
            )
            conn.executemany(
                "INSERT INTO budget_summary(update_time) VALUES (?)",
                [("2026-06-01T01:00:00Z",), ("2026-06-01T02:00:00Z",)],
            )

        with sqlite3.connect(self.compare_db) as conn:
            conn.execute(
                """
                CREATE TABLE settings(
                    id INTEGER PRIMARY KEY,
                    setting_key TEXT UNIQUE,
                    setting_value TEXT
                )
                """
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_budget_and_compare_refresh_times_are_stored_in_settings_tables(self) -> None:
        async def run() -> None:
            self.assertIsNone(await get_budget_refresh_time(self.budget_db))
            await set_budget_refresh_time(self.budget_db, "2026-06-02T01:00:00Z")
            self.assertEqual(await get_budget_refresh_time(self.budget_db), "2026-06-02T01:00:00Z")

            self.assertIsNone(await get_compare_refresh_time(self.compare_db))
            await set_compare_refresh_time(self.compare_db, "2026-06-02T02:00:00Z")
            self.assertEqual(await get_compare_refresh_time(self.compare_db), "2026-06-02T02:00:00Z")

        asyncio.run(run())

    def test_last_calc_time_prefers_compare_refresh_time(self) -> None:
        async def run() -> None:
            self.assertEqual(
                await last_budget_or_compare_calc_time(
                    budget_path=self.budget_db,
                    compare_path=self.compare_db,
                ),
                "2026-06-01T02:00:00Z",
            )

            await set_compare_refresh_time(self.compare_db, "2026-06-02T03:00:00Z")
            self.assertEqual(
                await last_budget_or_compare_calc_time(
                    budget_path=self.budget_db,
                    compare_path=self.compare_db,
                ),
                "2026-06-02T03:00:00Z",
            )

        asyncio.run(run())

    def test_collects_global_refresh_status_for_budget_files_sorted_by_year(self) -> None:
        async def run() -> None:
            root = Path(self.tmp.name)
            budget_2025 = root / "budget_2025.db"
            ignored = root / "not_budget.db"
            with sqlite3.connect(budget_2025) as conn:
                conn.execute("CREATE TABLE settings(setting_key TEXT UNIQUE, setting_value TEXT)")
            with sqlite3.connect(ignored) as conn:
                conn.execute("CREATE TABLE settings(setting_key TEXT UNIQUE, setting_value TEXT)")
            await set_budget_refresh_time(self.budget_db, "2026-06-02T01:00:00Z")
            await set_budget_refresh_time(budget_2025, "2025-06-02T01:00:00Z")
            await set_compare_refresh_time(self.compare_db, "2026-06-02T02:00:00Z")

            def parse_year(file_name: str) -> int | None:
                if file_name == "budget_2026.db":
                    return 2026
                if file_name == "budget_2025.db":
                    return 2025
                return None

            response = await collect_global_refresh_status(
                budget_paths=[budget_2025, ignored, self.budget_db],
                compare_path=self.compare_db,
                parse_year_from_budget_filename=parse_year,
                next_planned_refresh_time="2026-06-03T00:00:00Z",
            )

            self.assertEqual(
                [
                    (item.data_file_name, item.year, item.refresh_time_a)
                    for item in response.annual_items
                ],
                [
                    ("budget_2026.db", 2026, "2026-06-02T01:00:00Z"),
                    ("budget_2025.db", 2025, "2025-06-02T01:00:00Z"),
                ],
            )
            self.assertEqual(response.compare_refresh_time_b, "2026-06-02T02:00:00Z")
            self.assertEqual(response.next_planned_refresh_time_c, "2026-06-03T00:00:00Z")

        asyncio.run(run())

    def test_global_refresh_status_router_owns_http_interface(self) -> None:
        async def fetch_status():
            return await collect_global_refresh_status(
                budget_paths=[self.budget_db],
                compare_path=self.compare_db,
                parse_year_from_budget_filename=lambda _file_name: 2026,
                next_planned_refresh_time="2026-06-03T00:00:00Z",
            )

        router_module = importlib.import_module("app.routers.global_refresh_status")
        router = router_module.build_global_refresh_status_router(fetch_status)

        self.assertEqual({route.path for route in router.routes}, {"/api/global-refresh-status"})
        route = router.routes[0]
        self.assertIn("GET", route.methods)
        self.assertEqual(route.response_model.__name__, "GlobalRefreshStatusResponse")

    def test_main_no_longer_assembles_global_refresh_status_response(self) -> None:
        main_source = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("GlobalRefreshAnnualStatus(", main_source)
        self.assertNotIn("annual_items.sort(key=lambda x: (-x.year, x.data_file_name))", main_source)
        self.assertIn("collect_global_refresh_status", main_source)
        self.assertNotIn('@app.get("/api/global-refresh-status"', main_source)
        self.assertNotIn("async def global_refresh_status", main_source)


if __name__ == "__main__":
    unittest.main()
