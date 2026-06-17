from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import aiosqlite

from app.budget_data_writer import (
    BudgetDataWriteResult,
    delete_budget_data_for_runtime_ref,
    delete_rollup_budget_data_rows,
    delete_budget_data_for_version,
    purge_disallowed_budget_data_for_version,
)


async def _create_budget_db(path: Path, rows: list[tuple[str, float]] | None = None) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            CREATE TABLE budget_data (
              data_acct_code TEXT NOT NULL,
              value REAL
            )
            """
        )
        if rows:
            await db.executemany(
                "INSERT INTO budget_data(data_acct_code, value) VALUES (?, ?)",
                rows,
            )
        await db.commit()


async def _create_versioned_budget_db(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            CREATE TABLE budget_data (
              data_acct_code TEXT NOT NULL,
              version_id INTEGER NOT NULL,
              value REAL
            )
            """
        )
        await db.executemany(
            "INSERT INTO budget_data(data_acct_code, version_id, value) VALUES (?, ?, ?)",
            [
                ("A01.01.01.001", 1, 12.0),
                ("A02.01.01.001", 1, 22.0),
                ("A01.01.01.001", 2, 32.0),
            ],
        )
        await db.commit()


async def _create_month_window_budget_db(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            CREATE TABLE budget_data (
              data_acct_code TEXT NOT NULL,
              version_id INTEGER NOT NULL,
              period_id INTEGER NOT NULL,
              budget_actual INTEGER NOT NULL,
              value REAL
            )
            """
        )
        await db.executemany(
            """
            INSERT INTO budget_data(data_acct_code, version_id, period_id, budget_actual, value)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("A01.01.01.001", 1, 1, 0, 10.0),
                ("A01.01.01.001", 1, 1, 1, 11.0),
                ("A01.01.01.001", 1, 6, 1, 16.0),
                ("A01.01.01.001", 1, 7, 0, 20.0),
                ("A01.01.01.001", 1, 7, 1, 21.0),
                ("A01.01.01.001", 2, 1, 0, 99.0),
            ],
        )
        await db.commit()


async def _create_rollup_budget_db(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            CREATE TABLE budget_data (
              data_acct_code TEXT NOT NULL,
              product_code TEXT NOT NULL,
              version_id INTEGER NOT NULL,
              budget_actual INTEGER NOT NULL,
              value_source TEXT NOT NULL,
              value REAL
            )
            """
        )
        await db.executemany(
            """
            INSERT INTO budget_data(
              data_acct_code, product_code, version_id, budget_actual, value_source, value
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("A01.PARENT", "A01", 1, 0, "rollup", 10.0),
                ("A01.PARENT", "A01", 1, 1, "manual", 11.0),
                ("A02.PARENT", "A02", 1, 0, "rollup", 20.0),
                ("A01.PARENT", "A01", 2, 0, "rollup", 99.0),
            ],
        )
        await db.commit()


class BudgetDataWriteResultTests(unittest.TestCase):
    def test_note_for_source_prefers_matching_source_ref_and_falls_back_to_first_message(self) -> None:
        result = BudgetDataWriteResult(
            warnings=[
                "预算数 行 2 M01: 当前版本月份窗口限制",
                "预算数 行 3 M02: 机构及产品指标编码产品不匹配",
            ],
            errors=["全局写入失败"],
        )

        self.assertEqual(
            result.note_for_source("预算数 行 3 M02"),
            "预算数 行 3 M02: 机构及产品指标编码产品不匹配",
        )
        self.assertEqual(
            result.note_for_source("预算数 行 9 M09"),
            "预算数 行 2 M01: 当前版本月份窗口限制",
        )
        self.assertIsNone(BudgetDataWriteResult().note_for_source("预算数 行 9 M09"))


class BudgetDataWriterDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_budget_data_for_runtime_ref_scans_budget_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "budget_2026.db"
            no_table = root / "budget_empty.db"
            missing = root / "budget_missing.db"
            await _create_budget_db(
                current,
                [
                    ("A01.01.01.001", 12.0),
                    ("A02.01.01.001", 22.0),
                    ("A01.01.01.001", 13.0),
                ],
            )
            async with aiosqlite.connect(no_table) as db:
                await db.execute("CREATE TABLE version(version_id INTEGER PRIMARY KEY)")
                await db.commit()

            result = await delete_budget_data_for_runtime_ref(
                budget_paths=[current, no_table, missing],
                data_acct_code="a01.01.01.001",
            )

            self.assertEqual(result.deleted_rows, 2)
            self.assertEqual(result.deleted_by_budget_file, {str(current): 2})
            async with aiosqlite.connect(current) as db:
                cur = await db.execute("SELECT data_acct_code, value FROM budget_data")
                self.assertEqual(await cur.fetchall(), [("A02.01.01.001", 22.0)])

    async def test_delete_budget_data_for_version_uses_caller_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            budget_path = Path(tmp) / "budget_2026.db"
            await _create_versioned_budget_db(budget_path)

            async with aiosqlite.connect(budget_path) as db:
                deleted = await delete_budget_data_for_version(db, version_id=1)
                self.assertEqual(deleted, 2)
                await db.rollback()

            async with aiosqlite.connect(budget_path) as db:
                cur = await db.execute(
                    "SELECT COUNT(*) FROM budget_data WHERE version_id = 1"
                )
                self.assertEqual((await cur.fetchone())[0], 2)

    async def test_purge_disallowed_budget_data_for_version_follows_month_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            budget_path = Path(tmp) / "budget_2026.db"
            await _create_month_window_budget_db(budget_path)

            async with aiosqlite.connect(budget_path) as db:
                deleted = await purge_disallowed_budget_data_for_version(
                    db,
                    version_id=1,
                    current_month=7,
                    period_month_map={1: 1, 6: 6, 7: 7},
                )
                await db.commit()

            self.assertEqual(deleted, 2)
            async with aiosqlite.connect(budget_path) as db:
                cur = await db.execute(
                    """
                    SELECT version_id, period_id, budget_actual, value
                    FROM budget_data
                    ORDER BY version_id, period_id, budget_actual
                    """
                )
                self.assertEqual(
                    await cur.fetchall(),
                    [
                        (1, 1, 1, 11.0),
                        (1, 6, 1, 16.0),
                        (1, 7, 0, 20.0),
                        (2, 1, 0, 99.0),
                    ],
                )

    async def test_delete_rollup_budget_data_rows_only_removes_matching_rollups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            budget_path = Path(tmp) / "budget_2026.db"
            await _create_rollup_budget_db(budget_path)

            deleted = await delete_rollup_budget_data_rows(
                budget_path=budget_path,
                version_id=1,
                data_acct_codes=["a01.parent"],
                product_codes=["a01"],
                budget_actuals=[0, 1],
            )

            self.assertEqual(deleted, 1)
            async with aiosqlite.connect(budget_path) as db:
                cur = await db.execute(
                    """
                    SELECT data_acct_code, product_code, version_id, budget_actual, value_source, value
                    FROM budget_data
                    ORDER BY data_acct_code, product_code, version_id, budget_actual, value_source
                    """
                )
                self.assertEqual(
                    await cur.fetchall(),
                    [
                        ("A01.PARENT", "A01", 1, 1, "manual", 11.0),
                        ("A01.PARENT", "A01", 2, 0, "rollup", 99.0),
                        ("A02.PARENT", "A02", 1, 0, "rollup", 20.0),
                    ],
                )


if __name__ == "__main__":
    unittest.main()
