from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.expense_budget_entry_store import (
    load_expense_budget_entry_by_owner_subject,
    load_expense_budget_entry_subject_totals,
)
from app.services import expense_budget_execution_budget_source as budget_source_module
from app.services.expense_budget_execution_budget_source import (
    BudgetSourceError,
    extract_runtime_metric_ref_name,
    load_imported_caliber_monthly_totals,
    load_imported_owner_caliber_monthly_totals,
    load_budget_rows,
    load_previous_year_actual_by_owner_subject,
    load_previous_year_actual_subject_monthly,
)
from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    FrameworkSubjectRow,
    ParsedFramework,
    build_framework_context,
)


def _create_budget_db(path: Path, *, rows: list[tuple[int, int, str, str, str, float]] | None = None) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE version (
              version_id INTEGER PRIMARY KEY,
              version_date_time TEXT NOT NULL,
              version_name TEXT NOT NULL,
              current_month INTEGER NOT NULL
            );
            CREATE TABLE budget_summary (
              version_id INTEGER NOT NULL,
              budget_actual INTEGER NOT NULL,
              product_code_name TEXT,
              data_code_name TEXT,
              month TEXT,
              value REAL
            );
            """
        )
        conn.execute(
            "INSERT INTO version(version_id, version_date_time, version_name, current_month) VALUES (1, '2026-01-01T00:00:00Z', 'V1', 3)"
        )
        if rows:
            conn.executemany(
                """
                INSERT INTO budget_summary(version_id, budget_actual, product_code_name, data_code_name, month, value)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        conn.commit()
    finally:
        conn.close()


def _create_common_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE expense_budget_entry_batch (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              budget_year INTEGER NOT NULL,
              file_name TEXT NOT NULL,
              import_mode TEXT NOT NULL,
              total_rows INTEGER NOT NULL DEFAULT 0,
              matched_rows INTEGER NOT NULL DEFAULT 0,
              unmatched_rows INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              note TEXT
            );
            CREATE TABLE expense_budget_entry (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              batch_id INTEGER REFERENCES expense_budget_entry_batch(id) ON DELETE CASCADE,
              budget_year INTEGER NOT NULL,
              owner_name_raw TEXT NOT NULL,
              owner_name_mapped TEXT,
              budget_subject_raw TEXT NOT NULL,
              budget_subject_mapped TEXT,
              amount REAL NOT NULL DEFAULT 0,
              adjustment_amount REAL NOT NULL DEFAULT 0,
              owner_matched INTEGER NOT NULL DEFAULT 0,
              subject_matched INTEGER NOT NULL DEFAULT 0,
              match_note TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO expense_budget_entry_batch(
              budget_year, file_name, import_mode, total_rows, matched_rows, unmatched_rows, created_at, note
            ) VALUES (2026, 'budget.xlsx', 'append', 2, 2, 0, '2026-01-01T00:00:00Z', NULL)
            """
        )
        conn.executemany(
            """
            INSERT INTO expense_budget_entry(
              batch_id, budget_year, owner_name_raw, owner_name_mapped,
              budget_subject_raw, budget_subject_mapped, amount, adjustment_amount,
              owner_matched, subject_matched, match_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 2026, "A01 产品部", "A01 产品部", "IT费用", "IT费用", 1_000_000.0, 205_000.0, 1, 1, None),
                (1, 2026, "T01 平台部", "T01 平台部", "业务费用", "业务费用", 200_000.0, 0.0, 1, 1, None),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _framework_context():
    parsed = ParsedFramework(
        source_file=Path("framework.xlsx"),
        budget_departments=[
            FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "A01 产品部"),
            FrameworkBudgetDepartmentRow("科技子", "科技及智能事业群", "T01 平台部", "T01 平台部"),
        ],
        product_departments=[],
        subjects=[
            FrameworkSubjectRow("二级", "IT费用", "科技业务", "0", 1),
            FrameworkSubjectRow("二级", "业务费用", "", "0", 2),
        ],
    )
    return build_framework_context(parsed)


