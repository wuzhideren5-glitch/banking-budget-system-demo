from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/api/templates/{template_name}")
async def download_template(template_name: str):
    safe_name = template_name.strip()
    if not safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="模板名称不合法")
    template_dir = Path(__file__).resolve().parents[3] / "download_template"
    if not template_dir.exists() or not template_dir.is_dir():
        raise HTTPException(status_code=404, detail="模板目录 download_template 不存在")

    # 优先按完整文件名命中，其次按 stem（不含后缀）命中。
    exact = template_dir / safe_name
    if exact.exists() and exact.is_file():
        target = exact
    else:
        matches = [p for p in template_dir.iterdir() if p.is_file() and p.stem == safe_name]
        if not matches:
            raise HTTPException(
                status_code=404,
                detail=f"未找到模板 {safe_name}（请检查 download_template 目录）",
            )
        target = sorted(matches, key=lambda p: p.name)[0]

    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )
