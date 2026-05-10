from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.config import Settings
from app.db_paths import common_db_path
from app.schemas import (
    FirstLoginPasswordChangeRequest,
    LoginRequest,
    LoginResponse,
    SessionInfo,
)


def build_auth_router(
    *,
    settings: Settings,
    session_cookie_name: str,
    session_ttl_seconds: int,
    verify_daily_password: Callable[[str | None, str], bool],
    hash_daily_password: Callable[[str], str],
    validate_password_policy: Callable[[str], None],
    role_name_from_permission: Callable[[int], str],
    iso_now: Callable[[], str],
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    latest_version_in_path_provider: Callable[[Path], Awaitable[tuple[int, str, str]]],
    last_calc_time_provider: Callable[[Path | None], Awaitable[str | None]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/login", response_model=LoginResponse)
    async def login(req: LoginRequest, response: Response):
        user_name = req.user_name.strip()
        password = req.password
        if not user_name or not password:
            raise HTTPException(status_code=400, detail="用户名和密码不能为空")
        now = iso_now()
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                """
                SELECT id, user_name, first_login_password, daily_login_password, permission_type, first_login_flag
                FROM users
                WHERE user_name = ?
                """,
                (user_name,),
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="用户名或密码错误")

            user_id = int(row[0])
            first_login_password = str(row[2] or "")
            daily_login_password = row[3]
            permission_type = int(row[4])
            first_login_flag = int(row[5])
            need_change_password = first_login_flag == 1
            if need_change_password:
                if password != first_login_password:
                    raise HTTPException(status_code=401, detail="用户名或密码错误")
            else:
                if not verify_daily_password(str(daily_login_password or ""), password):
                    raise HTTPException(status_code=401, detail="用户名或密码错误")

            session_id = secrets.token_urlsafe(32)
            expire_time = datetime.fromtimestamp(
                datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
                + session_ttl_seconds,
                tz=timezone.utc,
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            await db.execute(
                """
                INSERT INTO user_sessions(session_id, user_id, must_change_password, create_time, expire_time, last_seen_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, 1 if need_change_password else 0, now, expire_time, now),
            )
            await db.commit()

        response.set_cookie(
            key=session_cookie_name,
            value=session_id,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=session_ttl_seconds,
        )
        return LoginResponse(
            ok=True,
            need_change_password=need_change_password,
            user_name=user_name,
            permission_type=permission_type,
        )

    @router.post("/api/logout")
    async def logout(request: Request):
        session_id = request.cookies.get(session_cookie_name)
        if session_id:
            async with aiosqlite.connect(common_db_path()) as db:
                await db.execute("PRAGMA foreign_keys = ON")
                await db.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
                await db.commit()
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(session_cookie_name)
        return resp

    @router.post("/api/change-password-first-login")
    async def change_password_first_login(req: FirstLoginPasswordChangeRequest, request: Request):
        user_ctx = getattr(request.state, "current_user", None)
        if not user_ctx:
            raise HTTPException(status_code=401, detail="未登录")
        if int(user_ctx.get("must_change_password", 0)) != 1:
            raise HTTPException(status_code=400, detail="当前无需首次改密")
        validate_password_policy(req.new_password)
        now = iso_now()
        hashed = hash_daily_password(req.new_password)
        session_id = str(user_ctx["session_id"])
        user_id = int(user_ctx["user_id"])
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                UPDATE users
                SET daily_login_password = ?, first_login_flag = 0, update_time = ?
                WHERE id = ?
                """,
                (hashed, now, user_id),
            )
            await db.execute(
                "UPDATE user_sessions SET must_change_password = 0, last_seen_time = ? WHERE session_id = ?",
                (now, session_id),
            )
            await db.commit()
        return {"ok": True}

    @router.get("/api/session", response_model=SessionInfo)
    async def session(request: Request):
        user_ctx = getattr(request.state, "current_user", None)
        if not user_ctx:
            raise HTTPException(status_code=401, detail="未登录")
        try:
            budget_path, budget_year, selected_vid = await editable_context_provider()
            vid = int(selected_vid)
            async with aiosqlite.connect(budget_path) as db:
                await db.execute("PRAGMA foreign_keys = ON")
                cur = await db.execute(
                    """
                    SELECT version_name, version_date_time
                    FROM version
                    WHERE version_id = ?
                    LIMIT 1
                    """,
                    (vid,),
                )
                row = await cur.fetchone()
            if row:
                vname = str(row[0] or "")
                vdt = str(row[1] or "")
            else:
                # Fallback if configured version is missing in selected DB.
                vid, vname, vdt = await latest_version_in_path_provider(budget_path)
            last = await last_calc_time_provider(budget_path)
            return SessionInfo(
                user_id=int(user_ctx["user_id"]),
                software_version=settings.software_version,
                budget_year=budget_year,
                version_id=vid,
                version_name=vname,
                version_date_time=vdt,
                user_display_name=str(user_ctx["user_name"]),
                user_role=role_name_from_permission(int(user_ctx["permission_type"])),
                permission_type=int(user_ctx["permission_type"]),
                first_login_required=int(user_ctx["must_change_password"]) == 1,
                db_connected=True,
                last_global_calc_refresh_time=last,
            )
        except HTTPException:
            raise
        except Exception:
            return SessionInfo(
                user_id=int(user_ctx["user_id"]),
                software_version=settings.software_version,
                budget_year=settings.budget_year,
                version_id=0,
                version_name="",
                version_date_time="",
                user_display_name=str(user_ctx["user_name"]),
                user_role=role_name_from_permission(int(user_ctx["permission_type"])),
                permission_type=int(user_ctx["permission_type"]),
                first_login_required=int(user_ctx["must_change_password"]) == 1,
                db_connected=False,
                last_global_calc_refresh_time=None,
            )

    return router
