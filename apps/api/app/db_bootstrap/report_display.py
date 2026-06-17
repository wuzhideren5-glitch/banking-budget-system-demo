"""Bootstrap helpers for budget-output display configuration tables."""
from __future__ import annotations

import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from typing import Protocol


class AsyncSqlExecutor(Protocol):
    async def execute(self, sql: str, parameters: object = ...) -> object: ...


ORG_PRODUCT_COLUMNS = {
    "org_product_ref": "TEXT",
    "org_product_entity_code": "TEXT",
    "org_product_table_name": "TEXT",
    "org_product_metric_code": "TEXT",
    "org_product_metric_name": "TEXT",
}


BUDGET_OUTPUT_DISPLAY_ITEM_SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_output_display_item (
  row_key TEXT PRIMARY KEY NOT NULL,
  display_view TEXT NOT NULL,
  parent_row_key TEXT REFERENCES budget_output_display_item(row_key) ON DELETE SET NULL,
  data_acct_code TEXT,
  org_product_ref TEXT,
  org_product_entity_code TEXT,
  org_product_table_name TEXT,
  org_product_metric_code TEXT,
  org_product_metric_name TEXT,
  row_type TEXT NOT NULL CHECK (row_type IN ('GROUP', 'METRIC')),
  display_name TEXT NOT NULL,
  value_type TEXT,
  level INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_budget_output_display_item_order
ON budget_output_display_item(display_view, is_active, sort_order, row_key);

CREATE INDEX IF NOT EXISTS idx_budget_output_display_item_parent
ON budget_output_display_item(parent_row_key);
"""


BUDGET_OUTPUT_DISPLAY_ITEM_COLUMNS = (
    "row_key",
    "display_view",
    "parent_row_key",
    "data_acct_code",
    "org_product_ref",
    "org_product_entity_code",
    "org_product_table_name",
    "org_product_metric_code",
    "org_product_metric_name",
    "row_type",
    "display_name",
    "value_type",
    "level",
    "sort_order",
    "is_active",
    "created_at",
    "updated_at",
)


def _has_data_account_fk(conn: sqlite3.Connection) -> bool:
    return any(
        str(row[2]) == "data_account"
        for row in conn.execute("PRAGMA foreign_key_list(budget_output_display_item)")
    )


def _rebuild_budget_output_display_item_without_data_account_fk(conn: sqlite3.Connection) -> None:
    if not _has_data_account_fk(conn):
        return
    existing_columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(budget_output_display_item)")
    }
    copy_columns = [column for column in BUDGET_OUTPUT_DISPLAY_ITEM_COLUMNS if column in existing_columns]
    conn.execute("ALTER TABLE budget_output_display_item RENAME TO budget_output_display_item__old")
    conn.executescript(BUDGET_OUTPUT_DISPLAY_ITEM_SCHEMA)
    column_list = ", ".join(copy_columns)
    conn.execute(
        f"""
        INSERT INTO budget_output_display_item({column_list})
        SELECT {column_list}
        FROM budget_output_display_item__old
        """
    )
    conn.execute("DROP TABLE budget_output_display_item__old")


async def ensure_budget_output_display_item_schema(db: AsyncSqlExecutor) -> None:
    """Ensure the active budget-output display configuration schema exists."""
    for statement in BUDGET_OUTPUT_DISPLAY_ITEM_SCHEMA.split(";"):
        sql = statement.strip()
        if sql:
            await db.execute(f"{sql};")
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_budget_output_display_item_order
        ON budget_output_display_item(display_view, is_active, sort_order, row_key)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_budget_output_display_item_parent
        ON budget_output_display_item(parent_row_key)
        """
    )
    cur = await db.execute("PRAGMA table_info(budget_output_display_item)")
    existing = {str(row[1]) for row in await cur.fetchall()}  # type: ignore[attr-defined]
    for column_name, column_type in ORG_PRODUCT_COLUMNS.items():
        if column_name not in existing:
            await db.execute(f"ALTER TABLE budget_output_display_item ADD COLUMN {column_name} {column_type}")


def ensure_budget_output_display_item_schema_sync(conn: sqlite3.Connection) -> None:
    """Ensure the active budget-output display configuration schema exists."""
    conn.executescript(BUDGET_OUTPUT_DISPLAY_ITEM_SCHEMA)
    _rebuild_budget_output_display_item_without_data_account_fk(conn)
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(budget_output_display_item)")}
    for column_name, column_type in ORG_PRODUCT_COLUMNS.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE budget_output_display_item ADD COLUMN {column_name} {column_type}")
