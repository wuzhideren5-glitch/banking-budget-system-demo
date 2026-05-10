from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent_debug_trace import AgentDebugTraceStore


def build_agent_debug_router(store: AgentDebugTraceStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/system/agent-debug/events")
    async def list_agent_debug_events(limit: int = 200):
        return {"items": store.list_recent(limit=limit)}

    @router.get("/api/system/agent-debug/stream")
    async def stream_agent_debug_events(request: Request, after_event_id: str | None = None):
        async def gen():
            cursor = str(after_event_id or "").strip() or None
            while True:
                if await request.is_disconnected():
                    break
                items = store.list_since(after_event_id=cursor, limit=300)
                if items:
                    for item in items:
                        cursor = str(item.get("event_id") or cursor or "")
                        payload = json.dumps(item, ensure_ascii=False)
                        yield f"event: trace\ndata: {payload}\n\n"
                else:
                    # Keep connection alive for proxies.
                    yield ": ping\n\n"
                await asyncio.sleep(0.8)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @router.delete("/api/system/agent-debug/events")
    async def clear_agent_debug_events():
        store.clear_all()
        return {"ok": True}

    return router
