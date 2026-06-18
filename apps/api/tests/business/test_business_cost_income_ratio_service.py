from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.services import business_cost_income_commands as business_cost_income_commands_module
from app.services import business_cost_income_ratio as business_cost_income_ratio_module
from app.services.business_cost_income_commands import (
    create_business_cost_income_indicator,
    create_business_cost_income_item,
    delete_business_cost_income_indicator,
    delete_business_cost_income_item,
    reorder_business_cost_income_indicators,
    reorder_business_cost_income_items,
    update_business_cost_income_indicator,
    update_business_cost_income_item,
    upsert_business_cost_income_value,
)
from app.services.business_cost_income_ratio import (
    build_business_cost_income_ratio_report,
    ensure_business_cost_income_tables,
)


class BusinessCostIncomeRatioServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_uses_mysql_for_runtime_budget_path(self) -> None:
        class FakePool:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

            async def fetch_all(self, sql: str, params=()):
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((" ".join(sql.split()), tuple(params)))
                if "from business_cost_income_item" in normalized:
                    return [
                        {
                            "id": 1,
                            "product_code": "A01",
                            "section": "input",
                            "name": "投入合计",
                            "parent_id": None,
                            "display_group": 1,
                            "data_acct_code": "",
                            "org_product_ref": "",
                            "org_product_entity_code": "",
                            "org_product_table_name": "",
                            "org_product_metric_code": "",
                            "org_product_metric_name": "",
                            "manual_entry_mode": "disabled",
                            "value_mode": "tree",
                            "sort_order": 1,
                            "enabled": 1,
                        },
                        {
                            "id": 2,
                            "product_code": "A01",
                            "section": "input",
                            "name": "营销费用",
                            "parent_id": 1,
                            "display_group": 0,
                            "data_acct_code": "",
                            "org_product_ref": "",
                            "org_product_entity_code": "",
                            "org_product_table_name": "",
                            "org_product_metric_code": "",
                            "org_product_metric_name": "",
                            "manual_entry_mode": "manual",
                            "value_mode": "tree",
                            "sort_order": 1,
                            "enabled": 1,
                        },
                        {
                            "id": 3,
                            "product_code": "A01",
                            "section": "output",
                            "name": "收入合计",
                            "parent_id": None,
                            "display_group": 0,
                            "data_acct_code": "",
                            "org_product_ref": "",
                            "org_product_entity_code": "",
                            "org_product_table_name": "",
                            "org_product_metric_code": "",
                            "org_product_metric_name": "",
                            "manual_entry_mode": "manual",
                            "value_mode": "tree",
                            "sort_order": 1,
                            "enabled": 1,
                        },
                    ]
                if "from business_cost_income_indicator" in normalized:
                    return [
                        {
                            "id": 1,
                            "product_code": "A01",
                            "name": "投入产出比",
                            "parent_id": None,
                            "display_group": 0,
                            "topic_metric_node_code": "A01:业务状况表:A0101",
                            "numerator_section": "input",
                            "numerator_item_id": 2,
                            "numerator_value_mode": "tree",
                            "denominator_section": "output",
                            "denominator_item_id": 3,
                            "denominator_value_mode": "tree",
                            "format": "percent",
                            "annualize": 0,
                            "sort_order": 1,
                            "enabled": 1,
                        }
                    ]
                if "sum(value) as total" in normalized and "group by item_section, item_id, field" in normalized:
                    return [
                        {"item_section": "input", "item_id": 2, "field": "actual", "total": 150.0},
                        {"item_section": "input", "item_id": 2, "field": "budget", "total": 1200.0},
                        {"item_section": "input", "item_id": 2, "field": "forecast", "total": 1100.0},
                        {"item_section": "output", "item_id": 3, "field": "actual", "total": 1500.0},
                        {"item_section": "output", "item_id": 3, "field": "budget", "total": 12000.0},
                        {"item_section": "output", "item_id": 3, "field": "forecast", "total": 11000.0},
                    ]
                if "sum(value) as total" in normalized and "group by item_section, item_id" in normalized:
                    return [
                        {"item_section": "input", "item_id": 2, "total": 120.0},
                        {"item_section": "output", "item_id": 3, "total": 1200.0},
                    ]
                if "from business_cost_income_value" in normalized:
                    return [
                        {"item_section": "input", "item_id": 2, "field": "actual", "value": 50.0},
                        {"item_section": "output", "item_id": 3, "field": "actual", "value": 500.0},
                    ]
                raise AssertionError(f"Unexpected fetch_all SQL: {sql}")

        fake_pool = FakePool()
        with patch.object(business_cost_income_ratio_module, "get_pool", return_value=fake_pool):
            report = await build_business_cost_income_ratio_report(
                entity_name="微众银行",
                report_month="2026-02",
                group_name=None,
                product_code="A01",
                amount_unit="yuan",
            )

        rows = {(row["section"], row["id"]): row for row in report["rows"]}
        self.assertEqual(rows[("input", 1)]["metrics"]["current_actual"], 150.0)
        self.assertEqual(rows[("indicator", 1)]["metrics"]["current_actual"], 10.0)
        value_calls = [
            (sql, params)
            for sql, params in fake_pool.fetch_all_calls
            if "FROM business_cost_income_value" in sql
        ]
        self.assertGreaterEqual(len(value_calls), 3)
        for sql, params in value_calls:
            self.assertIn("budget_year = %s", sql)
            self.assertEqual(params[0], 2026)

    def test_ratio_service_does_not_import_aiosqlite(self) -> None:
        source = Path(business_cost_income_ratio_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    async def test_command_mysql_adapter_handles_sqlite_compatibility_sql(self) -> None:
        source = Path(business_cost_income_commands_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

        conn = business_cost_income_commands_module._MySQLCommandConnection()
        conn._conn = object()
        pragma_cur = await conn.execute("PRAGMA foreign_keys = ON")
        self.assertEqual(await pragma_cur.fetchone(), (1,))

        translated = business_cost_income_commands_module._mysql_sql(
            """
            INSERT INTO business_cost_income_value (
              budget_year, year, month, entity_name, group_name, product_code,
              item_section, item_id, field, value, update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (
              budget_year, year, month,
              entity_name, group_name, product_code,
              item_section, item_id, field
            ) DO UPDATE SET value = excluded.value, update_time = excluded.update_time
            """
        )
        self.assertIn("ON DUPLICATE KEY UPDATE", translated)
        self.assertIn("value = VALUES(value)", translated)
        self.assertIn("update_time = VALUES(update_time)", translated)
        self.assertNotIn("ON CONFLICT", translated)
        self.assertNotIn("?", translated)

    async def test_report_rolls_up_tree_items_and_indicator_ratios(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            try:
                await ensure_business_cost_income_tables(2026)
                conn = sqlite3.connect(data_dir / "budget_2026.db")
                try:
                    conn.executescript(
                        """
                        DELETE FROM business_cost_income_source_mapping;
                        DELETE FROM business_cost_income_indicator;
                        DELETE FROM business_cost_income_value;
                        DELETE FROM business_cost_income_item;

                        INSERT INTO business_cost_income_item(
                          id, product_code, section, name, parent_id, display_group,
                          data_acct_code, manual_entry_mode, value_mode, sort_order, enabled
                        )
                        VALUES
                          (1, 'A01', 'input', '投入合计', NULL, 1, '', 'disabled', 'tree', 1, 1),
                          (2, 'A01', 'input', '营销费用', 1, 0, '', 'manual', 'tree', 1, 1),
                          (3, 'A01', 'output', '收入合计', NULL, 0, '', 'manual', 'tree', 1, 1);

                        INSERT INTO business_cost_income_indicator(
                          id, product_code, name, parent_id, display_group, topic_metric_node_code,
                          numerator_section, numerator_item_id, numerator_value_mode,
                          denominator_section, denominator_item_id, denominator_value_mode,
                          format, annualize, sort_order, enabled
                        ) VALUES (
                          1, 'A01', '投入产出比', NULL, 0, 'A01:业务状况表:A0101',
                          'input', 2, 'tree', 'output', 3, 'tree', 'percent', 0, 1, 1
                        );

                        INSERT INTO business_cost_income_value(
                          year, month, entity_name, group_name, product_code,
                          item_section, item_id, field, value, update_time
                        ) VALUES
                          (2026, 1, '微众银行', '', 'A01', 'input', 2, 'actual', 100, 'now'),
                          (2026, 2, '微众银行', '', 'A01', 'input', 2, 'actual', 50, 'now'),
                          (2026, 1, '微众银行', '', 'A01', 'input', 2, 'budget', 1200, 'now'),
                          (2026, 1, '微众银行', '', 'A01', 'input', 2, 'forecast', 1100, 'now'),
                          (2025, 1, '微众银行', '', 'A01', 'input', 2, 'actual', 80, 'now'),
                          (2025, 2, '微众银行', '', 'A01', 'input', 2, 'actual', 40, 'now'),

                          (2026, 1, '微众银行', '', 'A01', 'output', 3, 'actual', 1000, 'now'),
                          (2026, 2, '微众银行', '', 'A01', 'output', 3, 'actual', 500, 'now'),
                          (2026, 1, '微众银行', '', 'A01', 'output', 3, 'budget', 12000, 'now'),
                          (2026, 1, '微众银行', '', 'A01', 'output', 3, 'forecast', 11000, 'now'),
                          (2025, 1, '微众银行', '', 'A01', 'output', 3, 'actual', 800, 'now'),
                          (2025, 2, '微众银行', '', 'A01', 'output', 3, 'actual', 400, 'now');
                        """
                    )
                    conn.commit()
                finally:
                    conn.close()

                report = await build_business_cost_income_ratio_report(
                    entity_name="微众银行",
                    report_month="2026-02",
                    group_name=None,
                    product_code="A01",
                    amount_unit="yuan",
                )

                rows = {(row["section"], row["id"]): row for row in report["rows"]}
                parent = rows[("input", 1)]
                child = rows[("input", 2)]
                indicator = rows[("indicator", 1)]

                self.assertFalse(parent["is_leaf"])
                self.assertTrue(child["is_leaf"])
                self.assertEqual(parent["metrics"]["current_actual"], 150.0)
                self.assertEqual(parent["metrics"]["annual_budget"], 1200.0)
                self.assertEqual(parent["metrics"]["budget_progress"], 0.125)
                self.assertEqual(parent["metrics"]["yoy_change"], 30.0)
                self.assertEqual(parent["metrics"]["yoy_rate"], 0.25)
                self.assertEqual(parent["monthly_entry"]["month_actual"], 50.0)
                self.assertEqual(indicator["topic_metric_node_code"], "A01:业务状况表:A0101")
                self.assertEqual(indicator["metrics"]["current_actual"], 10.0)
                self.assertEqual(indicator["metrics"]["annual_budget"], 10.0)
            finally:
                settings.data_dir = original_data_dir

    async def test_item_commands_keep_tree_invariants_and_sorting(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            try:
                parent = await create_business_cost_income_item(
                    year=2026,
                    section="input",
                    name="投入合计",
                    parent_id=None,
                    enabled=True,
                )
                child = await create_business_cost_income_item(
                    year=2026,
                    section="input",
                    name="营销费用",
                    parent_id=parent["item"]["id"],
                    enabled=True,
                )
                grandchild = await create_business_cost_income_item(
                    year=2026,
                    section="input",
                    name="线上渠道",
                    parent_id=child["item"]["id"],
                    enabled=True,
                )
                sibling = await create_business_cost_income_item(
                    year=2026,
                    section="input",
                    name="运营费用",
                    parent_id=parent["item"]["id"],
                    enabled=True,
                )

                self.assertEqual(child["item"]["sort_order"], 0)
                self.assertEqual(sibling["item"]["sort_order"], 1)

                with self.assertRaisesRegex(ValueError, "自己的下级节点"):
                    await update_business_cost_income_item(
                        year=2026,
                        item_id=parent["item"]["id"],
                        name="投入合计",
                        parent_id=grandchild["item"]["id"],
                        sort_order=0,
                        enabled=True,
                    )

                with self.assertRaisesRegex(ValueError, "子项"):
                    await delete_business_cost_income_item(year=2026, item_id=child["item"]["id"])

                moved = await update_business_cost_income_item(
                    year=2026,
                    item_id=sibling["item"]["id"],
                    name="运营费用",
                    parent_id=None,
                    sort_order=9,
                    enabled=False,
                )
                self.assertIsNone(moved["item"]["parent_id"])
                self.assertFalse(moved["item"]["enabled"])

                reordered = await reorder_business_cost_income_items(
                    year=2026,
                    item_ids=[sibling["item"]["id"], parent["item"]["id"]],
                )
                self.assertEqual(reordered["count"], 2)
                conn = sqlite3.connect(data_dir / "budget_2026.db")
                try:
                    rows = dict(
                        conn.execute(
                            "SELECT id, sort_order FROM business_cost_income_item WHERE id IN (?, ?)",
                            (sibling["item"]["id"], parent["item"]["id"]),
                        ).fetchall()
                    )
                finally:
                    conn.close()
                self.assertEqual(rows[sibling["item"]["id"]], 0)
                self.assertEqual(rows[parent["item"]["id"]], 1)
            finally:
                settings.data_dir = original_data_dir

    async def test_indicator_commands_return_before_after_data(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            try:
                numerator = await create_business_cost_income_item(
                    year=2026,
                    product_code="A01",
                    section="input",
                    name="投入",
                    parent_id=None,
                    enabled=True,
                )
                denominator = await create_business_cost_income_item(
                    year=2026,
                    product_code="A01",
                    section="output",
                    name="产出",
                    parent_id=None,
                    enabled=True,
                )

                with self.assertRaisesRegex(ValueError, "分子细项不属于所选分区"):
                    await create_business_cost_income_indicator(
                        year=2026,
                        product_code="A01",
                        name="错配指标",
                        numerator_section="output",
                        numerator_item_id=numerator["item"]["id"],
                        denominator_section="output",
                        denominator_item_id=denominator["item"]["id"],
                        format="percent",
                        sort_order=1,
                        enabled=True,
                    )

                created = await create_business_cost_income_indicator(
                    year=2026,
                    name="投入产出比",
                    product_code="A01",
                    topic_metric_node_code="A01:业务状况表:A0101",
                    numerator_section="input",
                    numerator_item_id=numerator["item"]["id"],
                    denominator_section="output",
                    denominator_item_id=denominator["item"]["id"],
                    format="percent",
                    sort_order=3,
                    enabled=True,
                )
                self.assertEqual(created["indicator"]["topic_metric_node_code"], "A01:业务状况表:A0101")
                fee_topic = await create_business_cost_income_indicator(
                    year=2026,
                    name="05主题",
                    product_code="A01",
                    topic_metric_node_code="A01:业务状况表:A010501",
                    numerator_section="input",
                    numerator_item_id=numerator["item"]["id"],
                    denominator_section="output",
                    denominator_item_id=denominator["item"]["id"],
                    format="percent",
                    sort_order=4,
                    enabled=True,
                )
                self.assertEqual(fee_topic["indicator"]["topic_metric_node_code"], "A01:业务状况表:A010501")
                updated = await update_business_cost_income_indicator(
                    year=2026,
                    indicator_id=created["indicator"]["id"],
                    product_code="A01",
                    name="成本收入比",
                    topic_metric_node_code="A01:业务状况表:A0102",
                    numerator_section="input",
                    numerator_item_id=numerator["item"]["id"],
                    denominator_section="output",
                    denominator_item_id=denominator["item"]["id"],
                    format="ratio",
                    sort_order=1,
                    enabled=False,
                )
                self.assertEqual(updated["before_data"]["name"], "投入产出比")
                self.assertEqual(updated["indicator"]["name"], "成本收入比")
                self.assertEqual(updated["indicator"]["topic_metric_node_code"], "A01:业务状况表:A0102")
                self.assertFalse(updated["indicator"]["enabled"])
                fee_updated = await update_business_cost_income_indicator(
                    year=2026,
                    indicator_id=created["indicator"]["id"],
                    product_code="A01",
                    name="成本收入比",
                    topic_metric_node_code="A01.05.01",
                    numerator_section="input",
                    numerator_item_id=numerator["item"]["id"],
                    denominator_section="output",
                    denominator_item_id=denominator["item"]["id"],
                    format="ratio",
                    sort_order=1,
                    enabled=False,
                )
                self.assertEqual(fee_updated["indicator"]["topic_metric_node_code"], "A01.05.01")

                second = await create_business_cost_income_indicator(
                    year=2026,
                    product_code="A01",
                    name="备用指标",
                    numerator_section="input",
                    numerator_item_id=numerator["item"]["id"],
                    denominator_section="output",
                    denominator_item_id=denominator["item"]["id"],
                    format="percent",
                    sort_order=9,
                    enabled=True,
                )
                reordered = await reorder_business_cost_income_indicators(
                    year=2026,
                    indicator_ids=[second["indicator"]["id"], created["indicator"]["id"]],
                )
                self.assertEqual(reordered["count"], 2)

                deleted = await delete_business_cost_income_indicator(
                    year=2026,
                    indicator_id=created["indicator"]["id"],
                )
                self.assertEqual(deleted["before_data"]["name"], "成本收入比")
                with self.assertRaisesRegex(LookupError, "指标不存在"):
                    await delete_business_cost_income_indicator(
                        year=2026,
                        indicator_id=created["indicator"]["id"],
                    )
            finally:
                settings.data_dir = original_data_dir

    async def test_item_commands_persist_org_product_source_identity(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            with sqlite3.connect(data_dir / "common.db") as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY,
                      data_acct_name TEXT NOT NULL,
                      value_type TEXT NOT NULL
                    );
                    CREATE TABLE data_account_metric_binding (
                      data_acct_code TEXT PRIMARY KEY,
                      metric_node_code TEXT NOT NULL,
                      scope_type TEXT NOT NULL,
                      scope_code TEXT NOT NULL,
                      is_active INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT,
                      table_name TEXT,
                      payload_json TEXT
                    );
                    INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                    VALUES
                      ('A01.01.01.001', '底层营业收入', '金额'),
                      ('A01.05.01', '05费用指标', '金额');
                    INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code, is_active)
                    VALUES
                      ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01', 1),
                      ('A01.05.01', 'A01.05.01', 'PRODUCT', 'A01', 1);
                    INSERT INTO org_product_metric_table(entity_code, table_name, payload_json)
                    VALUES (
                      'A01',
                      '业务状况表',
                      '{"metrics":[{"code":"A010101001","name":"机构产品营业收入"},{"code":"A010501","name":"05费用指标"}]}'
                    );
                    """
                )
            try:
                created = await create_business_cost_income_item(
                    year=2026,
                    product_code="A01",
                    section="output",
                    name="",
                    parent_id=None,
                    data_acct_code="A01.01.01.001",
                    org_product_ref="A01:业务状况表:A010101001",
                    org_product_metric_name="机构产品营业收入",
                    enabled=True,
                )

                self.assertEqual(created["item"]["name"], "机构产品营业收入")
                self.assertEqual(created["item"]["data_acct_code"], "A01.01.01.001")
                self.assertEqual(created["item"]["org_product_ref"], "A01:业务状况表:A010101001")
                self.assertEqual(created["item"]["org_product_entity_code"], "A01")
                self.assertEqual(created["item"]["org_product_table_name"], "业务状况表")
                self.assertEqual(created["item"]["org_product_metric_code"], "A010101001")

                fee_item = await create_business_cost_income_item(
                    year=2026,
                    product_code="A01",
                    section="output",
                    name="",
                    parent_id=None,
                    data_acct_code="A01.05.01",
                    org_product_ref="A01:业务状况表:A010501",
                    org_product_metric_name="05费用指标",
                    enabled=True,
                )
                self.assertEqual(fee_item["item"]["org_product_ref"], "A01:业务状况表:A010501")
                self.assertEqual(fee_item["item"]["name"], "05费用指标")
                self.assertEqual(fee_item["item"]["data_acct_code"], "A01.05.01")
            finally:
                settings.data_dir = original_data_dir

    async def test_item_commands_reject_orphan_runtime_data_account(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            with sqlite3.connect(data_dir / "common.db") as conn:
                conn.executescript(
                    """
                    CREATE TABLE data_account (
                      data_acct_code TEXT PRIMARY KEY,
                      data_acct_name TEXT NOT NULL,
                      value_type TEXT NOT NULL
                    );
                    CREATE TABLE data_account_metric_binding (
                      data_acct_code TEXT PRIMARY KEY,
                      metric_node_code TEXT NOT NULL,
                      scope_type TEXT NOT NULL,
                      scope_code TEXT NOT NULL,
                      is_active INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE TABLE org_product_metric_table (
                      entity_code TEXT,
                      table_name TEXT,
                      payload_json TEXT
                    );
                    INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                    VALUES ('Z99.01.001', '孤立运行数据科目', '金额');
                    INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code, is_active)
                    VALUES ('Z99.01.001', 'Z99.01.001', 'PRODUCT', 'A01', 1);
                    INSERT INTO org_product_metric_table(entity_code, table_name, payload_json)
                    VALUES (
                      'A01',
                      '业务状况表',
                      '{"metrics":[{"code":"A0101","name":"未确认指标","mapping_status":"ORG_PRODUCT_ONLY_OR_CREATE_LATER","data_acct_code":"Z99.01.001","metric_node_code":"Z99.01.001"}]}'
                    );
                    """
                )
            try:
                with self.assertRaisesRegex(ValueError, "机构及产品指标主表"):
                    await create_business_cost_income_item(
                        year=2026,
                        product_code="A01",
                        section="output",
                        name="",
                        parent_id=None,
                        data_acct_code="Z99.01.001",
                        enabled=True,
                    )
            finally:
                settings.data_dir = original_data_dir

    async def test_value_command_rejects_section_item_mismatch(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            settings.data_dir = Path(tmp)
            try:
                input_item = await create_business_cost_income_item(
                    year=2026,
                    section="input",
                    name="投入",
                    parent_id=None,
                    enabled=True,
                )
                with self.assertRaisesRegex(ValueError, "录入细项不属于所选分区"):
                    await upsert_business_cost_income_value(
                        year_month="2026-01",
                        entity_name="微众银行",
                        group_name=None,
                        product_code="A01",
                        amount_unit="yuan",
                        item_section="output",
                        item_id=input_item["item"]["id"],
                        field="actual",
                        value=100,
                    )
            finally:
                settings.data_dir = original_data_dir


if __name__ == "__main__":
    unittest.main()
