"""Read models for expense forecast rule state."""
from __future__ import annotations

from collections import defaultdict
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.services.runtime_metric_refs import load_org_product_metric_refs_by_runtime_ref_code_sync


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


async def _fetch_all_for_path(db_path: Path, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_all(_mysql_sql(sql), tuple(params))
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, tuple(params)).fetchall()


async def _fetch_one_for_path(db_path: Path, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> Any:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_one(_mysql_sql(sql), tuple(params))
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, tuple(params)).fetchone()


async def _load_org_product_metric_refs_for_path(db_path: Path) -> dict[str, list[str]]:
    if _uses_mysql_path(db_path):
        try:
            rows = await get_pool().fetch_all(
                """
                SELECT node_code, node_name, product_code, metric_table_name
                FROM data_account_metric_node
                WHERE is_active = 1
                  AND runtime_account_enabled = 1
                  AND COALESCE(product_code, '') <> ''
                  AND COALESCE(metric_table_name, '') <> ''
                """
            )
        except Exception:
            return {}
        refs_by_code: dict[str, list[str]] = {}
        seen: set[tuple[str, str]] = set()
        for row in rows:
            data_acct_code = _text(_row_value(row, "node_code", 0)).upper()
            metric_name = _text(_row_value(row, "node_name", 1))
            entity_code = _text(_row_value(row, "product_code", 2)).upper()
            table_name = _text(_row_value(row, "metric_table_name", 3))
            if not data_acct_code or not entity_code or not table_name:
                continue
            source_ref = f"{entity_code}:{table_name}:{data_acct_code}"
            label = f"{source_ref} {metric_name}".strip()
            dedupe_key = (data_acct_code, source_ref)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            refs_by_code.setdefault(data_acct_code, []).append(label)
        return {code: sorted(refs) for code, refs in refs_by_code.items()}
    with sqlite3.connect(db_path) as conn:
        return {
            _text(code).upper(): list(refs)
            for code, refs in load_org_product_metric_refs_by_runtime_ref_code_sync(conn).items()
        }


def _org_product_refs_for_variable(
    *,
    source_type: Any,
    source_key: Any,
    refs_by_runtime_ref_code: dict[str, list[str]],
) -> list[str]:
    if _text(source_type) != "metric_tree":
        return []
    code = _text(source_key).upper()
    if not code:
        return []
    direct = list(refs_by_runtime_ref_code.get(code, []))
    if direct:
        return direct
    if code.startswith("."):
        suffix = code
    elif "." in code:
        suffix = f".{code}"
    else:
        suffix = ""
    if not suffix:
        return []
    refs: list[str] = []
    for runtime_code, labels in sorted(refs_by_runtime_ref_code.items()):
        if _text(runtime_code).upper().endswith(suffix):
            refs.extend(labels)
    return refs


async def load_expense_forecast_rule_identity(
    db_path: Path,
    *,
    rule_id: int,
) -> dict[str, Any] | None:
    row = await _fetch_one_for_path(
        db_path,
        """
        SELECT forecast_year, forecast_version, owner_name, subject_id
        FROM expense_forecast_rule
        WHERE id = ?
        """,
        (int(rule_id),),
    )
    if row is None:
        return None
    return {
        "forecast_year": int(_row_value(row, "forecast_year", 0)),
        "forecast_version": _text(_row_value(row, "forecast_version", 1)),
        "owner_name": _text(_row_value(row, "owner_name", 2)),
        "subject_id": int(_row_value(row, "subject_id", 3)),
    }


