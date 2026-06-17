"""智能预算模拟工作台 API."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import app.core.aiosqlite_compat as aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


async def _ensure_task_store_table(db_path: Path) -> None:
    """确保 intelligent_budget_tasks 表存在于 common.db 中。"""
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligent_budget_tasks (
                task_id TEXT PRIMARY KEY,
                target_text TEXT NOT NULL,
                parsed_target TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                step_summary TEXT,
                baseline_solution TEXT,
                solutions TEXT NOT NULL,
                negotiation_message TEXT,
                negotiation_suggestions TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        await db.commit()


async def _save_task(db_path: Path, task: dict[str, Any]) -> None:
    """将任务持久化到 SQLite。"""
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO intelligent_budget_tasks
                (task_id, target_text, parsed_target, status, stage, step_summary,
                 baseline_solution, solutions, negotiation_message, negotiation_suggestions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task["task_id"],
                task["target_text"],
                json.dumps(task["parsed_target"], ensure_ascii=False),
                task["status"],
                task["stage"],
                json.dumps(task["step_summary"], ensure_ascii=False) if task.get("step_summary") else None,
                json.dumps(task["baseline_solution"], ensure_ascii=False) if task.get("baseline_solution") else None,
                json.dumps(task["solutions"], ensure_ascii=False),
                task.get("negotiation_message"),
                json.dumps(task["negotiation_suggestions"], ensure_ascii=False) if task.get("negotiation_suggestions") else None,
            ),
        )
        await db.commit()


async def _load_task(db_path: Path, task_id: str) -> dict[str, Any] | None:
    """从 SQLite 加载任务并还原 JSON 字段。"""
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM intelligent_budget_tasks WHERE task_id = ?", (task_id,)
        ) as cursor:
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
        # 持久化到 SQLite
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
