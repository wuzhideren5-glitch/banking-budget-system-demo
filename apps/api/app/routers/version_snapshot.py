from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter

from app.core.db_paths import common_db_path
from app.schemas import VersionSnapshotResponse
from app.services.version_snapshot import build_version_snapshot


def build_version_snapshot_router(
    fetch_version_name_and_current_month: Callable[[str, int], Awaitable[tuple[str, int]]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/version-snapshot", response_model=VersionSnapshotResponse)
    async def version_snapshot():
        return await build_version_snapshot(
            common_db_path(),
            fetch_version_name_and_current_month,
        )

    return router
