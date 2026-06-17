from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter

from app.core.db_paths import common_db_path
from app.schemas import (
    BudgetSubjectCatalogCreate,
    BudgetSubjectCatalogRow,
    BudgetSubjectCatalogUpdate,
)
from app.services.budget_subject_catalog import (
    build_budget_subject_catalog_workbook,
    create_budget_subject_catalog as create_budget_subject_catalog_command,
    delete_budget_subject_catalog as delete_budget_subject_catalog_command,
    list_budget_subject_catalog as list_budget_subject_catalog_query,
    update_budget_subject_catalog as update_budget_subject_catalog_command,
)
from app.services.export_common import excel_streaming_response


def build_budget_subject_catalog_router(
    *,
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    async def _list_rows() -> list[BudgetSubjectCatalogRow]:
        return await list_budget_subject_catalog_query(common_db_path())

    @router.get("/api/budget-subject-catalog", response_model=list[BudgetSubjectCatalogRow])
    async def list_budget_subject_catalog():
        return await _list_rows()

    @router.post("/api/budget-subject-catalog", response_model=BudgetSubjectCatalogRow)
    async def create_budget_subject_catalog(body: BudgetSubjectCatalogCreate):
        row = await create_budget_subject_catalog_command(common_db_path(), body)
        await write_operation_log(
            action_type="INSERT",
            action_desc=f"新增部门预算科目 {body.subject_name.strip()}",
            target_table="budget_subject_catalog",
            affected_rows=1,
            after_data=body.model_dump(),
        )
        return row

    @router.patch("/api/budget-subject-catalog/{row_id}", response_model=BudgetSubjectCatalogRow)
    async def update_budget_subject_catalog(row_id: int, body: BudgetSubjectCatalogUpdate):
        row = await update_budget_subject_catalog_command(common_db_path(), row_id, body)
        await write_operation_log(
            action_type="UPDATE",
            action_desc=f"更新部门预算科目 {row_id}",
            target_table="budget_subject_catalog",
            affected_rows=1,
            after_data=body.model_dump(),
        )
        return row

    @router.delete("/api/budget-subject-catalog/{row_id}")
    async def delete_budget_subject_catalog(row_id: int):
        deleted = await delete_budget_subject_catalog_command(common_db_path(), row_id)
        await write_operation_log(
            action_type="DELETE",
            action_desc=f"删除部门预算科目 {row_id}",
            target_table="budget_subject_catalog",
            affected_rows=1,
            before_data={"id": row_id, "subject_name": deleted.subject_name},
            after_data=None,
        )
        return {"ok": True}

    @router.get("/api/budget-subject-catalog/export")
    async def export_budget_subject_catalog():
        rows = await _list_rows()
        workbook = build_budget_subject_catalog_workbook(rows)
        return excel_streaming_response(workbook.content, filename=workbook.filename)

    return router
