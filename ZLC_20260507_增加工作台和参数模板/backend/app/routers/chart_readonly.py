from __future__ import annotations

from typing import Any, Awaitable, Callable

import aiosqlite
from fastapi import APIRouter

from app.db_paths import common_db_path
from app.schemas import ChartReportTreeNodeDto, ChartVersionItemDto, ChartVersionOptionsResponseDto


def build_chart_readonly_router(
    chart_version_options_provider: Callable[[], Awaitable[list[ChartVersionItemDto]]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/chart/version-options", response_model=ChartVersionOptionsResponseDto)
    async def chart_version_options():
        return ChartVersionOptionsResponseDto(options=await chart_version_options_provider())

    @router.get("/api/chart/report-tree", response_model=list[ChartReportTreeNodeDto])
    async def chart_report_tree():
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                """
                SELECT report_acct_code, report_acct_name, parent_code, is_summary
                FROM report_account
                ORDER BY report_acct_code
                """
            )
            rows = await cur.fetchall()

        node_map: dict[str, dict[str, Any]] = {}
        roots: list[dict[str, Any]] = []
        for row in rows:
            code = str(row[0])
            node_map[code] = {
                "report_acct_code": code,
                "report_acct_name": str(row[1]),
                "parent_code": str(row[2]) if row[2] else None,
                "is_summary": bool(row[3]),
                "children": [],
            }
        for code, node in node_map.items():
            parent = node["parent_code"]
            if parent and parent in node_map:
                node_map[parent]["children"].append(node)
            else:
                roots.append(node)

        def _to_dto(raw_node: dict[str, Any]) -> ChartReportTreeNodeDto:
            children = sorted(raw_node["children"], key=lambda c: c["report_acct_code"])
            return ChartReportTreeNodeDto(
                report_acct_code=raw_node["report_acct_code"],
                report_acct_name=raw_node["report_acct_name"],
                is_summary=bool(raw_node["is_summary"]),
                children=[_to_dto(child) for child in children],
            )

        return [_to_dto(node) for node in sorted(roots, key=lambda n: n["report_acct_code"])]

    return router