async def load_expense_forecast_rule_rows(
    db_path: Path,
    *,
    year: int,
    forecast_version: str,
    owner_names: list[str] | None = None,
    subject_id: int | None = None,
    org_product_refs_by_runtime_ref_code: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    clauses = ["r.forecast_year = ?", "r.forecast_version = ?"]
    args: list[Any] = [year, forecast_version]
    if owner_names:
        placeholders = ",".join("?" for _ in owner_names)
        clauses.append(f"r.owner_name IN ({placeholders})")
        args.extend(owner_names)
    if subject_id is not None:
        clauses.append("r.subject_id = ?")
        args.append(int(subject_id))
    rows = await _fetch_all_for_path(
        db_path,
        f"""
        SELECT r.id, r.forecast_year, r.forecast_version, r.owner_name, r.subject_id,
               COALESCE(s.subject_name, '') AS subject_name,
               r.scheme_code, r.enabled, r.allow_manual_override, r.auto_refresh_enabled,
               r.manual_recalc_enabled, r.metric_source_priority, r.effective_from_month,
               r.effective_to_month, r.priority, r.remark, r.created_at, r.updated_at
        FROM expense_forecast_rule r
        LEFT JOIN budget_subject_catalog s ON s.id = r.subject_id
        WHERE {' AND '.join(clauses)}
        ORDER BY r.owner_name, r.priority, r.subject_id
        """,
        args,
    )
    if not rows:
        return []
    rule_ids = [int(_row_value(row, "id", 0)) for row in rows]
    placeholders = ",".join("?" for _ in rule_ids)
    param_rows = await _fetch_all_for_path(
        db_path,
        f"""
        SELECT rule_id, param_group, param_key, param_value, value_type
        FROM expense_forecast_rule_param
        WHERE rule_id IN ({placeholders})
        ORDER BY rule_id, id
        """,
        rule_ids,
    )
    variable_rows = await _fetch_all_for_path(
        db_path,
        f"""
        SELECT rule_id, variable_code, variable_name, source_type, source_key, source_subkey, default_value, sort_order
        FROM expense_forecast_rule_variable
        WHERE rule_id IN ({placeholders})
        ORDER BY rule_id, sort_order, id
        """,
        rule_ids,
    )
    if org_product_refs_by_runtime_ref_code is None:
        org_product_refs_by_runtime_ref_code = await _load_org_product_metric_refs_for_path(db_path)

    org_product_refs_by_runtime_ref_code = {
        _text(code).upper(): list(refs)
        for code, refs in (org_product_refs_by_runtime_ref_code or {}).items()
        if _text(code)
    }

    params_by_rule: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in param_rows:
        params_by_rule[int(_row_value(row, "rule_id", 0))].append(
            {
                "param_group": _text(_row_value(row, "param_group", 1)) or "common",
                "param_key": _text(_row_value(row, "param_key", 2)),
                "param_value": _text(_row_value(row, "param_value", 3)) if _row_value(row, "param_value", 3) is not None else None,
                "value_type": _text(_row_value(row, "value_type", 4)) or "string",
            }
        )

    vars_by_rule: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in variable_rows:
        default_value = _row_value(row, "default_value", 6)
        vars_by_rule[int(_row_value(row, "rule_id", 0))].append(
            {
                "variable_code": _text(_row_value(row, "variable_code", 1)),
                "variable_name": _text(_row_value(row, "variable_name", 2)) or None,
                "source_type": _text(_row_value(row, "source_type", 3)),
                "source_key": _text(_row_value(row, "source_key", 4)) or None,
                "source_subkey": _text(_row_value(row, "source_subkey", 5)) or None,
                "default_value": float(default_value) if default_value is not None else None,
                "sort_order": int(_row_value(row, "sort_order", 7) or 0),
                "org_product_refs": _org_product_refs_for_variable(
                    source_type=_row_value(row, "source_type", 3),
                    source_key=_row_value(row, "source_key", 4),
                    refs_by_runtime_ref_code=org_product_refs_by_runtime_ref_code,
                ),
            }
        )

    result: list[dict[str, Any]] = []
    for row in rows:
        rule_id = int(_row_value(row, "id", 0))
        result.append(
            {
                "id": rule_id,
                "forecast_year": int(_row_value(row, "forecast_year", 1)),
                "forecast_version": _text(_row_value(row, "forecast_version", 2)),
                "owner_name": _text(_row_value(row, "owner_name", 3)),
                "subject_id": int(_row_value(row, "subject_id", 4)),
                "subject_name": _text(_row_value(row, "subject_name", 5)),
                "scheme_code": _text(_row_value(row, "scheme_code", 6)),
                "enabled": bool(_row_value(row, "enabled", 7)),
                "allow_manual_override": bool(_row_value(row, "allow_manual_override", 8)),
                "auto_refresh_enabled": bool(_row_value(row, "auto_refresh_enabled", 9)),
                "manual_recalc_enabled": bool(_row_value(row, "manual_recalc_enabled", 10)),
                "metric_source_priority": _text(_row_value(row, "metric_source_priority", 11)) or "metric_first",
                "effective_from_month": int(_row_value(row, "effective_from_month", 12) or 1),
                "effective_to_month": int(_row_value(row, "effective_to_month", 13) or 12),
                "priority": int(_row_value(row, "priority", 14) or 100),
                "remark": _text(_row_value(row, "remark", 15)) or None,
                "created_at": _text(_row_value(row, "created_at", 16)),
                "updated_at": _text(_row_value(row, "updated_at", 17)),
                "params": params_by_rule.get(rule_id, []),
                "variables": vars_by_rule.get(rule_id, []),
            }
        )
    return result


def build_enabled_expense_forecast_rule_map(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (_text(row["owner_name"]), int(row["subject_id"])): row
        for row in rows
        if row.get("enabled")
    }


async def load_expense_forecast_calc_result_map(
    db_path: Path,
    *,
    year: int,
    forecast_version: str,
    owner_names: list[str],
) -> dict[tuple[str, int, int], dict[str, Any]]:
    if not owner_names:
        return {}
    placeholders = ",".join("?" for _ in owner_names)
    rows = await _fetch_all_for_path(
        db_path,
        f"""
        SELECT owner_name, subject_id, month, rule_id, calc_value, calc_basis_json, calc_status
        FROM expense_forecast_calc_result
        WHERE forecast_year = ? AND forecast_version = ?
          AND owner_name IN ({placeholders})
        """,
        (year, forecast_version, *owner_names),
    )
    return {
        (_text(_row_value(row, "owner_name", 0)), int(_row_value(row, "subject_id", 1)), int(_row_value(row, "month", 2))): {
            "rule_id": int(_row_value(row, "rule_id", 3)) if _row_value(row, "rule_id", 3) is not None else None,
            "calc_value": float(_row_value(row, "calc_value", 4) or 0.0),
            "calc_basis_json": _text(_row_value(row, "calc_basis_json", 5)) or None,
            "calc_status": _text(_row_value(row, "calc_status", 6)) or "ok",
        }
        for row in rows
    }


async def load_expense_forecast_override_map(
    db_path: Path,
    *,
    year: int,
    forecast_version: str,
    owner_names: list[str],
) -> dict[tuple[str, int, int], dict[str, Any]]:
    if not owner_names:
        return {}
    placeholders = ",".join("?" for _ in owner_names)
    rows = await _fetch_all_for_path(
        db_path,
        f"""
        SELECT owner_name, subject_id, month, rule_id, system_value, override_value, override_reason
        FROM expense_forecast_override
        WHERE forecast_year = ? AND forecast_version = ?
          AND owner_name IN ({placeholders})
        """,
        (year, forecast_version, *owner_names),
    )
    return {
        (_text(_row_value(row, "owner_name", 0)), int(_row_value(row, "subject_id", 1)), int(_row_value(row, "month", 2))): {
            "rule_id": int(_row_value(row, "rule_id", 3)) if _row_value(row, "rule_id", 3) is not None else None,
            "system_value": float(_row_value(row, "system_value", 4) or 0.0),
            "override_value": float(_row_value(row, "override_value", 5) or 0.0),
            "override_reason": _text(_row_value(row, "override_reason", 6)) or None,
        }
        for row in rows
    }
