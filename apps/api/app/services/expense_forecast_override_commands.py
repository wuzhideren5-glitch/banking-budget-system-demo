"""Manual override commands for expense forecast values."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Protocol

from app.core.config import settings
from app.core.database import get_pool
from app.services.expense_forecast_write_commands import (
    delete_month_forecast_override,
    upsert_month_forecast_override,
    upsert_month_forecast_value,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


async def _upsert_month_forecast_override_mysql(
    cur: Any,
    *,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    rule_id: int | None,
    system_value: float,
    override_value: float,
    override_reason: str | None,
    now: str,
) -> None:
    await cur.execute(
        """
        INSERT INTO expense_forecast_override(
          forecast_year, forecast_version, owner_name, subject_id, month, rule_id,
          system_value, override_value, override_reason, operator_name, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '', %s, %s)
        ON DUPLICATE KEY UPDATE
          rule_id = %s,
          system_value = %s,
          override_value = %s,
          override_reason = %s,
          updated_at = %s
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
            rule_id,
            float(system_value),
            float(override_value),
            override_reason,
            now,
        ),
    )


async def _delete_month_forecast_override_mysql(
    cur: Any,
    *,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
) -> None:
    await cur.execute(
        """
        DELETE FROM expense_forecast_override
        WHERE forecast_year = %s AND forecast_version = %s AND owner_name = %s AND subject_id = %s AND month = %s
        """,
        (int(year), forecast_version, owner_name, int(subject_id), int(month)),
    )


class ExpenseForecastOverrideWorkflowError(ValueError):
    """Raised when a manual override cannot be applied under current rule state."""


@dataclass(frozen=True)
class ExpenseForecastOverrideWorkflowResult:
    actual_cutoff_month: int


class ExpenseForecastOverrideSource(Protocol):
    async def load_rule_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int], dict[str, Any]]:
        ...

    async def load_calc_result_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], dict[str, Any]]:
        ...

    async def load_actual_cutoff_month(self, year: int) -> int:
        ...


async def save_expense_forecast_override(
    *,
    db_path: str | Path,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    rule_id: int | None,
    system_value: float,
    override_value: float,
    override_reason: str | None,
    now: str,
) -> None:
    path = Path(db_path)
    if _uses_mysql_path(path):
        async with get_pool().acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cur:
                    await _upsert_month_forecast_override_mysql(
                        cur,
                        year=year,
                        forecast_version=forecast_version,
                        owner_name=owner_name,
                        subject_id=subject_id,
                        month=month,
                        rule_id=rule_id,
                        system_value=system_value,
                        override_value=override_value,
                        override_reason=_text(override_reason) or None,
                        now=now,
                    )
                    await _upsert_month_forecast_value_mysql(
                        cur,
                        year=year,
                        forecast_version=forecast_version,
                        scope_type="owner",
                        scope_value=owner_name,
                        subject_id=subject_id,
                        month=month,
                        value=override_value,
                        now=now,
                    )
                await conn.commit()
                return
            except Exception:
                await conn.rollback()
                raise

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        db = _SqliteExecutor(conn)
        await upsert_month_forecast_override(
            db,
            year=year,
            forecast_version=forecast_version,
            owner_name=owner_name,
            subject_id=subject_id,
            month=month,
            rule_id=rule_id,
            system_value=system_value,
            override_value=override_value,
            override_reason=_text(override_reason) or None,
            now=now,
        )
        await upsert_month_forecast_value(
            db,
            year=year,
            forecast_version=forecast_version,
            scope_type="owner",
            scope_value=owner_name,
            subject_id=subject_id,
            month=month,
            value=override_value,
            now=now,
        )
        conn.commit()


async def save_expense_forecast_override_with_rule_check(
    *,
    db_path: str | Path,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    override_value: float,
    override_reason: str | None,
    source: ExpenseForecastOverrideSource,
    now: str,
) -> ExpenseForecastOverrideWorkflowResult:
    normalized_owner = _text(owner_name)
    normalized_subject_id = int(subject_id)
    normalized_month = int(month)
    owner_names = [normalized_owner]
    rule_map = await source.load_rule_map(
        year=int(year),
        forecast_version=forecast_version,
        owner_names=owner_names,
    )
    owner_rule = rule_map.get((normalized_owner, normalized_subject_id))
    if owner_rule is None or not bool(owner_rule.get("allow_manual_override")):
        raise ExpenseForecastOverrideWorkflowError("当前规则不允许人工覆盖")
    calc_map = await source.load_calc_result_map(
        year=int(year),
        forecast_version=forecast_version,
        owner_names=owner_names,
    )
    system_value = float(
        calc_map.get((normalized_owner, normalized_subject_id, normalized_month), {}).get("calc_value", 0.0)
    )
    await save_expense_forecast_override(
        db_path=db_path,
        year=int(year),
        forecast_version=forecast_version,
        owner_name=normalized_owner,
        subject_id=normalized_subject_id,
        month=normalized_month,
        rule_id=int(owner_rule["id"]),
        system_value=system_value,
        override_value=float(override_value),
        override_reason=override_reason,
        now=now,
    )
    return ExpenseForecastOverrideWorkflowResult(
        actual_cutoff_month=await source.load_actual_cutoff_month(int(year)),
    )


async def delete_expense_forecast_override(
    *,
    db_path: str | Path,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    restored_value: float,
    now: str,
) -> None:
    path = Path(db_path)
    if _uses_mysql_path(path):
        async with get_pool().acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cur:
                    await _delete_month_forecast_override_mysql(
                        cur,
                        year=year,
                        forecast_version=forecast_version,
                        owner_name=owner_name,
                        subject_id=subject_id,
                        month=month,
                    )
                    await _upsert_month_forecast_value_mysql(
                        cur,
                        year=year,
                        forecast_version=forecast_version,
                        scope_type="owner",
                        scope_value=owner_name,
                        subject_id=subject_id,
                        month=month,
                        value=restored_value,
                        now=now,
                    )
                await conn.commit()
                return
            except Exception:
                await conn.rollback()
                raise

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        db = _SqliteExecutor(conn)
        await delete_month_forecast_override(
            db,
            year=year,
            forecast_version=forecast_version,
            owner_name=owner_name,
            subject_id=subject_id,
            month=month,
        )
        await upsert_month_forecast_value(
            db,
            year=year,
            forecast_version=forecast_version,
            scope_type="owner",
            scope_value=owner_name,
            subject_id=subject_id,
            month=month,
            value=restored_value,
            now=now,
        )
        conn.commit()


async def delete_expense_forecast_override_with_restore(
    *,
    db_path: str | Path,
    year: int,
    forecast_version: str,
    owner_name: str,
    subject_id: int,
    month: int,
    source: ExpenseForecastOverrideSource,
    now: str,
) -> None:
    normalized_owner = _text(owner_name)
    normalized_subject_id = int(subject_id)
    normalized_month = int(month)
    calc_map = await source.load_calc_result_map(
        year=int(year),
        forecast_version=forecast_version,
        owner_names=[normalized_owner],
    )
    restored_value = float(
        calc_map.get((normalized_owner, normalized_subject_id, normalized_month), {}).get("calc_value", 0.0)
    )
    await delete_expense_forecast_override(
        db_path=db_path,
        year=int(year),
        forecast_version=forecast_version,
        owner_name=normalized_owner,
        subject_id=normalized_subject_id,
        month=normalized_month,
        restored_value=restored_value,
        now=now,
    )
