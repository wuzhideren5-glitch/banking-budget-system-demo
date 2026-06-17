from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter

from app.core.config import Settings
from app.core.db_paths import common_db_path
from app.schemas import SystemDatabaseCreateRequest, SystemDatabaseRow, SystemPeriodYearDto
from app.services.system_catalog import (
    create_system_database as create_system_database_command,
    delete_system_database as delete_system_database_command,
    list_system_databases as list_system_databases_query,
    list_system_period_years as list_system_period_years_query,
    sync_system_databases_table_with_files,
)


def build_system_catalog_router(
    *,
    settings: Settings,
    budget_schema: str,
    get_year_period_months: Callable[[int], Awaitable[dict[int, int]]],
    iso_now: Callable[[], str],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/system/databases/sync", response_model=list[SystemDatabaseRow])
    async def sync_system_databases():
        return await sync_system_databases_table_with_files(
            common_db_path(),
            settings.data_dir,
            fallback_now=iso_now,
        )

    @router.get("/api/system/period-years", response_model=list[SystemPeriodYearDto])
    async def list_system_period_years():
        return await list_system_period_years_query(common_db_path())

    @router.get("/api/system/databases", response_model=list[SystemDatabaseRow])
    async def list_system_databases():
        return await list_system_databases_query(common_db_path(), settings.data_dir)

    @router.post("/api/system/databases", response_model=SystemDatabaseRow)
    async def create_system_database(req: SystemDatabaseCreateRequest):
        return await create_system_database_command(
            common_db=common_db_path(),
            data_dir=settings.data_dir,
            local_user_name=settings.local_user_name,
            request=req,
            budget_schema=budget_schema,
            get_year_period_months=get_year_period_months,
            iso_now=iso_now,
        )

    @router.delete("/api/system/databases/{data_file_id}")
    async def delete_system_database(data_file_id: int):
        return await delete_system_database_command(common_db_path(), settings.data_dir, data_file_id)

    return router
