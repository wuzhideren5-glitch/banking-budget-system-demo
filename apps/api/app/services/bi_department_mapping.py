"""BI department mapping maintenance commands and reference-data reads."""
from __future__ import annotations

import re
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path
from app.db_bootstrap.expense import ensure_bi_mapping_schema_sync
from app.services.department_expense_contracts import DEPT_OWNER_LEVEL


class BiDepartmentMappingError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _path(db_path: str | Path | None) -> Path:
    return Path(db_path) if db_path is not None else common_db_path()


def _uses_mysql_path(path: str | Path | None) -> bool:
    resolved_path = _path(path)
    try:
        candidate = Path(resolved_path).expanduser().resolve()
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


def _text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _norm_key(value: str) -> str:
    return re.sub(r"\s+", "", _text(value)).lower()


def _is_integrity_error(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    exc_name = f"{type(exc).__module__}.{type(exc).__name__}".lower()
    return "integrityerror" in exc_name or "unique constraint failed" in str(exc).lower()


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


async def _ensure_tables(db_path: str | Path | None = None) -> None:
    if _uses_mysql_path(db_path):
        await get_pool().fetch_val("SELECT 1 FROM manage_dept_owner_mapping LIMIT 1")
        return
    with sqlite3.connect(_path(db_path)) as db:
        db.execute("PRAGMA foreign_keys = ON")
        ensure_bi_mapping_schema_sync(db)
        db.commit()


async def _load_owner_names(db_path: str | Path | None = None) -> set[str]:
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(
            """
            SELECT DISTINCT dept_name
            FROM dept_account
            WHERE level = %s AND is_leaf = 1
            ORDER BY dept_name
            """,
            (DEPT_OWNER_LEVEL,),
        )
    else:
        with sqlite3.connect(_path(db_path)) as db:
            rows = db.execute(
                """
                SELECT DISTINCT dept_name
                FROM dept_account
                WHERE level = ? AND is_leaf = 1
                ORDER BY dept_name
                """,
                (DEPT_OWNER_LEVEL,),
            ).fetchall()
    return {_text(_row_value(row, "dept_name", 0)) for row in rows if _text(_row_value(row, "dept_name", 0))}


async def _load_owner_dept_tree(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(
            """
            SELECT d1.dept_name AS group_name, d2.dept_name AS dept_name
            FROM dept_account d2
            LEFT JOIN dept_account d1 ON d2.parent_code = d1.dept_code
            WHERE d2.level = %s AND d2.is_leaf = 1
            ORDER BY d1.dept_code, d2.dept_code
            """,
            (DEPT_OWNER_LEVEL,),
        )
    else:
        with sqlite3.connect(_path(db_path)) as db:
            rows = db.execute(
                """
                SELECT d1.dept_name, d2.dept_name
                FROM dept_account d2
                LEFT JOIN dept_account d1 ON d2.parent_code = d1.dept_code
                WHERE d2.level = ? AND d2.is_leaf = 1
                ORDER BY d1.dept_code, d2.dept_code
                """,
                (DEPT_OWNER_LEVEL,),
            ).fetchall()
    grouped: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None
    for row in rows:
        group_name_raw = _row_value(row, "group_name", 0)
        dept_name_raw = _row_value(row, "dept_name", 1)
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
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(
            """
            SELECT id, manage_department, owner_department
            FROM manage_dept_owner_mapping
            ORDER BY manage_department, id
            """
        )
    else:
        with sqlite3.connect(_path(db_path)) as db:
            rows = db.execute(
                """
                SELECT id, manage_department, owner_department
                FROM manage_dept_owner_mapping
                ORDER BY manage_department, id
                """
            ).fetchall()
    return [
        {
            "id": int(_row_value(row, "id", 0)),
            "manage_department": _text(_row_value(row, "manage_department", 1)),
            "owner_department": _text(_row_value(row, "owner_department", 2)),
        }
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
    if _uses_mysql_path(db_path):
        try:
            async with get_pool().acquire() as db:
                async with db.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO manage_dept_owner_mapping(manage_department, owner_department)
                        VALUES (%s, %s)
                        """,
                        (manage_department, owner_department),
                    )
                    new_id = int(cur.lastrowid)
        except Exception as exc:
            if not _is_integrity_error(exc):
                raise
            raise BiDepartmentMappingError(409, "该归口管理部门已存在映射") from exc
        return {"id": new_id, "manage_department": manage_department, "owner_department": owner_department}

    with sqlite3.connect(_path(db_path)) as db:
        try:
            cur = db.execute(
                """
                INSERT INTO manage_dept_owner_mapping(manage_department, owner_department)
                VALUES (?, ?)
                """,
                (manage_department, owner_department),
            )
            db.commit()
        except Exception as exc:
            if not _is_integrity_error(exc):
                raise
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
    if _uses_mysql_path(db_path):
        rowcount = await get_pool().execute(
            "UPDATE manage_dept_owner_mapping SET owner_department = %s WHERE id = %s",
            (owner_department, mapping_id),
        )
    else:
        with sqlite3.connect(_path(db_path)) as db:
            cur = db.execute(
                "UPDATE manage_dept_owner_mapping SET owner_department = ? WHERE id = ?",
                (owner_department, mapping_id),
            )
            db.commit()
            rowcount = cur.rowcount
    if rowcount == 0:
        raise BiDepartmentMappingError(404, "映射记录不存在")
    return {"id": mapping_id, "owner_department": owner_department}


async def delete_manage_dept_owner_mapping(
    mapping_id: int,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    await _ensure_tables(db_path)
    if _uses_mysql_path(db_path):
        rowcount = await get_pool().execute("DELETE FROM manage_dept_owner_mapping WHERE id = %s", (mapping_id,))
    else:
        with sqlite3.connect(_path(db_path)) as db:
            cur = db.execute("DELETE FROM manage_dept_owner_mapping WHERE id = ?", (mapping_id,))
            db.commit()
            rowcount = cur.rowcount
    if rowcount == 0:
        raise BiDepartmentMappingError(404, "映射记录不存在")
    return {"id": mapping_id}


async def auto_generate_manage_dept_owner_mappings(db_path: str | Path | None = None) -> dict[str, int]:
    await _ensure_tables(db_path)
    owner_names = await _load_owner_names(db_path)
    normalized_owner_names = {_norm_key(name) for name in owner_names}
    generated = 0
    skipped = 0
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(
            """
            SELECT DISTINCT owner_name_raw, owner_name_mapped
            FROM expense_actual_detail_raw
            WHERE owner_matched = 1
              AND COALESCE(owner_name_raw, '') != ''
              AND COALESCE(owner_name_mapped, '') != ''
            """
        )
        async with get_pool().acquire() as db:
            async with db.cursor() as cur:
                for row in rows:
                    manage_department = _text(_row_value(row, "owner_name_raw", 0))
                    owner_department = _text(_row_value(row, "owner_name_mapped", 1))
                    if (
                        not manage_department
                        or not owner_department
                        or _norm_key(owner_department) not in normalized_owner_names
                    ):
                        skipped += 1
                        continue
                    try:
                        await cur.execute(
                            """
                            INSERT INTO manage_dept_owner_mapping(manage_department, owner_department)
                            VALUES (%s, %s)
                            """,
                            (manage_department, owner_department),
                        )
                        generated += 1
                    except Exception as exc:
                        if not _is_integrity_error(exc):
                            raise
                        skipped += 1
        return {"generated": generated, "skipped": skipped}

    with sqlite3.connect(_path(db_path)) as db:
        rows = db.execute(
            """
            SELECT DISTINCT owner_name_raw, owner_name_mapped
            FROM expense_actual_detail_raw
            WHERE owner_matched = 1
              AND COALESCE(owner_name_raw, '') != ''
              AND COALESCE(owner_name_mapped, '') != ''
            """
        ).fetchall()
        for manage_department, owner_department in rows:
            manage_department = _text(manage_department)
            owner_department = _text(owner_department)
            if not manage_department or not owner_department or _norm_key(owner_department) not in normalized_owner_names:
                skipped += 1
                continue
            try:
                db.execute(
                    """
                    INSERT INTO manage_dept_owner_mapping(manage_department, owner_department)
                    VALUES (?, ?)
                    """,
                    (manage_department, owner_department),
                )
                generated += 1
            except Exception as exc:
                if not _is_integrity_error(exc):
                    raise
                skipped += 1
        db.commit()
    return {"generated": generated, "skipped": skipped}


async def get_manage_dept_owner_reference_data(db_path: str | Path | None = None) -> dict[str, Any]:
    await _ensure_tables(db_path)
    owner_names = await _load_owner_names(db_path)
    owner_dept_groups = await _load_owner_dept_tree(db_path)
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(
            """
            SELECT DISTINCT owner_name_raw
            FROM expense_actual_detail_raw
            WHERE COALESCE(owner_name_raw, '') != ''
            ORDER BY owner_name_raw
            """
        )
    else:
        with sqlite3.connect(_path(db_path)) as db:
            rows = db.execute(
                """
                SELECT DISTINCT owner_name_raw
                FROM expense_actual_detail_raw
                WHERE COALESCE(owner_name_raw, '') != ''
                ORDER BY owner_name_raw
                """
            ).fetchall()
    manage_departments = [_text(_row_value(row, "owner_name_raw", 0)) for row in rows]
    return {
        "manage_departments": manage_departments,
        "owner_departments": sorted(owner_names),
        "owner_dept_groups": owner_dept_groups,
    }
