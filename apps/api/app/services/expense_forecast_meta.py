"""Meta read model for expense forecast UI filters."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import app.core.aiosqlite_compat as aiosqlite
from app.services.expense_forecast_data_context import (
    load_expense_forecast_budget_subject_rows,
    load_expense_forecast_scope_rows,
)


_ENTITY_ORDER = ["微众银行", "科技子", "科技孙"]
_GROUP_ORDER = [
    "个人金融事业群", "企业及机构金融事业群", "科技及智能事业群", "国际发展部", "国际业务",
    "资源管理及管控职能群", "其他", "历史架构", "科技子", "科技孙", "虚拟架构",
]


def default_expense_forecast_version() -> str:
    return datetime.now().strftime("%y%m%d") + "v1"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _entity_sort_key(entity_name: str) -> tuple[int, str]:
    text = _text(entity_name)
    try:
        return (_ENTITY_ORDER.index(text), text)
    except ValueError:
        return (len(_ENTITY_ORDER), text)


def _group_sort_key(group_name: str) -> tuple[int, str]:
    text = _text(group_name)
    try:
        return (_GROUP_ORDER.index(text), text)
    except ValueError:
        return (len(_GROUP_ORDER), text)


def build_expense_forecast_scope_options(
    rows: list[tuple[str, str, str]],
) -> dict[str, list[dict[str, Any]]]:
    entity_values: list[str] = []
    group_values: list[str] = []
    owner_values: list[str] = []
    owner_values_by_group: dict[str, list[str]] = {}
    for entity_name, group_name, owner_name in rows:
        if entity_name and entity_name not in entity_values:
            entity_values.append(entity_name)
        if group_name and group_name not in group_values:
            group_values.append(group_name)
        if owner_name and owner_name not in owner_values:
            owner_values.append(owner_name)
        if group_name and owner_name:
            owner_values_by_group.setdefault(group_name, [])
            if owner_name not in owner_values_by_group[group_name]:
                owner_values_by_group[group_name].append(owner_name)
    entity_values.sort(key=_entity_sort_key)
    group_values.sort(key=_group_sort_key)
    owner_values.sort(key=lambda value: (len(value), value))
    for group_name in owner_values_by_group:
        owner_values_by_group[group_name].sort(key=lambda value: (len(value), value))
    return {
        "entity_options": [{"value": value, "label": value} for value in entity_values],
        "group_options": [{"value": value, "label": value} for value in group_values],
        "owner_options": [{"value": value, "label": value} for value in owner_values],
        "owner_group_options": [
            {
                "group_value": group_name,
                "group_label": group_name,
                "owner_options": [
                    {"value": owner_name, "label": owner_name}
                    for owner_name in owner_values_by_group[group_name]
                ],
            }
            for group_name in group_values
        ],
    }


def build_expense_forecast_leaf_subject_options(
    subject_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    leaf_rows = [
        row
        for row in subject_rows
        if bool(row["is_leaf"]) and not row["formula_text"] and _text(row["subject_name"])
    ]
    leaf_rows.sort(key=lambda item: (int(item["sort_order"] or 0), int(item["id"])))
    return [
        {"id": int(row["id"]), "label": _text(row["subject_name"])}
        for row in leaf_rows
    ]


async def load_expense_forecast_version_suggestions(
    db_path: Path,
    *,
    year: int,
    default_version: str,
) -> list[str]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT forecast_version, MAX(update_time) AS latest_time
            FROM expense_forecast_entry
            WHERE forecast_year = ?
            GROUP BY forecast_version
            ORDER BY latest_time DESC, forecast_version DESC
            LIMIT 20
            """,
            (year,),
        )
        rows = await cur.fetchall()
    versions = [_text(row[0]) for row in rows if _text(row[0])]
    if default_version not in versions:
        versions.insert(0, default_version)
    return versions


async def load_expense_forecast_meta(
    db_path: Path,
    *,
    year: int,
    default_version: str | None = None,
) -> dict[str, Any]:
    resolved_default_version = _text(default_version) or default_expense_forecast_version()
    scope_rows = await load_expense_forecast_scope_rows(db_path)
    scope_options = build_expense_forecast_scope_options(scope_rows)
    subject_rows = await load_expense_forecast_budget_subject_rows(db_path)
    versions = await load_expense_forecast_version_suggestions(
        db_path,
        year=year,
        default_version=resolved_default_version,
    )
    return {
        "default_year": int(year),
        "default_version": versions[0] if versions else resolved_default_version,
        "version_suggestions": versions,
        **scope_options,
        "leaf_subject_options": build_expense_forecast_leaf_subject_options(subject_rows),
    }


async def load_expense_forecast_owner_group_options(db_path: Path) -> list[dict[str, Any]]:
    scope_rows = await load_expense_forecast_scope_rows(db_path)
    return build_expense_forecast_scope_options(scope_rows)["owner_group_options"]
