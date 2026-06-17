from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter

from app.schemas import (
    ChartBarRequestDto,
    ChartPptExportRequestDto,
    ChartStackedRequestDto,
    ChartStackedResponseDto,
    ChartVersionItemDto,
)
from app.services.chart_data import ChartDataBuilder
from app.services.chart_ppt_export import build_chart_ppt_export_file
from app.services.export_common import binary_streaming_response


def build_chart_write_router(
    *,
    chart_version_options_provider: Callable[[], Awaitable[list[ChartVersionItemDto]]],
    extract_runtime_metric_ref_code_from_name: Callable[[str], str | None],
) -> APIRouter:
    router = APIRouter()
    chart_data_builder = ChartDataBuilder(
        chart_version_options_provider=chart_version_options_provider,
        extract_runtime_metric_ref_code_from_name=extract_runtime_metric_ref_code_from_name,
    )

    @router.post("/api/chart/stacked", response_model=ChartStackedResponseDto)
    async def chart_stacked(req: ChartStackedRequestDto):
        return await chart_data_builder.build_stacked_response(req)

    @router.post("/api/chart/bar", response_model=ChartStackedResponseDto)
    async def chart_bar(req: ChartBarRequestDto):
        """柱状图：横轴为期间（单版本）或版本（多版本）；本指标合计为一组柱，下级指标为分组多柱。"""
        return await chart_data_builder.build_bar_response(req)

    @router.post("/api/chart/export-ppt")
    async def chart_export_ppt(req: ChartPptExportRequestDto):
        export_file = build_chart_ppt_export_file(req)
        return binary_streaming_response(
            export_file.content,
            media_type=export_file.media_type,
            filename=export_file.filename,
            fallback_filename=export_file.filename,
        )

    return router
