from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db_bootstrap.expense import ensure_expense_budget_entry_schema_sync
from app.services import expense_budget_entry_store as store_module
from app.services.expense_budget_entry_store import (
    ExpenseBudgetEntryBatchMissingError,
    delete_expense_budget_entry_batch,
    list_expense_budget_entries,
    list_expense_budget_entry_batches,
    update_expense_budget_entry_row,
)


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        ensure_expense_budget_entry_schema_sync(conn)
        conn.execute(
            """
            INSERT INTO expense_budget_entry_batch(
              budget_year, file_name, import_mode, total_rows, matched_rows, unmatched_rows, created_at, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (2026, "budget.xlsx", "append", 1, 1, 0, "2026-06-02T00:00:00Z", "note"),
        )
        conn.execute(
            """
            INSERT INTO expense_budget_entry(
              batch_id, budget_year, owner_name_raw, owner_name_mapped,
              budget_subject_raw, budget_subject_mapped, amount, adjustment_amount,
              owner_matched, subject_matched, match_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, 2026, "A01 产品部", "A01 产品部", "IT费用", "IT费用", 100.0, 5.0, 1, 1, None),
        )
        conn.commit()
    finally:
        conn.close()


class _FakeDeleteCursor:
    def __init__(self, state: dict[str, object]) -> None:
        self._state = state
        self._row: tuple[object, ...] | None = None

    async def __aenter__(self) -> "_FakeDeleteCursor":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def execute(self, sql: str, params: tuple[object, ...]) -> None:
        normalized_sql = " ".join(sql.lower().split())
        self._state.setdefault("cursor_execute_calls", []).append((normalized_sql, params))  # type: ignore[union-attr]
        if normalized_sql.startswith("select id from expense_budget_entry_batch"):
            self._row = (7,)
        elif normalized_sql.startswith("select count(*) from expense_budget_entry"):
            self._row = (2,)
        elif normalized_sql.startswith("delete from expense_budget_entry"):
            self._row = None
        elif normalized_sql.startswith("delete from expense_budget_entry_batch"):
            self._row = None
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    async def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class _FakeConnection:
    def __init__(self, state: dict[str, object]) -> None:
        self._state = state

    async def begin(self) -> None:
        self._state["began"] = True

    async def commit(self) -> None:
        self._state["committed"] = True

    async def rollback(self) -> None:
        self._state["rolled_back"] = True

    def cursor(self) -> _FakeDeleteCursor:
        return _FakeDeleteCursor(self._state)


class _FakeAcquire:
    def __init__(self, state: dict[str, object]) -> None:
        self._state = state

    async def __aenter__(self) -> _FakeConnection:
        return _FakeConnection(self._state)

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeMysqlPool:
    def __init__(self) -> None:
        self.state: dict[str, object] = {
            "fetch_all_calls": [],
            "fetch_one_calls": [],
            "execute_calls": [],
            "cursor_execute_calls": [],
        }
        self.amount = 100.0
        self.adjustment_amount = 5.0

    async def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized_sql = " ".join(sql.lower().split())
        self.state.setdefault("fetch_all_calls", []).append((normalized_sql, params))  # type: ignore[union-attr]
        if "from expense_budget_entry_batch" in normalized_sql:
            return [
                {
                    "id": 7,
                    "budget_year": 2026,
                    "file_name": "mysql-budget.xlsx",
                    "import_mode": "append",
                    "total_rows": 2,
                    "matched_rows": 1,
                    "unmatched_rows": 1,
                    "created_at": "2026-06-02T00:00:00Z",
                    "note": "mysql",
                }
            ]
        if "from expense_budget_entry" in normalized_sql:
            return [
                {
                    "id": 11,
                    "batch_id": 7,
                    "budget_year": 2026,
                    "owner_name_raw": "A01 产品部",
                    "owner_name_mapped": "A01 产品部",
                    "budget_subject_raw": "IT费用",
                    "budget_subject_mapped": "IT费用",
                    "amount": self.amount,
                    "adjustment_amount": self.adjustment_amount,
                    "owner_matched": 1,
                    "subject_matched": 1,
                    "match_note": None,
                }
            ]
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized_sql = " ".join(sql.lower().split())
        self.state.setdefault("fetch_one_calls", []).append((normalized_sql, params))  # type: ignore[union-attr]
        if "information_schema.tables" in normalized_sql:
            return {"exists_flag": 1}
        if "from expense_budget_entry" in normalized_sql:
            return {
                "id": 11,
                "batch_id": 7,
                "budget_year": 2026,
                "owner_name_raw": "A01 产品部",
                "owner_name_mapped": "A01 产品部",
                "budget_subject_raw": "IT费用",
                "budget_subject_mapped": "IT费用",
                "amount": self.amount,
                "adjustment_amount": self.adjustment_amount,
                "owner_matched": 1,
                "subject_matched": 1,
                "match_note": None,
            }
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        normalized_sql = " ".join(sql.lower().split())
        self.state.setdefault("execute_calls", []).append((normalized_sql, params))  # type: ignore[union-attr]
        self.amount = float(params[0])
        self.adjustment_amount = float(params[1])
        return 1

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self.state)


