from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.core.config import settings
from app.core.db_paths import common_db_path
from app.schemas import (
    ExpenseActualImportApplyResponse,
    ExpenseActualImportBatchRow,
    ExpenseActualImportPreviewResponse,
)
from app.services.expense_actual_import_apply import apply_expense_actual_import_rows
from app.services.expense_actual_import_batches import (
    IMPORT_KIND_LABELS,
    ExpenseActualImportBatchMissingError,
    ExpenseActualImportExportMissingError,
    delete_expense_actual_import_batch as delete_expense_actual_import_batch_command,
    export_expense_actual_import_batch,
    list_expense_actual_import_batches as list_expense_actual_import_batches_query,
    normalize_import_kind,
)
from app.services.expense_actual_import_context import (
    ExpenseActualImportContextError,
    load_expense_actual_import_context,
)
from app.services.expense_actual_import_parser import (
    ExpenseActualImportParseError,
    build_preview_response,
    parse_actual_file,
)
from app.services.expense_actual_import_schema import ensure_expense_actual_import_schema_ready
from app.services.export_common import excel_streaming_response


def build_expense_actual_import_router(
    *,
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    def _normalize_import_kind(value: str | None) -> str:
        try:
            return normalize_import_kind(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="导入类型仅支持本年实际导入、上年实际导入")

    async def _ensure_tables() -> None:
        await ensure_expense_actual_import_schema_ready(common_db_path())

    @router.get("/api/expense-actual-import/batches", response_model=list[ExpenseActualImportBatchRow])
    async def list_expense_actual_import_batches(import_kind: str = Query(default="current_year_actual")):
        await _ensure_tables()
        try:
            return await list_expense_actual_import_batches_query(common_db_path(), import_kind=import_kind)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/expense-actual-import/export")
    async def export_expense_actual_import(
        batch_id: int | None = Query(default=None),
        import_kind: str = Query(default="current_year_actual"),
    ):
        await _ensure_tables()
        try:
            workbook = await export_expense_actual_import_batch(
                common_db_path(),
                batch_id=batch_id,
                import_kind=import_kind,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (ExpenseActualImportBatchMissingError, ExpenseActualImportExportMissingError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return excel_streaming_response(
            workbook.content,
            filename=workbook.filename,
            fallback_filename="expense-actual-matched.xlsx",
            extra_headers={
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    @router.delete("/api/expense-actual-import/batches/{batch_id}")
    async def delete_expense_actual_import_batch(batch_id: int):
        await _ensure_tables()
        try:
            deleted = await delete_expense_actual_import_batch_command(common_db_path(), batch_id=batch_id)
        except ExpenseActualImportBatchMissingError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        await write_operation_log(
            action_type="DELETE",
            action_desc=f"删除费用执行明细导入批次 {batch_id}",
            target_table="expense_actual_import_batch",
            affected_rows=deleted.deleted_rows,
            before_data={
                "batch_id": batch_id,
                "file_name": deleted.file_name,
                "total_rows": deleted.total_rows,
                "import_kind": deleted.import_kind,
            },
        )
        return {"id": batch_id, "deleted_rows": deleted.deleted_rows}

    @router.post("/api/expense-actual-import/import-preview", response_model=ExpenseActualImportPreviewResponse)
    async def preview_expense_actual_import(
        import_kind: str = Query(default="current_year_actual"),
        file: UploadFile = File(...),
    ):
        await _ensure_tables()
        _normalize_import_kind(import_kind)
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="上传文件为空")
        try:
            ctx = await load_expense_actual_import_context(common_db_path(), settings.repo_root)
        except ExpenseActualImportContextError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            rows = parse_actual_file(file.filename or "部门费用执行.xls", raw, ctx)
            return build_preview_response(file.filename or "部门费用执行.xls", rows)
        except ExpenseActualImportParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/expense-actual-import/import-apply", response_model=ExpenseActualImportApplyResponse)
    async def apply_expense_actual_import(
        mode: str = Query("append"),
        import_kind: str = Query(default="current_year_actual"),
        file: UploadFile = File(...),
    ):
        await _ensure_tables()
        normalized_import_kind = _normalize_import_kind(import_kind)
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="上传文件为空")
        try:
            ctx = await load_expense_actual_import_context(common_db_path(), settings.repo_root)
        except ExpenseActualImportContextError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            rows = parse_actual_file(file.filename or "部门费用执行.xls", raw, ctx)
        except ExpenseActualImportParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            applied = await apply_expense_actual_import_rows(
                common_db_path(),
                import_kind=normalized_import_kind,
                import_mode=mode,
                file_name=file.filename or "部门费用执行.xls",
                rows=rows,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await write_operation_log(
            action_type="IMPORT",
            action_desc=f"{IMPORT_KIND_LABELS[applied.import_kind]} {applied.row_count} 行（{applied.import_mode}）",
            target_table="expense_actual_detail_raw",
            affected_rows=applied.row_count,
            after_data={
                "batch_id": applied.batch_id,
                "import_kind": applied.import_kind,
                "file_name": applied.file_name,
                "import_mode": applied.import_mode,
                "periods": applied.periods,
                "matched_owner_rows": applied.matched_owner_rows,
                "matched_subject_rows": applied.matched_subject_rows,
                "unmatched_rows": applied.unmatched_rows,
            },
        )
        return ExpenseActualImportApplyResponse(
            batch_id=applied.batch_id,
            import_kind=applied.import_kind,
            file_name=applied.file_name,
            import_mode=applied.import_mode,
            row_count=applied.row_count,
            periods=applied.periods,
            matched_owner_rows=applied.matched_owner_rows,
            matched_subject_rows=applied.matched_subject_rows,
            unmatched_rows=applied.unmatched_rows,
            note=applied.note,
            manage_department_warnings=applied.manage_department_warnings,
        )

    return router
