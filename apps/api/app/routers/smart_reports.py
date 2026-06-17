from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.schemas import (
    SmartReportAIInspectionResponse,
    SmartReportBlueprintDetail,
    SmartReportBlueprintGenerateResponse,
    SmartReportBlueprintPreviewResponse,
    SmartReportBlueprintRow,
    SmartReportBlueprintSaveRequest,
    SmartReportCalcMetricRow,
    SmartReportCalcMetricUpsert,
    SmartReportGenerateRequest,
    SmartReportGenerateResponse,
    SmartReportInstanceRow,
    SmartReportPreviewRequest,
    SmartReportPreviewResponse,
    SmartReportTemplateCreateResponse,
    SmartReportTemplateRow,
    SmartReportTextTemplateCreate,
    SmartReportTemplateVariableRow,
    SmartReportTemplateVariableUpsert,
)
from app.services.smart_report_service import SmartReportService


def build_smart_reports_router(
    *,
    service: SmartReportService,
    write_operation_log: Callable[..., Awaitable[None]],
) -> APIRouter:
    router = APIRouter(prefix="/api/smart-reports", tags=["smart-reports"])

    @router.get("/templates", response_model=list[SmartReportTemplateRow])
    async def list_templates():
        return await service.list_templates()

    @router.post("/ai/inspect", response_model=SmartReportAIInspectionResponse)
    async def inspect_report_with_ai(file: UploadFile = File(...)):
        return await service.inspect_report_with_ai(file)

    @router.get("/blueprints", response_model=list[SmartReportBlueprintRow])
    async def list_blueprints():
        return await service.list_blueprints()

    @router.post("/blueprints", response_model=SmartReportBlueprintDetail)
    async def save_blueprint(body: SmartReportBlueprintSaveRequest):
        result = await service.save_blueprint(body)
        await write_operation_log(
            action_type="smart_report_blueprint_save",
            action_desc=f"保存智能报告蓝图：{result.blueprint_name}",
            target_table="smart_report_blueprint",
            affected_rows=1,
            after_data=result.model_dump(),
        )
        return result

    @router.get("/blueprints/{blueprint_id}", response_model=SmartReportBlueprintDetail)
    async def get_blueprint(blueprint_id: int):
        return await service.get_blueprint(blueprint_id)

    @router.post("/blueprints/{blueprint_id}/preview", response_model=SmartReportBlueprintPreviewResponse)
    async def preview_blueprint(blueprint_id: int):
        return await service.preview_blueprint(blueprint_id)

    @router.post("/blueprints/{blueprint_id}/generate", response_model=SmartReportBlueprintGenerateResponse)
    async def generate_blueprint(blueprint_id: int):
        result = await service.generate_blueprint(blueprint_id)
        await write_operation_log(
            action_type="smart_report_blueprint_generate",
            action_desc=f"生成智能报告蓝图 Word：blueprint_id={blueprint_id}",
            target_table="smart_report_blueprint",
            affected_rows=1,
            after_data=result.model_dump(),
        )
        return result

    @router.get("/blueprints/{blueprint_id}/download")
    async def download_blueprint(blueprint_id: int):
        path = await service.blueprint_output_path(blueprint_id)
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @router.post("/templates", response_model=SmartReportTemplateCreateResponse)
    async def upload_template(
        file: UploadFile = File(...),
        template_code: str = Form(...),
        template_name: str = Form(...),
        template_type: str = Form("analysis"),
        remark: str | None = Form(None),
    ):
        filename = (file.filename or "").lower()
        if not (filename.endswith(".docx") or filename.endswith(".pptx")):
            raise HTTPException(status_code=400, detail="请上传 .docx 或 .pptx 文件")
        result = await service.create_or_update_template(
            file=file,
            template_code=template_code,
            template_name=template_name,
            template_type=template_type,
            remark=remark,
        )
        await write_operation_log(
            action_type="smart_report_template_upload",
            action_desc=f"上传智能报告模板：{result.template.template_code}",
            target_table="smart_report_template",
            affected_rows=1,
            after_data=result.model_dump(),
        )
        return result

    @router.post("/templates/text", response_model=SmartReportTemplateCreateResponse)
    async def create_text_template(body: SmartReportTextTemplateCreate):
        result = await service.create_or_update_text_template(
            template_code=body.template_code,
            template_name=body.template_name,
            content=body.content,
            template_type=body.template_type,
            remark=body.remark,
        )
        await write_operation_log(
            action_type="smart_report_template_text_create",
            action_desc=f"保存手工录入智能报告模板：{result.template.template_code}",
            target_table="smart_report_template",
            affected_rows=1,
            after_data=result.model_dump(),
        )
        return result

    @router.get("/templates/{template_id}", response_model=SmartReportTemplateRow)
    async def get_template(template_id: int):
        return await service.get_template(template_id)

    @router.get("/templates/{template_id}/variables", response_model=list[SmartReportTemplateVariableRow])
    async def list_variables(template_id: int):
        return await service.list_variables(template_id)

    @router.put("/templates/{template_id}/variables", response_model=list[SmartReportTemplateVariableRow])
    async def upsert_variables(template_id: int, variables: list[SmartReportTemplateVariableUpsert]):
        result = await service.upsert_variables(template_id, variables)
        await write_operation_log(
            action_type="smart_report_variable_upsert",
            action_desc=f"更新智能报告模板变量：template_id={template_id}",
            target_table="smart_report_template_variable",
            affected_rows=len(variables),
            after_data=[item.model_dump() for item in result],
        )
        return result

    @router.get("/calc-metrics", response_model=list[SmartReportCalcMetricRow])
    async def list_calc_metrics():
        return await service.list_calc_metrics()

    @router.put("/calc-metrics/{metric_code}", response_model=SmartReportCalcMetricRow)
    async def upsert_calc_metric(metric_code: str, body: SmartReportCalcMetricUpsert):
        body.metric_code = metric_code
        result = await service.upsert_calc_metric(body)
        await write_operation_log(
            action_type="smart_report_calc_metric_upsert",
            action_desc=f"保存智能报告计算指标：{result.metric_code}",
            target_table="smart_report_calc_metric",
            affected_rows=1,
            after_data=result.model_dump(),
        )
        return result

    @router.post("/generate", response_model=SmartReportGenerateResponse)
    async def generate_report(body: SmartReportGenerateRequest):
        result = await service.generate(body)
        await write_operation_log(
            action_type="smart_report_generate",
            action_desc=f"生成智能报告：instance_id={result.instance_id}",
            target_table="smart_report_instance",
            affected_rows=1,
            after_data=result.model_dump(),
        )
        return result

    @router.post("/preview", response_model=SmartReportPreviewResponse)
    async def preview_report(body: SmartReportPreviewRequest):
        return await service.preview(body)

    @router.get("/instances", response_model=list[SmartReportInstanceRow])
    async def list_instances():
        return await service.list_instances()

    @router.post("/instances/{instance_id}/refresh", response_model=SmartReportGenerateResponse)
    async def refresh_instance(instance_id: int):
        result = await service.refresh_instance(instance_id)
        await write_operation_log(
            action_type="smart_report_refresh",
            action_desc=f"刷新智能报告：instance_id={instance_id}",
            target_table="smart_report_instance",
            affected_rows=1,
            after_data=result.model_dump(),
        )
        return result

    @router.get("/instances/{instance_id}/download")
    async def download_instance(instance_id: int):
        path = await service.instance_output_path(instance_id)
        media_type = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if Path(path).suffix.lower() == ".pptx"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type=media_type,
        )

    return router
