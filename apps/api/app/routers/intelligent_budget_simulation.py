"""智能预算模拟工作台 API."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

import aiomysql
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.database import get_pool
from app.services.export_common import excel_streaming_response
from app.services.intelligent_budget_export import build_intelligent_budget_simulation_export
from app.services.intelligent_budget_solver import (
    IntelligentBudgetProductProfile,
    IntelligentBudgetSolveRequest,
    solve_intelligent_budget,
)
from app.services.intelligent_budget_product_loader import load_product_profiles_from_db
from app.services.intelligent_budget_target_parser import parse_leadership_target
from app.services.intelligent_budget_target_parser import build_deepseek_target_provider
from app.core.db_paths import common_db_path, budget_db_path
from app.core.config import settings


class ParseTargetRequest(BaseModel):
    target_text: str


class CreateTaskRequest(BaseModel):
    target_text: str
    confirmed: bool = False


class ExportRequest(BaseModel):
    task_id: str


def _load_product_profiles() -> list[IntelligentBudgetProductProfile]:
    """从数据库加载产品配置，替代硬编码的默认产品列表。"""
    return load_product_profiles_from_db(
        common_db_path=common_db_path(),
        budget_db_path=budget_db_path(settings.budget_year),
    )


@asynccontextmanager
async def _task_store_connection() -> AsyncIterator[aiomysql.Connection]:
    try:
        pool = get_pool()
    except RuntimeError:
        pool = None
    raw_pool = getattr(pool, "_pool", None) if pool is not None else None
    pool_loop = getattr(raw_pool, "_loop", None)
    if raw_pool is not None and pool_loop is asyncio.get_running_loop():
        async with pool.acquire() as conn:
            yield conn
        return

    conn = await aiomysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
        init_command="SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
    )
    try:
        yield conn
    finally:
        conn.close()
        await conn.ensure_closed()


async def _ensure_task_store_table(db_path: Path) -> None:
    """确保 intelligent_budget_tasks 表存在于 MySQL 当前库中。"""
    del db_path
    async with _task_store_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT 1
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                LIMIT 1
                """,
                ("intelligent_budget_tasks",),
            )
            if await cur.fetchone():
                return
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS intelligent_budget_tasks (
                    task_id VARCHAR(255) PRIMARY KEY,
                    target_text VARCHAR(255) NOT NULL,
                    parsed_target LONGTEXT NOT NULL,
                    status VARCHAR(255) NOT NULL,
                    stage VARCHAR(255) NOT NULL,
                    step_summary LONGTEXT,
                    baseline_solution LONGTEXT,
                    solutions LONGTEXT NOT NULL,
                    negotiation_message LONGTEXT,
                    negotiation_suggestions LONGTEXT,
                    created_at VARCHAR(255) NOT NULL DEFAULT (NOW())
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )


def _task_store_row(task: dict[str, Any]) -> tuple[Any, ...]:
    return (
        task["task_id"],
        task["target_text"],
        json.dumps(task["parsed_target"], ensure_ascii=False),
        task["status"],
        task["stage"],
        json.dumps(task["step_summary"], ensure_ascii=False) if task.get("step_summary") else None,
        json.dumps(task["baseline_solution"], ensure_ascii=False) if task.get("baseline_solution") else None,
        json.dumps(task["solutions"], ensure_ascii=False),
        task.get("negotiation_message"),
        json.dumps(task["negotiation_suggestions"], ensure_ascii=False)
        if task.get("negotiation_suggestions")
        else None,
    )


async def _save_task(db_path: Path, task: dict[str, Any]) -> None:
    """将任务持久化到 MySQL。"""
    del db_path
    async with _task_store_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO intelligent_budget_tasks
                    (task_id, target_text, parsed_target, status, stage, step_summary,
                     baseline_solution, solutions, negotiation_message, negotiation_suggestions)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    target_text = %s,
                    parsed_target = %s,
                    status = %s,
                    stage = %s,
                    step_summary = %s,
                    baseline_solution = %s,
                    solutions = %s,
                    negotiation_message = %s,
                    negotiation_suggestions = %s
                """,
                _task_store_row(task) + _task_store_row(task)[1:],
            )


async def _load_task(db_path: Path, task_id: str) -> dict[str, Any] | None:
    """从 MySQL 加载任务并还原 JSON 字段。"""
    del db_path
    async with _task_store_connection() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT * FROM intelligent_budget_tasks WHERE task_id = %s", (task_id,)
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        row = dict(row)
        # 还原 JSON 字段
        for field in ("parsed_target", "step_summary", "baseline_solution", "solutions", "negotiation_suggestions"):
            if row.get(field) and isinstance(row[field], str):
                row[field] = json.loads(row[field])
        return row


def build_intelligent_budget_simulation_router(deepseek_client: Any | None = None) -> APIRouter:
    router = APIRouter()
    deepseek_json_provider = build_deepseek_target_provider(deepseek_client)

    # 启动时确保表存在
    async def on_startup() -> None:
        await _ensure_task_store_table(common_db_path())

    router.add_event_handler("startup", on_startup)

    def parsed_target_dict(target_text: str) -> dict[str, Any]:
        return asdict(parse_leadership_target(target_text, deepseek_json_provider=deepseek_json_provider))

    @router.post("/api/intelligent-budget-simulation/parse-target")
    async def parse_target(body: ParseTargetRequest):
        return parsed_target_dict(body.target_text)

    @router.post("/api/intelligent-budget-simulation/tasks")
    async def create_task(body: CreateTaskRequest):
        if not body.confirmed:
            raise HTTPException(status_code=400, detail="请先确认AI解析后的目标和约束，再开始求解。")
        parsed = parse_leadership_target(body.target_text, deepseek_json_provider=deepseek_json_provider)
        result = solve_intelligent_budget(
            IntelligentBudgetSolveRequest(
                parsed_target=parsed,
                product_profiles=_load_product_profiles(),
                required_solution_count=10,
            )
        )
        task_id = uuid4().hex
        task = {
            "task_id": task_id,
            "target_text": body.target_text,
            "parsed_target": asdict(parsed),
            "status": result.status,
            "stage": "completed" if result.status == "completed" else "negotiation",
            "step_summary": result.step_summary,
            "baseline_solution": asdict(result.baseline_solution),
            "solutions": [asdict(solution) for solution in result.solutions],
            "negotiation_message": result.negotiation_message,
            "negotiation_suggestions": result.negotiation_suggestions,
        }
        # 持久化到 MySQL
        await _save_task(common_db_path(), task)
        return task

    @router.get("/api/intelligent-budget-simulation/tasks/{task_id}")
    async def read_task(task_id: str):
        task = await _load_task(common_db_path(), task_id)
        if not task:
            raise HTTPException(status_code=404, detail="未找到智能预算模拟任务。")
        return task

    @router.post("/api/intelligent-budget-simulation/export")
    async def export_task(body: ExportRequest):
        task = await _load_task(common_db_path(), body.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="未找到智能预算模拟任务。")
        out, filename = build_intelligent_budget_simulation_export(task)
        return excel_streaming_response(out, filename=filename, fallback_filename=filename)

    return router
