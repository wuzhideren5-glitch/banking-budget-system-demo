from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.services.expense_budget_execution_export import (
    ExpenseBudgetExecutionExportError,
    ExpenseBudgetExecutionExportOptions,
    build_expense_budget_execution_export,
    expense_budget_execution_workbook_response,
)
from app.services.expense_budget_execution_framework import (
    ExpenseFrameworkError,
    ParsedFramework,
    parse_framework_source_bytes as _parse_framework_source_bytes_service,
)
from app.services.expense_budget_execution_framework_sync import (
    preview_expense_framework_sync as _preview_expense_framework_sync_service,
    sync_expense_framework as _sync_expense_framework_service,
)
from app.services.expense_budget_execution_report_resolver import (
    ExpenseBudgetExecutionReportError,
    ExpenseBudgetExecutionReportSelection,
    resolve_display_report_payload as _resolve_display_report_payload_service,
    resolve_export_report_payload as _resolve_export_report_payload_service,
)
from app.services.expense_budget_execution_status import (
    build_expense_budget_execution_status as _build_expense_budget_execution_status,
)


class ExpenseBudgetExecutionExportRequest(BaseModel):
    mode: str = "query"
    perspective: str = "group"
    amount_unit: str = "yuan"
    keyword: str = ""
    include_zero_rows: bool = False
    entity_name: str = ""
    group_name: str = ""
    owner_dept: str = ""
    subject_id: int | None = None
    report_month: int | None = None
    include_monthly_actuals: bool = False
    include_last_year_monthly_actuals: bool = False


def build_expense_budget_execution_report_selection(
    *,
    mode: str = "query",
    perspective: str = "group",
    keyword: str = "",
    include_zero_rows: bool = False,
    entity_name: str = "",
    group_name: str = "",
    owner_dept: str = "",
    subject_id: int | None = None,
    report_month: int | None = None,
) -> ExpenseBudgetExecutionReportSelection:
    return ExpenseBudgetExecutionReportSelection(
        mode=mode,
        perspective=perspective,
        keyword=keyword,
        include_zero_rows=include_zero_rows,
        entity_name=entity_name,
        group_name=group_name,
        owner_dept=owner_dept,
        subject_id=subject_id,
        report_month=report_month,
    )


def build_expense_budget_execution_export_options(
    body: ExpenseBudgetExecutionExportRequest,
) -> ExpenseBudgetExecutionExportOptions:
    return ExpenseBudgetExecutionExportOptions(
        mode=body.mode,
        perspective=body.perspective,
        amount_unit=body.amount_unit,
        include_monthly_actuals=body.include_monthly_actuals,
        include_last_year_monthly_actuals=body.include_last_year_monthly_actuals,
    )


def build_expense_budget_execution_export_selection(
    body: ExpenseBudgetExecutionExportRequest,
) -> ExpenseBudgetExecutionReportSelection:
    return build_expense_budget_execution_report_selection(
        mode=body.mode,
        perspective=body.perspective,
        keyword=body.keyword,
        include_zero_rows=body.include_zero_rows,
        entity_name=body.entity_name,
        group_name=body.group_name,
        owner_dept=body.owner_dept,
        subject_id=body.subject_id,
        report_month=body.report_month,
    )


def expense_budget_execution_report_http_error(exc: ExpenseBudgetExecutionReportError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def build_expense_budget_execution_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
) -> APIRouter:
    router = APIRouter()

    async def _read_upload_file(file: UploadFile) -> tuple[str, bytes]:
        file_name = file.filename or "upload.xlsx"
        if not file_name.lower().endswith((".xls", ".xlsx", ".xlsm")):
            raise HTTPException(status_code=400, detail="请上传 .xls / .xlsx / .xlsm 文件")
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="上传文件为空")
        return file_name, raw

    def _parse_framework_source_bytes(source_file: str, raw: bytes) -> ParsedFramework:
        try:
            return _parse_framework_source_bytes_service(source_file, raw)
        except ExpenseFrameworkError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/expense-budget-execution")
    async def get_expense_budget_execution(
        mode: str = Query("query"),
        perspective: str = Query("group"),
        keyword: str = Query(""),
        include_zero_rows: bool = Query(False),
        entity_name: str = Query(""),
        group_name: str = Query(""),
        owner_dept: str = Query(""),
        subject_id: int | None = Query(None),
        report_month: int | None = Query(None),
    ):
        selection = build_expense_budget_execution_report_selection(
            mode=mode,
            perspective=perspective,
            keyword=keyword,
            include_zero_rows=include_zero_rows,
            entity_name=entity_name,
            group_name=group_name,
            owner_dept=owner_dept,
            subject_id=subject_id,
            report_month=report_month,
        )
        try:
            return await _resolve_display_report_payload_service(
                editable_context_provider=editable_context_provider,
                selection=selection,
            )
        except ExpenseBudgetExecutionReportError as exc:
            raise expense_budget_execution_report_http_error(exc) from exc

    @router.get("/api/expense-budget-execution/status")
    async def get_expense_budget_execution_status():
        return await _build_expense_budget_execution_status()

    @router.post("/api/expense-budget-execution/admin/framework-preview")
    async def preview_expense_framework_sync(file: UploadFile = File(...)):
        file_name, raw = await _read_upload_file(file)
        parsed = _parse_framework_source_bytes(file_name, raw)
        return await _preview_expense_framework_sync_service(parsed)

    @router.post("/api/expense-budget-execution/admin/framework-sync")
    async def sync_expense_framework(
        file: UploadFile = File(...),
        apply_to_master_data: bool = Form(True),
    ):
        file_name, raw = await _read_upload_file(file)
        parsed = _parse_framework_source_bytes(file_name, raw)
        return await _sync_expense_framework_service(
            parsed,
            apply_to_master_data=apply_to_master_data,
        )

    @router.post("/api/expense-budget-execution/export")
    async def export_expense_budget_execution(body: ExpenseBudgetExecutionExportRequest):
        options = build_expense_budget_execution_export_options(body)
        selection = build_expense_budget_execution_export_selection(body)

        try:
            report = await _resolve_export_report_payload_service(
                editable_context_provider=editable_context_provider,
                selection=selection,
            )
        except ExpenseBudgetExecutionReportError as exc:
            raise expense_budget_execution_report_http_error(exc) from exc

        try:
            export = build_expense_budget_execution_export(report, options)
        except ExpenseBudgetExecutionExportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return expense_budget_execution_workbook_response(export)

    return router
