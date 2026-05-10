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


def build_budget_assumptions_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/budget-assumptions/parameters", response_model=list[AssumptionParameterRow])
    async def list_assumption_parameters():
        async with aiosqlite.connect(common_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT parameter_code, parameter_name, category, value_type, scope_type,
                       time_granularity, apply_products, input_mode, value_formula, source_data_code,
                       default_unit, is_enabled, remark, create_time, update_time
                FROM assumption_parameter
                ORDER BY category, parameter_code
                """
            )
            rows = await cur.fetchall()
        return [AssumptionParameterRow(**dict(row)) for row in rows]

    @router.post("/api/budget-assumptions/parameters", response_model=AssumptionParameterRow)
    async def create_assumption_parameter(body: AssumptionParameterCreate):
        now = _iso_now()
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                "SELECT 1 FROM assumption_parameter WHERE parameter_code = ?",
                (body.parameter_code,),
            )
            if await cur.fetchone():
                raise HTTPException(status_code=409, detail="参数编码已存在")
            await db.execute(
                """
                INSERT INTO assumption_parameter(
                  parameter_code, parameter_name, category, value_type, scope_type,
                  time_granularity, apply_products, input_mode, value_formula, source_data_code,
                  default_unit, is_enabled, remark, create_time, update_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    body.parameter_code,
                    body.parameter_name,
                    body.category,
                    body.value_type,
                    body.scope_type,
                    body.time_granularity,
                    body.apply_products,
                    body.input_mode,
                    body.value_formula,
                    body.source_data_code,
                    body.default_unit,
                    body.remark,
                    now,
                    now,
                ),
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT parameter_code, parameter_name, category, value_type, scope_type,
                       time_granularity, apply_products, input_mode, value_formula, source_data_code,
                       default_unit, is_enabled, remark, create_time, update_time
                FROM assumption_parameter
                WHERE parameter_code = ?
                """,
                (body.parameter_code,),
            )
            row = await cur.fetchone()
        return AssumptionParameterRow(**dict(row))

    @router.patch("/api/budget-assumptions/parameters/{parameter_code}", response_model=AssumptionParameterRow)
    async def update_assumption_parameter(parameter_code: str, body: AssumptionParameterUpdate):
        updates: list[str] = []
        values: list[object] = []
        next_code = parameter_code.strip().upper()
        if body.parameter_code is not None:
            proposed = body.parameter_code.strip().upper()
            if proposed != next_code:
                updates.append("parameter_code = ?")
                values.append(proposed)
                next_code = proposed
        if body.parameter_name is not None:
            updates.append("parameter_name = ?")
            values.append(body.parameter_name)
        if body.category is not None:
            updates.append("category = ?")
            values.append(body.category)
        if body.value_type is not None:
            updates.append("value_type = ?")
            values.append(body.value_type)
        if body.scope_type is not None:
            updates.append("scope_type = ?")
            values.append(body.scope_type)
        if body.time_granularity is not None:
            updates.append("time_granularity = ?")
            values.append(body.time_granularity)
        if body.apply_products is not None:
            updates.append("apply_products = ?")
            values.append(body.apply_products)
        if body.input_mode is not None:
            updates.append("input_mode = ?")
            values.append(body.input_mode)
        if body.value_formula is not None:
            updates.append("value_formula = ?")
            values.append(body.value_formula)
        if body.source_data_code is not None:
            updates.append("source_data_code = ?")
            values.append(body.source_data_code)
        if body.default_unit is not None:
            updates.append("default_unit = ?")
            values.append(body.default_unit)
        if body.is_enabled is not None:
            updates.append("is_enabled = ?")
            values.append(1 if body.is_enabled else 0)
        if body.remark is not None:
            updates.append("remark = ?")
            values.append(body.remark)
        if not updates:
            raise HTTPException(status_code=400, detail="未提供更新内容")
        updates.append("update_time = ?")
        values.append(_iso_now())
        values.append(parameter_code.strip().upper())
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                "SELECT 1 FROM assumption_parameter WHERE parameter_code = ?",
                (parameter_code.strip().upper(),),
            )
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="参数不存在")
            if next_code != parameter_code.strip().upper():
                cur = await db.execute(
                    "SELECT 1 FROM assumption_parameter WHERE parameter_code = ?",
                    (next_code,),
                )
                if await cur.fetchone():
                    raise HTTPException(status_code=409, detail="目标参数编码已存在")
                cur = await db.execute(
                    "SELECT COUNT(*) FROM assumption_value WHERE parameter_code = ?",
                    (parameter_code.strip().upper(),),
                )
                bound_value_count = int((await cur.fetchone())[0] or 0)
                cur = await db.execute(
                    "SELECT COUNT(*) FROM data_account WHERE IFNULL(budget_rule_config_json, '') LIKE ?",
                    (f'%{parameter_code.strip().upper()}%',),
                )
                bound_template_count = int((await cur.fetchone())[0] or 0)
                if bound_value_count or bound_template_count:
                    raise HTTPException(
                        status_code=409,
                        detail="该参数已存在参数值或已被模板绑定，请先解除绑定后再修改编码",
                    )
            await db.execute(
                f"UPDATE assumption_parameter SET {', '.join(updates)} WHERE parameter_code = ?",
                values,
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT parameter_code, parameter_name, category, value_type, scope_type,
                       time_granularity, apply_products, input_mode, value_formula, source_data_code,
                       default_unit, is_enabled, remark, create_time, update_time
                FROM assumption_parameter
                WHERE parameter_code = ?
                """,
                (next_code,),
            )
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
        params: list[object] = [budget_year, version_id, scenario_code.strip().upper()]
        if parameter_code:
            sql += " AND parameter_code = ?"
            params.append(parameter_code.strip().upper())
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
        expanded_items = body.items
        if body.fill_from_month is not None and body.fill_to_month is not None and body.fill_from_month <= body.fill_to_month:
            cloned: list = []
            for item in body.items:
                if item.month_index not in (0, body.fill_from_month):
                    cloned.append(item)
                    continue
                for month_index in range(body.fill_from_month, body.fill_to_month + 1):
                    cloned.append(
                        item.model_copy(
                            update={
                                "month_index": month_index,
                            }
                        )
                    )
            expanded_items = cloned
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            for item in expanded_items:
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
                        item.parameter_code.strip().upper(),
                        body.budget_year,
                        body.version_id,
                        item.scenario_code.strip().upper() or "BASE",
                        item.product_scope_key or "",
                        item.product_code.strip().upper() if item.product_code else None,
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

    @router.get("/api/budget-assumptions/impact/{parameter_code}", response_model=AssumptionImpactResponse)
    async def get_assumption_impact(parameter_code: str):
        code = parameter_code.strip().upper()
        async with aiosqlite.connect(common_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT parameter_name
                FROM assumption_parameter
                WHERE parameter_code = ?
                """,
                (code,),
            )
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

    @router.patch("/api/budget-assumptions/rule-templates/{rule_code}", response_model=AssumptionRuleTemplateRow)
    async def update_assumption_rule_template(rule_code: str, body: AssumptionRuleTemplateUpdate):
        updates: list[str] = []
        values: list[object] = []
        if body.rule_name is not None:
            updates.append("rule_name = ?")
            values.append(body.rule_name)
        if body.config_json is not None:
            updates.append("config_json = ?")
            values.append(body.config_json)
        if body.is_enabled is not None:
            updates.append("is_enabled = ?")
            values.append(1 if body.is_enabled else 0)
        if body.remark is not None:
            updates.append("remark = ?")
            values.append(body.remark)
        if not updates:
            raise HTTPException(status_code=400, detail="未提供更新内容")
        updates.append("update_time = ?")
        values.append(_iso_now())
        values.append(rule_code.strip().upper())
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                "SELECT 1 FROM assumption_rule_template WHERE rule_code = ?",
                (rule_code.strip().upper(),),
            )
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="模板不存在")
            await db.execute(
                f"UPDATE assumption_rule_template SET {', '.join(updates)} WHERE rule_code = ?",
                values,
            )
            await db.commit()
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT rule_code, rule_name, rule_type, config_json, is_enabled, remark, create_time, update_time
                FROM assumption_rule_template
                WHERE rule_code = ?
                """,
                (rule_code.strip().upper(),),
            )
            row = await cur.fetchone()
        return AssumptionRuleTemplateRow(**dict(row))

    return router
