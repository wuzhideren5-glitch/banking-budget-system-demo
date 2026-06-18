from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.services import expense_budget_execution_master_sync as master_sync_module
from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    FrameworkSubjectRow,
    ParsedFramework,
    read_sync_meta,
)
from app.services.expense_budget_execution_master_sync import (
    apply_framework_master_plan,
    build_framework_master_apply_payload,
    build_framework_master_plan,
    build_framework_master_plan_from_metric_subjects,
    build_framework_master_preview_payload,
)


def _parsed_framework() -> ParsedFramework:
    return ParsedFramework(
        source_file=Path("framework.xlsx"),
        budget_departments=[
            FrameworkBudgetDepartmentRow("微众银行", "科技及智能事业群", "科技子平台", "科技子平台"),
            FrameworkBudgetDepartmentRow("微众银行", "企业及机构金融事业群", "B01 企业部", "B01 企业部"),
            FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "A01 产品部"),
        ],
        product_departments=[],
        subjects=[
            FrameworkSubjectRow("一级", "业务费用", "A01 产品部", "A+B", 1),
            FrameworkSubjectRow("一级", "IT费用", "T01 平台部", "0", 2),
        ],
    )


def _create_common_db(data_dir: Path) -> None:
    conn = sqlite3.connect(data_dir / "common.db")
    try:
        conn.executescript(
            """
            CREATE TABLE dept_account (
              dept_code TEXT PRIMARY KEY NOT NULL,
              dept_name TEXT NOT NULL,
              entity_name TEXT NOT NULL DEFAULT '',
              parent_code TEXT,
              level INTEGER NOT NULL DEFAULT 1,
              is_leaf INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE data_account (
              data_acct_code TEXT PRIMARY KEY NOT NULL,
              data_acct_name TEXT NOT NULL,
              budget_formula TEXT,
              actual_formula TEXT,
              need_calc INTEGER NOT NULL DEFAULT 0,
              value_type TEXT NOT NULL DEFAULT '金额',
              remark TEXT
            );
            CREATE TABLE expense_sync_meta (
              sync_key TEXT PRIMARY KEY NOT NULL,
              source_file TEXT NOT NULL,
              source_mtime TEXT,
              synced_at TEXT NOT NULL,
              row_count INTEGER NOT NULL DEFAULT 0,
              note TEXT
            );
            CREATE TABLE org_product_metric_table (
              entity_code TEXT NOT NULL,
              entity_name TEXT NOT NULL,
              table_id TEXT,
              table_name TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              updated_at TEXT,
              PRIMARY KEY (entity_code, table_name)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO data_account(
              data_acct_code, data_acct_name, budget_formula, actual_formula, need_calc, value_type, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("D001", "业务费用", "已有预算公式", "已有实际公式", 1, "金额", "已有备注"),
        )
        conn.execute(
            """
            INSERT INTO data_account(
              data_acct_code, data_acct_name, budget_formula, actual_formula, need_calc, value_type, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("D999", "其他费用", None, None, 0, "金额", None),
        )
        payload = {
            "metrics": [
                {
                    "code": "AA0501",
                    "name": "业务费用",
                    "value_type": "金额",
                },
                {
                    "code": "AA0599",
                    "name": "其他费用",
                    "value_type": "金额",
                },
            ]
        }
        conn.execute(
            """
            INSERT INTO org_product_metric_table(entity_code, entity_name, table_id, table_name, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("AA", "微众银行", "expense", "业务支出评估", json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


class _FakeMysqlCursor:
    def __init__(self, pool: "_FakeMasterSyncMysqlPool") -> None:
        self.pool = pool

    async def __aenter__(self) -> "_FakeMysqlCursor":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.pool.executed.append(("execute", " ".join(sql.split()), params))

    async def executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        self.pool.executed.append(("executemany", " ".join(sql.split()), tuple(rows)))


class _FakeMysqlConnection:
    def __init__(self, pool: "_FakeMasterSyncMysqlPool") -> None:
        self.pool = pool

    async def begin(self) -> None:
        self.pool.executed.append(("begin", "", ()))

    def cursor(self) -> _FakeMysqlCursor:
        return _FakeMysqlCursor(self.pool)

    async def commit(self) -> None:
        self.pool.executed.append(("commit", "", ()))

    async def rollback(self) -> None:
        self.pool.executed.append(("rollback", "", ()))


class _FakeMysqlAcquire:
    def __init__(self, pool: "_FakeMasterSyncMysqlPool") -> None:
        self.pool = pool

    async def __aenter__(self) -> _FakeMysqlConnection:
        return _FakeMysqlConnection(self.pool)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeMasterSyncMysqlPool:
    def __init__(self) -> None:
        self.executed: list[tuple[str, str, tuple[object, ...]]] = []

    async def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized_sql = " ".join(sql.lower().split())
        if "information_schema.tables" in normalized_sql:
            return {"exists_flag": 1}
        raise AssertionError(f"Unexpected SQL: {sql}")

    async def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized_sql = " ".join(sql.lower().split())
        if "from data_account_metric_node" in normalized_sql:
            return [
                {
                    "node_code": "AA.05.01",
                    "node_name": "业务费用",
                    "product_code": "AA",
                    "metric_table_name": "业务支出评估",
                    "value_type": "金额",
                }
            ]
        if "from dept_account" in normalized_sql:
            return [
                {
                    "dept_code": "OLD",
                    "dept_name": "旧部门",
                    "entity_name": "微众银行",
                    "parent_code": None,
                    "level": 1,
                    "is_leaf": 0,
                }
            ]
        raise AssertionError(f"Unexpected SQL: {sql}")

    def acquire(self) -> _FakeMysqlAcquire:
        return _FakeMysqlAcquire(self)


class ExpenseBudgetExecutionMasterSyncTests(unittest.IsolatedAsyncioTestCase):
    def test_build_framework_master_plan_keeps_dept_and_subject_rules_together(self) -> None:
        parsed = _parsed_framework()

        plan = build_framework_master_plan_from_metric_subjects(
            parsed,
            {
                "业务费用": {
                    "metric_code": "AA.05.01",
                    "value_type": "金额",
                },
                "其他费用": {
                    "metric_code": "AA.05.99",
                    "value_type": "金额",
                },
            },
        )

        self.assertEqual(
            plan.dept_rows,
            [
                ("Y1", "个人金融事业群", "微众银行", None, 1, 0),
                ("Y101", "A01 产品部", "微众银行", "Y1", 2, 1),
                ("Y2", "企业及机构金融事业群", "微众银行", None, 1, 0),
                ("Y201", "B01 企业部", "微众银行", "Y2", 2, 1),
            ],
        )
        self.assertEqual(plan.matched_subjects, 1)
        self.assertEqual(plan.new_subjects, ["IT费用"])
        self.assertEqual(plan.unmatched_existing_subjects, ["其他费用"])
        self.assertEqual(
            plan.metric_subject_matches,
            [("AA.05.01", "业务费用", "金额")],
        )
        preview = build_framework_master_preview_payload(parsed, plan)
        self.assertEqual(preview["master_preview"]["dept_rows"], 4)
        self.assertEqual(preview["master_preview"]["new_subjects"], 1)

    async def test_apply_framework_master_plan_updates_master_tables_and_sync_meta(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            _create_common_db(data_dir)
            parsed = _parsed_framework()
            try:
                plan = await build_framework_master_plan(parsed)
                result = await apply_framework_master_plan(parsed, plan)
                payload = build_framework_master_apply_payload(result)
                backup_path = Path(payload["backup_file"])
                backup_exists = backup_path.exists()
                meta = await read_sync_meta()
                conn = sqlite3.connect(data_dir / "common.db")
                try:
                    dept_rows = conn.execute(
                        "SELECT dept_code, dept_name, entity_name, parent_code, level, is_leaf FROM dept_account ORDER BY dept_code"
                    ).fetchall()
                    data_row = conn.execute(
                        "SELECT data_acct_name, budget_formula, actual_formula, need_calc, value_type, remark FROM data_account WHERE data_acct_code='D001'"
                    ).fetchone()
                    account_count = conn.execute("SELECT COUNT(*) FROM data_account").fetchone()[0]
                finally:
                    conn.close()
            finally:
                settings.data_dir = original_data_dir

        self.assertEqual(len(dept_rows), 4)
        self.assertEqual(dept_rows[0], ("Y1", "个人金融事业群", "微众银行", None, 1, 0))
        self.assertEqual(data_row[0], "业务费用")
        self.assertEqual(data_row[1], "已有预算公式")
        self.assertEqual(data_row[2], "已有实际公式")
        self.assertEqual(data_row[3], 1)
        self.assertEqual(data_row[4], "金额")
        self.assertEqual(data_row[5], "已有备注")
        self.assertEqual(account_count, 2)
        self.assertTrue(backup_exists)
        self.assertEqual(backup_path.parent.name, "backups")
        self.assertRegex(backup_path.name, r"^common_before_expense_framework_\d{8}_\d{6}\.db$")
        self.assertEqual(payload["dept_rows"], 4)
        self.assertEqual(payload["matched_metric_subjects"], 1)
        self.assertEqual(meta["master_apply"]["row_count"], 4)
        self.assertIn("部门4行", meta["master_apply"]["note"])
        self.assertIn("指标匹配1项", meta["master_apply"]["note"])

    async def test_build_framework_master_plan_uses_mysql_pool_for_runtime_common_db(self) -> None:
        fake_pool = _FakeMasterSyncMysqlPool()
        db_path = Path(master_sync_module.settings.data_dir) / "common.db"
        with (
            patch.object(master_sync_module, "get_pool", return_value=fake_pool),
            patch.object(master_sync_module, "common_db_path", return_value=db_path),
        ):
            plan = await build_framework_master_plan(_parsed_framework())

        self.assertEqual(plan.matched_subjects, 1)
        self.assertEqual(plan.metric_subject_matches, [("AA.05.01", "业务费用", "金额")])
        self.assertEqual(plan.new_subjects, ["IT费用"])

    async def test_apply_framework_master_plan_uses_mysql_transaction_for_runtime_common_db(self) -> None:
        fake_pool = _FakeMasterSyncMysqlPool()
        sync_calls: list[tuple[str, int, str | None]] = []

        async def fake_upsert_sync_meta(
            sync_key: str,
            source_file: str,
            row_count: int,
            note: str | None = None,
        ) -> None:
            sync_calls.append((sync_key, row_count, note))

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with (
                patch.object(master_sync_module, "get_pool", return_value=fake_pool),
                patch.object(master_sync_module, "common_db_path", return_value=db_path),
                patch.object(master_sync_module, "_uses_mysql_path", return_value=True),
                patch.object(master_sync_module, "upsert_sync_meta", side_effect=fake_upsert_sync_meta),
            ):
                result = await apply_framework_master_plan(
                    _parsed_framework(),
                    build_framework_master_plan_from_metric_subjects(
                        _parsed_framework(),
                        {"业务费用": {"metric_code": "AA.05.01", "value_type": "金额"}},
                    ),
                )
            self.assertEqual(result.backup_file.suffix, ".json")
            self.assertTrue(result.backup_file.exists())
            self.assertIn("mysql.dept_account", result.backup_file.read_text(encoding="utf-8"))

        self.assertIn(("begin", "", ()), fake_pool.executed)
        self.assertIn(("commit", "", ()), fake_pool.executed)
        self.assertTrue(any(item[0] == "executemany" and "INSERT INTO dept_account" in item[1] for item in fake_pool.executed))
        self.assertEqual(sync_calls[0][0], "master_apply")
        self.assertEqual(sync_calls[0][1], 4)

    async def test_master_sync_service_does_not_import_aiosqlite(self) -> None:
        source = Path(master_sync_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
