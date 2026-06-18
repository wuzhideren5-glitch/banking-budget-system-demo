from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services import formula_engine as formula_engine_module
from app.services.formula_engine import (
    load_runtime_metric_scope_map,
    try_calculate_formula_value,
    validate_formula_reference_scope,
)


class FormulaEngineTests(unittest.TestCase):
    def test_calculates_formula_refs_functions_and_full_width_operators(self) -> None:
        value, error = try_calculate_formula_value(
            "（<A01.01.01.001 日均余额>＋SUM(2, 3)）×2",
            {"A01.01.01.001": 10},
        )

        self.assertIsNone(error)
        self.assertEqual(value, 30.0)

    def test_returns_error_for_division_by_zero(self) -> None:
        value, error = try_calculate_formula_value("1 / 0", {})

        self.assertEqual(value, 0.0)
        self.assertEqual(error, "#DIV/0!")

    def test_calculates_bare_official_data_account_refs(self) -> None:
        value, error = try_calculate_formula_value(
            "A.01.01.001 + B.01.01.001",
            {"A.01.01.001": 10, "B.01.01.001": 5},
        )

        self.assertIsNone(error)
        self.assertEqual(value, 15.0)

    def test_calculates_five_level_and_parent_data_account_refs(self) -> None:
        value, error = try_calculate_formula_value(
            "A01.01.01.001 / A01.01.01",
            {"A01.01.01.001": 20, "A01.01.01": 100},
        )

        self.assertIsNone(error)
        self.assertEqual(value, 0.2)

    def test_corp_formula_allows_child_product_refs(self) -> None:
        validate_formula_reference_scope(
            formula="A.01.01.001 + B.01.01.001",
            target_is_all=True,
            scope_by_code={"A.01.01.001": False, "B.01.01.001": False},
            formula_label="预算公式",
        )


class _FakeFormulaEngineMysqlPool:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((" ".join(sql.split()), tuple(params)))
        return [
            {"data_acct_code": "A01.01.001", "scope_code": "A01"},
            {"data_acct_code": "AA.90", "scope_code": "CORP"},
        ]


class FormulaEngineMysqlPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_runtime_metric_scope_map_uses_mysql_for_runtime_common_path(self) -> None:
        fake_pool = _FakeFormulaEngineMysqlPool()

        with patch.object(formula_engine_module, "get_pool", return_value=fake_pool):
            scope_map = await load_runtime_metric_scope_map(settings.data_dir / "common.db")

        self.assertEqual(scope_map, {"A01.01.001": False, "AA.90": True})
        self.assertEqual(len(fake_pool.fetch_all_calls), 1)
        sql, params = fake_pool.fetch_all_calls[0]
        self.assertIn("FROM data_account_metric_binding", sql)
        self.assertEqual(params, ())

    def test_formula_engine_service_does_not_import_aiosqlite(self) -> None:
        source = Path(formula_engine_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
