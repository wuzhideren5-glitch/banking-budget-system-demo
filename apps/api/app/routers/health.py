from __future__ import annotations

from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.head("/api/health", include_in_schema=False)
async def health_head() -> Response:
    return Response(status_code=200)
