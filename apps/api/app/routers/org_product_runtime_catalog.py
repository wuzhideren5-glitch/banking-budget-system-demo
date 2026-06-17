from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter

from app.core.db_paths import common_db_path
from app.schemas import OrgProductRuntimeProductRow
from app.services.org_product_runtime_catalog import list_org_product_runtime_product_rows


def build_org_product_runtime_catalog_router(
    *,
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    _ = write_operation_log
    router = APIRouter()

    @router.get("/api/org-product-runtime-products", response_model=list[OrgProductRuntimeProductRow])
    async def list_org_product_runtime_products():
        rows = await list_org_product_runtime_product_rows(common_db_path())
        return [OrgProductRuntimeProductRow(**row.__dict__) for row in rows]

    return router
