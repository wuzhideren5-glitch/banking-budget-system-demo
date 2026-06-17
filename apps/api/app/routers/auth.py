from __future__ import annotations

import secrets
from pathlib import Path
from typing import Awaitable, Callable

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.db_paths import common_db_path
from app.schemas import (
    FirstLoginPasswordChangeRequest,
    LoginRequest,
    LoginResponse,
    SessionInfo,
)
from app.services.auth_sessions import (
    AuthInvalidCredentials,
    authenticate_login,
    change_first_login_password as change_first_login_password_command,
    delete_auth_session,
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
        try:
            login_result = await authenticate_login(
                common_db=common_db_path(),
                user_name=user_name,
                password=password,
                verify_daily_password=verify_daily_password,
                session_id_factory=lambda: secrets.token_urlsafe(32),
                now=now,
                session_ttl_seconds=session_ttl_seconds,
            )
        except AuthInvalidCredentials as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        response.set_cookie(
            key=session_cookie_name,
            value=login_result.session_id,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=session_ttl_seconds,
        )
        return LoginResponse(
            ok=True,
            need_change_password=login_result.need_change_password,
            user_name=login_result.user_name,
            permission_type=login_result.permission_type,
        )

    @router.post("/api/logout")
    async def logout(request: Request):
        session_id = request.cookies.get(session_cookie_name)
        await delete_auth_session(common_db_path(), session_id)
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
        await change_first_login_password_command(
            common_db=common_db_path(),
            user_id=user_id,
            session_id=session_id,
            hashed_password=hashed,
            now=now,
        )
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
