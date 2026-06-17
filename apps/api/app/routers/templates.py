from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings

router = APIRouter()


ACTIVE_DOWNLOAD_TEMPLATES = {
    "budget_data_temp": "budget_data_temp.xlsx",
    "dept_acct_temp": "dept_acct_temp.xlsx",
    "pivot_export_temp": "pivot_export_temp.xlsx",
    "product_org_tree_import_template": "product_org_tree_import_template.xlsx",
}


@router.get("/api/templates/{template_name}")
async def download_template(template_name: str):
    safe_name = template_name.strip()
    if not safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="模板名称不合法")
    file_name = ACTIVE_DOWNLOAD_TEMPLATES.get(safe_name)
    if file_name is None:
        raise HTTPException(status_code=404, detail=f"未注册模板 {safe_name}")

    template_dir = settings.download_template_dir
    if not template_dir.exists() or not template_dir.is_dir():
        raise HTTPException(status_code=404, detail="模板目录 resources/download_template 不存在")

    target = template_dir / file_name
    if not target.exists() or not target.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"未找到模板 {safe_name}（请检查 resources/download_template 目录）",
        )

    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )
