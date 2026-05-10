from __future__ import annotations

import asyncio
from datetime import datetime
from io import BytesIO
import secrets
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import BudgetSummaryExportPivotRequest


def build_compare_summary_export_router(
    *,
    compare_formula_export_jobs: dict[str, dict[str, Any]],
    compare_formula_export_jobs_lock: asyncio.Lock,
    run_compare_formula_export_job: Callable[[str, BudgetSummaryExportPivotRequest], Awaitable[None]],
    export_compare_summary_full_pivot_callable: Callable[[], Awaitable[StreamingResponse]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/compare-summary/export-formula-workbook/start")
    async def start_compare_formula_workbook_export(body: BudgetSummaryExportPivotRequest):
        job_id = secrets.token_hex(16)
        async with compare_formula_export_jobs_lock:
            compare_formula_export_jobs[job_id] = {
                "status": "queued",
                "processed_sheets": 0,
                "total_sheets": 0,
                "message": "任务已创建",
                "error": "",
                "file_bytes": None,
                "filename": "",
                "created_at": datetime.now().timestamp(),
            }
        asyncio.create_task(run_compare_formula_export_job(job_id, body))
        return {"job_id": job_id}

    @router.get("/api/compare-summary/export-formula-workbook/status")
    async def get_compare_formula_workbook_export_status(job_id: str = Query(...)):
        async with compare_formula_export_jobs_lock:
            job = compare_formula_export_jobs.get(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="导出任务不存在")
            return {
                "job_id": job_id,
                "status": job.get("status", "queued"),
                "processed_sheets": int(job.get("processed_sheets", 0) or 0),
                "total_sheets": int(job.get("total_sheets", 0) or 0),
                "message": str(job.get("message", "") or ""),
                "error": str(job.get("error", "") or ""),
            }

    @router.get("/api/compare-summary/export-formula-workbook/download")
    async def download_compare_formula_workbook_export(job_id: str = Query(...)):
        async with compare_formula_export_jobs_lock:
            job = compare_formula_export_jobs.get(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="导出任务不存在")
            if str(job.get("status")) != "done":
                raise HTTPException(status_code=409, detail="导出任务尚未完成")
            file_bytes = job.get("file_bytes")
            if not isinstance(file_bytes, (bytes, bytearray)):
                raise HTTPException(status_code=500, detail="导出文件不存在")
            filename = str(job.get("filename") or "compare_summary_formula_workbook.xlsx")
        out = BytesIO(bytes(file_bytes))
        out.seek(0)
        return StreamingResponse(
            out,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/api/compare-summary/export-full-pivot")
    async def export_compare_summary_full_pivot():
        return await export_compare_summary_full_pivot_callable()

    return router
