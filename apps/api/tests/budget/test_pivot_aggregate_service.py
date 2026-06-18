from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from app.schemas import BudgetSummaryAggregateRequest
from app.services import pivot_aggregate as pivot_aggregate_module
from app.services.pivot_aggregate import (
    list_budget_pivot_aggregate_rows,
    list_compare_pivot_aggregate_rows,
    rebuild_budget_pivot_aggregate_for_version,
    rebuild_compare_pivot_aggregate,
)


class _FakePivotAggregateMysqlPool:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((" ".join(sql.split()), params))
        return 1

    async def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized_sql = " ".join(sql.lower().split())
        if "from budget_pivot_aggregate" in normalized_sql:
            return {"aggregate_count": 3}
        if "from compare_pivot_aggregate" in normalized_sql:
            return {"aggregate_count": 2}
        raise AssertionError(f"Unexpected fetch_one SQL: {sql}")

    async def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized_sql = " ".join(sql.lower().split())
        if "from budget_pivot_aggregate" in normalized_sql:
            return [
                {
                    "metric_level1": "收入",
                    "metric_level2": None,
                    "metric_level3": None,
                    "metric_level4": None,
                    "metric_level5": None,
                    "dept_level1": None,
                    "dept_level2": None,
                    "dept_level3": None,
                    "data_code_name": "聚合指标编码",
                    "product_code_name": None,
                    "year": "Y2026",
                    "month": "全部",
                    "quarter": "全部",
                    "budget_actual": 0,
                    "value_source": "manual",
                    "version_id": 9,
                    "version_name": "V9",
                    "value": 12.5,
                    "value_type": "金额",
                    "update_time": "2026-06-18T00:00:00Z",
                }
            ]
        if "from compare_pivot_aggregate" in normalized_sql:
            return [
                {
                    "show_level": 1,
                    "data_file_id": 2,
                    "source_year": 2026,
                    "source_version_id": 9,
                    "source_version_name": "V9",
                    "metric_level1": "收入",
                    "metric_level2": None,
                    "metric_level3": None,
                    "metric_level4": None,
                    "metric_level5": None,
                    "dept_level1": None,
                    "dept_level2": None,
                    "dept_level3": None,
                    "data_code_name": "聚合指标编码",
                    "product_code_name": None,
                    "year": "Y2026",
                    "month": "全部",
                    "quarter": "全部",
                    "budget_actual": 0,
                    "value_source": "manual",
                    "value": 12.5,
                    "value_type": "金额",
                    "sync_time": "2026-06-18T00:00:00Z",
                }
            ]
        if "from data_account_metric_node" in normalized_sql:
            return []
        raise AssertionError(f"Unexpected fetch_all SQL: {sql}")


class PivotAggregateServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_budget_pivot_aggregate_uses_mysql_for_runtime_budget_db(self) -> None:
        fake_pool = _FakePivotAggregateMysqlPool()
        budget_path = Path(pivot_aggregate_module.settings.data_dir) / "budget_2026.db"
        with patch.object(pivot_aggregate_module, "get_pool", return_value=fake_pool):
            rebuilt = await rebuild_budget_pivot_aggregate_for_version(9, budget_path)
            rows = await list_budget_pivot_aggregate_rows(
                budget_path=budget_path,
                body=BudgetSummaryAggregateRequest(row_field_ids=["metric_level1"], page_field_ids=[]),
                current_month_by_version={9: 4},
            )

        self.assertEqual(rebuilt, 3)
        self.assertEqual(rows[0].metric_level1, "收入")
        self.assertEqual(rows[0].version_id, 9)
        self.assertTrue(any("DELETE FROM budget_pivot_aggregate" in sql for sql, _params in fake_pool.executed))
        self.assertTrue(any("INSERT INTO budget_pivot_aggregate" in sql for sql, _params in fake_pool.executed))

    async def test_compare_pivot_aggregate_uses_mysql_for_runtime_compare_db(self) -> None:
        fake_pool = _FakePivotAggregateMysqlPool()
        with patch.object(pivot_aggregate_module, "get_pool", return_value=fake_pool):
            rebuilt = await rebuild_compare_pivot_aggregate()
            rows = await list_compare_pivot_aggregate_rows(
                BudgetSummaryAggregateRequest(row_field_ids=["metric_level1"], page_field_ids=[]),
            )

        self.assertEqual(rebuilt, 2)
        self.assertEqual(rows[0].show_level, 1)
        self.assertEqual(rows[0].source_version_id, 9)
        self.assertTrue(any("DELETE FROM compare_pivot_aggregate" in sql for sql, _params in fake_pool.executed))
        self.assertTrue(any("INSERT INTO compare_pivot_aggregate" in sql for sql, _params in fake_pool.executed))

    async def test_pivot_aggregate_service_does_not_import_aiosqlite(self) -> None:
        source = Path(pivot_aggregate_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
