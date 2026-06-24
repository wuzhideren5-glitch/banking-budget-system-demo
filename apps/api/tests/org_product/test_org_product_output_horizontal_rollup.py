from __future__ import annotations

import asyncio
import sqlite3
import unittest

from app.core.db_paths import common_db_path
from app.routers.org_product_helpers import OrgProductOutputRunRequest, _ensure_org_product_tree_table
from app.routers import org_product_output as mod
from app.services.org_product_output_engine import _load_org_product_direct_children


class OrgProductOutputHorizontalRollupTests(unittest.TestCase):
    def test_child_map_for_retail_group(self) -> None:
        path = common_db_path()
        if not path.exists():
            self.skipTest("common db missing")
        with sqlite3.connect(path) as conn:
            _ensure_org_product_tree_table(conn)
            child_map = _load_org_product_direct_children(conn)
        self.assertIn("A", child_map)
        self.assertEqual(set(child_map["A"]), {"A01", "A02", "A03", "A04", "A05"})

    def test_group_a_rollup_from_products(self) -> None:
        async def _run() -> None:
            payload = OrgProductOutputRunRequest(
                entity_code="A",
                year=2026,
                version_id=1,
                table_name="业务状况表",
                include_children=False,
            )
            result = await mod.run_org_product_output(payload)
            ent = (result.get("entities") or [None])[0]
            rows = {r["code"]: r for r in (ent or {}).get("rows") or []}

            product_sum = 0.0
            for ec in ("A01", "A02", "A03", "A04", "A05"):
                sub = await mod.run_org_product_output(
                    OrgProductOutputRunRequest(
                        entity_code=ec,
                        year=2026,
                        version_id=1,
                        table_name="业务状况表",
                        include_children=False,
                    )
                )
                sub_rows = {r["code"]: r for r in (sub.get("entities") or [{}])[0].get("rows") or []}
                product_sum += float(sub_rows[f"{ec}.01"]["months"][0])

            group_val = float(rows["A.01"]["months"][0])
            self.assertGreater(group_val, 0.0)
            self.assertAlmostEqual(group_val, product_sum, places=2)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