class _FakeMysqlPool:
    async def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized_sql = " ".join(sql.lower().split())
        if "information_schema.tables" in normalized_sql:
            return {"exists_flag": 1}
        if "from expense_actual_import_batch" in normalized_sql:
            return {"id": 9, "file_name": "mysql-actual.xlsx", "created_at": "2026-06-18T00:00:00Z"}
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized_sql = " ".join(sql.lower().split())
        if "information_schema.columns" in normalized_sql:
            return [
                {"COLUMN_NAME": "import_kind"},
                {"COLUMN_NAME": "owner_name_mapped"},
                {"COLUMN_NAME": "budget_release_caliber_mapped"},
                {"COLUMN_NAME": "period_ym"},
                {"COLUMN_NAME": "amount"},
                {"COLUMN_NAME": "owner_matched"},
            ]
        if "select budget_release_caliber_mapped, period_ym, amount" in normalized_sql:
            return [
                {"budget_release_caliber_mapped": "IT费用", "period_ym": "2026-01", "amount": 100.0},
                {"budget_release_caliber_mapped": "业务费用", "period_ym": "2026-02", "amount": 200.0},
            ]
        if "select owner_name_mapped, budget_release_caliber_mapped, period_ym, amount" in normalized_sql:
            return [
                {
                    "owner_name_mapped": "A01 产品部",
                    "budget_release_caliber_mapped": "IT费用",
                    "period_ym": "2026-01",
                    "amount": 100.0,
                },
                {
                    "owner_name_mapped": "T01 平台部",
                    "budget_release_caliber_mapped": "业务费用",
                    "period_ym": "2026-02",
                    "amount": 200.0,
                },
            ]
        raise AssertionError(f"Unexpected SQL: {sql}")


