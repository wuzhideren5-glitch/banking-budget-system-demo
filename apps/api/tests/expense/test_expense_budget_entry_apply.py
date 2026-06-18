from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db_bootstrap.expense import ensure_expense_budget_entry_schema_sync
from app.services import expense_budget_entry_apply as apply_module
from app.services.expense_budget_entry_apply import apply_expense_budget_entry_rows
from app.services.expense_budget_entry_parser import ParsedBudgetEntryRow


def _row(
    *,
    amount: float = 100.0,
    owner_matched: bool = True,
    subject_matched: bool = True,
) -> ParsedBudgetEntryRow:
    return ParsedBudgetEntryRow(
        owner_name_raw="A01 产品部" if owner_matched else "未知部门",
        owner_name_mapped="A01 产品部" if owner_matched else None,
        budget_subject_raw="IT费用" if subject_matched else "未知科目",
        budget_subject_mapped="IT费用" if subject_matched else None,
        amount=amount,
        owner_matched=owner_matched,
        subject_matched=subject_matched,
        match_note=None if owner_matched and subject_matched else "未匹配",
    )


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        ensure_expense_budget_entry_schema_sync(conn)
        conn.commit()
    finally:
        conn.close()


class _FakeMysqlCursor:
    def __init__(self, state: dict[str, object]) -> None:
        self._state = state
        self.lastrowid = 77

    async def __aenter__(self) -> "_FakeMysqlCursor":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def execute(self, sql: str, params: tuple[object, ...]) -> None:
        normalized_sql = " ".join(sql.lower().split())
        self._state.setdefault("execute_calls", []).append((normalized_sql, params))  # type: ignore[union-attr]

    async def executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        normalized_sql = " ".join(sql.lower().split())
        self._state.setdefault("executemany_calls", []).append((normalized_sql, rows))  # type: ignore[union-attr]


class _FakeMysqlConnection:
    def __init__(self, state: dict[str, object]) -> None:
        self._state = state

    async def begin(self) -> None:
        self._state["began"] = True

    async def commit(self) -> None:
        self._state["committed"] = True

    async def rollback(self) -> None:
        self._state["rolled_back"] = True

    def cursor(self) -> _FakeMysqlCursor:
        return _FakeMysqlCursor(self._state)


class _FakeAcquire:
    def __init__(self, state: dict[str, object]) -> None:
        self._state = state

    async def __aenter__(self) -> _FakeMysqlConnection:
        return _FakeMysqlConnection(self._state)

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeMysqlPool:
    def __init__(self) -> None:
        self.state: dict[str, object] = {"execute_calls": [], "executemany_calls": []}

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self.state)


class ExpenseBudgetEntryApplyServiceTests(unittest.TestCase):
    def test_append_writes_matched_and_skipped_rows(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _init_db(db_path)

                result = await apply_expense_budget_entry_rows(
                    db_path,
                    budget_year=2026,
                    import_mode="append",
                    file_name="budget.xlsx",
                    rows=[_row(amount=100.0), _row(amount=999.0, owner_matched=False)],
                    created_at="2026-06-02T00:00:00Z",
                )

                with sqlite3.connect(db_path) as conn:
                    batch = conn.execute(
                        """
                        SELECT budget_year, file_name, import_mode, total_rows, matched_rows, unmatched_rows
                        FROM expense_budget_entry_batch
                        """
                    ).fetchone()
                    rows = conn.execute(
                        """
                        SELECT batch_id, budget_year, amount, owner_matched, subject_matched
                        FROM expense_budget_entry
                        ORDER BY id
                        """
                    ).fetchall()

                self.assertEqual(result.batch_id, 1)
                self.assertEqual(result.row_count, 1)
                self.assertEqual(result.unmatched_rows, 1)
                self.assertEqual(batch, (2026, "budget.xlsx", "append", 1, 1, 1))
                self.assertEqual(rows, [(1, 2026, 100.0, 1, 1), (1, 2026, 999.0, 0, 1)])

        asyncio.run(run())

    def test_overwrite_replaces_existing_year_rows(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _init_db(db_path)
                await apply_expense_budget_entry_rows(
                    db_path,
                    budget_year=2026,
                    import_mode="append",
                    file_name="old.xlsx",
                    rows=[_row(amount=10.0)],
                    created_at="2026-06-02T00:00:00Z",
                )

                result = await apply_expense_budget_entry_rows(
                    db_path,
                    budget_year=2026,
                    import_mode="overwrite",
                    file_name="new.xlsx",
                    rows=[_row(amount=200.0)],
                    created_at="2026-06-02T00:00:01Z",
                )

                with sqlite3.connect(db_path) as conn:
                    amounts = conn.execute("SELECT amount FROM expense_budget_entry ORDER BY id").fetchall()
                    batch_count = conn.execute("SELECT COUNT(*) FROM expense_budget_entry_batch").fetchone()[0]

                self.assertEqual(result.import_mode, "overwrite")
                self.assertEqual(batch_count, 1)
                self.assertEqual(amounts, [(200.0,)])

        asyncio.run(run())

    def test_runtime_common_db_uses_mysql_transaction_for_overwrite_apply(self) -> None:
        async def run() -> None:
            fake_pool = _FakeMysqlPool()
            db_path = Path(apply_module.settings.data_dir) / "common.db"
            with patch.object(apply_module, "get_pool", return_value=fake_pool):
                result = await apply_expense_budget_entry_rows(
                    db_path,
                    budget_year=2026,
                    import_mode="overwrite",
                    file_name="budget.xlsx",
                    rows=[_row(), _row(owner_matched=False)],
                    created_at="2026-06-02T00:00:00Z",
                )

            execute_calls = fake_pool.state["execute_calls"]
            executemany_calls = fake_pool.state["executemany_calls"]
            self.assertEqual(result.batch_id, 77)
            self.assertEqual(result.row_count, 1)
            self.assertEqual(result.unmatched_rows, 1)
            self.assertTrue(fake_pool.state.get("began"))
            self.assertTrue(fake_pool.state.get("committed"))
            self.assertNotIn("rolled_back", fake_pool.state)
            self.assertEqual(len(execute_calls), 3)
            self.assertIn("delete from expense_budget_entry where budget_year = %s", execute_calls[0][0])
            self.assertIn("delete from expense_budget_entry_batch where budget_year = %s", execute_calls[1][0])
            self.assertIn("insert into expense_budget_entry_batch", execute_calls[2][0])
            self.assertEqual(len(executemany_calls[0][1]), 2)
            self.assertEqual(executemany_calls[0][1][0][0], 77)
            self.assertEqual(executemany_calls[0][1][1][8], 0)

        asyncio.run(run())

    def test_rejects_import_without_matched_rows(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _init_db(db_path)
                with self.assertRaisesRegex(ValueError, "没有可导入"):
                    await apply_expense_budget_entry_rows(
                        db_path,
                        budget_year=2026,
                        import_mode="append",
                        file_name="budget.xlsx",
                        rows=[_row(owner_matched=False)],
                    )

        asyncio.run(run())

    def test_budget_entry_apply_service_does_not_import_aiosqlite(self) -> None:
        source = Path(apply_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
