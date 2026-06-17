from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.db_paths import common_db_path
from app.services.bi_ai_subject_mapping import (
    BiAiSubjectMappingHeaderError,
    BiAiSubjectMappingNotFoundError,
    BiAiSubjectMappingSourceMissingError,
    BiAiSubjectMappingUpdateError,
    create_bi_ai_subject_mapping_row,
    ensure_bi_ai_subject_mapping_seeded,
    get_bi_ai_subject_mapping_reference_data,
    list_bi_ai_subject_mapping_rows,
    update_bi_ai_subject_mapping_manage_departments,
)


class BiAiSubjectMappingManageDepartmentsUpdateBody(BaseModel):
    manage_departments: list[str] | None = Field(
        default=None,
        description="Manual manage departments; null clears override and restores auto/default-all logic.",
    )


class BiAiSubjectMappingCreateBody(BaseModel):
    level5_code: str = Field(default="")
    level5_name: str = Field(default="")
    level6_code: str = Field(default="")
    level6_name: str = Field(default="")
    budget_release_caliber: str = Field(default="")
    fee_category: str = Field(default="")
    fee_major: str = Field(default="")
    manage_departments: list[str] | None = Field(default=None)


def build_bi_ai_subject_mapping_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/bi-ai-subject-mapping/list")
    async def list_bi_ai_subject_mapping():
        try:
            return await list_bi_ai_subject_mapping_rows(common_db_path(), settings.repo_root)
        except BiAiSubjectMappingHeaderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/bi-ai-subject-mapping/reference-data")
    async def bi_ai_subject_mapping_reference_data():
        return await get_bi_ai_subject_mapping_reference_data(common_db_path())

    @router.post("/api/bi-ai-subject-mapping/create")
    async def create_bi_ai_subject_mapping(body: BiAiSubjectMappingCreateBody):
        try:
            return await create_bi_ai_subject_mapping_row(
                body.model_dump(),
                db_path=common_db_path(),
                repo_root=settings.repo_root,
            )
        except BiAiSubjectMappingUpdateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/api/bi-ai-subject-mapping/update/{mapping_id}/manage-departments")
    async def update_bi_ai_subject_mapping_manage_departments_route(
        mapping_id: int,
        body: BiAiSubjectMappingManageDepartmentsUpdateBody,
    ):
        try:
            return await update_bi_ai_subject_mapping_manage_departments(
                mapping_id,
                body.manage_departments,
                db_path=common_db_path(),
                repo_root=settings.repo_root,
            )
        except BiAiSubjectMappingNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BiAiSubjectMappingUpdateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/bi-ai-subject-mapping/reload")
    async def reload_bi_ai_subject_mapping():
        try:
            result = await ensure_bi_ai_subject_mapping_seeded(
                common_db_path(),
                settings.repo_root,
                force_reload=True,
            )
        except BiAiSubjectMappingSourceMissingError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BiAiSubjectMappingHeaderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"row_count": result.row_count, "source_file": result.source_file}

    return router
