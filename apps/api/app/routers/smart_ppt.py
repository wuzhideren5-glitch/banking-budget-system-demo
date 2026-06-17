"""智能PPT路由 —— 场景驱动的PPT生成 API"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas import (
    SmartPptGenerateRequest,
    SmartPptGenerateResponse,
    SmartPptInstanceRow,
    SmartPptPreviewRequest,
    SmartPptSceneDetailResponse,
    SmartPptSceneRow,
    SmartPptChartConfigRow,
    SmartPptTemplateBindingConfigRequest,
    SmartPptTemplateBindingConfigResponse,
    SmartPptTemplateChartBlockResponse,
    SmartPptTemplateGenerateRequest,
    SmartPptTemplateGenerateResponse,
    SmartPptTemplateInspectResponse,
)
from app.services.smart_ppt_service import SmartPptService


def build_smart_ppt_router(
    *,
    service: SmartPptService,
) -> APIRouter:
    router = APIRouter(prefix="/api/smart-ppt", tags=["smart-ppt"])

    # ── 场景管理 ──────────────────────────────────────────

    @router.get("/scenes", response_model=list[SmartPptSceneRow])
    async def list_scenes():
        return await service.list_scenes()

    # ── PPT 生成 ──────────────────────────────────────────

    @router.post("/generate", response_model=SmartPptGenerateResponse)
    async def generate_ppt(body: SmartPptGenerateRequest):
        return await service.generate(
            scene_id=body.scene_id,
            params=body.params,
            instance_name=body.instance_name or "",
        )

    @router.post("/preview", response_model=SmartPptSceneDetailResponse)
    async def preview_ppt(body: SmartPptPreviewRequest):
        return await service.preview(scene_id=body.scene_id, params=body.params)

    # ── 实例管理 ──────────────────────────────────────────

    @router.get("/instances", response_model=list[SmartPptInstanceRow])
    async def list_instances():
        return await service.list_instances()

    @router.get("/instances/{instance_id}/download")
    async def download_instance(instance_id: int):
        path = await service.instance_output_path(instance_id)
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    # ── 模板工作台 ──────────────────────────────────────────

    @router.get("/template-studio/inspect", response_model=SmartPptTemplateInspectResponse)
    async def inspect_template(template_file_name: str):
        return service.inspect_template_file(template_file_name)

    @router.get("/template-studio/bindings", response_model=SmartPptTemplateBindingConfigResponse)
    async def get_template_bindings(template_file_name: str):
        return service.get_template_bindings(template_file_name)

    @router.get("/template-studio/chart-blocks", response_model=SmartPptTemplateChartBlockResponse)
    async def suggest_template_chart_blocks(
        template_file_name: str,
        max_slides: int = 10,
    ):
        return await service.suggest_template_chart_blocks(template_file_name, max_slides=max_slides)

    @router.put("/template-studio/bindings", response_model=SmartPptTemplateBindingConfigResponse)
    async def save_template_bindings(body: SmartPptTemplateBindingConfigRequest):
        return service.save_template_bindings(body)

    @router.post("/template-studio/generate", response_model=SmartPptTemplateGenerateResponse)
    async def generate_template_ppt(body: SmartPptTemplateGenerateRequest):
        return await service.generate_from_template_bindings(body)

    @router.get("/template-studio/download/{output_filename}")
    async def download_template_ppt(output_filename: str):
        path = service.template_studio_output_path(output_filename)
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    # ── 图表规则 ──────────────────────────────────────────

    @router.get("/chart-configs", response_model=list[SmartPptChartConfigRow])
    async def list_chart_configs():
        return await service.list_chart_configs()

    return router
