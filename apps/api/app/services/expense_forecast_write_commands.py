"""Shared SQLite write commands for the expense forecast table."""
from __future__ import annotations

from typing import Protocol


class AsyncSqlExecutor(Protocol):
    async def execute(self, sql: str, parameters: object = ...) -> object: ...


async def upsert_month_forecast_value(
    db: AsyncSqlExecutor,
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
    await db.execute(
        """
        INSERT INTO expense_forecast_entry(
          forecast_year, forecast_version, scope_type, scope_value, subject_id, month,
          forecast_value, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(forecast_year, forecast_version, scope_type, scope_value, subject_id, month)
        DO UPDATE SET forecast_value = excluded.forecast_value, update_time = excluded.update_time
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
        ),
    )


async def delete_month_forecast_override(
    db: AsyncSqlExecutor,
    *,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
) -> None:
    await db.execute(
        """
        DELETE FROM expense_forecast_override
        WHERE forecast_year = ? AND forecast_version = ? AND owner_name = ? AND subject_id = ? AND month = ?
        """,
        (int(year), forecast_version, owner_name, int(subject_id), int(month)),
    )


async def upsert_month_forecast_override(
    db: AsyncSqlExecutor,
    *,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    rule_id: int | None,
    system_value: float,
    override_value: float,
    now: str,
    override_reason: str | None = "Excel导入覆盖",
) -> None:
    await db.execute(
        """
        INSERT INTO expense_forecast_override(
          forecast_year, forecast_version, owner_name, subject_id, month, rule_id,
          system_value, override_value, override_reason, operator_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
        ON CONFLICT(forecast_year, forecast_version, owner_name, subject_id, month)
        DO UPDATE SET
          rule_id = excluded.rule_id,
          system_value = excluded.system_value,
          override_value = excluded.override_value,
          override_reason = excluded.override_reason,
          updated_at = excluded.updated_at
        """,
        (
            int(year),
            forecast_version,
            owner_name,
            int(subject_id),
            int(month),
            rule_id,
            float(system_value),
            float(override_value),
            override_reason,
            now,
            now,
        ),
    )


async def upsert_annual_forecast_value(
    db: AsyncSqlExecutor,
    *,
    year: int,
    forecast_version: str,
    scope_type: str,
    scope_value: str,
    subject_id: int,
    field_name: str,
    value: float,
    now: str,
) -> None:
    await db.execute(
        """
        INSERT INTO expense_forecast_annual_entry(
          forecast_year, forecast_version, scope_type, scope_value, subject_id, field_name,
          field_value, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(forecast_year, forecast_version, scope_type, scope_value, subject_id, field_name)
        DO UPDATE SET field_value = excluded.field_value, update_time = excluded.update_time
        """,
        (
            int(year),
            forecast_version,
            scope_type,
            scope_value,
            int(subject_id),
            field_name,
            float(value),
            now,
            now,
        ),
    )


async def upsert_month_forecast_calc_result(
    db: AsyncSqlExecutor,
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
    await db.execute(
        """
        INSERT INTO expense_forecast_calc_result(
          forecast_year, forecast_version, owner_name, subject_id, month, rule_id,
          calc_value, calc_basis_json, calc_status, calc_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok', ?)
        ON CONFLICT(forecast_year, forecast_version, owner_name, subject_id, month)
        DO UPDATE SET
          rule_id = excluded.rule_id,
          calc_value = excluded.calc_value,
          calc_basis_json = excluded.calc_basis_json,
          calc_status = excluded.calc_status,
          calc_time = excluded.calc_time
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
        ),
    )


async def update_month_forecast_override_system_value(
    db: AsyncSqlExecutor,
    *,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    system_value: float,
    now: str,
) -> None:
    await db.execute(
        """
        UPDATE expense_forecast_override
        SET system_value = ?, updated_at = ?
        WHERE forecast_year = ? AND forecast_version = ? AND owner_name = ? AND subject_id = ? AND month = ?
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
