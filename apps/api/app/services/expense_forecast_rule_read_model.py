"""Read models for expense forecast rule state."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import app.core.aiosqlite_compat as aiosqlite
from app.services.runtime_metric_refs import load_org_product_metric_refs_by_runtime_ref_code


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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
    return list(refs_by_runtime_ref_code.get(code, []))


async def load_expense_forecast_rule_identity(
    db_path: Path,
    *,
    rule_id: int,
) -> dict[str, Any] | None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT forecast_year, forecast_version, owner_name, subject_id
            FROM expense_forecast_rule
            WHERE id = ?
            """,
            (int(rule_id),),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "forecast_year": int(row[0]),
        "forecast_version": _text(row[1]),
        "owner_name": _text(row[2]),
        "subject_id": int(row[3]),
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
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
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
        rows = await cur.fetchall()
        if not rows:
            return []
        rule_ids = [int(row[0]) for row in rows]
        placeholders = ",".join("?" for _ in rule_ids)
        cur = await db.execute(
            f"""
            SELECT rule_id, param_group, param_key, param_value, value_type
            FROM expense_forecast_rule_param
            WHERE rule_id IN ({placeholders})
            ORDER BY rule_id, id
            """,
            rule_ids,
        )
        param_rows = await cur.fetchall()
        cur = await db.execute(
            f"""
            SELECT rule_id, variable_code, variable_name, source_type, source_key, source_subkey, default_value, sort_order
            FROM expense_forecast_rule_variable
            WHERE rule_id IN ({placeholders})
            ORDER BY rule_id, sort_order, id
            """,
            rule_ids,
        )
        variable_rows = await cur.fetchall()
        if org_product_refs_by_runtime_ref_code is None:
            org_product_refs_by_runtime_ref_code = await load_org_product_metric_refs_by_runtime_ref_code(db)

    org_product_refs_by_runtime_ref_code = {
        _text(code).upper(): list(refs)
        for code, refs in (org_product_refs_by_runtime_ref_code or {}).items()
        if _text(code)
    }

    params_by_rule: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in param_rows:
        params_by_rule[int(row[0])].append(
            {
                "param_group": _text(row[1]) or "common",
                "param_key": _text(row[2]),
                "param_value": _text(row[3]) if row[3] is not None else None,
                "value_type": _text(row[4]) or "string",
            }
        )

    vars_by_rule: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in variable_rows:
        vars_by_rule[int(row[0])].append(
            {
                "variable_code": _text(row[1]),
                "variable_name": _text(row[2]) or None,
                "source_type": _text(row[3]),
                "source_key": _text(row[4]) or None,
                "source_subkey": _text(row[5]) or None,
                "default_value": float(row[6]) if row[6] is not None else None,
                "sort_order": int(row[7] or 0),
                "org_product_refs": _org_product_refs_for_variable(
                    source_type=row[3],
                    source_key=row[4],
                    refs_by_runtime_ref_code=org_product_refs_by_runtime_ref_code,
                ),
            }
        )

    result: list[dict[str, Any]] = []
    for row in rows:
        rule_id = int(row[0])
        result.append(
            {
                "id": rule_id,
                "forecast_year": int(row[1]),
                "forecast_version": _text(row[2]),
                "owner_name": _text(row[3]),
                "subject_id": int(row[4]),
                "subject_name": _text(row[5]),
                "scheme_code": _text(row[6]),
                "enabled": bool(row[7]),
                "allow_manual_override": bool(row[8]),
                "auto_refresh_enabled": bool(row[9]),
                "manual_recalc_enabled": bool(row[10]),
                "metric_source_priority": _text(row[11]) or "metric_first",
                "effective_from_month": int(row[12] or 1),
                "effective_to_month": int(row[13] or 12),
                "priority": int(row[14] or 100),
                "remark": _text(row[15]) or None,
                "created_at": _text(row[16]),
                "updated_at": _text(row[17]),
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
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            f"""
            SELECT owner_name, subject_id, month, rule_id, calc_value, calc_basis_json, calc_status
            FROM expense_forecast_calc_result
            WHERE forecast_year = ? AND forecast_version = ?
              AND owner_name IN ({placeholders})
            """,
            (year, forecast_version, *owner_names),
        )
        rows = await cur.fetchall()
    return {
        (_text(row[0]), int(row[1]), int(row[2])): {
            "rule_id": int(row[3]) if row[3] is not None else None,
            "calc_value": float(row[4] or 0.0),
            "calc_basis_json": _text(row[5]) or None,
            "calc_status": _text(row[6]) or "ok",
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
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            f"""
            SELECT owner_name, subject_id, month, rule_id, system_value, override_value, override_reason
            FROM expense_forecast_override
            WHERE forecast_year = ? AND forecast_version = ?
              AND owner_name IN ({placeholders})
            """,
            (year, forecast_version, *owner_names),
        )
        rows = await cur.fetchall()
    return {
        (_text(row[0]), int(row[1]), int(row[2])): {
            "rule_id": int(row[3]) if row[3] is not None else None,
            "system_value": float(row[4] or 0.0),
            "override_value": float(row[5] or 0.0),
            "override_reason": _text(row[6]) or None,
        }
        for row in rows
    }
