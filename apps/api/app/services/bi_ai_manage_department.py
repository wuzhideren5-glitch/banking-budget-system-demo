"""Resolve manage department for BI-AI mapping and expense import validation."""
from __future__ import annotations

import json
from typing import Any, Literal

from app.services.expense_budget_execution_budget_rollup import (
    BUDGET_DISPLAY_ALIASES,
    normalize_budget_subject_name,
)
from app.services.expense_budget_execution_caliber_catalog import CALIBER_CATALOG_ALIASES
from app.services.expense_budget_execution_framework import (
    effective_manage_departments,
    normalized_manage_department,
    text,
)

MANAGE_DEPARTMENT_SUBJECT_ALIASES: dict[str, str] = {
    **CALIBER_CATALOG_ALIASES,
    **BUDGET_DISPLAY_ALIASES,
    "客服费（含坐席）": "客服费",
    "其他外包服务费": "外包服务费",
}

ManageDepartmentSource = Literal["override", "auto", "default_all"]


def parse_manage_department_override(raw: Any) -> list[str] | None:
    """Return parsed override list, or None when no manual override is stored."""
    value = text(raw)
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    departments: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        department = text(item)
        if not department or department in seen:
            continue
        seen.add(department)
        departments.append(department)
    return departments


def serialize_manage_department_override(departments: list[str] | None) -> str:
    if departments is None:
        return ""
    cleaned: list[str] = []
    seen: set[str] = set()
    for department in departments:
        normalized = text(department)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    if not cleaned:
        return ""
    return json.dumps(cleaned, ensure_ascii=False)


def format_manage_departments_display(departments: list[str], *, default_all: bool = False) -> str:
    if default_all and departments:
        return f"全部（{len(departments)}）"
    if not departments:
        return ""
    if len(departments) <= 3:
        return "、".join(departments)
    return f"{'、'.join(departments[:3])} 等{len(departments)}个"


async def load_all_expense_departments(db: Any) -> list[str]:
    """All expense owner departments from dept_account (level-2 nodes in 部门科目维护)."""
    cur = await db.execute('PRAGMA table_info("dept_account")')
    columns = {str(row[1]) for row in await cur.fetchall()}
    if not columns:
        return []
    order_clause = "entity_name, dept_name" if "entity_name" in columns else "dept_name"
    cur = await db.execute(
        f"""
        SELECT dept_name
        FROM dept_account
        WHERE level = 2
        ORDER BY {order_clause}
        """
    )
    departments: list[str] = []
    seen: set[str] = set()
    for row in await cur.fetchall():
        department = text(row[0])
        if not department or department in seen:
            continue
        seen.add(department)
        departments.append(department)
    return departments


def normalize_manage_department_subject_label(value: str) -> str:
    raw = text(value)
    if not raw:
        return ""
    return normalize_budget_subject_name(MANAGE_DEPARTMENT_SUBJECT_ALIASES.get(raw, raw))


def build_effective_manage_department_by_subject(
    subject_rows: list[dict[str, Any]],
) -> dict[str, str]:
    """Map budget subject name to inherited manage department from catalog."""
    effective_by_id, manage_by_name = effective_manage_departments(subject_rows)
    result: dict[str, str] = {}
    for row in subject_rows:
        subject_name = normalize_manage_department_subject_label(text(row.get("subject_name")))
        if not subject_name or subject_name in result:
            continue
        department = normalized_manage_department(text(effective_by_id.get(int(row["id"]), "")))
        if department:
            result[subject_name] = department
    for subject_name, departments in manage_by_name.items():
        normalized_subject = normalize_manage_department_subject_label(subject_name)
        if not normalized_subject or normalized_subject in result:
            continue
        department = normalized_manage_department(departments[0]) if departments else ""
        if department:
            result[normalized_subject] = department
    return result


def build_caliber_to_catalog_subject_map(
    bi_rows: list[dict[str, Any]],
    catalog_names: set[str],
) -> dict[str, str]:
    """Map BI budget release caliber labels to catalog budget subject names."""
    mapping: dict[str, str] = {}
    for alias_source, alias_target in MANAGE_DEPARTMENT_SUBJECT_ALIASES.items():
        normalized_target = normalize_manage_department_subject_label(alias_target)
        if normalized_target in catalog_names:
            mapping[alias_source] = normalized_target
    for row in bi_rows:
        caliber = text(row.get("budget_release_caliber", ""))
        if not caliber or caliber in mapping:
            continue
        normalized_caliber = normalize_manage_department_subject_label(caliber)
        if normalized_caliber in catalog_names:
            mapping[caliber] = normalized_caliber
            continue
        for level_name in (text(row.get("level6_name", "")), text(row.get("level5_name", ""))):
            candidate = normalize_manage_department_subject_label(level_name)
            if candidate and candidate in catalog_names:
                mapping[caliber] = candidate
                break
    return mapping


