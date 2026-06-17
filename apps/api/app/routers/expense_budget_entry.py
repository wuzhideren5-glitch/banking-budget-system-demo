from __future__ import annotations

from io import BytesIO
from typing import Awaitable, Callable
from urllib.parse import quote

import app.core.aiosqlite_compat as aiosqlite
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.db_bootstrap.expense import ensure_expense_budget_entry_schema
from app.core.db_paths import common_db_path
from app.schemas import (
    ExpenseBudgetEntryApplyResponse,
    ExpenseBudgetEntryBatchRow,
    ExpenseBudgetEntryPreviewResponse,
    ExpenseBudgetEntryRow,
    ExpenseBudgetEntryUpdateRequest,
)
from app.services.expense_actual_import_context import (
    ExpenseActualImportContextError,
    load_expense_budget_entry_context,
)
from app.services.expense_budget_entry_apply import apply_expense_budget_entry_rows
from app.services.expense_budget_entry_export import build_matched_preview_export_workbook
from app.services.expense_budget_entry_parser import (
    ExpenseBudgetEntryParseError,
    build_preview_response,
    build_template_workbook,
    parse_budget_entry_file,
)
from app.services.expense_budget_entry_store import (
    ExpenseBudgetEntryBatchMissingError,
    ExpenseBudgetEntryRowMissingError,
    delete_expense_budget_entry_batch,
    list_expense_budget_entry_batches,
    list_expense_budget_entries,
    update_expense_budget_entry_row,
)
from app.services.expense_budget_entry_units import (
    ExpenseBudgetEntryAmountUnitError,
    resolve_budget_entry_amount_unit,
)


