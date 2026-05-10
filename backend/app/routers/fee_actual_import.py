"""费用实际数模块 API 路由。"""
from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiosqlite
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.db_paths import common_db_path
from app.fee_actual_import import generate_fee_actual_template, run_fee_actual_import


def build_fee_actual_import_router(
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    recalculate_product_formula_rows: Callable[..., Awaitable[int]],
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter()

    # ── 模板下载 ───────────────────────────────────────

    @router.get("/api/fee-actual/template")
    async def download_fee_actual_template():
        """下载费用实际导入模板（预填系统科目及产品代码）。"""
        async with aiosqlite.connect(common_db_path()) as cdb:
            await cdb.execute("PRAGMA foreign_keys = ON")
            cur = await cdb.execute(
                """
                SELECT data_acct_code, data_acct_name
                FROM data_account
                WHERE data_acct_code LIKE 'C7%'
                   OR data_acct_code LIKE 'C8%'
                ORDER BY data_acct_code
                """
            )
            fee_accounts = [
                {"data_acct_code": str(r[0]), "data_acct_name": str(r[1])}
                for r in await cur.fetchall()
            ]
            cur = await cdb.execute(
                "SELECT product_code, product_name FROM product_type ORDER BY product_code"
            )
            products = [
                {"product_code": str(r[0]), "product_name": str(r[1])}
                for r in await cur.fetchall()
            ]

        xlsx_bytes = await asyncio.to_thread(
            generate_fee_actual_template, fee_accounts, products
        )
        return StreamingResponse(
            BytesIO(xlsx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="fee_actual_template.xlsx"',
            },
        )

    # ── 预览 ────────────────────────────────────────────

    @router.post("/api/fee-actual/preview")
    async def preview_fee_actual_import(
        file: UploadFile = File(...),
        year_month: str = Query(..., description="YYYY-MM"),
    ):
        if not file.filename or not str(file.filename).lower().endswith((".xlsx", ".xlsm")):
            raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xlsm 文件")

        raw = await file.read()
        if len(raw) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件过大（上限 15MB）")

        editable_budget_path, editable_year, editable_vid = await editable_context_provider()
        if editable_vid is None:
            raise HTTPException(status_code=409, detail="无可编辑版本")

        import sqlite3

        cconn = sqlite3.connect(str(common_db_path()))
        cconn.execute("PRAGMA foreign_keys = ON")
        bconn = sqlite3.connect(str(editable_budget_path))
        bconn.execute("PRAGMA foreign_keys = ON")

        try:
            result = await asyncio.to_thread(
                run_fee_actual_import,
                raw,
                year_month,
                editable_vid,
                editable_year,
                cconn,
                bconn,
                preview_only=True,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            cconn.close()
            bconn.close()

        # 汇总统计
        total_data_cells = 0
        matched_cells = 0
        error_cells = 0
        skipped_cells = 0
        empty_cells = 0

        for row in result.rows:
            for m in row.months:
                total_data_cells += 1
                if m.status == "preview_ok":
                    matched_cells += 1
                elif m.status == "error":
                    error_cells += 1
                elif m.status == "skipped":
                    skipped_cells += 1
                elif m.status == "empty":
                    empty_cells += 1

        # 预览样本（前 20 行）
        sample_rows: list[dict] = []
        for row in result.rows[:20]:
            month_vals: dict[str, Any] = {}
            for m in row.months:
                month_vals[f"M{m.month:02d}"] = {
                    "value": m.value_text,
                    "status": m.status,
                }
            sample_rows.append({
                "excel_row": row.excel_row,
                "data_acct_code": row.data_acct_code,
                "product_code": row.product_code,
                "fee_type": row.fee_type,
                "note": row.note,
                "months": month_vals,
            })

        return {
            "file_name": file.filename,
            "year_month": year_month,
            "version_id": editable_vid,
            "budget_year": editable_year,
            "total_rows": len(result.rows),
            "total_cells": total_data_cells,
            "matched_cells": matched_cells,
            "error_cells": error_cells,
            "skipped_cells": skipped_cells,
            "empty_cells": empty_cells,
            "sample_rows": sample_rows,
        }

    # ── 执行导入 ────────────────────────────────────────

    @router.post("/api/fee-actual/apply")
    async def apply_fee_actual_import(
        file: UploadFile = File(...),
        year_month: str = Query(..., description="YYYY-MM"),
    ):
        if not file.filename or not str(file.filename).lower().endswith((".xlsx", ".xlsm")):
            raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xlsm 文件")

        raw = await file.read()
        if len(raw) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件过大（上限 15MB）")

        editable_budget_path, editable_year, editable_vid = await editable_context_provider()
        if editable_vid is None:
            raise HTTPException(status_code=409, detail="无可编辑版本")

        import sqlite3

        cconn = sqlite3.connect(str(common_db_path()))
        cconn.execute("PRAGMA foreign_keys = ON")
        bconn = sqlite3.connect(str(editable_budget_path))
        bconn.execute("PRAGMA foreign_keys = ON")

        try:
            result = await asyncio.to_thread(
                run_fee_actual_import,
                raw,
                year_month,
                editable_vid,
                editable_year,
                cconn,
                bconn,
                preview_only=False,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            cconn.close()
            bconn.close()

        # 全局公式重算（影响范围内产品）
        products_touched: set[str] = set()
        for row in result.rows:
            if row.product_code and row.product_code != "—":
                products_touched.add(row.product_code)

        for pc in sorted(products_touched):
            await recalculate_product_formula_rows(
                pc,
                editable_vid,
                budget_actual=1,
                budget_path=editable_budget_path,
                budget_year=editable_year,
            )

        # 错误详情
        error_rows: list[dict] = []
        for row in result.rows:
            if row.note:
                error_rows.append({
                    "excel_row": row.excel_row,
                    "data_acct_code": row.data_acct_code,
                    "product_code": row.product_code,
                    "fee_type": row.fee_type,
                    "note": row.note,
                })

        await write_operation_log(
            action_type="IMPORT",
            action_desc=f"费用实际数据导入，写入 {result.saved_cells} 个单元格",
            target_table="budget_data",
            affected_rows=result.saved_cells,
            after_data={
                "version_id": editable_vid,
                "budget_year": editable_year,
                "year_month": year_month,
                "saved_cells": result.saved_cells,
            },
        )

        return {
            "ok": True,
            "file_name": file.filename,
            "year_month": year_month,
            "version_id": editable_vid,
            "saved_cells": result.saved_cells,
            "total_rows": len(result.rows),
            "error_rows": error_rows,
        }

    return router
