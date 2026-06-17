from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import bi_department_mapping as service
from app.services.bi_department_mapping import BiDepartmentMappingError


def _http_error(exc: BiDepartmentMappingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def build_bi_department_mapping_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/manage-dept-owner-mapping/list")
    async def list_manage_dept_owner_mappings():
        return await service.list_manage_dept_owner_mappings()

    @router.post("/api/manage-dept-owner-mapping/create")
    async def create_manage_dept_owner_mapping(body: dict[str, str]):
        try:
            return await service.create_manage_dept_owner_mapping(body)
        except BiDepartmentMappingError as exc:
            raise _http_error(exc) from exc

    @router.put("/api/manage-dept-owner-mapping/update/{mapping_id}")
    async def update_manage_dept_owner_mapping(mapping_id: int, body: dict[str, str]):
        try:
            return await service.update_manage_dept_owner_mapping(mapping_id, body)
        except BiDepartmentMappingError as exc:
            raise _http_error(exc) from exc

    @router.delete("/api/manage-dept-owner-mapping/delete/{mapping_id}")
    async def delete_manage_dept_owner_mapping(mapping_id: int):
        try:
            return await service.delete_manage_dept_owner_mapping(mapping_id)
        except BiDepartmentMappingError as exc:
            raise _http_error(exc) from exc

    @router.post("/api/manage-dept-owner-mapping/auto-generate")
    async def auto_generate_manage_dept_owner_mappings():
        return await service.auto_generate_manage_dept_owner_mappings()

    @router.get("/api/manage-dept-owner-mapping/reference-data")
    async def get_manage_dept_owner_reference_data():
        return await service.get_manage_dept_owner_reference_data()

    return router
