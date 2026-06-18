"""Persistence commands for expense forecast rule definitions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Mapping

from app.core.config import settings
from app.core.database import get_pool


@dataclass(frozen=True)
class SavedExpenseForecastRuleDefinition:
    rule_id: int


class ExpenseForecastRuleDeleteNotFound(RuntimeError):
    """Raised when a rule delete command targets a missing rule."""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _flag(value: Any) -> int:
    return 1 if bool(value) else 0


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


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


def _normalized_rule_values(rule: Mapping[str, Any], now: str, *, include_created_at: bool) -> tuple[Any, ...]:
    values: tuple[Any, ...] = (
        int(_get(rule, "forecast_year")),
        _text(_get(rule, "forecast_version")),
        _text(_get(rule, "owner_name")),
        int(_get(rule, "subject_id")),
        _text(_get(rule, "scheme_code")),
        _flag(_get(rule, "enabled", True)),
        _flag(_get(rule, "allow_manual_override", False)),
        _flag(_get(rule, "auto_refresh_enabled", True)),
        _flag(_get(rule, "manual_recalc_enabled", True)),
        _text(_get(rule, "metric_source_priority")) or "metric_first",
        int(_get(rule, "effective_from_month", 1)),
        int(_get(rule, "effective_to_month", 12)),
        int(_get(rule, "priority", 100)),
        _text(_get(rule, "remark")) or None,
    )
    if include_created_at:
        return values + (now, now)
    return values + (now,)


async def _save_expense_forecast_rule_definition_mysql(
    *,
    rule: Mapping[str, Any],
    rule_id: int | None,
    now: str,
) -> int:
    async with get_pool().acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor() as cur:
                if rule_id is None:
                    await cur.execute(
                        _mysql_sql(
                            """
                            INSERT INTO expense_forecast_rule(
                              forecast_year, forecast_version, owner_name, subject_id, scheme_code,
                              enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
                              metric_source_priority, effective_from_month, effective_to_month, priority,
                              remark, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """
                        ),
                        _normalized_rule_values(rule, now, include_created_at=True),
                    )
                    rule_id = int(cur.lastrowid)
                else:
                    await cur.execute(
                        _mysql_sql(
                            """
                            UPDATE expense_forecast_rule
                            SET forecast_year = ?, forecast_version = ?, owner_name = ?, subject_id = ?, scheme_code = ?,
                                enabled = ?, allow_manual_override = ?, auto_refresh_enabled = ?, manual_recalc_enabled = ?,
                                metric_source_priority = ?, effective_from_month = ?, effective_to_month = ?, priority = ?,
                                remark = ?, updated_at = ?
                            WHERE id = ?
                            """
                        ),
                        _normalized_rule_values(rule, now, include_created_at=False) + (int(rule_id),),
                    )
                    await cur.execute(
                        "DELETE FROM expense_forecast_rule_param WHERE rule_id = %s",
                        (int(rule_id),),
                    )
                    await cur.execute(
                        "DELETE FROM expense_forecast_rule_variable WHERE rule_id = %s",
                        (int(rule_id),),
                    )

                for item in list(_get(rule, "params", []) or []):
                    await cur.execute(
                        """
                        INSERT INTO expense_forecast_rule_param(rule_id, param_group, param_key, param_value, value_type)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            int(rule_id),
                            _text(_get(item, "param_group")) or "common",
                            _text(_get(item, "param_key")),
                            _get(item, "param_value"),
                            _text(_get(item, "value_type")) or "string",
                        ),
                    )
                for item in list(_get(rule, "variables", []) or []):
                    await cur.execute(
                        """
                        INSERT INTO expense_forecast_rule_variable(
                          rule_id, variable_code, variable_name, source_type, source_key, source_subkey, default_value, sort_order
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(rule_id),
                            _text(_get(item, "variable_code")),
                            _text(_get(item, "variable_name")) or None,
                            _text(_get(item, "source_type")),
                            _text(_get(item, "source_key")) or None,
                            _text(_get(item, "source_subkey")) or None,
                            _get(item, "default_value"),
                            int(_get(item, "sort_order", 0) or 0),
                        ),
                    )
            await conn.commit()
            return int(rule_id)
        except Exception:
            await conn.rollback()
            raise


async def _delete_expense_forecast_rule_definition_mysql(*, rule_id: int) -> bool:
    async with get_pool().acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM expense_forecast_rule WHERE id = %s",
                    (int(rule_id),),
                )
                deleted = int(cur.rowcount or 0) > 0
            await conn.commit()
            return deleted
        except Exception:
            await conn.rollback()
            raise


async def save_expense_forecast_rule_definition(
    *,
    db_path: str | Path,
    rule: Mapping[str, Any],
    rule_id: int | None,
    now: str,
) -> SavedExpenseForecastRuleDefinition:
    path = Path(db_path)
    if _uses_mysql_path(path):
        saved_rule_id = await _save_expense_forecast_rule_definition_mysql(
            rule=rule,
            rule_id=rule_id,
            now=now,
        )
        return SavedExpenseForecastRuleDefinition(rule_id=saved_rule_id)

    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        if rule_id is None:
            cur = db.execute(
                """
                INSERT INTO expense_forecast_rule(
                  forecast_year, forecast_version, owner_name, subject_id, scheme_code,
                  enabled, allow_manual_override, auto_refresh_enabled, manual_recalc_enabled,
                  metric_source_priority, effective_from_month, effective_to_month, priority,
                  remark, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _normalized_rule_values(rule, now, include_created_at=True),
            )
            rule_id = int(cur.lastrowid)
        else:
            db.execute(
                """
                UPDATE expense_forecast_rule
                SET forecast_year = ?, forecast_version = ?, owner_name = ?, subject_id = ?, scheme_code = ?,
                    enabled = ?, allow_manual_override = ?, auto_refresh_enabled = ?, manual_recalc_enabled = ?,
                    metric_source_priority = ?, effective_from_month = ?, effective_to_month = ?, priority = ?,
                    remark = ?, updated_at = ?
                WHERE id = ?
                """,
                _normalized_rule_values(rule, now, include_created_at=False) + (int(rule_id),),
            )
            db.execute("DELETE FROM expense_forecast_rule_param WHERE rule_id = ?", (int(rule_id),))
            db.execute("DELETE FROM expense_forecast_rule_variable WHERE rule_id = ?", (int(rule_id),))

        for item in list(_get(rule, "params", []) or []):
            db.execute(
                """
                INSERT INTO expense_forecast_rule_param(rule_id, param_group, param_key, param_value, value_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(rule_id),
                    _text(_get(item, "param_group")) or "common",
                    _text(_get(item, "param_key")),
                    _get(item, "param_value"),
                    _text(_get(item, "value_type")) or "string",
                ),
            )
        for item in list(_get(rule, "variables", []) or []):
            db.execute(
                """
                INSERT INTO expense_forecast_rule_variable(
                  rule_id, variable_code, variable_name, source_type, source_key, source_subkey, default_value, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(rule_id),
                    _text(_get(item, "variable_code")),
                    _text(_get(item, "variable_name")) or None,
                    _text(_get(item, "source_type")),
                    _text(_get(item, "source_key")) or None,
                    _text(_get(item, "source_subkey")) or None,
                    _get(item, "default_value"),
                    int(_get(item, "sort_order", 0) or 0),
                ),
            )
        db.commit()
    return SavedExpenseForecastRuleDefinition(rule_id=int(rule_id))


async def delete_expense_forecast_rule_definition(
    *,
    db_path: str | Path,
    rule_id: int,
) -> bool:
    path = Path(db_path)
    if _uses_mysql_path(path):
        return await _delete_expense_forecast_rule_definition_mysql(rule_id=rule_id)

    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        cur = db.execute(
            "DELETE FROM expense_forecast_rule WHERE id = ?",
            (int(rule_id),),
        )
        db.commit()
        return int(cur.rowcount or 0) > 0


async def delete_expense_forecast_rule_definition_or_raise(
    *,
    db_path: str | Path,
    rule_id: int,
) -> None:
    deleted = await delete_expense_forecast_rule_definition(
        db_path=db_path,
        rule_id=rule_id,
    )
    if not deleted:
        raise ExpenseForecastRuleDeleteNotFound("预测规则不存在")
