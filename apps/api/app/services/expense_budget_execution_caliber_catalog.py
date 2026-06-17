"""Map budget release caliber names to budget subject catalog names."""
from __future__ import annotations

import app.core.aiosqlite_compat as aiosqlite
from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_framework import text

CALIBER_CATALOG_ALIASES: dict[str, str] = {
    "部门内部会议费": "部门会议费",
    "资产摊销及折旧": "日常资产摊销及折旧",
}


async def load_catalog_subject_names(db: aiosqlite.Connection | None = None) -> set[str]:
    if db is not None:
        exists_cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'budget_subject_catalog'"
        )
        if not await exists_cur.fetchone():
            return set()
        cur = await db.execute(
            """
            SELECT subject_name
            FROM budget_subject_catalog
            ORDER BY sort_order, id
            """
        )
        return {text(row[0]) for row in await cur.fetchall() if text(row[0])}

    async with aiosqlite.connect(common_db_path()) as owned_db:
        await owned_db.execute("PRAGMA foreign_keys = ON")
        return await load_catalog_subject_names(owned_db)


async def load_budget_caliber_catalog_map(
    db: aiosqlite.Connection | None = None,
    *,
    catalog_names: set[str] | None = None,
) -> dict[str, str]:
    mapping = dict(CALIBER_CATALOG_ALIASES)
    if catalog_names is None:
        catalog_names = await load_catalog_subject_names(db)

    async def _load_from(connection: aiosqlite.Connection) -> None:
        cur = await connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'bi_ai_subject_mapping'
            """
        )
        if not await cur.fetchone():
            return
        cur = await connection.execute(
            """
            SELECT level5_name, level6_name, budget_release_caliber
            FROM bi_ai_subject_mapping
            WHERE TRIM(COALESCE(budget_release_caliber, '')) <> ''
            ORDER BY sort_order, id
            """
        )
        for level5, level6, caliber in await cur.fetchall():
            caliber_name = text(caliber)
            if not caliber_name or caliber_name in mapping:
                continue
            for level_name in (level6, level5):
                candidate = text(level_name)
                if candidate and candidate in catalog_names:
                    mapping[caliber_name] = candidate
                    break

    if db is not None:
        await _load_from(db)
        return mapping

    async with aiosqlite.connect(common_db_path()) as owned_db:
        await owned_db.execute("PRAGMA foreign_keys = ON")
        await _load_from(owned_db)
    return mapping


def resolve_caliber_catalog_subject(
    caliber_name: str,
    *,
    catalog_names: set[str],
    caliber_catalog_map: dict[str, str],
) -> str:
    raw_name = text(caliber_name)
    if not raw_name:
        return ""
    if raw_name in catalog_names:
        return raw_name
    mapped = text(caliber_catalog_map.get(raw_name, ""))
    if mapped and mapped in catalog_names:
        return mapped
    return raw_name
