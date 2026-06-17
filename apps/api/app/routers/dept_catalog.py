from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.core.db_paths import common_db_path
from app.schemas import (
    DeptAccountCreate,
    DeptAccountRow,
    DeptAccountUpdate,
)
from app.services.dept_catalog import (
    apply_dept_account_import as apply_dept_account_import_command,
    build_dept_tree_export_workbook,
    create_dept_account as create_dept_account_command,
    delete_dept_account as delete_dept_account_command,
    list_dept_accounts as list_dept_accounts_query,
    preview_dept_account_import as preview_dept_account_import_command,
    update_dept_account as update_dept_account_command,
)
from app.services.export_common import excel_streaming_response


def build_dept_catalog_router(
    *,
    normalize_cell: Callable[[Any], str],
    color_row: Callable[[Any, int, int, str], None],
    validate_dept_code_with_parent: Callable[[str, int, str | None], str | None],
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/dept-accounts/import-preview")
    async def preview_dept_account_import(file: UploadFile = File(...)):
        content = await file.read()
        return await preview_dept_account_import_command(content, normalize_cell=normalize_cell)

    @router.post("/api/dept-accounts/import-apply")
    async def apply_dept_account_import(
        file: UploadFile = File(...),
        mappings_json: str = Form(...),
    ):
        try:
            mappings = json.loads(mappings_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="字段映射格式不合法") from exc
        if not isinstance(mappings, dict):
            raise HTTPException(status_code=400, detail="字段映射格式不合法")

        content = await file.read()
        result = await apply_dept_account_import_command(
            common_db_path(),
            content,
            mappings,
            normalize_cell=normalize_cell,
            color_row=color_row,
            validate_dept_code_with_parent=validate_dept_code_with_parent,
        )
        return excel_streaming_response(
            result.content,
            filename=result.filename,
            extra_headers={
                "X-Import-Total": str(result.total),
                "X-Import-Success": str(result.success),
                "X-Import-Overwrite": str(result.overwrite),
                "X-Import-Failed": str(result.failed),
                "Access-Control-Expose-Headers": (
                    "Content-Disposition,"
                    "X-Import-Total,X-Import-Success,X-Import-Overwrite,X-Import-Failed"
                ),
            },
        )

    @router.get("/api/dept-accounts", response_model=list[DeptAccountRow])
    async def list_dept_accounts():
        return await list_dept_accounts_query(common_db_path())

    @router.get("/api/dept-tree/export")
    async def export_dept_tree():
        workbook = await build_dept_tree_export_workbook(
            common_db_path(),
            template_path=settings.download_template_dir / "dept_acct_temp.xlsx",
        )
        return excel_streaming_response(workbook.content, filename=workbook.filename)

    @router.post("/api/dept-accounts", response_model=DeptAccountRow)
    async def create_dept_account(body: DeptAccountCreate):
        row = await create_dept_account_command(common_db_path(), body)
        await write_operation_log(
            action_type="INSERT",
            action_desc=f"新增部门科目 {body.dept_code}",
            target_table="dept_account",
            affected_rows=1,
            after_data=body.model_dump(),
        )
        return row

    @router.patch("/api/dept-accounts/{code}", response_model=DeptAccountRow)
    async def update_dept_account(code: str, body: DeptAccountUpdate):
        result = await update_dept_account_command(common_db_path(), code, body)
        await write_operation_log(
            action_type="UPDATE",
            action_desc=f"更新部门科目 {code}",
            target_table="dept_account",
            affected_rows=1,
            before_data=result.before_data,
            after_data=result.after_data,
        )
        return result.row

    @router.delete("/api/dept-accounts/{code}")
    async def delete_dept_account(code: str):
        deleted = await delete_dept_account_command(common_db_path(), code)
        await write_operation_log(
            action_type="DELETE",
            action_desc=f"删除部门科目 {code}",
            target_table="dept_account",
            affected_rows=1,
            before_data=deleted.before_data,
            after_data=None,
        )
        return {"ok": True}

    return router