class ExpenseBudgetExecutionBudgetSourceTests(unittest.IsolatedAsyncioTestCase):
    def test_extract_runtime_metric_ref_name_supports_product_prefixed_metric_codes(self) -> None:
        self.assertEqual(extract_runtime_metric_ref_name("05.03.01.01.004.A01 IT费用"), "IT费用")
        self.assertEqual(extract_runtime_metric_ref_name("A01 IT费用"), "IT费用")
        self.assertEqual(extract_runtime_metric_ref_name("业务费用"), "业务费用")

    async def test_load_budget_rows_uses_budget_entry_adjusted_amounts(self) -> None:
        ctx = _framework_context()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            budget_db = tmp_path / "budget_2026.db"
            common_db = tmp_path / "common.db"
            _create_budget_db(budget_db)
            _create_common_db(common_db)

            with patch("app.services.expense_budget_entry_store.common_db_path", return_value=common_db):
                version_name, current_month, by_entity, by_group, by_owner, source = await load_budget_rows(
                    ctx,
                    budget_db,
                    1,
                )

        self.assertEqual(version_name, "V1")
        self.assertEqual(current_month, 3)
        self.assertEqual(by_owner[("A01 产品部", "IT费用")], 1_205_000.0)
        self.assertEqual(by_group[("个人金融事业群", "IT费用")], 1_205_000.0)
        self.assertEqual(by_entity[("微众银行", "IT费用")], 1_205_000.0)
        self.assertEqual(by_owner[("T01 平台部", "业务费用")], 200_000.0)
        self.assertIn("预算导入-已匹配及导入预算表", source or "")

    async def test_load_expense_budget_entry_excludes_unmatched_rows(self) -> None:
        ctx = _framework_context()
        with tempfile.TemporaryDirectory() as tmp:
            common_db = Path(tmp) / "common.db"
            conn = sqlite3.connect(common_db)
            try:
                conn.executescript(
                    """
                    CREATE TABLE expense_budget_entry_batch (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      budget_year INTEGER NOT NULL,
                      file_name TEXT NOT NULL,
                      import_mode TEXT NOT NULL,
                      total_rows INTEGER NOT NULL DEFAULT 0,
                      matched_rows INTEGER NOT NULL DEFAULT 0,
                      unmatched_rows INTEGER NOT NULL DEFAULT 0,
                      created_at TEXT NOT NULL,
                      note TEXT
                    );
                    CREATE TABLE expense_budget_entry (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      batch_id INTEGER,
                      budget_year INTEGER NOT NULL,
                      owner_name_raw TEXT NOT NULL,
                      owner_name_mapped TEXT,
                      budget_subject_raw TEXT NOT NULL,
                      budget_subject_mapped TEXT,
                      amount REAL NOT NULL DEFAULT 0,
                      adjustment_amount REAL NOT NULL DEFAULT 0,
                      owner_matched INTEGER NOT NULL DEFAULT 0,
                      subject_matched INTEGER NOT NULL DEFAULT 0,
                      match_note TEXT
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO expense_budget_entry_batch VALUES (1, 2026, 'a.xlsx', 'append', 2, 1, 1, 't', NULL)"
                )
                conn.executemany(
                    """
                    INSERT INTO expense_budget_entry(
                      batch_id, budget_year, owner_name_raw, owner_name_mapped,
                      budget_subject_raw, budget_subject_mapped, amount, adjustment_amount,
                      owner_matched, subject_matched, match_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (1, 2026, "A01 产品部", "A01 产品部", "IT费用", "IT费用", 100.0, 0.0, 1, 1, None),
                        (1, 2026, "未知部门", None, "业务费用", "业务费用", 999.0, 0.0, 0, 1, "部门未匹配"),
                    ],
                )
                conn.commit()
            finally:
                conn.close()
            totals, _source = await load_expense_budget_entry_by_owner_subject(
                ctx,
                budget_year=2026,
                db_path=common_db,
            )
        self.assertEqual(totals, {("A01 产品部", "IT费用"): 100.0})

    async def test_load_expense_budget_entry_subject_totals_prefers_bank_wide_total(self) -> None:
        ctx = _framework_context()
        with tempfile.TemporaryDirectory() as tmp:
            common_db = Path(tmp) / "common.db"
            conn = sqlite3.connect(common_db)
            try:
                conn.executescript(
                    """
                    CREATE TABLE expense_budget_entry (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      batch_id INTEGER,
                      budget_year INTEGER NOT NULL,
                      owner_name_raw TEXT NOT NULL,
                      owner_name_mapped TEXT,
                      budget_subject_raw TEXT NOT NULL,
                      budget_subject_mapped TEXT,
                      amount REAL NOT NULL DEFAULT 0,
                      adjustment_amount REAL NOT NULL DEFAULT 0,
                      owner_matched INTEGER NOT NULL DEFAULT 0,
                      subject_matched INTEGER NOT NULL DEFAULT 0,
                      match_note TEXT
                    );
                    """
                )
                conn.executemany(
                    """
                    INSERT INTO expense_budget_entry(
                      batch_id, budget_year, owner_name_raw, owner_name_mapped,
                      budget_subject_raw, budget_subject_mapped, amount, adjustment_amount,
                      owner_matched, subject_matched, match_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (1, 2026, "全行合计", None, "业务费用", "业务费用", 29900.0, 0.0, 0, 1, None),
                        (1, 2026, "A01 产品部", "A01 产品部", "业务费用", "业务费用", 200.0, 0.0, 1, 1, None),
                        (1, 2026, "T01 平台部", "T01 平台部", "IT费用", "IT费用", 100.0, 0.0, 1, 1, None),
                    ],
                )
                conn.commit()
            finally:
                conn.close()
            totals, source = await load_expense_budget_entry_subject_totals(
                ctx,
                budget_year=2026,
                db_path=common_db,
            )
        self.assertEqual(totals["业务费用"], 29900.0)
        self.assertEqual(totals["IT费用"], 100.0)
        self.assertIn("全行合计", source or "")

    async def test_load_expense_budget_entry_uses_adjusted_amount_in_yuan(self) -> None:
        ctx = _framework_context()
        with tempfile.TemporaryDirectory() as tmp:
            common_db = Path(tmp) / "common.db"
            _create_common_db(common_db)
            totals, source = await load_expense_budget_entry_by_owner_subject(
                ctx,
                budget_year=2026,
                db_path=common_db,
            )
        self.assertEqual(totals[("A01 产品部", "IT费用")], 1_205_000.0)
        self.assertIn("预算导入-已匹配及导入预算表", source or "")
        self.assertIn("单位：元", source or "")

    async def test_imported_caliber_totals_use_all_matched_source_rows_not_latest_batch_only(self) -> None:
        ctx = _framework_context()
        with tempfile.TemporaryDirectory() as tmp:
            common_db = Path(tmp) / "common.db"
            conn = sqlite3.connect(common_db)
            try:
                conn.executescript(
                    """
                    CREATE TABLE expense_actual_import_batch (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      import_kind TEXT NOT NULL,
                      file_name TEXT NOT NULL,
                      import_mode TEXT NOT NULL,
                      periods_text TEXT,
                      total_rows INTEGER NOT NULL DEFAULT 0,
                      matched_owner_rows INTEGER NOT NULL DEFAULT 0,
                      matched_subject_rows INTEGER NOT NULL DEFAULT 0,
                      unmatched_rows INTEGER NOT NULL DEFAULT 0,
                      created_at TEXT NOT NULL,
                      note TEXT
                    );
                    CREATE TABLE expense_actual_detail_raw (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      batch_id INTEGER,
                      import_kind TEXT NOT NULL,
                      owner_name_mapped TEXT,
                      budget_release_caliber_mapped TEXT,
                      period_ym TEXT,
                      amount REAL,
                      owner_matched INTEGER NOT NULL DEFAULT 0,
                      subject_matched INTEGER NOT NULL DEFAULT 0
                    );
                    """
                )
                conn.executemany(
                    """
                    INSERT INTO expense_actual_import_batch(
                      id, import_kind, file_name, import_mode, periods_text,
                      total_rows, matched_owner_rows, matched_subject_rows, unmatched_rows, created_at, note
                    ) VALUES (?, 'current_year_actual', ?, 'append', '2026-01', 1, 1, 1, 0, ?, NULL)
                    """,
                    [
                        (1, "batch1.xlsx", "2026-01-01T00:00:00Z"),
                        (2, "batch2.xlsx", "2026-01-02T00:00:00Z"),
                    ],
                )
                conn.executemany(
                    """
                    INSERT INTO expense_actual_detail_raw(
                      batch_id, import_kind, owner_name_mapped, budget_release_caliber_mapped,
                      period_ym, amount, owner_matched, subject_matched
                    ) VALUES (?, 'current_year_actual', ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (1, "A01 产品部", "IT费用", "2026-01", 100.0, 1, 1),
                        (2, "A01 产品部", "IT费用", "2026-02", 200.0, 1, 1),
                        (2, "未知部门", "业务费用", "2026-01", 999.0, 0, 1),
                        (2, "A01 产品部", "业务费用", "2026-01", 888.0, 1, 0),
                    ],
                )
                conn.commit()
            finally:
                conn.close()

            with patch("app.services.expense_budget_execution_budget_source.common_db_path", return_value=common_db):
                subject_totals, _subject_source = await load_imported_caliber_monthly_totals("current_year_actual")
                owner_totals, _owner_source = await load_imported_owner_caliber_monthly_totals(
                    ctx,
                    "current_year_actual",
                )

        self.assertEqual(subject_totals["IT费用"][:2], [100.0, 200.0])
        self.assertEqual(subject_totals["业务费用"][:2], [1887.0, 0.0])
        self.assertEqual(owner_totals[("A01 产品部", "IT费用")][:2], [100.0, 200.0])
        self.assertEqual(owner_totals[("A01 产品部", "业务费用")][:2], [888.0, 0.0])
        self.assertNotIn(("未知部门", "业务费用"), owner_totals)

    async def test_imported_actual_totals_use_mysql_pool_for_runtime_common_db(self) -> None:
        ctx = _framework_context()

        async def fake_catalog_names(_db=None):
            return {"IT费用", "业务费用"}

        async def fake_catalog_map(_db=None, *, catalog_names=None):
            return {}

        with (
            patch.object(budget_source_module, "get_pool", return_value=_FakeMysqlPool()),
            patch.object(
                budget_source_module,
                "common_db_path",
                return_value=Path(budget_source_module.settings.data_dir) / "common.db",
            ),
            patch.object(budget_source_module, "load_catalog_subject_names", side_effect=fake_catalog_names),
            patch.object(budget_source_module, "load_budget_caliber_catalog_map", side_effect=fake_catalog_map),
        ):
            subject_totals, subject_source = await load_imported_caliber_monthly_totals("current_year_actual")
            owner_totals, owner_source = await load_imported_owner_caliber_monthly_totals(
                ctx,
                "current_year_actual",
            )

        self.assertEqual(subject_totals["IT费用"][0], 100.0)
        self.assertEqual(subject_totals["业务费用"][1], 200.0)
        self.assertEqual(owner_totals[("A01 产品部", "IT费用")][0], 100.0)
        self.assertEqual(owner_totals[("T01 平台部", "业务费用")][1], 200.0)
        self.assertIn("mysql-actual.xlsx", subject_source)
        self.assertIn("mysql-actual.xlsx", owner_source)

    async def test_load_budget_rows_raises_for_missing_version(self) -> None:
        ctx = _framework_context()
        with tempfile.TemporaryDirectory() as tmp:
            budget_db = Path(tmp) / "budget_2026.db"
            _create_budget_db(budget_db, rows=[])

            with self.assertRaisesRegex(BudgetSourceError, "版本 99 不存在"):
                await load_budget_rows(ctx, budget_db, 99)

    async def test_previous_year_actual_loaders_filter_scope_and_return_monthly_values(self) -> None:
        ctx = _framework_context()
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            current_db = data_dir / "budget_2026.db"
            current_db.touch()
            _create_budget_db(
                data_dir / "budget_2025.db",
                rows=[
                    (1, 1, "A01 产品部-小微", "05.03.01.01.004.A01 IT费用", "M01", 10),
                    (1, 1, "A01 产品部-小微", "05.03.01.01.004.A01 IT费用", "M02", 20),
                    (1, 1, "A01 产品部-小微", "05.01.02.01.003.A01 业务费用", "M03", 30),
                    (1, 1, "T01 平台部-平台", "05.03.01.01.004.A01 IT费用", "M01", 99),
                ],
            )

            monthly, totals, source = await load_previous_year_actual_subject_monthly(
                ctx,
                current_db,
                2026,
                3,
                entity_name="微众银行",
            )
            by_owner, owner_source = await load_previous_year_actual_by_owner_subject(ctx, current_db, 2026)

        self.assertEqual(monthly["IT费用"][:3], [10.0, 20.0, 0.0])
        self.assertEqual(totals, {"IT费用": 30.0, "业务费用": 30.0})
        self.assertIn("V1", source)
        self.assertEqual(by_owner[("A01 产品部", "IT费用")][:3], [10.0, 20.0, 0.0])
        self.assertEqual(by_owner[("T01 平台部", "IT费用")][0], 99.0)
        self.assertIn("V1", owner_source)

    async def test_budget_source_service_does_not_import_aiosqlite(self) -> None:
        source = Path(budget_source_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
