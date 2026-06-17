"""Persistence commands for expense forecast rule recalculation results."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import app.core.aiosqlite_compat as aiosqlite
from app.services.expense_forecast_write_commands import (
    update_month_forecast_override_system_value,
    upsert_month_forecast_calc_result,
    upsert_month_forecast_value,
)


@dataclass(frozen=True)
class ExpenseForecastRecalculatedMonth:
    owner_name: str
    subject_id: int
    month: int
    rule_id: int
    calc_value: float
    calc_basis_json: str
    has_override: bool = False
    override_value: float = 0.0


async def save_expense_forecast_recalculation_results(
    *,
    db_path: str | Path,
    year: int,
    forecast_version: str,
    rows: list[ExpenseForecastRecalculatedMonth],
    now: str,
) -> int:
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        updated_cells = 0
        for row in rows:
            await upsert_month_forecast_calc_result(
                db,
                year=year,
                forecast_version=forecast_version,
                owner_name=row.owner_name,
                subject_id=row.subject_id,
                month=row.month,
                rule_id=row.rule_id,
                calc_value=row.calc_value,
                calc_basis_json=row.calc_basis_json,
                now=now,
            )
            final_value = float(row.override_value) if row.has_override else float(row.calc_value)
            await upsert_month_forecast_value(
                db,
                year=year,
                forecast_version=forecast_version,
                scope_type="owner",
                scope_value=row.owner_name,
                subject_id=row.subject_id,
                month=row.month,
                value=final_value,
                now=now,
            )
            if row.has_override:
                await update_month_forecast_override_system_value(
                    db,
                    year=year,
                    forecast_version=forecast_version,
                    owner_name=row.owner_name,
                    subject_id=row.subject_id,
                    month=row.month,
                    system_value=row.calc_value,
                    now=now,
                )
            updated_cells += 1
        await db.commit()
    return updated_cells
