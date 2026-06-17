from __future__ import annotations

from typing import Awaitable, Callable

import aiosqlite
from fastapi import APIRouter

from app.core.db_paths import common_db_path
from app.metric_tree_paths import load_metric_tree_with_data_accounts
from app.schemas import ChartMetricTreeNodeDto, ChartVersionItemDto, ChartVersionOptionsResponseDto


def build_chart_readonly_router(
    chart_version_options_provider: Callable[[], Awaitable[list[ChartVersionItemDto]]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/chart/version-options", response_model=ChartVersionOptionsResponseDto)
    async def chart_version_options():
        return ChartVersionOptionsResponseDto(options=await chart_version_options_provider())

    @router.get("/api/chart/metric-tree", response_model=list[ChartMetricTreeNodeDto])
    async def chart_metric_tree():
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            roots = await load_metric_tree_with_data_accounts(db)

        def _to_dto(raw_node: dict) -> ChartMetricTreeNodeDto:
            children = [child for child in raw_node.get("children", []) if child.get("type") == "metric"]
            return ChartMetricTreeNodeDto(
                metric_node_code=str(raw_node["code"]),
                metric_node_name=str(raw_node["name"]),
                is_summary=True,
                children=[_to_dto(child) for child in children],
            )

        return [_to_dto(node) for node in roots if node.get("type") == "metric"]

    return router
