"""Manual override commands for expense forecast values."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import app.core.aiosqlite_compat as aiosqlite
from app.services.expense_forecast_write_commands import (
    delete_month_forecast_override,
    upsert_month_forecast_override,
    upsert_month_forecast_value,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
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
        await db.commit()


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
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
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
        await db.commit()


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
