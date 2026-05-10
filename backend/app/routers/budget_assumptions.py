from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, HTTPException, Query

from app.db_paths import common_db_path
from app.schemas import (
    AssumptionImpactItem,
    AssumptionImpactResponse,
    AssumptionParameterCreate,
    AssumptionParameterRow,
    AssumptionParameterUpdate,
    AssumptionRuleTemplateRow,
    AssumptionRuleTemplateUpdate,
    AssumptionValueBatchUpsert,
    AssumptionValueRow,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_code(value: str) -> str:
    return value.strip().upper()


def build_budget_assumptions_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/budget-assumptions/parameters", response_model=list[AssumptionParameterRow])
    async def list_assumption_parameters():
        async with aiosqlite.connect(common_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT parameter_code, parameter_name, category, value_type, scope_type,
                       time_granularity, apply_products, input_mode, value_formula,
                       source_data_code, default_unit, is_enabled, remark, create_time, update_time
                FROM assumption_parameter
                ORDER BY category, parameter_code
                """
            )
            rows = await cur.fetchall()
        return [AssumptionParameterRow(**dict(row)) for row in rows]

    @router.post("/api/budget-assumptions/parameters", response_model=AssumptionParameterRow)
    async def create_assumption_parameter(body: AssumptionParameterCreate):
        now = _iso_now()
        code = _clean_code(body.parameter_code)
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute("SELECT 1 FROM assumption_parameter WHERE parameter_code = ?", (code,))
            if await cur.fetchone():
                raise HTTPException(status_code=409, detail="参数编码已存在")
            await db.execute(
                """
                INSERT INTO assumption_parameter(
                  parameter_code, parameter_name, category, value_type, scope_type,
                  time_granularity, apply_products, input_mode, value_formula,
                  source_data_code, default_unit, is_enabled, remark, create_time, update_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    code,
                    body.parameter_name,
                    body.category,
                    body.value_type,
                    body.scope_type,
                    body.time_granularity,
                    body.apply_products,
                    body.input_mode,
                    body.value_formula,
                    _clean_code(body.source_data_code) if body.source_data_code else None,
                    body.default_unit,
                    body.remark,
                    now,
                    now,
                ),
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM assumption_parameter WHERE parameter_code = ?", (code,))
            row = await cur.fetchone()
        return AssumptionParameterRow(**dict(row))

    @router.patch("/api/budget-assumptions/parameters/{parameter_code}", response_model=AssumptionParameterRow)
    async def update_assumption_parameter(parameter_code: str, body: AssumptionParameterUpdate):
        current_code = _clean_code(parameter_code)
        next_code = current_code
        updates: list[str] = []
        values: list[object] = []
        for field_name in (
            "parameter_name",
            "category",
            "value_type",
            "scope_type",
            "time_granularity",
            "apply_products",
            "input_mode",
            "value_formula",
            "source_data_code",
            "default_unit",
            "remark",
        ):
            value = getattr(body, field_name)
            if value is not None:
                updates.append(f"{field_name} = ?")
                values.append(_clean_code(value) if field_name == "source_data_code" and value else value)
        if body.parameter_code is not None:
            proposed_code = _clean_code(body.parameter_code)
            if proposed_code != current_code:
                next_code = proposed_code
                updates.append("parameter_code = ?")
                values.append(next_code)
        if body.is_enabled is not None:
            updates.append("is_enabled = ?")
            values.append(1 if body.is_enabled else 0)
        if not updates:
            raise HTTPException(status_code=400, detail="未提供更新内容")
        updates.append("update_time = ?")
        values.append(_iso_now())
        values.append(current_code)

        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute("SELECT 1 FROM assumption_parameter WHERE parameter_code = ?", (current_code,))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="参数不存在")
            if next_code != current_code:
                cur = await db.execute("SELECT 1 FROM assumption_parameter WHERE parameter_code = ?", (next_code,))
                if await cur.fetchone():
                    raise HTTPException(status_code=409, detail="目标参数编码已存在")
                cur = await db.execute(
                    "SELECT COUNT(*) FROM assumption_value WHERE parameter_code = ?",
                    (current_code,),
                )
                if int((await cur.fetchone())[0] or 0) > 0:
                    raise HTTPException(status_code=409, detail="该参数已有参数值，请先清理后再修改编码")
            await db.execute(f"UPDATE assumption_parameter SET {', '.join(updates)} WHERE parameter_code = ?", values)
            await db.commit()
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM assumption_parameter WHERE parameter_code = ?", (next_code,))
            row = await cur.fetchone()
        return AssumptionParameterRow(**dict(row))

    @router.get("/api/budget-assumptions/values", response_model=list[AssumptionValueRow])
    async def list_assumption_values(
        budget_year: int = Query(...),
        version_id: int = Query(...),
        parameter_code: str | None = Query(None),
        scenario_code: str = Query("BASE"),
    ):
        sql = """
            SELECT parameter_code, budget_year, version_id, scenario_code,
                   product_scope_key, product_code, month_index, value, update_time
            FROM assumption_value
            WHERE budget_year = ? AND version_id = ? AND scenario_code = ?
        """
        params: list[object] = [budget_year, version_id, _clean_code(scenario_code)]
        if parameter_code:
            sql += " AND parameter_code = ?"
            params.append(_clean_code(parameter_code))
        sql += " ORDER BY parameter_code, product_scope_key, month_index"
        async with aiosqlite.connect(common_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
        return [AssumptionValueRow(**dict(row)) for row in rows]

    @router.put("/api/budget-assumptions/values", response_model=list[AssumptionValueRow])
    async def upsert_assumption_values(body: AssumptionValueBatchUpsert):
        if not body.items:
            return []
        now = _iso_now()
        expanded = body.items
        if body.fill_from_month is not None and body.fill_to_month is not None and body.fill_from_month <= body.fill_to_month:
            expanded = []
            for item in body.items:
                if item.month_index not in (0, body.fill_from_month):
                    expanded.append(item)
                    continue
                expanded.extend(
                    item.model_copy(update={"month_index": month_index})
                    for month_index in range(body.fill_from_month, body.fill_to_month + 1)
                )
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            for item in expanded:
                await db.execute(
                    """
                    INSERT INTO assumption_value(
                      parameter_code, budget_year, version_id, scenario_code,
                      product_scope_key, product_code, month_index, value, create_time, update_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(parameter_code, budget_year, version_id, scenario_code, product_scope_key, month_index)
                    DO UPDATE SET value = excluded.value, product_code = excluded.product_code, update_time = excluded.update_time
                    """,
                    (
                        _clean_code(item.parameter_code),
                        body.budget_year,
                        body.version_id,
                        _clean_code(item.scenario_code) or "BASE",
                        item.product_scope_key,
                        _clean_code(item.product_code) if item.product_code else None,
                        item.month_index,
                        item.value,
                        now,
                        now,
                    ),
                )
            await db.commit()
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT parameter_code, budget_year, version_id, scenario_code,
                       product_scope_key, product_code, month_index, value, update_time
                FROM assumption_value
                WHERE budget_year = ? AND version_id = ?
                ORDER BY parameter_code, product_scope_key, month_index
                """,
                (body.budget_year, body.version_id),
            )
            rows = await cur.fetchall()
        return [AssumptionValueRow(**dict(row)) for row in rows]

    @router.get("/api/budget-assumptions/rule-templates", response_model=list[AssumptionRuleTemplateRow])
    async def list_assumption_rule_templates():
        async with aiosqlite.connect(common_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT rule_code, rule_name, rule_type, config_json, is_enabled, remark, create_time, update_time
                FROM assumption_rule_template
                WHERE is_enabled = 1
                ORDER BY rule_code
                """
            )
            rows = await cur.fetchall()
        return [AssumptionRuleTemplateRow(**dict(row)) for row in rows]

    @router.patch("/api/budget-assumptions/rule-templates/{rule_code}", response_model=AssumptionRuleTemplateRow)
    async def update_assumption_rule_template(rule_code: str, body: AssumptionRuleTemplateUpdate):
        updates: list[str] = []
        values: list[object] = []
        for field_name in ("rule_name", "config_json", "remark"):
            value = getattr(body, field_name)
            if value is not None:
                updates.append(f"{field_name} = ?")
                values.append(value)
        if body.is_enabled is not None:
            updates.append("is_enabled = ?")
            values.append(1 if body.is_enabled else 0)
        if not updates:
            raise HTTPException(status_code=400, detail="未提供更新内容")
        updates.append("update_time = ?")
        values.append(_iso_now())
        values.append(_clean_code(rule_code))

        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute("SELECT 1 FROM assumption_rule_template WHERE rule_code = ?", (_clean_code(rule_code),))
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="模板不存在")
            await db.execute(f"UPDATE assumption_rule_template SET {', '.join(updates)} WHERE rule_code = ?", values)
            await db.commit()
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM assumption_rule_template WHERE rule_code = ?", (_clean_code(rule_code),))
            row = await cur.fetchone()
        return AssumptionRuleTemplateRow(**dict(row))

    @router.get("/api/budget-assumptions/impact/{parameter_code}", response_model=AssumptionImpactResponse)
    async def get_assumption_impact(parameter_code: str):
        code = _clean_code(parameter_code)
        async with aiosqlite.connect(common_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT parameter_name FROM assumption_parameter WHERE parameter_code = ?", (code,))
            parameter_row = await cur.fetchone()
            if not parameter_row:
                raise HTTPException(status_code=404, detail="参数不存在")
            items: list[AssumptionImpactItem] = []
            cur = await db.execute(
                """
                SELECT rule_code, rule_name
                FROM assumption_rule_template
                WHERE IFNULL(config_json, '') LIKE ?
                ORDER BY rule_code
                """,
                (f"%{code}%",),
            )
            for row in await cur.fetchall():
                items.append(
                    AssumptionImpactItem(
                        rule_code=str(row["rule_code"]),
                        rule_name=str(row["rule_name"]),
                        match_source="模板配置",
                    )
                )
            cur = await db.execute(
                """
                SELECT data_acct_code, data_acct_name, budget_rule_code
                FROM data_account
                WHERE IFNULL(budget_rule_config_json, '') LIKE ?
                ORDER BY data_acct_code
                """,
                (f"%{code}%",),
            )
            for row in await cur.fetchall():
                items.append(
                    AssumptionImpactItem(
                        rule_code=str(row["budget_rule_code"] or "") or None,
                        data_acct_code=str(row["data_acct_code"]),
                        data_acct_name=str(row["data_acct_name"]),
                        match_source="数据科目模板绑定",
                    )
                )
        return AssumptionImpactResponse(
            parameter_code=code,
            parameter_name=str(parameter_row["parameter_name"]),
            items=items,
        )

    return router
