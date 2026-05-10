from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.knowledge_base import KnowledgeBaseService
from app.schemas import AgentKbContextRequest, AgentKbContextResponse, AgentKbStatsResponse


def build_agent_kb_router(kb_service: KnowledgeBaseService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/agent/kb/stats", response_model=AgentKbStatsResponse)
    async def agent_kb_stats():
        return AgentKbStatsResponse(**kb_service.stats())

    @router.post("/api/agent/kb/context", response_model=AgentKbContextResponse)
    async def agent_kb_context(req: AgentKbContextRequest):
        query = req.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="query 不能为空")
        return AgentKbContextResponse(**kb_service.search_context(query=query, top_k=req.top_k))

    return router
