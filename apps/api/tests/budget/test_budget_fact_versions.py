from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import aiosqlite

from app.services.budget_fact_versions import (
    BudgetFactVersionNotFound,
    budget_fact_version_exists,
    ensure_budget_fact_version_exists,
    load_budget_fact_current_month_from_path,
    load_budget_fact_version_identity_sync,
    load_budget_fact_version_options,
    load_budget_fact_version_options_from_path,
)


class BudgetFactVersionTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_version_options_sorts_desc_and_normalizes_display_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "budget.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE version (
                      version_id INTEGER PRIMARY KEY,
                      version_name TEXT,
                      version_date_time TEXT,
                      current_month INTEGER
                    );
                    INSERT INTO version(version_id, version_name, version_date_time, current_month)
                    VALUES
                      (1, '', '', 3),
                      (3, '三版', '2026-06-01 10:00:00', 6),
                      (2, NULL, NULL, 4);
                    """
                )

            async with aiosqlite.connect(db_path) as db:
                rows = await load_budget_fact_version_options(db)

        self.assertEqual([row.version_id for row in rows], [3, 2, 1])
        self.assertEqual(rows[0].version_name, "三版")
        self.assertEqual(rows[0].version_date_time, "2026-06-01 10:00:00")
        self.assertEqual(rows[0].current_month, 6)
        self.assertEqual(rows[1].version_name, "V2")
        self.assertIsNone(rows[1].version_date_time)
        self.assertEqual(rows[2].version_name, "V1")
        self.assertIsNone(rows[2].version_date_time)

    async def test_load_version_options_from_path_opens_budget_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "budget.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE version (
                      version_id INTEGER PRIMARY KEY,
                      version_name TEXT,
                      version_date_time TEXT,
                      current_month INTEGER
                    );
                    INSERT INTO version(version_id, version_name, version_date_time, current_month)
                    VALUES
                      (1, '初始版', '', 3),
                      (3, '当前版', '2026-06-01 10:00:00', 6);
                    """
                )

            rows = await load_budget_fact_version_options_from_path(db_path)

        self.assertEqual([row.version_id for row in rows], [3, 1])
        self.assertEqual(rows[0].version_name, "当前版")
        self.assertEqual(rows[1].version_name, "初始版")

    async def test_load_current_month_from_path_reads_version_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "budget.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE version (
                      version_id INTEGER PRIMARY KEY,
                      version_name TEXT,
                      version_date_time TEXT,
                      current_month INTEGER
                    );
                    INSERT INTO version(version_id, version_name, version_date_time, current_month)
                    VALUES (7, '当前版', '', 5);
                    """
                )

            current_month = await load_budget_fact_current_month_from_path(db_path, 7)
            with self.assertRaises(BudgetFactVersionNotFound) as raised:
                await load_budget_fact_current_month_from_path(db_path, 8)

        self.assertEqual(current_month, 5)
        self.assertEqual(raised.exception.version_id, 8)

    async def test_load_version_identity_sync_reads_name_and_current_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "budget.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE version (
                      version_id INTEGER PRIMARY KEY,
                      version_name TEXT,
                      version_date_time TEXT,
                      current_month INTEGER
                    );
                    INSERT INTO version(version_id, version_name, version_date_time, current_month)
                    VALUES (7, '当前版', '', 5);
                    """
                )

                identity = load_budget_fact_version_identity_sync(conn, 7)
                with self.assertRaises(BudgetFactVersionNotFound) as raised:
                    load_budget_fact_version_identity_sync(conn, 8)

        self.assertEqual(identity.version_id, 7)
        self.assertEqual(identity.version_name, "当前版")
        self.assertEqual(identity.current_month, 5)
        self.assertEqual(raised.exception.version_id, 8)

    async def test_budget_fact_version_exists_checks_current_version_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "budget.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE version (
                      version_id INTEGER PRIMARY KEY,
                      version_name TEXT,
                      version_date_time TEXT,
                      current_month INTEGER
                    );
                    INSERT INTO version(version_id, version_name, version_date_time, current_month)
                    VALUES (7, '当前版', '', 5);
                    """
                )

            async with aiosqlite.connect(db_path) as db:
                self.assertTrue(await budget_fact_version_exists(db, 7))
                self.assertFalse(await budget_fact_version_exists(db, 8))

    async def test_ensure_budget_fact_version_exists_opens_path_and_raises_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "budget.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE version (
                      version_id INTEGER PRIMARY KEY,
                      version_name TEXT,
                      version_date_time TEXT,
                      current_month INTEGER
                    );
                    INSERT INTO version(version_id, version_name, version_date_time, current_month)
                    VALUES (7, '当前版', '', 5);
                    """
                )

            await ensure_budget_fact_version_exists(db_path, 7)
            with self.assertRaises(BudgetFactVersionNotFound) as raised:
                await ensure_budget_fact_version_exists(db_path, 8)

        self.assertEqual(raised.exception.version_id, 8)


if __name__ == "__main__":
    unittest.main()
