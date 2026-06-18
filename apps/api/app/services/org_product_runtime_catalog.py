"""Org-product runtime catalog derived from the organization-product master tree."""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool


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


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _uses_mysql_path(path: str | Path) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
    except TypeError:
        return False
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    data_dir = Path(settings.data_dir).expanduser().resolve()
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return candidate.name == "common.db" or candidate.name == "compare.db" or (
        candidate.name.startswith("budget_") and candidate.suffix == ".db"
    )


def _org_product_runtime_product_from_record(row: Any) -> OrgProductRuntimeProduct:
    return OrgProductRuntimeProduct(
        product_code=str(_row_value(row, "product_code", 0)),
        product_name=str(_row_value(row, "product_name", 1)),
        parent_code=(
            str(_row_value(row, "parent_code", 2))
            if _row_value(row, "parent_code", 2) is not None
            else None
        ),
        level=(
            int(_row_value(row, "level", 3))
            if _row_value(row, "level", 3) is not None
            else None
        ),
        remark=(
            str(_row_value(row, "remark", 4))
            if _row_value(row, "remark", 4) is not None
            else None
        ),
    )


def org_product_runtime_products_cte(
    cte_name: str = "org_product_runtime_products",
    *,
    dialect: str = "mysql",
) -> str:
    if dialect == "sqlite":
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
    return f"""
        WITH RECURSIVE {cte_name}(
          product_code, product_name, parent_code, level, children
        ) AS (
          SELECT
            CAST(UPPER(TRIM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.code')), ''))) AS CHAR(64)),
            CAST(TRIM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.name')), '')) AS CHAR(255)),
            CAST(NULL AS CHAR(64)),
            1,
            JSON_EXTRACT(payload_json, '$.children')
          FROM org_product_tree_snapshot
          WHERE id = 1
          UNION ALL
          SELECT
            CAST(UPPER(TRIM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(child.child_json, '$.code')), ''))) AS CHAR(64)),
            CAST(TRIM(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(child.child_json, '$.name')), '')) AS CHAR(255)),
            CAST({cte_name}.product_code AS CHAR(64)),
            {cte_name}.level + 1,
            JSON_EXTRACT(child.child_json, '$.children')
          FROM {cte_name}
          JOIN JSON_TABLE(
            IFNULL({cte_name}.children, JSON_ARRAY()),
            '$[*]' COLUMNS (child_json JSON PATH '$')
          ) AS child
        )
        """


def org_product_runtime_products_cte_for_cursor(
    cur: Any,
    cte_name: str = "org_product_runtime_products",
) -> str:
    cursor_type = f"{type(cur).__module__}.{type(cur).__name__}".lower()
    dialect = "sqlite" if "sqlite" in cursor_type else "mysql"
    return org_product_runtime_products_cte(cte_name, dialect=dialect)


def org_product_runtime_products_cte_for_conn(
    conn: Any,
    cte_name: str = "org_product_runtime_products",
) -> str:
    return org_product_runtime_products_cte(cte_name, dialect=_dialect_for_db(conn))


def org_product_runtime_products_cte_for_db(
    db: Any,
    cte_name: str = "org_product_runtime_products",
) -> str:
    return org_product_runtime_products_cte(cte_name, dialect=_dialect_for_db(db))


def _dialect_for_db(db: Any) -> str:
    db_type = f"{type(db).__module__}.{type(db).__name__}".lower()
    dialect = "mysql"
    if "sqlite" in db_type or "aiosqlite" in db_type or "_sqliteconnectionadapter" in db_type:
        dialect = "sqlite"
    return dialect


def drop_retired_product_type_object(conn: Any) -> None:
    """Remove the retired product maintenance table/view from the runtime DB."""
    dialect = _dialect_for_db(conn)
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = 'product_type'"
    ).fetchone()
    existing_type = str(row[0] or "").strip().lower() if row else ""
    if not existing_type:
        return
    if dialect == "mysql":
        conn.execute("SET foreign_key_checks = 0")
        try:
            if existing_type in {"base table", "table"}:
                conn.execute("DROP TABLE IF EXISTS `product_type`")
            elif existing_type == "view":
                conn.execute("DROP VIEW IF EXISTS `product_type`")
        finally:
            conn.execute("SET foreign_key_checks = 1")
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


def select_org_product_runtime_products_sql(
    *, order_by: str = "level, product_code", dialect: str = "sqlite"
) -> str:
    return f"""
        {org_product_runtime_products_cte(dialect=dialect)}
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
    if _uses_mysql_path(common_path):
        rows = await get_pool().fetch_all(
            select_org_product_runtime_products_sql(dialect="mysql")
        )
    else:
        rows = await asyncio.to_thread(_sqlite_list_org_product_runtime_product_rows, common_path)

    return [_org_product_runtime_product_from_record(row) for row in rows]


def _sqlite_list_org_product_runtime_product_rows(common_path: str | Path) -> list[Any]:
    with sqlite3.connect(str(common_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(select_org_product_runtime_products_sql(dialect="sqlite")).fetchall()


def sync_org_product_runtime_catalog_from_tree(
    conn: Any,
    tree: dict[str, Any],
) -> OrgProductRuntimeCatalogSyncResult:
    """Validate the org-product tree and remove the retired product maintenance object."""
    rows = _flatten_org_product_tree(tree)
    ensure_retired_product_type_absent(conn)
    return OrgProductRuntimeCatalogSyncResult(row_count=len(rows))
