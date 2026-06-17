from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.schemas import SystemDatabaseCreateRequest
from app.services.system_catalog import (
    create_system_database,
    delete_system_database,
    list_system_databases,
    list_system_period_years,
    parse_year_from_budget_filename,
    resolve_system_database_file_name,
    sync_system_databases_table_with_files,
)


COMMON_SCHEMA = """
CREATE TABLE period(
    period_id INTEGER PRIMARY KEY AUTOINCREMENT,
    year TEXT NOT NULL
);
CREATE TABLE databases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_file_name TEXT NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    create_time TEXT NOT NULL
);
CREATE TABLE edit_show_version(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_file_id INTEGER NOT NULL,
    version_id INTEGER NOT NULL,
    edit_show_sign INTEGER NOT NULL
);
"""

BUDGET_SCHEMA = """
CREATE TABLE IF NOT EXISTS version(
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_date_time TEXT NOT NULL,
    version_name TEXT NOT NULL,
    current_month INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS settings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT NOT NULL
);
"""


class SystemCatalogServiceTests(unittest.TestCase):
    def test_parse_year_from_budget_filename_accepts_only_current_budget_db_names(self) -> None:
        self.assertEqual(parse_year_from_budget_filename("budget_2026.db"), 2026)
        self.assertIsNone(parse_year_from_budget_filename("budget_26.db"))
        self.assertIsNone(parse_year_from_budget_filename("archive_budget_2026.db"))

    def test_resolves_database_file_name_by_id(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                common_db = Path(tmp) / "common.db"
                with sqlite3.connect(common_db) as conn:
                    conn.executescript(COMMON_SCHEMA)
                    conn.execute(
                        "INSERT INTO databases(id, data_file_name, year, create_time) VALUES (42, 'budget_2026.db', 2026, 'now')"
                    )

                self.assertEqual(
                    await resolve_system_database_file_name(common_db, 42),
                    "budget_2026.db",
                )
                with self.assertRaises(HTTPException) as ctx:
                    await resolve_system_database_file_name(common_db, 99)
                self.assertEqual(ctx.exception.status_code, 404)

        asyncio.run(run())

    def test_lists_period_years_from_current_common_db(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                common_db = Path(tmp) / "common.db"
                with sqlite3.connect(common_db) as conn:
                    conn.executescript(COMMON_SCHEMA)
                    conn.executemany(
                        "INSERT INTO period(year) VALUES (?)",
                        [("Y2026",), ("2025年度",), ("bad",), ("Y2026",)],
                    )

                years = await list_system_period_years(common_db)

                self.assertEqual([item.year for item in years], [2025, 2026])

        asyncio.run(run())

    def test_creates_lists_and_deletes_system_database(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                common_db = data_dir / "common.db"
                with sqlite3.connect(common_db) as conn:
                    conn.executescript(COMMON_SCHEMA)
                    conn.executemany("INSERT INTO period(year) VALUES (?)", [("Y2027",)])

                async def get_periods(year: int) -> dict[int, int]:
                    return {1: 1} if year == 2027 else {}

                row = await create_system_database(
                    common_db=common_db,
                    data_dir=data_dir,
                    local_user_name="tester",
                    request=SystemDatabaseCreateRequest(year=2027, first_version_name="初始版本"),
                    budget_schema=BUDGET_SCHEMA,
                    get_year_period_months=get_periods,
                    iso_now=lambda: "2026-06-03T00:00:00",
                )

                self.assertEqual(row.data_file_name, "budget_2027.db")
                self.assertTrue((data_dir / "budget_2027.db").exists())
                listed = await list_system_databases(common_db, data_dir)
                self.assertEqual([item.data_file_name for item in listed], ["budget_2027.db"])
                self.assertEqual(listed[0].file_path, str(data_dir / "budget_2027.db"))

                with sqlite3.connect(data_dir / "budget_2027.db") as conn:
                    version = conn.execute("SELECT version_name, current_month FROM version").fetchone()
                    settings = dict(conn.execute("SELECT setting_key, setting_value FROM settings").fetchall())
                self.assertEqual(version, ("初始版本", 1))
                self.assertEqual(settings["year"], "2027")
                self.assertEqual(settings["create_user"], "tester")

                with sqlite3.connect(common_db) as conn:
                    conn.execute(
                        "INSERT INTO edit_show_version(data_file_id, version_id, edit_show_sign) VALUES (?, ?, ?)",
                        (row.id, 1, 0),
                    )
                    conn.commit()

                deleted = await delete_system_database(common_db, data_dir, row.id)

                self.assertEqual(deleted["file_name"], "budget_2027.db")
                self.assertFalse((data_dir / "budget_2027.db").exists())
                with sqlite3.connect(common_db) as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM databases").fetchone()[0], 0)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM edit_show_version").fetchone()[0], 0)

        asyncio.run(run())

    def test_syncs_databases_table_with_current_budget_files(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                common_db = data_dir / "common.db"
                with sqlite3.connect(common_db) as conn:
                    conn.executescript(COMMON_SCHEMA)
                    conn.execute(
                        "INSERT INTO databases(id, data_file_name, year, create_time) VALUES (1, 'missing.db', 2025, 'old')"
                    )
                    conn.execute(
                        "INSERT INTO edit_show_version(data_file_id, version_id, edit_show_sign) VALUES (1, 1, 0)"
                    )

                with sqlite3.connect(data_dir / "budget_2029.db") as conn:
                    conn.executescript(BUDGET_SCHEMA)
                    conn.execute(
                        "INSERT INTO settings(setting_key, setting_value) VALUES ('create_time', 'from-settings')"
                    )
                (data_dir / "not_budget_2029.db").write_text("", encoding="utf-8")

                rows = await sync_system_databases_table_with_files(common_db, data_dir)

                self.assertEqual([row.data_file_name for row in rows], ["budget_2029.db"])
                self.assertEqual(rows[0].year, 2029)
                self.assertEqual(rows[0].create_time, "from-settings")
                with sqlite3.connect(common_db) as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM edit_show_version").fetchone()[0], 0)

        asyncio.run(run())

    def test_main_no_longer_keeps_system_catalog_sync_helpers(self) -> None:
        main_source = (Path(__file__).parent / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("def _parse_year_from_budget_filename", main_source)
        self.assertNotIn("def _fmt_file_ctime", main_source)
        self.assertNotIn("async def _sync_databases_table_with_files", main_source)
        self.assertNotIn("async def _resolve_data_file_name", main_source)

    def test_create_rejects_missing_period_year(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                common_db = data_dir / "common.db"
                with sqlite3.connect(common_db) as conn:
                    conn.executescript(COMMON_SCHEMA)

                async def get_periods(_: int) -> dict[int, int]:
                    return {}

                with self.assertRaises(HTTPException) as ctx:
                    await create_system_database(
                        common_db=common_db,
                        data_dir=data_dir,
                        local_user_name="tester",
                        request=SystemDatabaseCreateRequest(year=2028, first_version_name="初始版本"),
                        budget_schema=BUDGET_SCHEMA,
                        get_year_period_months=get_periods,
                        iso_now=lambda: "2026-06-03T00:00:00",
                    )
                self.assertEqual(ctx.exception.status_code, 400)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
