"""Department-expense master-data synchronization helpers."""
from __future__ import annotations

from typing import Any


async def _table_exists(db: Any, table_name: str) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return bool(await cur.fetchone())


async def _execute_change_count(
    db: Any,
    sql: str,
    params: tuple[Any, ...],
) -> int:
    cur = await db.execute(sql, params)
    return max(0, int(getattr(cur, "rowcount", 0) or 0))


async def sync_expense_dept_name_refs(
    db: Any,
    *,
    dept_level: int,
    old_name: str,
    new_name: str,
) -> dict[str, int]:
    """Propagate department renames to expense private facts and read models."""
    old_text = str(old_name or "").strip()
    new_text = str(new_name or "").strip()
    if not old_text or not new_text or old_text == new_text:
        return {}

    sync_counts: dict[str, int] = {}

    async def track(
        table_name: str,
        sync_key: str,
        sql: str,
        params: tuple[Any, ...],
    ) -> None:
        if not await _table_exists(db, table_name):
            return
        changed = await _execute_change_count(db, sql, params)
        if changed > 0:
            sync_counts[sync_key] = changed

    if dept_level == 1:
        await track(
            "expense_framework_budget_department",
            "expense_framework_budget_department.group_name",
            "UPDATE expense_framework_budget_department SET group_name = ? WHERE group_name = ?",
            (new_text, old_text),
        )
        await track(
            "expense_framework_product_department",
            "expense_framework_product_department.group_name",
            "UPDATE expense_framework_product_department SET group_name = ? WHERE group_name = ?",
            (new_text, old_text),
        )
        await track(
            "expense_forecast_entry",
            "expense_forecast_entry.scope_value[group]",
            "UPDATE expense_forecast_entry SET scope_value = ? WHERE scope_type = 'group' AND scope_value = ?",
            (new_text, old_text),
        )
        await track(
            "expense_forecast_annual_entry",
            "expense_forecast_annual_entry.scope_value[group]",
            "UPDATE expense_forecast_annual_entry SET scope_value = ? WHERE scope_type = 'group' AND scope_value = ?",
            (new_text, old_text),
        )
        return sync_counts

    if dept_level == 2:
        await track(
            "expense_framework_budget_department",
            "expense_framework_budget_department.owner_name",
            """
            UPDATE expense_framework_budget_department
            SET owner_name = ?,
                budget_department = CASE WHEN budget_department = ? THEN ? ELSE budget_department END
            WHERE owner_name = ?
            """,
            (new_text, old_text, new_text, old_text),
        )
        await track(
            "expense_framework_product_department",
            "expense_framework_product_department.owner_name",
            """
            UPDATE expense_framework_product_department
            SET owner_name = ?,
                product_department = CASE WHEN product_department = ? THEN ? ELSE product_department END
            WHERE owner_name = ?
            """,
            (new_text, old_text, new_text, old_text),
        )
        await track(
            "expense_forecast_entry",
            "expense_forecast_entry.scope_value[owner]",
            "UPDATE expense_forecast_entry SET scope_value = ? WHERE scope_type = 'owner' AND scope_value = ?",
            (new_text, old_text),
        )
        await track(
            "expense_forecast_annual_entry",
            "expense_forecast_annual_entry.scope_value[owner]",
            "UPDATE expense_forecast_annual_entry SET scope_value = ? WHERE scope_type = 'owner' AND scope_value = ?",
            (new_text, old_text),
        )
        await track(
            "expense_actual_detail_raw",
            "expense_actual_detail_raw.owner_name_mapped",
            "UPDATE expense_actual_detail_raw SET owner_name_mapped = ? WHERE owner_name_mapped = ?",
            (new_text, old_text),
        )
    return sync_counts
