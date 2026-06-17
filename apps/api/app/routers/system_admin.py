from __future__ import annotations

from typing import Awaitable, Callable

import app.core.aiosqlite_compat as aiosqlite
from fastapi import APIRouter, HTTPException

from app.core.config import Settings
from app.core.db_paths import common_db_path
from app.integrations.feishu_store import delete_binding as feishu_delete_binding
from app.integrations.feishu_store import list_bindings as feishu_list_bindings
from app.integrations.feishu_store import upsert_binding as feishu_upsert_binding
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
from app.services.system_users import (
    SystemUserDuplicateName,
    SystemUserNoUpdateFields,
    SystemUserNotFound,
    create_system_user as create_system_user_command,
    delete_system_user as delete_system_user_command,
    list_system_users as list_system_users_query,
    reset_system_user_first_password as reset_system_user_first_password_command,
    set_system_user_first_login_flag as set_system_user_first_login_flag_command,
    system_user_exists,
    update_system_user as update_system_user_command,
)
from app.services.system_versions import (
    SystemVersionBadRequest,
    SystemVersionNotFound,
    SystemVersionOperationFailed,
    SystemVersionSchemaError,
    create_system_version as create_system_version_command,
    delete_system_version as delete_system_version_command,
    list_system_versions as list_system_versions_query,
    patch_system_version as patch_system_version_command,
)


def _raise_system_version_http_error(exc: Exception) -> None:
    if isinstance(exc, SystemVersionNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, SystemVersionBadRequest):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, (SystemVersionSchemaError, SystemVersionOperationFailed)):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise exc


def build_system_admin_router(
    *,
    settings: Settings,
    resolve_data_file_name: Callable[[int], Awaitable[str]],
    parse_year_from_budget_filename: Callable[[str], int | None],
    get_year_period_months: Callable[[int], Awaitable[dict[int, int]]],
    iso_now: Callable[[], str],
    purge_disallowed_budget_data_for_version: Callable[[aiosqlite.Connection, int, int, dict[int, int]], Awaitable[int]],
    validate_password_policy: Callable[[str], None],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/system/databases/{data_file_id}/versions", response_model=list[SystemVersionRow])
    async def list_system_versions(data_file_id: int):
        try:
            return await list_system_versions_query(
                data_dir=settings.data_dir,
                data_file_id=data_file_id,
                resolve_data_file_name=resolve_data_file_name,
            )
        except Exception as exc:
            _raise_system_version_http_error(exc)

    @router.post("/api/system/databases/{data_file_id}/versions", response_model=SystemVersionRow)
    async def create_system_version(data_file_id: int, req: SystemVersionCreateRequest):
        try:
            return await create_system_version_command(
                data_dir=settings.data_dir,
                data_file_id=data_file_id,
                request=req,
                resolve_data_file_name=resolve_data_file_name,
                parse_year_from_budget_filename=parse_year_from_budget_filename,
                get_year_period_months=get_year_period_months,
                purge_disallowed_budget_data_for_version=purge_disallowed_budget_data_for_version,
                now=iso_now(),
            )
        except Exception as exc:
            _raise_system_version_http_error(exc)

    @router.patch("/api/system/databases/{data_file_id}/versions/{version_id}", response_model=SystemVersionRow)
    async def patch_system_version(data_file_id: int, version_id: int, req: SystemVersionPatchRequest):
        """仅更新版本名称；版本 ID、创建时间、current_month 不可修改。"""
        try:
            return await patch_system_version_command(
                data_dir=settings.data_dir,
                data_file_id=data_file_id,
                version_id=version_id,
                request=req,
                resolve_data_file_name=resolve_data_file_name,
            )
        except Exception as exc:
            _raise_system_version_http_error(exc)

    @router.delete("/api/system/databases/{data_file_id}/versions/{version_id}")
    async def delete_system_version(data_file_id: int, version_id: int):
        try:
            result = await delete_system_version_command(
                common_db=common_db_path(),
                data_dir=settings.data_dir,
                data_file_id=data_file_id,
                version_id=version_id,
                resolve_data_file_name=resolve_data_file_name,
            )
            result.pop("file_name", None)
            return result
        except Exception as exc:
            _raise_system_version_http_error(exc)

    @router.get("/api/system/users", response_model=list[SystemUserRow])
    async def list_system_users():
        return await list_system_users_query(common_db_path())

    @router.post("/api/system/users", response_model=SystemUserRow)
    async def create_system_user(req: SystemUserCreateRequest):
        validate_password_policy(req.first_login_password)
        try:
            return await create_system_user_command(common_db_path(), req, iso_now())
        except SystemUserDuplicateName as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/api/system/users/{user_id}", response_model=SystemUserRow)
    async def update_system_user(user_id: int, req: SystemUserUpdateRequest):
        try:
            return await update_system_user_command(common_db_path(), user_id, req, iso_now())
        except SystemUserNoUpdateFields as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SystemUserDuplicateName as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SystemUserNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/api/system/users/{user_id}")
    async def delete_system_user(user_id: int):
        try:
            await delete_system_user_command(common_db_path(), user_id)
        except SystemUserNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"deleted": True, "user_id": user_id}

    @router.get("/api/system/feishu/bindings", response_model=list[FeishuBindingRow])
    async def list_feishu_bindings_api():
        rows = feishu_list_bindings(common_db_path())
        return [FeishuBindingRow(**r) for r in rows]

    @router.post("/api/system/feishu/bindings", response_model=FeishuBindingRow)
    async def upsert_feishu_binding_api(req: FeishuBindingUpsertRequest):
        if not await system_user_exists(common_db_path(), req.user_id):
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
        try:
            return await reset_system_user_first_password_command(common_db_path(), user_id, req, iso_now())
        except SystemUserNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.patch("/api/system/users/{user_id}/first-login-flag", response_model=SystemUserRow)
    async def set_system_user_first_login_flag(user_id: int, req: SystemUserFirstLoginFlagRequest):
        try:
            return await set_system_user_first_login_flag_command(common_db_path(), user_id, req, iso_now())
        except SystemUserNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
