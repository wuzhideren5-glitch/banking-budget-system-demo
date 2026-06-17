"""Org-product runtime catalog derived from the organization-product master tree."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import app.core.aiosqlite_compat as aiosqlite
@dataclass(frozen=True)
class OrgProductRuntimeProduct:
    product_code: str
    product_name: str
    parent_code: str | None
    level: int | None
    remark: str | None


@dataclass(frozen=True)
class OrgProductRuntimeCatalogSyncResult:
    row_count: int
    source: str = "org_product_tree_snapshot"


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _org_product_runtime_product_from_record(row: aiosqlite.Row) -> OrgProductRuntimeProduct:
    return OrgProductRuntimeProduct(
        product_code=row["product_code"],
        product_name=row["product_name"],
        parent_code=row["parent_code"],
        level=(int(row["level"]) if row["level"] is not None else None),
        remark=row["remark"],
    )


def org_product_runtime_products_cte(cte_name: str = "org_product_runtime_products") -> str:
    return f"""
        WITH RECURSIVE {cte_name}(
          product_code, product_name, parent_code, level, children
        ) AS (
          SELECT
            UPPER(TRIM(COALESCE(json_extract(payload_json, '$.code'), ''))),
            TRIM(COALESCE(json_extract(payload_json, '$.name'), '')),
            NULL,
            1,
            json_extract(payload_json, '$.children')
          FROM org_product_tree_snapshot
          WHERE id = 1
          UNION ALL
          SELECT
            UPPER(TRIM(COALESCE(json_extract(child.value, '$.code'), ''))),
            TRIM(COALESCE(json_extract(child.value, '$.name'), '')),
            {cte_name}.product_code,
            {cte_name}.level + 1,
            json_extract(child.value, '$.children')
          FROM {cte_name}, json_each(COALESCE({cte_name}.children, '[]')) AS child
        )
        """


def drop_retired_product_type_object(conn: Any) -> None:
    """Remove the retired product maintenance table/view from the runtime DB."""
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = 'product_type'"
    ).fetchone()
    existing_type = str(row[0] or "").strip().lower() if row else ""
    if not existing_type:
        return
    foreign_keys_row = conn.execute("PRAGMA foreign_keys").fetchone()
    foreign_keys_enabled = bool(foreign_keys_row and int(foreign_keys_row[0] or 0))
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        if existing_type == "table":
            conn.execute("DROP TABLE product_type")
        elif existing_type == "view":
            conn.execute("DROP VIEW product_type")
    finally:
        if foreign_keys_enabled:
            conn.execute("PRAGMA foreign_keys = ON")


def select_org_product_runtime_products_sql(*, order_by: str = "level, product_code") -> str:
    return f"""
        {org_product_runtime_products_cte()}
        SELECT
          product_code,
          product_name,
          parent_code,
          level,
          '来源：机构及产品主表快照；运行产品清单' AS remark
        FROM org_product_runtime_products
        WHERE product_code <> '' AND product_name <> ''
        ORDER BY {order_by}
        """


def ensure_retired_product_type_absent(conn: Any) -> None:
    drop_retired_product_type_object(conn)


def _node_type_label(node_type: str) -> str:
    if node_type == "level0":
        return "集团"
    if node_type == "level1":
        return "主体"
    if node_type == "level2":
        return "机构"
    if node_type == "level3":
        return "产品"
    return node_type or "未知"


def _flatten_org_product_tree(tree: dict[str, Any]) -> list[OrgProductRuntimeProduct]:
    rows: list[OrgProductRuntimeProduct] = []
    seen: set[str] = set()

    def walk(node: dict[str, Any], parent_code: str | None, level: int) -> None:
        code = _normalize_code(node.get("code"))
        name = _normalize_text(node.get("name"))
        node_type = _normalize_text(node.get("type"))
        if not code or not name:
            raise ValueError("机构及产品树存在空编码或空名称")
        if code in seen:
            raise ValueError(f"机构及产品树存在重复编码：{code}")
        seen.add(code)
        rows.append(
            OrgProductRuntimeProduct(
                product_code=code,
                product_name=name,
                parent_code=parent_code,
                level=level,
                remark=f"来源：机构及产品主表保存刷新；节点类型：{_node_type_label(node_type)}",
            )
        )
        children = node.get("children") if isinstance(node.get("children"), list) else []
        for child in children:
            if not isinstance(child, dict):
                continue
            walk(child, code, level + 1)

    walk(tree, None, 1)
    return rows


async def list_org_product_runtime_product_rows(
    common_path: str | Path,
) -> list[OrgProductRuntimeProduct]:
    async with aiosqlite.connect(str(common_path)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(select_org_product_runtime_products_sql())
        rows = await cur.fetchall()

    return [_org_product_runtime_product_from_record(row) for row in rows]


def sync_org_product_runtime_catalog_from_tree(
    conn: Any,
    tree: dict[str, Any],
) -> OrgProductRuntimeCatalogSyncResult:
    """Validate the org-product tree and remove the retired product maintenance object."""
    rows = _flatten_org_product_tree(tree)
    ensure_retired_product_type_absent(conn)
    return OrgProductRuntimeCatalogSyncResult(row_count=len(rows))
