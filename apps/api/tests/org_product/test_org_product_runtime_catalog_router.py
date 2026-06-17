from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import org_product_runtime_catalog as org_product_runtime_catalog_module
from app.services.org_product_runtime_catalog import (
    list_org_product_runtime_product_rows,
    sync_org_product_runtime_catalog_from_tree,
)


async def _noop_operation_log(*_args, **_kwargs) -> None:
    return None


ORG_PRODUCT_TREE = {
    "id": "root",
    "code": "AAA",
    "name": "微众集团",
    "type": "level0",
    "children": [
        {
            "id": "aa",
            "code": "AA",
            "name": "微众银行",
            "type": "level1",
            "children": [
                {
                    "id": "a",
                    "code": "A",
                    "name": "个金群",
                    "type": "level2",
                    "children": [
                        {
                            "id": "a01",
                            "code": "A01",
                            "name": "泛微粒贷",
                            "type": "level3",
                            "children": [],
                        }
                    ],
                }
            ],
        },
        {
            "id": "ab",
            "code": "AB",
            "name": "微众科技",
            "type": "level1",
            "children": [],
        },
    ],
}


class OrgProductRuntimeCatalogRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.common_path = Path(self.tmp.name) / "common.db"
        with sqlite3.connect(self.common_path) as conn:
            conn.executescript(
                """
                CREATE TABLE org_product_tree_snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE product_type (
                  product_code TEXT PRIMARY KEY,
                  product_name TEXT NOT NULL,
                  parent_code TEXT REFERENCES product_type(product_code),
                  level INTEGER NOT NULL,
                  remark TEXT
                );
                INSERT INTO product_type(product_code, product_name, parent_code, level, remark)
                VALUES ('OLD', '旧产品', NULL, 1, '旧维护表数据');
                """
            )
            conn.execute(
                "INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at) VALUES(1, ?, 'now')",
                (json.dumps(ORG_PRODUCT_TREE, ensure_ascii=False),),
            )
            sync_org_product_runtime_catalog_from_tree(conn, ORG_PRODUCT_TREE)
            conn.commit()

        self.previous_common_db_path = org_product_runtime_catalog_module.common_db_path
        org_product_runtime_catalog_module.common_db_path = lambda: self.common_path

        app = FastAPI()
        app.include_router(
            org_product_runtime_catalog_module.build_org_product_runtime_catalog_router(
                write_operation_log=_noop_operation_log,
            )
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        org_product_runtime_catalog_module.common_db_path = self.previous_common_db_path
        self.tmp.cleanup()

    def test_org_product_runtime_catalog_service_lists_view_rows_only(self) -> None:
        rows = asyncio.run(list_org_product_runtime_product_rows(common_path=self.common_path))

        self.assertEqual([row.product_code for row in rows], ["AAA", "AA", "AB", "A", "A01"])
        self.assertEqual(rows[-1].product_name, "泛微粒贷")

    def test_router_keeps_org_product_runtime_products_read_only(self) -> None:
        base_path = "/api/org-product-runtime-products"

        self.assertEqual(self.client.get(base_path).status_code, 200)
        self.assertEqual(self.client.post(base_path, json={}).status_code, 405)
        self.assertEqual(self.client.patch(f"{base_path}/A01", json={}).status_code, 404)
        self.assertEqual(self.client.delete(f"{base_path}/A01").status_code, 404)
        self.assertEqual(self.client.get(f"{base_path}/template").status_code, 404)
        self.assertEqual(self.client.post(f"{base_path}/import-preview").status_code, 404)
        self.assertEqual(self.client.post(f"{base_path}/import-apply").status_code, 404)
        self.assertEqual(self.client.get("/api/product-types").status_code, 404)

    def test_router_does_not_keep_product_maintenance_handlers(self) -> None:
        router_source = Path(org_product_runtime_catalog_module.__file__).read_text(encoding="utf-8")

        self.assertIn('router.get("/api/org-product-runtime-products"', router_source)
        self.assertNotIn('router.get("/api/product-types"', router_source)
        self.assertNotIn("router.post(", router_source)
        self.assertNotIn("router.patch(", router_source)
        self.assertNotIn("router.delete(", router_source)
        self.assertNotIn("import-preview", router_source)
        self.assertNotIn("import-apply", router_source)
        self.assertNotIn("template", router_source)

    def test_org_product_tree_sync_removes_product_maintenance_object(self) -> None:
        with sqlite3.connect(self.common_path) as conn:
            result = sync_org_product_runtime_catalog_from_tree(conn, ORG_PRODUCT_TREE)
            conn.commit()

        self.assertEqual(result.row_count, 5)
        with sqlite3.connect(self.common_path) as conn:
            product_object = conn.execute(
                "SELECT type FROM sqlite_master WHERE name='product_type'"
            ).fetchone()
            self.assertIsNone(product_object)
        rows = asyncio.run(list_org_product_runtime_product_rows(common_path=self.common_path))
        self.assertEqual(
            [(row.product_code, row.product_name, row.parent_code, row.level) for row in rows],
            [
                ("AAA", "微众集团", None, 1),
                ("AA", "微众银行", "AAA", 2),
                ("AB", "微众科技", "AAA", 2),
                ("A", "个金群", "AA", 3),
                ("A01", "泛微粒贷", "A", 4),
            ],
        )

    def test_org_product_tree_sync_rejects_duplicate_codes(self) -> None:
        bad_tree = {
            "id": "root",
            "code": "AA",
            "name": "微众银行",
            "type": "level1",
            "children": [
                {
                    "id": "duplicate",
                    "code": "AA",
                    "name": "重复",
                    "type": "level2",
                    "children": [],
                }
            ],
        }

        with sqlite3.connect(self.common_path) as conn:
            with self.assertRaises(ValueError):
                sync_org_product_runtime_catalog_from_tree(conn, bad_tree)


if __name__ == "__main__":
    unittest.main()
