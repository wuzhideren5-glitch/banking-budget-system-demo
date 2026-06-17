from __future__ import annotations

import unittest

from app.routers.org_product_output import router as org_product_output_router
from app.routers.org_product_data_entry import router as org_product_data_entry_router
from app.routers.org_product_helpers import _derive_metric_logic_code
from app.routers.org_product_helpers import _normalize_rollup_flag
from app.routers.org_product_helpers import _resolve_metric_formula_for_month


class OrgProductOutputRouterContractTests(unittest.TestCase):
    def test_v02_logic_code_and_rollup_flags_are_normalized(self) -> None:
        self.assertEqual(_derive_metric_logic_code("A01", "A01.01.01.01", ""), "01.01.01")
        self.assertEqual(_derive_metric_logic_code("AA", "AA.01", ""), "01")
        self.assertEqual(_derive_metric_logic_code("B01", "B01.11.01", "11.01"), "11.01")
        self.assertEqual(_normalize_rollup_flag("是"), 1)
        self.assertEqual(_normalize_rollup_flag("否"), 0)
        self.assertEqual(_normalize_rollup_flag("需要汇总"), 1)

    def test_month_specific_formula_does_not_fallback_to_other_month_type(self) -> None:
        forecast_only = {
            "formula": "B01.11.01.01.01 * B01.14.01.03.03.03",
            "formula_actual": "",
            "formula_forecast": "B01.11.01.01.01 * B01.14.01.03.03.03",
        }
        self.assertEqual(_resolve_metric_formula_for_month(forecast_only, 1, 3), "")
        self.assertEqual(
            _resolve_metric_formula_for_month(forecast_only, 4, 3),
            "B01.11.01.01.01 * B01.14.01.03.03.03",
        )

        actual_only = {
            "formula": "B01.14.01.03.03.02/B01.11.01.01.01",
            "formula_actual": "B01.14.01.03.03.02/B01.11.01.01.01",
            "formula_forecast": "",
        }
        self.assertEqual(
            _resolve_metric_formula_for_month(actual_only, 1, 3),
            "B01.14.01.03.03.02/B01.11.01.01.01",
        )
        self.assertEqual(_resolve_metric_formula_for_month(actual_only, 4, 3), "")

    def test_legacy_formula_still_applies_when_no_month_specific_formula_exists(self) -> None:
        legacy_only = {
            "formula": "B01.01.01 + B01.01.02",
            "formula_actual": "",
            "formula_forecast": "",
        }
        self.assertEqual(_resolve_metric_formula_for_month(legacy_only, 1, 3), "B01.01.01 + B01.01.02")
        self.assertEqual(_resolve_metric_formula_for_month(legacy_only, 4, 3), "B01.01.01 + B01.01.02")

    def test_output_and_data_entry_write_routes_bind_payload_from_json_body(self) -> None:
        output_routes = org_product_output_router.routes
        entry_routes = org_product_data_entry_router.routes
        all_routes = output_routes + entry_routes
        paths = {
            "/api/org-product-output/run",
            "/api/org-product-output/commit",
            "/api/org-product-data-entry/commit/preview",
            "/api/org-product-data-entry/commit/apply",
            "/api/org-product-data-entry/budget-sync/preview",
            "/api/org-product-data-entry/budget-sync/apply",
        }

        by_path = {getattr(route, "path", ""): route for route in all_routes}
        for path in paths:
            with self.subTest(path=path):
                route = by_path[path]
                body_params = [param.name for param in route.dependant.body_params]
                query_params = [param.name for param in route.dependant.query_params]
                self.assertEqual(body_params, ["payload"])
                self.assertNotIn("payload", query_params)
                self.assertIsNotNone(getattr(route, "body_field", None))


if __name__ == "__main__":
    unittest.main()
