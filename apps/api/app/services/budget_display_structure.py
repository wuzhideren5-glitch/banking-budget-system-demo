from __future__ import annotations

import re
from typing import Protocol

import aiosqlite


DISPLAY_ROW_KEY_PATTERN = re.compile(r"^(TOTAL|OVERVIEW|PRODUCT\.[^.]+)(?:\.\d{2})+$")


class AsyncSqlExecutor(Protocol):
    async def execute(self, sql: str, parameters: object = ...) -> object: ...


def display_view_key(display_view: str) -> str:
    value = str(display_view or "").strip().upper()
    if value.startswith("PRODUCT."):
        return value
    if value == "OVERVIEW":
        return "OVERVIEW"
    return "TOTAL"


def parse_display_row_key(row_key: str) -> tuple[str, tuple[int, ...]] | None:
    parts = str(row_key or "").split(".")
    if not parts:
        return None
    if parts[0] == "PRODUCT":
        if len(parts) < 3:
            return None
        prefix = ".".join(parts[:2])
        segment_parts = parts[2:]
    elif parts[0] in {"TOTAL", "OVERVIEW"}:
        prefix = parts[0]
        segment_parts = parts[1:]
    else:
        return None
    try:
        segments = tuple(int(part) for part in segment_parts)
    except ValueError:
        return None
    if not segments or any(segment < 1 or segment > 99 for segment in segments):
        return None
    return prefix, segments


def format_budget_display_row_key(display_view: str, segments: tuple[int, ...]) -> str:
    prefix = display_view_key(display_view)
    return ".".join([prefix, *(f"{segment:02d}" for segment in segments)])


async def allocate_budget_display_row_key(
    db: aiosqlite.Connection,
    *,
    display_view: str,
    parent_row_key: str | None,
) -> str:
    """Allocate a display-position key such as TOTAL.01.02 or PRODUCT.A01.01.02."""
    parent_segments = parse_display_row_key(parent_row_key or "") if parent_row_key else None
    prefix = parent_segments[0] if parent_segments else display_view_key(display_view)
    parent_path = parent_segments[1] if parent_segments else ()
    if parent_path:
        like_pattern = ".".join([prefix, *(f"{segment:02d}" for segment in parent_path), "__"])
    else:
        like_pattern = f"{prefix}.__"
    cur = await db.execute(
        "SELECT row_key FROM budget_output_display_item WHERE row_key LIKE ?",
        (like_pattern,),
    )
    used_child_segments: set[int] = set()
    for row in await cur.fetchall():
        raw = row["row_key"] if isinstance(row, aiosqlite.Row) else row[0]
        parsed = parse_display_row_key(str(raw))
        if not parsed:
            continue
        row_prefix, segments = parsed
        if row_prefix != prefix or segments[:-1] != parent_path:
            continue
        used_child_segments.add(segments[-1])
    next_segment = (max(used_child_segments) if used_child_segments else 0) + 1
    if next_segment > 99:
        raise ValueError("同一层级展示行超过 99 个，请先拆分展示层级")
    return format_budget_display_row_key(prefix, (*parent_path, next_segment))


async def clear_budget_display_runtime_ref_binding(db: AsyncSqlExecutor, data_acct_code: str) -> int:
    """Keep display rows, but clear their data source when the runtime metric ref is removed."""
    cur = await db.execute(
        """
        UPDATE budget_output_display_item
        SET data_acct_code = NULL,
            org_product_ref = NULL,
            org_product_entity_code = NULL,
            org_product_table_name = NULL,
            org_product_metric_code = NULL,
            org_product_metric_name = NULL,
            row_type = 'GROUP',
            value_type = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE data_acct_code = ?
        """,
        (str(data_acct_code or "").strip().upper(),),
    )
    return max(0, int(getattr(cur, "rowcount", 0) or 0))
