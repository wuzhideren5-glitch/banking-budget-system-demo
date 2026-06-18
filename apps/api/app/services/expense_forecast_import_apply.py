"""Database write commands for expense forecast imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Protocol

from app.core.config import settings
from app.core.database import get_pool
from app.services.expense_forecast_write_commands import (
    upsert_annual_forecast_value,
    upsert_month_forecast_override,
    upsert_month_forecast_value,
)


@dataclass
class ExpenseForecastImportApplyResult:
    inserted_cells: int = 0
    updated_cells: int = 0
    skipped_cells: int = 0
    recalc_targets: list[tuple[str, int]] = field(default_factory=list)


@dataclass(frozen=True)
class ExpenseForecastImportApplyWorkflowResult:
    inserted_cells: int
    updated_cells: int
    skipped_cells: int
    error_cells: int
    recalc_targets: list[tuple[str, int]]

    @property
    def affected_cells(self) -> int:
        return self.inserted_cells + self.updated_cells


class ExpenseForecastImportApplySource(Protocol):
    async def recalculate_rules(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_name: str,
        subject_id: int,
    ) -> tuple[int, int]:
        ...

    async def write_operation_log(self, **kwargs) -> None:
        ...


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
    now: str,
) -> None:
    await cur.execute(
        """
        INSERT INTO expense_forecast_override(
          forecast_year, forecast_version, owner_name, subject_id, month, rule_id,
          system_value, override_value, override_reason, operator_name, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Excel导入覆盖', '', %s, %s)
        ON DUPLICATE KEY UPDATE
          rule_id = %s,
          system_value = %s,
          override_value = %s,
          override_reason = 'Excel导入覆盖',
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
            now,
            now,
            rule_id,
            float(system_value),
            float(override_value),
            now,
        ),
    )