def build_expense_budget_entry_router(
    *,
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    async def _ensure_tables() -> None:
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await ensure_expense_budget_entry_schema(db)
            await db.commit()

    @router.get("/api/expense-budget-entry/template")
    async def download_expense_budget_entry_template():
        content, filename = build_template_workbook()
        encoded = quote(filename)
        return StreamingResponse(
            BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=expense-budget-entry-template.xlsx; filename*=UTF-8''{encoded}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    @router.get("/api/expense-budget-entry/batches", response_model=list[ExpenseBudgetEntryBatchRow])
    async def get_expense_budget_entry_batches(
        budget_year: int = Query(default=settings.budget_year),
    ):
        await _ensure_tables()
        return await list_expense_budget_entry_batches(common_db_path(), budget_year=budget_year)

    @router.get("/api/expense-budget-entry/rows", response_model=list[ExpenseBudgetEntryRow])
    async def get_expense_budget_entry_rows(
        budget_year: int = Query(default=settings.budget_year),
        batch_id: int | None = Query(default=None),
    ):
        await _ensure_tables()
        return await list_expense_budget_entries(
            common_db_path(),
            budget_year=budget_year,
            batch_id=batch_id,
        )

    @router.patch("/api/expense-budget-entry/rows/{row_id}", response_model=ExpenseBudgetEntryRow)
    async def patch_expense_budget_entry_row(row_id: int, body: ExpenseBudgetEntryUpdateRequest):
        await _ensure_tables()
        try:
            updated = await update_expense_budget_entry_row(
                common_db_path(),
                row_id=row_id,
                amount=body.amount,
                adjustment_amount=body.adjustment_amount,
            )
        except ExpenseBudgetEntryRowMissingError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await write_operation_log(
            action_type="UPDATE",
            action_desc=f"更新预算录入行 {row_id}",
            target_table="expense_budget_entry",
            affected_rows=1,
            after_data={
                "row_id": row_id,
                "amount": updated.amount,
                "adjustment_amount": updated.adjustment_amount,
                "adjusted_amount": updated.adjusted_amount,
            },
        )
        return updated

    @router.delete("/api/expense-budget-entry/batches/{batch_id}")
    async def remove_expense_budget_entry_batch(batch_id: int):
        await _ensure_tables()
        try:
            deleted_rows = await delete_expense_budget_entry_batch(common_db_path(), batch_id=batch_id)
        except ExpenseBudgetEntryBatchMissingError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await write_operation_log(
            action_type="DELETE",
            action_desc=f"删除预算录入批次 {batch_id}",
            target_table="expense_budget_entry",
            affected_rows=deleted_rows,
            before_data={"batch_id": batch_id},
        )
        return {"id": batch_id, "deleted_rows": deleted_rows}

    @router.post("/api/expense-budget-entry/import-preview", response_model=ExpenseBudgetEntryPreviewResponse)
    async def preview_expense_budget_entry(
        file: UploadFile = File(...),
        budget_year: int = Query(default=settings.budget_year),
        amount_unit_form: str = Form(default="", alias="amount_unit"),
        amount_unit: str | None = Query(default=None),
    ):
        await _ensure_tables()
        try:
            resolved_amount_unit = resolve_budget_entry_amount_unit(
                form_value=amount_unit_form,
                query_value=amount_unit,
            )
        except ExpenseBudgetEntryAmountUnitError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="上传文件为空")
        try:
            ctx = await load_expense_budget_entry_context(common_db_path(), settings.repo_root)
        except ExpenseActualImportContextError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            rows = parse_budget_entry_file(
                file.filename or "预算录入.xlsx",
                raw,
                ctx,
                amount_unit=resolved_amount_unit,
            )
            return build_preview_response(
                file.filename or "预算录入.xlsx",
                budget_year,
                rows,
                amount_unit=resolved_amount_unit,
            )
        except ExpenseBudgetEntryParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/expense-budget-entry/import-export")
    async def export_expense_budget_entry_preview(
        file: UploadFile = File(...),
        budget_year: int = Query(default=settings.budget_year),
        amount_unit_form: str = Form(default="", alias="amount_unit"),
        amount_unit: str | None = Query(default=None),
    ):
        await _ensure_tables()
        try:
            resolved_amount_unit = resolve_budget_entry_amount_unit(
                form_value=amount_unit_form,
                query_value=amount_unit,
            )
        except ExpenseBudgetEntryAmountUnitError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="上传文件为空")
        try:
            ctx = await load_expense_budget_entry_context(common_db_path(), settings.repo_root)
        except ExpenseActualImportContextError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            rows = parse_budget_entry_file(
                file.filename or "预算录入.xlsx",
                raw,
                ctx,
                amount_unit=resolved_amount_unit,
            )
            workbook = build_matched_preview_export_workbook(
                rows=rows,
                file_name=file.filename or "预算录入.xlsx",
                amount_unit=resolved_amount_unit,
            )
        except ExpenseBudgetEntryParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        encoded = quote(workbook.filename)
        return StreamingResponse(
            BytesIO(workbook.content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=expense-budget-entry-matched.xlsx; filename*=UTF-8''{encoded}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    @router.post("/api/expense-budget-entry/import-apply", response_model=ExpenseBudgetEntryApplyResponse)
    async def apply_expense_budget_entry(
        file: UploadFile = File(...),
        budget_year: int = Query(default=settings.budget_year),
        mode_form: str = Form(default="append"),
        mode: str | None = Query(default=None),
        amount_unit_form: str = Form(default="", alias="amount_unit"),
        amount_unit: str | None = Query(default=None),
    ):
        await _ensure_tables()
        resolved_mode = (mode or mode_form or "append").strip().lower()
        try:
            resolved_amount_unit = resolve_budget_entry_amount_unit(
                form_value=amount_unit_form,
                query_value=amount_unit,
            )
        except ExpenseBudgetEntryAmountUnitError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="上传文件为空")
        try:
            ctx = await load_expense_budget_entry_context(common_db_path(), settings.repo_root)
        except ExpenseActualImportContextError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            rows = parse_budget_entry_file(
                file.filename or "预算录入.xlsx",
                raw,
                ctx,
                amount_unit=resolved_amount_unit,
            )
        except ExpenseBudgetEntryParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            applied = await apply_expense_budget_entry_rows(
                common_db_path(),
                budget_year=budget_year,
                import_mode=resolved_mode,
                file_name=file.filename or "预算录入.xlsx",
                rows=rows,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await write_operation_log(
            action_type="IMPORT",
            action_desc=f"预算录入导入 {applied.row_count} 行（{applied.import_mode}）",
            target_table="expense_budget_entry",
            affected_rows=applied.row_count,
            after_data={
                "batch_id": applied.batch_id,
                "budget_year": applied.budget_year,
                "file_name": applied.file_name,
                "matched_rows": applied.matched_rows,
                "unmatched_rows": applied.unmatched_rows,
                "amount_unit": resolved_amount_unit,
            },
        )
        return ExpenseBudgetEntryApplyResponse(
            batch_id=applied.batch_id,
            budget_year=applied.budget_year,
            file_name=applied.file_name,
            import_mode=applied.import_mode,
            amount_unit=resolved_amount_unit,
            row_count=applied.row_count,
            matched_rows=applied.matched_rows,
            unmatched_rows=applied.unmatched_rows,
            note=applied.note,
        )

    return router
