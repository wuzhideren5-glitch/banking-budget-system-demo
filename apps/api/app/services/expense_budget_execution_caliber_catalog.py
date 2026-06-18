"""Map budget release caliber names to budget subject catalog names."""
from __future__ import annotations

import re
from typing import Any

from app.core.database import get_pool

CALIBER_CATALOG_ALIASES: dict[str, str] = {
    "部门内部会议费": "部门会议费",
    "资产摊销及折旧": "日常资产摊销及折旧",
}


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


async def _mysql_table_exists(table_name: str) -> bool:
    value = await get_pool().fetch_val(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return bool(value)


async def _connection_table_exists(db: Any, table_name: str) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return bool(await cur.fetchone())


async def load_catalog_subject_names(db: Any | None = None) -> set[str]:
    if db is not None:
        if not await _connection_table_exists(db, "budget_subject_catalog"):
            return set()
        cur = await db.execute(
            """
            SELECT subject_name
            FROM budget_subject_catalog
            ORDER BY sort_order, id
            """
        )
        subject_names: set[str] = set()
        for row in await cur.fetchall():
            subject_name = text_value(_row_value(row, "subject_name", 0))
            if subject_name:
                subject_names.add(subject_name)
        return subject_names

    if not await _mysql_table_exists("budget_subject_catalog"):
        return set()
    rows = await get_pool().fetch_all(
        """
        SELECT subject_name
        FROM budget_subject_catalog
        ORDER BY sort_order, id
        """
    )
    return {
        text_value(_row_value(row, "subject_name", 0))
        for row in rows
        if text_value(_row_value(row, "subject_name", 0))
    }


async def load_budget_caliber_catalog_map(
    db: Any | None = None,
    *,
    catalog_names: set[str] | None = None,
) -> dict[str, str]:
    mapping = dict(CALIBER_CATALOG_ALIASES)
    if catalog_names is None:
        catalog_names = await load_catalog_subject_names(db)

    async def _load_from_connection(connection: Any) -> None:
        if not await _connection_table_exists(connection, "bi_ai_subject_mapping"):
            return
        cur = await connection.execute(
            """
            SELECT level5_name, level6_name, budget_release_caliber
            FROM bi_ai_subject_mapping
            WHERE TRIM(COALESCE(budget_release_caliber, '')) <> ''
            ORDER BY sort_order, id
            """
        )
        for row in await cur.fetchall():
            level5 = _row_value(row, "level5_name", 0)
            level6 = _row_value(row, "level6_name", 1)
            caliber = _row_value(row, "budget_release_caliber", 2)
            caliber_name = text_value(caliber)
            if not caliber_name or caliber_name in mapping:
                continue
            for level_name in (level6, level5):
                candidate = text_value(level_name)
                if candidate and candidate in catalog_names:
                    mapping[caliber_name] = candidate
                    break

    if db is not None:
        await _load_from_connection(db)
        return mapping

    if not await _mysql_table_exists("bi_ai_subject_mapping"):
        return mapping
    rows = await get_pool().fetch_all(
        """
        SELECT level5_name, level6_name, budget_release_caliber
        FROM bi_ai_subject_mapping
        WHERE TRIM(COALESCE(budget_release_caliber, '')) <> ''
        ORDER BY sort_order, id
        """
    )
    for row in rows:
        caliber_name = text_value(_row_value(row, "budget_release_caliber", 2))
        if not caliber_name or caliber_name in mapping:
            continue
        for level_name in (_row_value(row, "level6_name", 1), _row_value(row, "level5_name", 0)):
            candidate = text_value(level_name)
            if candidate and candidate in catalog_names:
                mapping[caliber_name] = candidate
                break
    return mapping


def resolve_caliber_catalog_subject(
    caliber_name: str,
    *,
    catalog_names: set[str],
    caliber_catalog_map: dict[str, str],
) -> str:
    raw_name = text_value(caliber_name)
    if not raw_name:
        return ""
    if raw_name in catalog_names:
        return raw_name
    mapped = text_value(caliber_catalog_map.get(raw_name, ""))
    if mapped and mapped in catalog_names:
        return mapped
    return raw_name