class ExpenseBudgetEntryStoreTests(unittest.TestCase):
    def test_sqlite_list_update_and_delete_batch(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _init_db(db_path)

                batches = await list_expense_budget_entry_batches(db_path, budget_year=2026)
                rows = await list_expense_budget_entries(db_path, budget_year=2026, batch_id=1)
                updated = await update_expense_budget_entry_row(
                    db_path,
                    row_id=1,
                    amount=120.0,
                    adjustment_amount=8.0,
                )
                deleted_rows = await delete_expense_budget_entry_batch(db_path, batch_id=1)

                self.assertEqual(batches[0].file_name, "budget.xlsx")
                self.assertEqual(rows[0].adjusted_amount, 105.0)
                self.assertEqual(updated.adjusted_amount, 128.0)
                self.assertEqual(deleted_rows, 1)
                with sqlite3.connect(db_path) as conn:
                    remaining = conn.execute("SELECT COUNT(*) FROM expense_budget_entry").fetchone()[0]
                self.assertEqual(remaining, 0)

        asyncio.run(run())

    def test_missing_batch_raises(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _init_db(db_path)
                with self.assertRaises(ExpenseBudgetEntryBatchMissingError):
                    await delete_expense_budget_entry_batch(db_path, batch_id=999)

        asyncio.run(run())

    def test_runtime_common_db_uses_mysql_pool_for_store_operations(self) -> None:
        async def run() -> None:
            fake_pool = _FakeMysqlPool()
            db_path = Path(store_module.settings.data_dir) / "common.db"
            with patch.object(store_module, "get_pool", return_value=fake_pool):
                batches = await list_expense_budget_entry_batches(db_path, budget_year=2026)
                rows = await list_expense_budget_entries(db_path, budget_year=2026, batch_id=7)
                updated = await update_expense_budget_entry_row(db_path, row_id=11, amount=130.0)
                deleted_rows = await delete_expense_budget_entry_batch(db_path, batch_id=7)

            self.assertEqual(batches[0].id, 7)
            self.assertEqual(rows[0].id, 11)
            self.assertEqual(updated.adjusted_amount, 135.0)
            self.assertEqual(deleted_rows, 2)
            self.assertTrue(fake_pool.state.get("began"))
            self.assertTrue(fake_pool.state.get("committed"))
            self.assertNotIn("rolled_back", fake_pool.state)
            self.assertTrue(fake_pool.state["execute_calls"])  # type: ignore[index]
            self.assertTrue(fake_pool.state["cursor_execute_calls"])  # type: ignore[index]

        asyncio.run(run())

    def test_budget_entry_store_does_not_import_aiosqlite(self) -> None:
        source = Path(store_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
