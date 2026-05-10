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

    @router.get(
        "/api/forecast-workbench/overview",
        response_model=ForecastWorkbenchOverviewResponse,
    )
    async def get_forecast_workbench_overview():
        budget_path = budget_db_path(settings.budget_year)
        async with aiosqlite.connect(budget_path) as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
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
            await cdb.execute("PRAGMA foreign_keys = ON")
            cdb.row_factory = aiosqlite.Row

            cur = await cdb.execute("SELECT COUNT(*) FROM forecast_workbench_layout")
            layout_count = int((await cur.fetchone())[0] or 0)

            cur = await cdb.execute("SELECT COUNT(*) FROM forecast_line_binding")
            binding_count = int((await cur.fetchone())[0] or 0)

            cur = await cdb.execute("SELECT COUNT(*) FROM data_account")
            data_account_count = int((await cur.fetchone())[0] or 0)

            cur = await cdb.execute("SELECT COUNT(*) FROM assumption_parameter WHERE is_enabled = 1")
            parameter_count = int((await cur.fetchone())[0] or 0)

            cur = await cdb.execute("SELECT COUNT(*) FROM assumption_rule_template WHERE is_enabled = 1")
            template_count = int((await cur.fetchone())[0] or 0)

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

            cur = await cdb.execute(
                "SELECT data_acct_code AS code, data_acct_name AS name FROM data_account"
            )
            data_account_names = {str(r["code"]): str(r["name"]) for r in await cur.fetchall()}

            cur = await cdb.execute(
                "SELECT parameter_code AS code, parameter_name AS name FROM assumption_parameter"
            )
            parameter_names = {str(r["code"]): str(r["name"]) for r in await cur.fetchall()}

            cur = await cdb.execute(
                "SELECT rule_code AS code, rule_name AS name FROM assumption_rule_template"
            )
            template_names = {str(r["code"]): str(r["name"]) for r in await cur.fetchall()}

            cur = await cdb.execute(
                "SELECT report_acct_code AS code, report_acct_name AS name FROM report_account"
            )
            report_names = {str(r["code"]): str(r["name"]) for r in await cur.fetchall()}

        binding_name_maps = {
            "data_account": data_account_names,
            "assumption_parameter": parameter_names,
            "rule_template": template_names,
            "report_account": report_names,
        }

        bindings_by_line: dict[str, list[ForecastWorkbenchBindingRow]] = defaultdict(list)
        for row in binding_rows:
            binding_type = str(row["binding_type"] or "").strip()
            binding_code = str(row["binding_code"] or "").strip()
            resolved_name = str(row["binding_name"] or "").strip() or binding_name_maps.get(binding_type, {}).get(binding_code)
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
            layout_count=layout_count,
            binding_count=binding_count,
            bound_line_count=bound_line_count,
            unbound_line_count=max(layout_count - bound_line_count, 0),
            data_account_count=data_account_count,
            parameter_count=parameter_count,
            template_count=template_count,
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
