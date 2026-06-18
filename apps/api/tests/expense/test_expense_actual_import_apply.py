from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db_bootstrap.expense import ensure_expense_actual_import_schema_sync
from app.services import expense_actual_import_apply as apply_module
from app.services.expense_actual_import_apply import apply_expense_actual_import_rows
from app.services.expense_actual_import_parser import ParsedActualDetailRow


def _row(*, period_ym: str = "2026-04", amount: float = 100.0) -> ParsedActualDetailRow:
    return ParsedActualDetailRow(
        data_date=f"{period_ym}-30",
        period_ym=period_ym,
        period_text=period_ym,
        org_code="ORG",
        org_name="费用部门",
        dep_code="DEP",
        dep_name="责任中心",
        subject_code="SUB",
        subject_name="科目",
        amount=amount,
        fee_type_code="F01",
        fee_type_name="费用类别",
        bi_ai_source_code="C01",
        bi_ai_source_name="管控口径",
        manage_department_code="CD01",
        journal_name="日记帐",
        serial_no="SN001",
        line_desc="说明",
        owner_name_raw="原始归口",
        owner_name_mapped="映射归口",
        monthly_caliber="月报口径",
        budget_subject_raw="原始预算科目",
        budget_subject_mapped="映射预算科目",
        fee_major_mapped="费用大类",
        fee_category_mapped="费用类别一级",
        budget_release_caliber_mapped="预算发布",
        manage_department2="归口2",
        special_control_tag="",
        owner_matched=True,
        subject_matched=True,
        match_note=None,
    )


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        ensure_expense_actual_import_schema_sync(conn)
        conn.commit()
    finally:
        conn.close()


class _FakeMysqlCursor:
    def __init__(self, state: dict[str, object]) -> None:
        self._state = state
        self.lastrowid = 99

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


class ExpenseActualImportApplyServiceTests(unittest.TestCase):
    def test_append_writes_batch_and_detail_rows(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _init_db(db_path)

                result = await apply_expense_actual_import_rows(
                    db_path,
                    import_kind="current_year_actual",
                    import_mode="append",
                    file_name="actual.xlsx",
                    rows=[_row()],
                    created_at="2026-06-02T00:00:00Z",
                )

                with sqlite3.connect(db_path) as conn:
                    batch = conn.execute(
                        "SELECT import_kind, file_name, import_mode, periods_text, total_rows FROM expense_actual_import_batch"
                    ).fetchone()
                    detail = conn.execute(
                        "SELECT batch_id, import_kind, period_ym, amount, owner_matched, subject_matched FROM expense_actual_detail_raw"
                    ).fetchone()

                self.assertEqual(result.batch_id, 1)
                self.assertEqual(result.periods, ["2026-04"])
                self.assertEqual(result.row_count, 1)
                self.assertEqual(batch, ("current_year_actual", "actual.xlsx", "append", "2026-04", 1))
                self.assertEqual(detail, (1, "current_year_actual", "2026-04", 100.0, 1, 1))

        asyncio.run(run())

    def test_overwrite_only_replaces_same_kind_and_period_details(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _init_db(db_path)
                await apply_expense_actual_import_rows(
                    db_path,
                    import_kind="current_year_actual",
                    import_mode="append",
                    file_name="old-current.xlsx",
                    rows=[_row(amount=10.0)],
                    created_at="2026-06-02T00:00:00Z",
                )
                await apply_expense_actual_import_rows(
                    db_path,
                    import_kind="prior_year_actual",
                    import_mode="append",
                    file_name="old-prior.xlsx",
                    rows=[_row(amount=20.0)],
                    created_at="2026-06-02T00:00:01Z",
                )

                result = await apply_expense_actual_import_rows(
                    db_path,
                    import_kind="current_year_actual",
                    import_mode="overwrite",
                    file_name="new-current.xlsx",
                    rows=[_row(amount=200.0)],
                    created_at="2026-06-02T00:00:02Z",
                )

                with sqlite3.connect(db_path) as conn:
                    detail_rows = conn.execute(
                        """
                        SELECT import_kind, period_ym, amount
                        FROM expense_actual_detail_raw
                        ORDER BY import_kind, amount
                        """
                    ).fetchall()
                    batch_count = conn.execute("SELECT COUNT(*) FROM expense_actual_import_batch").fetchone()[0]

                self.assertEqual(result.import_mode, "overwrite")
                self.assertEqual(batch_count, 3)
                self.assertEqual(
                    detail_rows,
                    [
                        ("current_year_actual", "2026-04", 200.0),
                        ("prior_year_actual", "2026-04", 20.0),
                    ],
                )

        asyncio.run(run())

    def test_rejects_invalid_import_mode(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _init_db(db_path)
                with self.assertRaisesRegex(ValueError, "导入模式仅支持"):
                    await apply_expense_actual_import_rows(
                        db_path,
                        import_kind="current_year_actual",
                        import_mode="replace",
                        file_name="actual.xlsx",
                        rows=[_row()],
                    )

        asyncio.run(run())

    def test_runtime_common_db_uses_mysql_transaction_for_overwrite_apply(self) -> None:
        async def run() -> None:
            fake_pool = _FakeMysqlPool()
            db_path = Path(apply_module.settings.data_dir) / "common.db"
            with patch.object(apply_module, "get_pool", return_value=fake_pool):
                result = await apply_expense_actual_import_rows(
                    db_path,
                    import_kind="current_year_actual",
                    import_mode="overwrite",
                    file_name="actual.xlsx",
                    rows=[_row()],
                    created_at="2026-06-02T00:00:00Z",
                )

            execute_calls = fake_pool.state["execute_calls"]
            executemany_calls = fake_pool.state["executemany_calls"]
            self.assertEqual(result.batch_id, 99)
            self.assertEqual(result.import_mode, "overwrite")
            self.assertTrue(fake_pool.state.get("began"))
            self.assertTrue(fake_pool.state.get("committed"))
            self.assertNotIn("rolled_back", fake_pool.state)
            self.assertEqual(len(execute_calls), 2)
            self.assertIn("delete from expense_actual_detail_raw", execute_calls[0][0])
            self.assertEqual(execute_calls[0][1], ("current_year_actual", "2026-04"))
            self.assertIn("insert into expense_actual_import_batch", execute_calls[1][0])
            self.assertEqual(len(executemany_calls), 1)
            self.assertIn("insert into expense_actual_detail_raw", executemany_calls[0][0])
            self.assertEqual(executemany_calls[0][1][0][0], 99)
            self.assertEqual(executemany_calls[0][1][0][1], "current_year_actual")

        asyncio.run(run())

    def test_actual_import_apply_service_does_not_import_aiosqlite(self) -> None:
        source = Path(apply_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
