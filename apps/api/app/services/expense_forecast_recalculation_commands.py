"""Persistence commands for expense forecast rule recalculation results."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
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


class _SqliteExecutor:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    async def execute(self, sql: str, parameters: object = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, parameters)  # type: ignore[arg-type]


def _uses_mysql_path(path: Path | str) -> bool:
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
    return candidate.name == "common.db"


async def _upsert_month_forecast_calc_result_mysql(
    cur: Any,
    *,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    rule_id: int,
    calc_value: float,
    calc_basis_json: str,
    now: str,
) -> None:
    await cur.execute(
        """
        INSERT INTO expense_forecast_calc_result(
          forecast_year, forecast_version, owner_name, subject_id, month, rule_id,
          calc_value, calc_basis_json, calc_status, calc_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ok', %s)
        ON DUPLICATE KEY UPDATE
          rule_id = %s,
          calc_value = %s,
          calc_basis_json = %s,
          calc_status = 'ok',
          calc_time = %s
        """,
        (
            int(year),
            forecast_version,
            owner_name,
            int(subject_id),
            int(month),
            int(rule_id),
            float(calc_value),
            calc_basis_json,
            now,
            int(rule_id),
            float(calc_value),
            calc_basis_json,
            now,
        ),
    )


async def _upsert_month_forecast_value_mysql(
    cur: Any,
    *,
    year: int,
    forecast_version: str,
    scope_type: str,
    scope_value: str,
    subject_id: int,
    month: int,
    value: float,
    now: str,
) -> None:
    await cur.execute(
        """
        INSERT INTO expense_forecast_entry(
          forecast_year, forecast_version, scope_type, scope_value, subject_id, month,
          forecast_value, create_time, update_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          forecast_value = %s,
          update_time = %s
        """,
        (
            int(year),
            forecast_version,
            scope_type,
            scope_value,
            int(subject_id),
            int(month),
            float(value),
            now,
            now,
            float(value),
            now,
        ),
    )


async def _update_month_forecast_override_system_value_mysql(
    cur: Any,
    *,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    system_value: float,
    now: str,
) -> None:
    await cur.execute(
        """
        UPDATE expense_forecast_override
        SET system_value = %s, updated_at = %s
        WHERE forecast_year = %s AND forecast_version = %s AND owner_name = %s AND subject_id = %s AND month = %s
        """,
        (
            float(system_value),
            now,
            int(year),
            forecast_version,
            owner_name,
            int(subject_id),
            int(month),
        ),
    )


async def _save_expense_forecast_recalculation_results_mysql(
    *,
    year: int,
    forecast_version: str,
    rows: list[ExpenseForecastRecalculatedMonth],
    now: str,
) -> int:
    async with get_pool().acquire() as conn:
        await conn.begin()
        try:
            updated_cells = 0
            async with conn.cursor() as cur:
                for row in rows:
                    await _upsert_month_forecast_calc_result_mysql(
                        cur,
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
                    await _upsert_month_forecast_value_mysql(
                        cur,
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
                        await _update_month_forecast_override_system_value_mysql(
                            cur,
                            year=year,
                            forecast_version=forecast_version,
                            owner_name=row.owner_name,
                            subject_id=row.subject_id,
                            month=row.month,
                            system_value=row.calc_value,
                            now=now,
                        )
                    updated_cells += 1
            await conn.commit()
            return updated_cells
        except Exception:
            await conn.rollback()
            raise


async def save_expense_forecast_recalculation_results(
    *,
    db_path: str | Path,
    year: int,
    forecast_version: str,
    rows: list[ExpenseForecastRecalculatedMonth],
    now: str,
) -> int:
    path = Path(db_path)
    if _uses_mysql_path(path):
        return await _save_expense_forecast_recalculation_results_mysql(
            year=year,
            forecast_version=forecast_version,
            rows=rows,
            now=now,
        )

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        db = _SqliteExecutor(conn)
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
        conn.commit()
    return updated_cells