def resolve_manage_department_for_budget_subject(
    budget_subject: str,
    manage_by_subject: dict[str, str],
) -> str:
    normalized = normalize_manage_department_subject_label(budget_subject)
    if not normalized:
        return ""
    return manage_by_subject.get(normalized, "")


def resolve_manage_department_for_bi_mapping_row(
    row: dict[str, Any],
    manage_by_subject: dict[str, str],
    *,
    catalog_names: set[str],
    caliber_to_catalog: dict[str, str],
) -> str:
    """Resolve manage department for one BI-AI mapping row."""
    caliber_raw = text(row.get("budget_release_caliber", ""))
    caliber_candidates: list[str] = []
    if caliber_raw:
        mapped = text(caliber_to_catalog.get(caliber_raw, ""))
        for candidate in (mapped, caliber_raw):
            normalized = normalize_manage_department_subject_label(candidate)
            if normalized and normalized not in caliber_candidates:
                caliber_candidates.append(normalized)
    for candidate in caliber_candidates:
        department = manage_by_subject.get(candidate, "")
        if department:
            return department

    for value in (text(row.get("level6_name", "")), text(row.get("level5_name", ""))):
        normalized = normalize_manage_department_subject_label(value)
        if not normalized:
            continue
        department = manage_by_subject.get(normalized, "")
        if department:
            return department
    return ""


def resolve_effective_manage_departments_for_bi_mapping_row(
    row: dict[str, Any],
    manage_by_subject: dict[str, str],
    all_expense_departments: list[str],
    *,
    catalog_names: set[str],
    caliber_to_catalog: dict[str, str],
) -> tuple[list[str], ManageDepartmentSource]:
    override = parse_manage_department_override(row.get("manage_department_override"))
    if override is not None:
        return override, "override"
    auto_value = resolve_manage_department_for_bi_mapping_row(
        row,
        manage_by_subject,
        catalog_names=catalog_names,
        caliber_to_catalog=caliber_to_catalog,
    )
    if auto_value:
        return [auto_value], "auto"
    return list(all_expense_departments), "default_all"


def build_bi_mapping_manage_departments_index(
    rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    from app.services.expense_budget_execution_framework import norm_key

    index: dict[str, list[str]] = {}
    for row in rows:
        departments = row.get("manage_departments")
        if not isinstance(departments, list):
            continue
        key_sources = [
            text(row.get("budget_release_caliber", "")),
            text(row.get("level6_code", "")),
            text(row.get("level6_name", "")),
            text(row.get("level5_code", "")),
            text(row.get("level5_name", "")),
        ]
        for key_source in key_sources:
            if not key_source:
                continue
            for candidate in (key_source, normalize_manage_department_subject_label(key_source)):
                if not candidate:
                    continue
                key = norm_key(candidate)
                if key not in index:
                    index[key] = list(departments)
    return index


def build_manage_department_validation(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Report rows whose budget release caliber did not resolve a manage department."""
    missing_samples: list[dict[str, str | int]] = []
    with_caliber = 0
    missing_count = 0
    for row in rows:
        caliber = text(row.get("budget_release_caliber", ""))
        if not caliber:
            continue
        with_caliber += 1
        manage_departments = row.get("manage_departments")
        if isinstance(manage_departments, list):
            has_value = any(text(item) for item in manage_departments)
        else:
            has_value = bool(text(row.get("manage_department", "")))
        if has_value:
            continue
        missing_count += 1
        if len(missing_samples) < 20:
            missing_samples.append(
                {
                    "id": int(row.get("id") or 0),
                    "level6_code": text(row.get("level6_code", "")),
                    "level6_name": text(row.get("level6_name", "")),
                    "budget_release_caliber": caliber,
                }
            )
    resolved_count = with_caliber - missing_count
    return {
        "total_rows": len(rows),
        "rows_with_caliber": with_caliber,
        "resolved_count": resolved_count,
        "missing_count": missing_count,
        "is_valid": missing_count == 0,
        "missing_samples": missing_samples,
    }


async def load_budget_subject_catalog_manage_rows(db: Any) -> list[dict[str, Any]]:
    cur = await db.execute(
        """
        SELECT id, parent_id, subject_name, manage_department
        FROM budget_subject_catalog
        ORDER BY sort_order, id
        """
    )
    rows = await cur.fetchall()
    return [
        {
            "id": int(row[0]),
            "parent_id": int(row[1]) if row[1] is not None else None,
            "subject_name": text(row[2]),
            "manage_department": text(row[3]) or None,
        }
        for row in rows
    ]