async def _upsert_annual_forecast_value_mysql(
    cur: Any,
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
    await cur.execute(
        """
        INSERT INTO expense_forecast_annual_entry(
          forecast_year, forecast_version, scope_type, scope_value, subject_id, field_name,
          field_value, create_time, update_time
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          field_value = %s,
          update_time = %s
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
            float(value),
            now,
        ),
    )


async def _apply_expense_forecast_import_rows_mysql(
    *,
    rows: list[dict[str, Any]],
    year: int,
    forecast_version: str,
    scope_type: str,
    now: str,
) -> ExpenseForecastImportApplyResult:
    inserted = 0
    updated = 0
    skipped = 0
    recalc_targets: set[tuple[str, int]] = set()

    async with get_pool().acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor() as cur:
                for row in rows:
                    action = _text(row["action"])
                    if action == "skipped":
                        skipped += 1
                        continue
                    if action not in {"inserted", "updated"}:
                        continue

                    owner_name = _text(row.get("scope_value"))
                    subject_id = int(row["subject_id"])
                    field_name = _text(row["field_name"])

                    if field_name == "month_forecast":
                        month = int(row["month"])
                        if _text(row.get("rule_scheme")) == "MANUAL":
                            await _upsert_month_forecast_value_mysql(
                                cur,
                                year=year,
                                forecast_version=forecast_version,
                                scope_type=scope_type,
                                scope_value=owner_name,
                                subject_id=subject_id,
                                month=month,
                                value=float(row["value"]),
                                now=now,
                            )
                        else:
                            await _upsert_month_forecast_override_mysql(
                                cur,
                                year=year,
                                forecast_version=forecast_version,
                                owner_name=owner_name,
                                subject_id=subject_id,
                                month=month,
                                rule_id=int(row.get("rule_id") or 0) or None,
                                system_value=float(row.get("system_value") or 0.0),
                                override_value=float(row["value"]),
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
                                value=float(row["value"]),
                                now=now,
                            )
                    else:
                        await _upsert_annual_forecast_value_mysql(
                            cur,
                            year=year,
                            forecast_version=forecast_version,
                            scope_type=scope_type,
                            scope_value=owner_name,
                            subject_id=subject_id,
                            field_name=field_name,
                            value=float(row["value"]),
                            now=now,
                        )
                        recalc_targets.add((owner_name, subject_id))

                    if action == "inserted":
                        inserted += 1
                    else:
                        updated += 1
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    return ExpenseForecastImportApplyResult(
        inserted_cells=inserted,
        updated_cells=updated,
        skipped_cells=skipped,
        recalc_targets=sorted(recalc_targets),
    )


async def apply_expense_forecast_import_rows(
    *,
    db_path: str | Path,
    rows: list[dict[str, Any]],
    year: int,
    forecast_version: str,
    scope_type: str,
    now: str,
) -> ExpenseForecastImportApplyResult:
    path = Path(db_path)
    if _uses_mysql_path(path):
        return await _apply_expense_forecast_import_rows_mysql(
            rows=rows,
            year=year,
            forecast_version=forecast_version,
            scope_type=scope_type,
            now=now,
        )

    inserted = 0
    updated = 0
    skipped = 0
    recalc_targets: set[tuple[str, int]] = set()

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        db = _SqliteExecutor(conn)
        for row in rows:
            action = _text(row["action"])
            if action == "skipped":
                skipped += 1
                continue
            if action not in {"inserted", "updated"}:
                continue

            owner_name = _text(row.get("scope_value"))
            subject_id = int(row["subject_id"])
            field_name = _text(row["field_name"])

            if field_name == "month_forecast":
                month = int(row["month"])
                if _text(row.get("rule_scheme")) == "MANUAL":
                    await upsert_month_forecast_value(
                        db,
                        year=year,
                        forecast_version=forecast_version,
                        scope_type=scope_type,
                        scope_value=owner_name,
                        subject_id=subject_id,
                        month=month,
                        value=float(row["value"]),
                        now=now,
                    )
                else:
                    await upsert_month_forecast_override(
                        db,
                        year=year,
                        forecast_version=forecast_version,
                        owner_name=owner_name,
                        subject_id=subject_id,
                        month=month,
                        rule_id=int(row.get("rule_id") or 0) or None,
                        system_value=float(row.get("system_value") or 0.0),
                        override_value=float(row["value"]),
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
                        value=float(row["value"]),
                        now=now,
                    )
            else:
                await upsert_annual_forecast_value(
                    db,
                    year=year,
                    forecast_version=forecast_version,
                    scope_type=scope_type,
                    scope_value=owner_name,
                    subject_id=subject_id,
                    field_name=field_name,
                    value=float(row["value"]),
                    now=now,
                )
                recalc_targets.add((owner_name, subject_id))

            if action == "inserted":
                inserted += 1
            else:
                updated += 1
        conn.commit()

    return ExpenseForecastImportApplyResult(
        inserted_cells=inserted,
        updated_cells=updated,
        skipped_cells=skipped,
        recalc_targets=sorted(recalc_targets),
    )


async def apply_expense_forecast_import_rows_with_recalculation(
    *,
    db_path: str | Path,
    rows: list[dict[str, Any]],
    year: int,
    forecast_version: str,
    scope_type: str,
    scope_value: str,
    group_name: str,
    import_mode: str,
    skipped_cells: int,
    error_cells: int,
    source: ExpenseForecastImportApplySource,
    now: str,
) -> ExpenseForecastImportApplyWorkflowResult:
    result = await apply_expense_forecast_import_rows(
        db_path=db_path,
        rows=rows,
        year=year,
        forecast_version=forecast_version,
        scope_type=scope_type,
        now=now,
    )
    for owner_name, subject_id in result.recalc_targets:
        await source.recalculate_rules(
            year=year,
            forecast_version=forecast_version,
            owner_name=owner_name,
            subject_id=subject_id,
        )
    workflow_result = ExpenseForecastImportApplyWorkflowResult(
        inserted_cells=result.inserted_cells,
        updated_cells=result.updated_cells,
        skipped_cells=skipped_cells,
        error_cells=error_cells,
        recalc_targets=result.recalc_targets,
    )
    await source.write_operation_log(
        action_type="IMPORT",
        action_desc=f"导入费用预测 {workflow_result.affected_cells} 个单元格（{_text(import_mode)}）",
        target_table="expense_forecast_entry / expense_forecast_annual_entry",
        affected_rows=workflow_result.affected_cells,
        after_data={
            "year": int(year),
            "forecast_version": _text(forecast_version),
            "scope_type": _text(scope_type),
            "scope_value": _text(scope_value),
            "group_name": _text(group_name),
            "mode": _text(import_mode),
            "inserted_cells": workflow_result.inserted_cells,
            "updated_cells": workflow_result.updated_cells,
            "skipped_cells": workflow_result.skipped_cells,
            "error_cells": workflow_result.error_cells,
        },
    )
    return workflow_result
