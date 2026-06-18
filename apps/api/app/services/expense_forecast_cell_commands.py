"""Cell-level write commands for the expense forecast table."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Protocol

from app.core.config import settings
from app.core.database import get_pool
from app.services.expense_forecast_data_context import build_expense_forecast_effective_manage_departments
from app.services.expense_forecast_write_commands import (
    delete_month_forecast_override,
    upsert_annual_forecast_value,
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


@dataclass(frozen=True)
class ExpenseForecastCellUpsertResult:
    mode: str


class ExpenseForecastCellWorkflowError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


@dataclass(frozen=True)
class ExpenseForecastCellWorkflowResult:
    actual_cutoff_month: int
    mode: str
    subject_name: str
    field_name: str
    field_label: str
    month: int | None
    recalculated: bool


class ExpenseForecastCellSource(Protocol):
    async def load_subject_lookup(self) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        ...

    async def load_manage_department_map(self) -> dict[str, str]:
        ...

    async def load_actual_cutoff_month(self, year: int) -> int:
        ...

    async def load_rule_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int], dict[str, Any]]:
        ...

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


def _field_label(field_name: str, month: int | None = None) -> str:
    if field_name == "month_forecast":
        return f"M{int(month or 0)}"
    if field_name == "business_submission":
        return "业务报送"
    return "资划建议"


async def upsert_expense_forecast_cell_value(
    *,
    db_path: str | Path,
    year: int,
    forecast_version: str,
    scope_type: str,
    scope_value: str,
    subject_id: int,
    field_name: str,
    month: int | None,
    value: float,
    now: str,
) -> ExpenseForecastCellUpsertResult:
    path = Path(db_path)
    if _uses_mysql_path(path):
        async with get_pool().acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cur:
                    if field_name == "month_forecast":
                        normalized_month = int(month or 0)
                        await _upsert_month_forecast_value_mysql(
                            cur,
                            year=year,
                            forecast_version=forecast_version,
                            scope_type=scope_type,
                            scope_value=scope_value,
                            subject_id=subject_id,
                            month=normalized_month,
                            value=value,
                            now=now,
                        )
                        await _delete_month_forecast_override_mysql(
                            cur,
                            year=year,
                            forecast_version=forecast_version,
                            owner_name=scope_value,
                            subject_id=subject_id,
                            month=normalized_month,
                        )
                        mode = "manual"
                    else:
                        await _upsert_annual_forecast_value_mysql(
                            cur,
                            year=year,
                            forecast_version=forecast_version,
                            scope_type=scope_type,
                            scope_value=scope_value,
                            subject_id=subject_id,
                            field_name=field_name,
                            value=value,
                            now=now,
                        )
                        mode = "annual"
                await conn.commit()
                return ExpenseForecastCellUpsertResult(mode=mode)
            except Exception:
                await conn.rollback()
                raise

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        db = _SqliteExecutor(conn)
        if field_name == "month_forecast":
            normalized_month = int(month or 0)
            await upsert_month_forecast_value(
                db,
                year=year,
                forecast_version=forecast_version,
                scope_type=scope_type,
                scope_value=scope_value,
                subject_id=subject_id,
                month=normalized_month,
                value=value,
                now=now,
            )
            await delete_month_forecast_override(
                db,
                year=year,
                forecast_version=forecast_version,
                owner_name=scope_value,
                subject_id=subject_id,
                month=normalized_month,
            )
            mode = "manual"
        else:
            await upsert_annual_forecast_value(
                db,
                year=year,
                forecast_version=forecast_version,
                scope_type=scope_type,
                scope_value=scope_value,
                subject_id=subject_id,
                field_name=field_name,
                value=value,
                now=now,
            )
            mode = "annual"
        conn.commit()
    return ExpenseForecastCellUpsertResult(mode=mode)


async def upsert_expense_forecast_cell_with_validation(
    *,
    db_path: str | Path,
    year: int,
    forecast_version: str,
    scope_type: str,
    scope_value: str,
    subject_id: int,
    field_name: str,
    month: int | None,
    value: float,
    source: ExpenseForecastCellSource,
    now: str,
) -> ExpenseForecastCellWorkflowResult:
    normalized_scope_type = _text(scope_type)
    if normalized_scope_type != "owner":
        raise ExpenseForecastCellWorkflowError("费用预估仅支持在费用归属部门口径下录入")

    normalized_owner = _text(scope_value)
    normalized_year = int(year)
    normalized_subject_id = int(subject_id)
    normalized_version = _text(forecast_version)
    normalized_field_name = _text(field_name) or "month_forecast"

    by_id, _by_name = await source.load_subject_lookup()
    subject = by_id.get(normalized_subject_id)
    if not subject:
        raise ExpenseForecastCellWorkflowError("预算科目不存在", status_code=404)
    if not bool(subject["is_leaf"]) or subject.get("formula_text"):
        raise ExpenseForecastCellWorkflowError("当前预算科目不可录入预估")

    manage_department_map = await source.load_manage_department_map()
    effective_manage_by_id, _effective_manage_by_name = build_expense_forecast_effective_manage_departments(
        list(by_id.values()),
        manage_department_map,
    )
    normalized_manage_department = effective_manage_by_id.get(normalized_subject_id, "")
    if normalized_manage_department and normalized_manage_department != normalized_owner:
        raise ExpenseForecastCellWorkflowError(f"该预算科目仅归口管理部门“{normalized_manage_department}”可录入")

    actual_cutoff_month = await source.load_actual_cutoff_month(normalized_year)
    rule_map = await source.load_rule_map(
        year=normalized_year,
        forecast_version=normalized_version,
        owner_names=[normalized_owner],
    )
    owner_rule = rule_map.get((normalized_owner, normalized_subject_id))

    normalized_month: int | None = None
    if normalized_field_name == "month_forecast":
        if month is None or int(month) < 1 or int(month) > 12:
            raise ExpenseForecastCellWorkflowError("月份必须在 1 到 12 之间")
        normalized_month = int(month)
        if normalized_month <= actual_cutoff_month:
            raise ExpenseForecastCellWorkflowError("该月份已有实际数，不允许修改预估")
    elif normalized_field_name not in {"business_submission", "capital_advice"}:
        raise ExpenseForecastCellWorkflowError("仅支持录入月度预估、业务报送或资划建议")

    upsert_result = await upsert_expense_forecast_cell_value(
        db_path=db_path,
        year=normalized_year,
        forecast_version=normalized_version,
        scope_type=normalized_scope_type,
        scope_value=normalized_owner,
        subject_id=normalized_subject_id,
        field_name=normalized_field_name,
        month=normalized_month,
        value=float(value),
        now=now,
    )

    recalculated = False
    if (
        normalized_field_name in {"business_submission", "capital_advice"}
        and owner_rule
        and bool(owner_rule.get("auto_refresh_enabled"))
    ):
        await source.recalculate_rules(
            year=normalized_year,
            forecast_version=normalized_version,
            owner_name=normalized_owner,
            subject_id=normalized_subject_id,
        )
        recalculated = True

    await source.write_operation_log(
        action_type="UPSERT",
        action_desc=f"写入费用预测 {_text(subject['subject_name'])} {_field_label(normalized_field_name, normalized_month)}",
        target_table="expense_forecast_entry"
        if normalized_field_name == "month_forecast"
        else "expense_forecast_annual_entry",
        affected_rows=1,
        after_data={
            "year": normalized_year,
            "forecast_version": normalized_version,
            "scope_type": normalized_scope_type,
            "scope_value": normalized_owner,
            "subject_id": normalized_subject_id,
            "field_name": normalized_field_name,
            "month": normalized_month,
            "value": float(value),
        },
    )

    return ExpenseForecastCellWorkflowResult(
        actual_cutoff_month=actual_cutoff_month,
        mode=upsert_result.mode,
        subject_name=_text(subject["subject_name"]),
        field_name=normalized_field_name,
        field_label=_field_label(normalized_field_name, normalized_month),
        month=normalized_month,
        recalculated=recalculated,
    )
