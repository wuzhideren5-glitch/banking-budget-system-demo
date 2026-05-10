from __future__ import annotations

from collections import defaultdict

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.db_paths import budget_db_path, common_db_path
from app.schemas import (
    ForecastWorkbenchBindingRow,
    ForecastWorkbenchLineRow,
    ForecastWorkbenchOverviewResponse,
    ForecastWorkbenchSummary,
)


def build_forecast_workbench_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/forecast-workbench/overview", response_model=ForecastWorkbenchOverviewResponse)
    async def get_forecast_workbench_overview():
        async with aiosqlite.connect(budget_db_path(settings.budget_year)) as bdb:
            cur = await bdb.execute(
                """
                SELECT version_id, version_name, current_month
                FROM version
                ORDER BY version_id DESC
                LIMIT 1
                """
            )
            version_row = await cur.fetchone()
        if not version_row:
            raise HTTPException(status_code=500, detail="当前年度版本不存在")

        async with aiosqlite.connect(common_db_path()) as cdb:
            cdb.row_factory = aiosqlite.Row
            count_tables = {
                "layout_count": "forecast_workbench_layout",
                "binding_count": "forecast_line_binding",
                "data_account_count": "data_account",
                "parameter_count": "assumption_parameter WHERE is_enabled = 1",
                "template_count": "assumption_rule_template WHERE is_enabled = 1",
            }
            counts: dict[str, int] = {}
            for key, table_expr in count_tables.items():
                cur = await cdb.execute(f"SELECT COUNT(*) FROM {table_expr}")
                counts[key] = int((await cur.fetchone())[0] or 0)

            cur = await cdb.execute(
                """
                SELECT line_code, line_name, line_group, line_category, display_mode,
                       sort_order, is_enabled, binding_hint, remark
                FROM forecast_workbench_layout
                WHERE is_enabled = 1
                ORDER BY sort_order, line_code
                """
            )
            line_rows = await cur.fetchall()

            cur = await cdb.execute(
                """
                SELECT id, line_code, binding_type, binding_code, binding_name,
                       binding_role, sort_order, remark
                FROM forecast_line_binding
                ORDER BY line_code, sort_order, id
                """
            )
            binding_rows = await cur.fetchall()

            name_maps: dict[str, dict[str, str]] = {}
            for binding_type, table_name, code_col, name_col in (
                ("data_account", "data_account", "data_acct_code", "data_acct_name"),
                ("assumption_parameter", "assumption_parameter", "parameter_code", "parameter_name"),
                ("assumption_rule_template", "assumption_rule_template", "rule_code", "rule_name"),
                ("rule_template", "assumption_rule_template", "rule_code", "rule_name"),
                ("report_account", "report_account", "report_acct_code", "report_acct_name"),
            ):
                cur = await cdb.execute(f"SELECT {code_col} AS code, {name_col} AS name FROM {table_name}")
                name_maps[binding_type] = {str(row["code"]): str(row["name"]) for row in await cur.fetchall()}

        bindings_by_line: dict[str, list[ForecastWorkbenchBindingRow]] = defaultdict(list)
        for row in binding_rows:
            binding_type = str(row["binding_type"] or "").strip()
            binding_code = str(row["binding_code"] or "").strip()
            resolved_name = str(row["binding_name"] or "").strip() or name_maps.get(binding_type, {}).get(binding_code)
            bindings_by_line[str(row["line_code"])].append(
                ForecastWorkbenchBindingRow(
                    id=int(row["id"]),
                    line_code=str(row["line_code"]),
                    binding_type=binding_type,
                    binding_code=binding_code,
                    binding_name=resolved_name or None,
                    binding_role=str(row["binding_role"] or ""),
                    sort_order=int(row["sort_order"] or 0),
                    remark=str(row["remark"]) if row["remark"] is not None else None,
                )
            )

        lines: list[ForecastWorkbenchLineRow] = []
        bound_line_count = 0
        for row in line_rows:
            line_bindings = bindings_by_line.get(str(row["line_code"]), [])
            if line_bindings:
                bound_line_count += 1
            lines.append(
                ForecastWorkbenchLineRow(
                    line_code=str(row["line_code"]),
                    line_name=str(row["line_name"]),
                    line_group=str(row["line_group"]),
                    line_category=str(row["line_category"]),
                    display_mode=str(row["display_mode"] or "detail"),
                    sort_order=int(row["sort_order"] or 0),
                    is_enabled=bool(int(row["is_enabled"] or 0)),
                    binding_hint=str(row["binding_hint"]) if row["binding_hint"] is not None else None,
                    remark=str(row["remark"]) if row["remark"] is not None else None,
                    binding_count=len(line_bindings),
                    bindings=line_bindings,
                )
            )

        summary = ForecastWorkbenchSummary(
            **counts,
            bound_line_count=bound_line_count,
            unbound_line_count=max(counts["layout_count"] - bound_line_count, 0),
        )
        return ForecastWorkbenchOverviewResponse(
            budget_year=settings.budget_year,
            version_id=int(version_row[0]),
            version_name=str(version_row[1]),
            current_month=int(version_row[2] or 1),
            summary=summary,
            lines=lines,
        )

    return router
