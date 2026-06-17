"""BI department mapping maintenance commands and reference-data reads."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import aiosqlite

from app.db_bootstrap.expense import ensure_bi_mapping_schema
from app.core.db_paths import common_db_path
from app.services.department_expense_contracts import DEPT_OWNER_LEVEL


class BiDepartmentMappingError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _path(db_path: str | Path | None) -> Path:
    return Path(db_path) if db_path is not None else common_db_path()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _norm_key(value: str) -> str:
    return re.sub(r"\s+", "", _text(value)).lower()


async def _ensure_tables(db_path: str | Path | None = None) -> None:
    async with aiosqlite.connect(_path(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_bi_mapping_schema(db)
        await db.commit()


async def _load_owner_names(db_path: str | Path | None = None) -> set[str]:
    async with aiosqlite.connect(_path(db_path)) as db:
        cur = await db.execute(
            """
            SELECT DISTINCT dept_name
            FROM dept_account
            WHERE level = ? AND is_leaf = 1
            ORDER BY dept_name
            """,
            (DEPT_OWNER_LEVEL,),
        )
        return {_text(row[0]) for row in await cur.fetchall() if _text(row[0])}


async def _load_owner_dept_tree(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    async with aiosqlite.connect(_path(db_path)) as db:
        cur = await db.execute(
            """
            SELECT d1.dept_name, d2.dept_name
            FROM dept_account d2
            LEFT JOIN dept_account d1 ON d2.parent_code = d1.dept_code
            WHERE d2.level = ? AND d2.is_leaf = 1
            ORDER BY d1.dept_code, d2.dept_code
            """,
            (DEPT_OWNER_LEVEL,),
        )
        rows = await cur.fetchall()
    grouped: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None
    for group_name_raw, dept_name_raw in rows:
        group_name = _text(group_name_raw) or "未分组"
        dept_name = _text(dept_name_raw)
        if not dept_name:
            continue
        if current_group is None or current_group["group_name"] != group_name:
            current_group = {"group_name": group_name, "departments": []}
            grouped.append(current_group)
        current_group["departments"].append(dept_name)
    return grouped


async def list_manage_dept_owner_mappings(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    await _ensure_tables(db_path)
    async with aiosqlite.connect(_path(db_path)) as db:
        cur = await db.execute(
            """
            SELECT id, manage_department, owner_department
            FROM manage_dept_owner_mapping
            ORDER BY manage_department, id
            """
        )
        rows = await cur.fetchall()
    return [
        {"id": int(row[0]), "manage_department": _text(row[1]), "owner_department": _text(row[2])}
        for row in rows
    ]


async def create_manage_dept_owner_mapping(
    body: dict[str, str],
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    await _ensure_tables(db_path)
    manage_department = _text(body.get("manage_department"))
    owner_department = _text(body.get("owner_department"))
    if not manage_department or not owner_department:
        raise BiDepartmentMappingError(400, "归口管理部门和费用归属部门不能为空")
    async with aiosqlite.connect(_path(db_path)) as db:
        try:
            cur = await db.execute(
                """
                INSERT INTO manage_dept_owner_mapping(manage_department, owner_department)
                VALUES (?, ?)
                """,
                (manage_department, owner_department),
            )
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise BiDepartmentMappingError(409, "该归口管理部门已存在映射") from exc
    return {"id": int(cur.lastrowid), "manage_department": manage_department, "owner_department": owner_department}


async def update_manage_dept_owner_mapping(
    mapping_id: int,
    body: dict[str, str],
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    await _ensure_tables(db_path)
    owner_department = _text(body.get("owner_department"))
    if not owner_department:
        raise BiDepartmentMappingError(400, "费用归属部门不能为空")
    async with aiosqlite.connect(_path(db_path)) as db:
        cur = await db.execute(
            "UPDATE manage_dept_owner_mapping SET owner_department = ? WHERE id = ?",
            (owner_department, mapping_id),
        )
        await db.commit()
    if cur.rowcount == 0:
        raise BiDepartmentMappingError(404, "映射记录不存在")
    return {"id": mapping_id, "owner_department": owner_department}


async def delete_manage_dept_owner_mapping(
    mapping_id: int,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    await _ensure_tables(db_path)
    async with aiosqlite.connect(_path(db_path)) as db:
        cur = await db.execute("DELETE FROM manage_dept_owner_mapping WHERE id = ?", (mapping_id,))
        await db.commit()
    if cur.rowcount == 0:
        raise BiDepartmentMappingError(404, "映射记录不存在")
    return {"id": mapping_id}


async def auto_generate_manage_dept_owner_mappings(db_path: str | Path | None = None) -> dict[str, int]:
    await _ensure_tables(db_path)
    owner_names = await _load_owner_names(db_path)
    normalized_owner_names = {_norm_key(name) for name in owner_names}
    generated = 0
    skipped = 0
    async with aiosqlite.connect(_path(db_path)) as db:
        cur = await db.execute(
            """
            SELECT DISTINCT owner_name_raw, owner_name_mapped
            FROM expense_actual_detail_raw
            WHERE owner_matched = 1
              AND COALESCE(owner_name_raw, '') != ''
              AND COALESCE(owner_name_mapped, '') != ''
            """
        )
        rows = await cur.fetchall()
        for manage_department, owner_department in rows:
            manage_department = _text(manage_department)
            owner_department = _text(owner_department)
            if not manage_department or not owner_department or _norm_key(owner_department) not in normalized_owner_names:
                skipped += 1
                continue
            try:
                await db.execute(
                    """
                    INSERT INTO manage_dept_owner_mapping(manage_department, owner_department)
                    VALUES (?, ?)
                    """,
                    (manage_department, owner_department),
                )
                generated += 1
            except aiosqlite.IntegrityError:
                skipped += 1
        await db.commit()
    return {"generated": generated, "skipped": skipped}


async def get_manage_dept_owner_reference_data(db_path: str | Path | None = None) -> dict[str, Any]:
    await _ensure_tables(db_path)
    owner_names = await _load_owner_names(db_path)
    owner_dept_groups = await _load_owner_dept_tree(db_path)
    async with aiosqlite.connect(_path(db_path)) as db:
        cur = await db.execute(
            """
            SELECT DISTINCT owner_name_raw
            FROM expense_actual_detail_raw
            WHERE COALESCE(owner_name_raw, '') != ''
            ORDER BY owner_name_raw
            """
        )
        manage_departments = [_text(row[0]) for row in await cur.fetchall()]
    return {
        "manage_departments": manage_departments,
        "owner_departments": sorted(owner_names),
        "owner_dept_groups": owner_dept_groups,
    }
