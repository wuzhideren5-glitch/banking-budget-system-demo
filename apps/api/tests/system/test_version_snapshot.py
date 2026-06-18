from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.services.version_snapshot import (
    build_version_snapshot,
    load_editable_version_context,
    load_latest_version_in_path,
    load_version_name_and_current_month_from_file,
)


class VersionSnapshotTests(unittest.TestCase):
    def test_loads_current_editable_version_context_from_common_db(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                db_path = data_dir / "common.db"
                with sqlite3.connect(db_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE databases(
                            id INTEGER PRIMARY KEY,
                            data_file_name TEXT NOT NULL,
                            year INTEGER NOT NULL
                        );
                        CREATE TABLE edit_show_version(
                            id INTEGER PRIMARY KEY,
                            data_file_id INTEGER NOT NULL,
                            edit_show_sign INTEGER NOT NULL,
                            version_id INTEGER NOT NULL
                        );

                        INSERT INTO databases(id, data_file_name, year)
                        VALUES (1, 'budget_2026.db', 2026);
                        INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id)
                        VALUES (1, 1, 0, 7);
                        """
                    )

                budget_path, year, version_id = await load_editable_version_context(db_path, data_dir)

                self.assertEqual(budget_path, data_dir / "budget_2026.db")
                self.assertEqual(year, 2026)
                self.assertEqual(version_id, 7)

        asyncio.run(run())

    def test_editable_version_context_rejects_missing_edit_slot(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                with sqlite3.connect(db_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE databases(
                            id INTEGER PRIMARY KEY,
                            data_file_name TEXT NOT NULL,
                            year INTEGER NOT NULL
                        );
                        CREATE TABLE edit_show_version(
                            id INTEGER PRIMARY KEY,
                            data_file_id INTEGER NOT NULL,
                            edit_show_sign INTEGER NOT NULL,
                            version_id INTEGER NOT NULL
                        );
                        """
                    )

                with self.assertRaises(HTTPException) as ctx:
                    await load_editable_version_context(db_path, Path(tmp))
                self.assertEqual(ctx.exception.status_code, 500)

        asyncio.run(run())

    def test_loads_version_name_and_current_month_from_budget_file(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                budget_path = data_dir / "budget_2026.db"
                with sqlite3.connect(budget_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE version(
                            version_id INTEGER PRIMARY KEY,
                            version_name TEXT NOT NULL,
                            version_date_time TEXT NOT NULL,
                            current_month INTEGER NOT NULL DEFAULT 1
                        );
                        INSERT INTO version(version_id, version_name, version_date_time, current_month)
                        VALUES (7, '六月滚动版', '2026-06-04T00:00:00Z', 6);
                        """
                    )

                self.assertEqual(
                    await load_version_name_and_current_month_from_file(data_dir, "budget_2026.db", 7),
                    ("六月滚动版", 6),
                )
                self.assertEqual(
                    await load_version_name_and_current_month_from_file(data_dir, "budget_2026.db", 99),
                    ("V99", 1),
                )
                self.assertEqual(
                    await load_version_name_and_current_month_from_file(data_dir, "missing.db", 8),
                    ("V8", 1),
                )

        asyncio.run(run())

    def test_loads_latest_version_in_budget_path(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                budget_path = Path(tmp) / "budget_2026.db"
                with sqlite3.connect(budget_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE version(
                            version_id INTEGER PRIMARY KEY,
                            version_name TEXT NOT NULL,
                            version_date_time TEXT NOT NULL,
                            current_month INTEGER NOT NULL DEFAULT 1
                        );
                        INSERT INTO version(version_id, version_name, version_date_time, current_month)
                        VALUES (1, '一月版', '2026-01-01T00:00:00Z', 1),
                               (3, '三月版', '2026-03-01T00:00:00Z', 3);
                        """
                    )

                self.assertEqual(
                    await load_latest_version_in_path(budget_path),
                    (3, "三月版", "2026-03-01T00:00:00Z"),
                )

        asyncio.run(run())

    def test_latest_version_in_budget_path_rejects_empty_version_table(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                budget_path = Path(tmp) / "budget_2026.db"
                with sqlite3.connect(budget_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE version(
                            version_id INTEGER PRIMARY KEY,
                            version_name TEXT NOT NULL,
                            version_date_time TEXT NOT NULL,
                            current_month INTEGER NOT NULL DEFAULT 1
                        );
                        """
                    )

                with self.assertRaises(HTTPException) as ctx:
                    await load_latest_version_in_path(budget_path)
                self.assertEqual(ctx.exception.status_code, 500)

        asyncio.run(run())

    def test_builds_edit_then_sorted_show_versions(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                with sqlite3.connect(db_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE databases(
                            id INTEGER PRIMARY KEY,
                            data_file_name TEXT NOT NULL,
                            year INTEGER NOT NULL
                        );
                        CREATE TABLE edit_show_version(
                            id INTEGER PRIMARY KEY,
                            data_file_id INTEGER NOT NULL,
                            edit_show_sign INTEGER NOT NULL,
                            version_id INTEGER NOT NULL
                        );

                        INSERT INTO databases(id, data_file_name, year)
                        VALUES (1, 'budget_2026.db', 2026),
                               (2, 'budget_2025.db', 2025);
                        INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id)
                        VALUES (1, 1, 2, 202),
                               (2, 2, 0, 101),
                               (3, 1, 1, 201);
                        """
                    )

                async def resolve(file_name: str, version_id: int) -> tuple[str, int]:
                    return (f"{file_name}:{version_id}", version_id % 100)

                response = await build_version_snapshot(db_path, resolve)

                self.assertEqual(
                    [item.label for item in response.items],
                    ["可编辑版本", "展示版本第1级", "展示版本第2级"],
                )
                self.assertEqual(response.items[0].budget_year, 2025)
                self.assertEqual(response.items[0].version_name, "budget_2025.db:101")
                self.assertEqual(response.items[1].version_name, "budget_2026.db:201")
                self.assertEqual(response.items[2].current_month, 2)

        asyncio.run(run())

    def test_allows_missing_edit_version(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                with sqlite3.connect(db_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE databases(
                            id INTEGER PRIMARY KEY,
                            data_file_name TEXT NOT NULL,
                            year INTEGER NOT NULL
                        );
                        CREATE TABLE edit_show_version(
                            id INTEGER PRIMARY KEY,
                            data_file_id INTEGER NOT NULL,
                            edit_show_sign INTEGER NOT NULL,
                            version_id INTEGER NOT NULL
                        );

                        INSERT INTO databases(id, data_file_name, year)
                        VALUES (1, 'budget_2026.db', 2026);
                        INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id)
                        VALUES (1, 1, 1, 201);
                        """
                    )

                async def resolve(file_name: str, version_id: int) -> tuple[str, int]:
                    return (f"{file_name}:{version_id}", 1)

                response = await build_version_snapshot(db_path, resolve)

                self.assertEqual([item.label for item in response.items], ["展示版本第1级"])

        asyncio.run(run())

    def test_main_no_longer_keeps_editable_context_sql(self) -> None:
        main_source = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("SELECT d.data_file_name, d.year, e.version_id", main_source)
        self.assertNotIn("WHERE e.edit_show_sign = 0", main_source)
        self.assertNotIn("async def _latest_version_in_path", main_source)
        self.assertNotIn("SELECT version_id, version_name, version_date_time", main_source)
        self.assertNotIn("async def _fetch_version_name_and_current_month_from_file", main_source)
        self.assertNotIn("SELECT version_name, current_month FROM version WHERE version_id", main_source)
