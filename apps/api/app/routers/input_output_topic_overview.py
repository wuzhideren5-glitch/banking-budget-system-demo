from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.services.export_common import workbook_streaming_response
from app.services.input_output_topic_overview import (
    build_input_output_topic_meta,
    build_input_output_topic_report,
    build_input_output_topic_workbook,
)


def build_input_output_topic_overview_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/input-output-topic-overview/meta")
    async def get_input_output_topic_overview_meta():
        return await build_input_output_topic_meta()

    @router.get("/api/input-output-topic-overview/report")
    async def get_input_output_topic_overview_report(
        entity_name: str = Query("微众银行"),
        report_month: str = Query(..., description="YYYY-MM"),
        group_name: str | None = Query(None),
        product_codes: list[str] | None = Query(None),
        amount_unit: str = Query("ten_thousand"),
    ):
        try:
            return await build_input_output_topic_report(
                entity_name=entity_name,
                report_month=report_month,
                group_name=group_name,
                product_codes=product_codes,
                amount_unit=amount_unit,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/api/input-output-topic-overview/export")
    async def export_input_output_topic_overview(
        entity_name: str = Query("微众银行"),
        report_month: str = Query(..., description="YYYY-MM"),
        group_name: str | None = Query(None),
        product_codes: list[str] | None = Query(None),
        amount_unit: str = Query("ten_thousand"),
        view_mode: Literal["total", "detail"] = Query("total"),
    ):
        try:
            report = await build_input_output_topic_report(
                entity_name=entity_name,
                report_month=report_month,
                group_name=group_name,
                product_codes=product_codes,
                amount_unit=amount_unit,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        wb = build_input_output_topic_workbook(report, view_mode=view_mode)
        filename = f"投入产出专题概览_{'分产品明细' if view_mode == 'detail' else '全行总表'}_{report_month}.xlsx"
        return workbook_streaming_response(
            wb,
            filename=filename,
            fallback_filename="input-output-topic-overview.xlsx",
        )

    return router
