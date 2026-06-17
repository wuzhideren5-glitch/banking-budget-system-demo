from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter

from app.schemas import GlobalRefreshStatusResponse


def build_global_refresh_status_router(
    fetch_status: Callable[[], Awaitable[GlobalRefreshStatusResponse]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/global-refresh-status", response_model=GlobalRefreshStatusResponse)
    async def global_refresh_status():
        return await fetch_status()

    return router
