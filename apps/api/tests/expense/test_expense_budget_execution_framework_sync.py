from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    FrameworkProductDepartmentRow,
    FrameworkSubjectRow,
    ParsedFramework,
    read_sync_meta,
)
from app.services.expense_budget_execution_framework_sync import (
    preview_expense_framework_sync,
    sync_expense_framework,
)


def _parsed_framework() -> ParsedFramework:
    return ParsedFramework(
        source_file=Path("framework.xlsx"),
        budget_departments=[
            FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "A01 产品部")
        ],
        product_departments=[
            FrameworkProductDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "小微产品")
        ],
        subjects=[
            FrameworkSubjectRow("一级", "业务费用", "A01 产品部", "A+B", 1),
            FrameworkSubjectRow("二级", "IT费用", "T01 平台部", "0", 2),
        ],
    )


def _create_common_db(data_dir: Path) -> None:
    conn = sqlite3.connect(data_dir / "common.db")
    try:
        conn.executescript(
            """
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
            CREATE TABLE expense_framework_budget_department (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              entity_name TEXT NOT NULL DEFAULT '',
              group_name TEXT NOT NULL,
              owner_name TEXT NOT NULL,
              budget_department TEXT NOT NULL
            );
            CREATE TABLE expense_framework_product_department (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              entity_name TEXT NOT NULL DEFAULT '',
              group_name TEXT NOT NULL,
              owner_name TEXT NOT NULL,
              product_department TEXT NOT NULL
            );
            CREATE TABLE expense_framework_subject (
              budget_subject TEXT PRIMARY KEY NOT NULL,
              level_label TEXT,
              manage_department TEXT,
              formula_text TEXT,
              sort_order INTEGER NOT NULL DEFAULT 0
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
            INSERT INTO data_account(
              data_acct_code, data_acct_name, budget_formula, actual_formula, need_calc, value_type, remark
            ) VALUES
              ('D001', '业务费用', '已有预算公式', '已有实际公式', 1, '金额', '已有备注'),
              ('D999', '其他费用', NULL, NULL, 0, '金额', NULL);
            """
        )
        payload = {
            "metrics": [
                {
                    "name": "业务费用",
                    "mapping_status": "MANUAL_CONFIRMED",
                    "metric_node_code": "AA.05.01",
                    "data_acct_code": "AA.05.01",
                    "value_type": "金额",
                },
                {
                    "name": "其他费用",
                    "mapping_status": "MANUAL_CONFIRMED",
                    "metric_node_code": "AA.05.99",
                    "data_acct_code": "AA.05.99",
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


class ExpenseBudgetExecutionFrameworkSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._original_data_dir = settings.data_dir
        self._tmp = tempfile.TemporaryDirectory()
        settings.data_dir = Path(self._tmp.name)
        _create_common_db(settings.data_dir)

    async def asyncTearDown(self) -> None:
        settings.data_dir = self._original_data_dir
        self._tmp.cleanup()

    async def test_preview_builds_master_payload(self) -> None:
        preview = await preview_expense_framework_sync(_parsed_framework())

        self.assertEqual(preview["source_file"], "framework.xlsx")
        self.assertEqual(preview["framework"]["owner_count"], 1)
        self.assertEqual(preview["framework"]["subject_count"], 2)
        self.assertEqual(preview["master_preview"]["matched_subjects"], 1)
        self.assertEqual(preview["master_preview"]["new_subjects"], 1)
        self.assertEqual(preview["master_preview"]["unmatched_existing_subjects"], 1)

    async def test_sync_persists_framework_snapshot_and_writes_audit_without_master_apply(self) -> None:
        audit_calls: list[dict[str, Any]] = []

        async def audit_writer(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        result = await sync_expense_framework(
            _parsed_framework(),
            apply_to_master_data=False,
            audit_writer=audit_writer,
        )
        meta = await read_sync_meta()
        conn = sqlite3.connect(settings.data_dir / "common.db")
        try:
            counts = {
                "budget": conn.execute("SELECT COUNT(*) FROM expense_framework_budget_department").fetchone()[0],
                "product": conn.execute("SELECT COUNT(*) FROM expense_framework_product_department").fetchone()[0],
                "subject": conn.execute("SELECT COUNT(*) FROM expense_framework_subject").fetchone()[0],
            }
        finally:
            conn.close()

        self.assertFalse(result["master_applied"])
        self.assertEqual(result["framework_rows"], {"budget_departments": 1, "product_departments": 1, "subjects": 2})
        self.assertNotIn("master_apply", result)
        self.assertEqual(counts, {"budget": 1, "product": 1, "subject": 2})
        self.assertEqual(meta["framework_import"]["row_count"], 4)
        self.assertEqual(len(audit_calls), 1)
        self.assertEqual(audit_calls[0]["action_type"], "IMPORT")
        self.assertEqual(audit_calls[0]["target_table"], "expense_framework_*")
        self.assertEqual(audit_calls[0]["affected_rows"], 4)


if __name__ == "__main__":
    unittest.main()
