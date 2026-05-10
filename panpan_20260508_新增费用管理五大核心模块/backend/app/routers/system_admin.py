from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.config import Settings
from app.db_paths import common_db_path
from app.feishu_store import delete_binding as feishu_delete_binding
from app.feishu_store import list_bindings as feishu_list_bindings
from app.feishu_store import upsert_binding as feishu_upsert_binding
from app.schemas import (
    FeishuBindingRow,
    FeishuBindingUpsertRequest,
    SystemUserCreateRequest,
    SystemUserFirstLoginFlagRequest,
    SystemUserPasswordResetRequest,
    SystemUserRow,
    SystemUserUpdateRequest,
    SystemVersionCreateRequest,
    SystemVersionPatchRequest,
    SystemVersionRow,
)


def build_system_admin_router(
    *,
    settings: Settings,
    resolve_data_file_name: Callable[[int], Awaitable[str]],
    parse_year_from_budget_filename: Callable[[str], int | None],
    get_year_period_months: Callable[[int], Awaitable[dict[int, int]]],
    iso_now: Callable[[], str],
    purge_disallowed_budget_data_for_version: Callable[[aiosqlite.Connection, int, int, dict[int, int]], Awaitable[None]],
    sync_compare_budget_summary: Callable[..., Awaitable[Any]],
    validate_password_policy: Callable[[str], None],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/system/databases/{data_file_id}/versions", response_model=list[SystemVersionRow])
    async def list_system_versions(data_file_id: int):
        file_name = await resolve_data_file_name(data_file_id)
        db_path = settings.data_dir / file_name
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"数据库文件不存在: {file_name}")
        async with aiosqlite.connect(db_path) as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
            cur = await bdb.execute("PRAGMA table_info(version)")
            cols = {str(r[1]) for r in await cur.fetchall()}
            has_current_month = "current_month" in cols
            sql = (
                "SELECT version_id, version_name, version_date_time, current_month FROM version ORDER BY version_id DESC"
                if has_current_month
                else "SELECT version_id, version_name, version_date_time, 1 AS current_month FROM version ORDER BY version_id DESC"
            )
            cur = await bdb.execute(sql)
            rows = await cur.fetchall()
        return [
            SystemVersionRow(
                version_id=int(r[0]),
                version_name=str(r[1]),
                version_date_time=str(r[2]),
                current_month=int(r[3] or 1),
            )
            for r in rows
        ]

    @router.post("/api/system/databases/{data_file_id}/versions", response_model=SystemVersionRow)
    async def create_system_version(data_file_id: int, req: SystemVersionCreateRequest):
        file_name = await resolve_data_file_name(data_file_id)
        db_path = settings.data_dir / file_name
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"数据库文件不存在: {file_name}")
        year = parse_year_from_budget_filename(file_name)
        if year is None:
            raise HTTPException(status_code=400, detail="数据库文件名不符合 budget_YYYY.db")
        period_month_map = await get_year_period_months(year)
        if not period_month_map:
            raise HTTPException(status_code=400, detail=f"period 中不存在年份 Y{year}")

        now = iso_now()
        async with aiosqlite.connect(db_path) as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
            cur = await bdb.execute(
                "INSERT INTO version(version_date_time, version_name, current_month) VALUES (?, ?, ?)",
                (now, req.version_name, req.current_month),
            )
            new_version_id = int(cur.lastrowid)

            x = max(1, min(13, int(req.current_month)))
            pids_year = [pid for pid, m in period_month_map.items() if 1 <= m <= 12]

            if req.parent_version_id is not None:
                cur = await bdb.execute(
                    "SELECT 1 FROM version WHERE version_id = ?",
                    (req.parent_version_id,),
                )
                if not await cur.fetchone():
                    raise HTTPException(status_code=400, detail=f"父版本 {req.parent_version_id} 不存在")
                parent_id = int(req.parent_version_id)
                insert_shared = """
                    INSERT INTO budget_data(
                      data_acct_code, product_code, period_id, budget_actual, version_id, value, need_calc, create_time, update_time
                    )
                    SELECT data_acct_code, product_code, period_id, budget_actual, ?, value, need_calc, ?, ?
                    FROM budget_data
                    WHERE version_id = ?
                    """
                if x == 13:
                    if pids_year:
                        ph = ",".join(["?"] * len(pids_year))
                        await bdb.execute(
                            insert_shared
                            + f" AND budget_actual = 1 AND period_id IN ({ph})",
                            (new_version_id, now, now, parent_id, *pids_year),
                        )
                elif x == 1:
                    if pids_year:
                        ph = ",".join(["?"] * len(pids_year))
                        await bdb.execute(
                            insert_shared
                            + f" AND budget_actual = 0 AND period_id IN ({ph})",
                            (new_version_id, now, now, parent_id, *pids_year),
                        )
                else:
                    pids_actual = [pid for pid, m in period_month_map.items() if 1 <= m < x]
                    pids_budget = [pid for pid, m in period_month_map.items() if x <= m <= 12]
                    if pids_actual:
                        ph = ",".join(["?"] * len(pids_actual))
                        await bdb.execute(
                            insert_shared
                            + f" AND budget_actual = 1 AND period_id IN ({ph})",
                            (new_version_id, now, now, parent_id, *pids_actual),
                        )
                    if pids_budget:
                        ph = ",".join(["?"] * len(pids_budget))
                        await bdb.execute(
                            insert_shared
                            + f" AND budget_actual = 0 AND period_id IN ({ph})",
                            (new_version_id, now, now, parent_id, *pids_budget),
                        )

            await purge_disallowed_budget_data_for_version(
                bdb, new_version_id, req.current_month, period_month_map
            )
            await bdb.commit()

            cur = await bdb.execute(
                """
                SELECT version_id, version_name, version_date_time, current_month
                FROM version
                WHERE version_id = ?
                """,
                (new_version_id,),
            )
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="创建版本失败")
        return SystemVersionRow(
            version_id=int(row[0]),
            version_name=str(row[1]),
            version_date_time=str(row[2]),
            current_month=int(row[3] or 1),
        )

    @router.patch("/api/system/databases/{data_file_id}/versions/{version_id}", response_model=SystemVersionRow)
    async def patch_system_version(data_file_id: int, version_id: int, req: SystemVersionPatchRequest):
        """仅更新版本名称；版本 ID、创建时间、current_month 不可修改。"""
        file_name = await resolve_data_file_name(data_file_id)
        db_path = settings.data_dir / file_name
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"数据库文件不存在: {file_name}")
        async with aiosqlite.connect(db_path) as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
            cur = await bdb.execute("SELECT 1 FROM version WHERE version_id = ?", (version_id,))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail=f"version_id={version_id} 不存在")
            await bdb.execute(
                "UPDATE version SET version_name = ? WHERE version_id = ?",
                (req.version_name, version_id),
            )
            await bdb.commit()
            cur = await bdb.execute("PRAGMA table_info(version)")
            cols = {str(r[1]) for r in await cur.fetchall()}
            has_cm = "current_month" in cols
            sql = (
                "SELECT version_id, version_name, version_date_time, current_month FROM version WHERE version_id = ?"
                if has_cm
                else "SELECT version_id, version_name, version_date_time, 1 AS current_month FROM version WHERE version_id = ?"
            )
            cur = await bdb.execute(sql, (version_id,))
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="更新版本失败")
        return SystemVersionRow(
            version_id=int(row[0]),
            version_name=str(row[1]),
            version_date_time=str(row[2]),
            current_month=int(row[3] or 1),
        )

    @router.delete("/api/system/databases/{data_file_id}/versions/{version_id}")
    async def delete_system_version(data_file_id: int, version_id: int):
        file_name = await resolve_data_file_name(data_file_id)
        db_path = settings.data_dir / file_name
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"数据库文件不存在: {file_name}")
        async with aiosqlite.connect(db_path) as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
            cur = await bdb.execute("SELECT 1 FROM version WHERE version_id = ?", (version_id,))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail=f"version_id={version_id} 不存在")
            await bdb.execute("DELETE FROM budget_data WHERE version_id = ?", (version_id,))
            await bdb.execute("DELETE FROM budget_summary WHERE version_id = ?", (version_id,))
            await bdb.execute("DELETE FROM version WHERE version_id = ?", (version_id,))
            await bdb.commit()

        async with aiosqlite.connect(common_db_path()) as cdb:
            await cdb.execute("PRAGMA foreign_keys = ON")
            await cdb.execute(
                "DELETE FROM edit_show_version WHERE data_file_id = ? AND version_id = ?",
                (data_file_id, version_id),
            )
            await cdb.commit()
        await sync_compare_budget_summary(trigger_source="auto_after_setting_save")
        return {"deleted": True, "data_file_id": data_file_id, "version_id": version_id}

    @router.get("/api/system/users", response_model=list[SystemUserRow])
    async def list_system_users():
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                """
                SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
                FROM users
                ORDER BY id
                """
            )
            rows = await cur.fetchall()
        return [
            SystemUserRow(
                id=int(r[0]),
                user_name=str(r[1]),
                permission_type=int(r[2]),
                first_login_flag=int(r[3]),
                create_time=str(r[4]),
                update_time=str(r[5]) if r[5] is not None else None,
            )
            for r in rows
        ]

    @router.post("/api/system/users", response_model=SystemUserRow)
    async def create_system_user(req: SystemUserCreateRequest):
        validate_password_policy(req.first_login_password)
        now = iso_now()
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            try:
                cur = await db.execute(
                    """
                    INSERT INTO users(
                      user_name, first_login_password, daily_login_password,
                      permission_type, first_login_flag, create_time, update_time
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        req.user_name.strip(),
                        req.first_login_password,
                        None,
                        req.permission_type,
                        now,
                        now,
                    ),
                )
                await db.commit()
                user_id = int(cur.lastrowid)
            except aiosqlite.IntegrityError:
                raise HTTPException(status_code=400, detail="用户名已存在")

            cur = await db.execute(
                """
                SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
                FROM users WHERE id = ?
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="创建用户失败")
        return SystemUserRow(
            id=int(row[0]),
            user_name=str(row[1]),
            permission_type=int(row[2]),
            first_login_flag=int(row[3]),
            create_time=str(row[4]),
            update_time=str(row[5]) if row[5] is not None else None,
        )

    @router.patch("/api/system/users/{user_id}", response_model=SystemUserRow)
    async def update_system_user(user_id: int, req: SystemUserUpdateRequest):
        set_parts: list[str] = []
        args: list[Any] = []
        if req.user_name is not None:
            set_parts.append("user_name = ?")
            args.append(req.user_name.strip())
        if req.permission_type is not None:
            set_parts.append("permission_type = ?")
            args.append(req.permission_type)
        if not set_parts:
            raise HTTPException(status_code=400, detail="没有可更新字段")
        set_parts.append("update_time = ?")
        args.append(iso_now())
        args.append(user_id)
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            try:
                cur = await db.execute(
                    f"UPDATE users SET {', '.join(set_parts)} WHERE id = ?",
                    tuple(args),
                )
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail=f"user_id={user_id} 不存在")
                await db.commit()
            except aiosqlite.IntegrityError:
                raise HTTPException(status_code=400, detail="用户名已存在")
            cur = await db.execute(
                """
                SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
                FROM users WHERE id = ?
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="更新用户失败")
        return SystemUserRow(
            id=int(row[0]),
            user_name=str(row[1]),
            permission_type=int(row[2]),
            first_login_flag=int(row[3]),
            create_time=str(row[4]),
            update_time=str(row[5]) if row[5] is not None else None,
        )

    @router.delete("/api/system/users/{user_id}")
    async def delete_system_user(user_id: int):
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"user_id={user_id} 不存在")
            await db.commit()
        return {"deleted": True, "user_id": user_id}

    @router.get("/api/system/feishu/bindings", response_model=list[FeishuBindingRow])
    async def list_feishu_bindings_api():
        rows = feishu_list_bindings(common_db_path())
        return [FeishuBindingRow(**r) for r in rows]

    @router.post("/api/system/feishu/bindings", response_model=FeishuBindingRow)
    async def upsert_feishu_binding_api(req: FeishuBindingUpsertRequest):
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute("SELECT id FROM users WHERE id = ?", (req.user_id,))
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"user_id={req.user_id} 不存在")
        feishu_upsert_binding(common_db_path(), req.open_id.strip(), req.user_id)
        for r in feishu_list_bindings(common_db_path()):
            if r["open_id"] == req.open_id.strip():
                return FeishuBindingRow(**r)
        raise HTTPException(status_code=500, detail="绑定写入后读取失败")

    @router.delete("/api/system/feishu/bindings/{open_id}")
    async def delete_feishu_binding_api(open_id: str):
        ok = feishu_delete_binding(common_db_path(), open_id)
        if not ok:
            raise HTTPException(status_code=404, detail="open_id 不存在")
        return {"deleted": True, "open_id": open_id}

    @router.patch("/api/system/users/{user_id}/reset-first-password", response_model=SystemUserRow)
    async def reset_system_user_first_password(user_id: int, req: SystemUserPasswordResetRequest):
        validate_password_policy(req.first_login_password)
        now = iso_now()
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                """
                UPDATE users
                SET first_login_password = ?, daily_login_password = ?, first_login_flag = 1, update_time = ?
                WHERE id = ?
                """,
                (req.first_login_password, None, now, user_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"user_id={user_id} 不存在")
            await db.commit()
            cur = await db.execute(
                """
                SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
                FROM users WHERE id = ?
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="重置首次密码失败")
        return SystemUserRow(
            id=int(row[0]),
            user_name=str(row[1]),
            permission_type=int(row[2]),
            first_login_flag=int(row[3]),
            create_time=str(row[4]),
            update_time=str(row[5]) if row[5] is not None else None,
        )

    @router.patch("/api/system/users/{user_id}/first-login-flag", response_model=SystemUserRow)
    async def set_system_user_first_login_flag(user_id: int, req: SystemUserFirstLoginFlagRequest):
        now = iso_now()
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                """
                UPDATE users
                SET first_login_flag = ?, update_time = ?
                WHERE id = ?
                """,
                (req.first_login_flag, now, user_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"user_id={user_id} 不存在")
            await db.commit()
            cur = await db.execute(
                """
                SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
                FROM users WHERE id = ?
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="更新首次登录标记失败")
        return SystemUserRow(
            id=int(row[0]),
            user_name=str(row[1]),
            permission_type=int(row[2]),
            first_login_flag=int(row[3]),
            create_time=str(row[4]),
            update_time=str(row[5]) if row[5] is not None else None,
        )

    return router
