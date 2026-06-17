from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.core.db_paths import common_db_path
from app.routers.org_product_helpers import *

router = APIRouter()

@router.get("/api/org-product-tree/db-snapshot")
async def get_org_product_tree_snapshot():
    path = common_db_path()
    if not path.exists():
        return {"found": False}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_org_product_tree_table(conn)
            cur = conn.execute(
                "SELECT payload_json, updated_at FROM org_product_tree_snapshot WHERE id=1"
            )
            row = cur.fetchone()
            if not row:
                return {"found": False}
            payload_obj = json.loads(row[0]) if row[0] else None
            return {"found": True, "tree": payload_obj, "updated_at": row[1]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取机构及产品快照失败：{exc}") from exc

@router.post("/api/org-product-tree/save-refresh")
async def save_org_product_tree_snapshot(payload: OrgProductTreeSavePayload):
    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            _ensure_org_product_tree_table(conn)
            now = _now_iso()
            payload_json = json.dumps(payload.tree.model_dump(), ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
                VALUES(1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                (payload_json, now),
            )
            sync_result = sync_org_product_runtime_catalog_from_tree(
                conn,
                payload.tree.model_dump(),
            )
            conn.commit()
            return {
                "ok": True,
                "updated_at": now,
                "org_product_runtime_catalog_rows": sync_result.row_count,
            }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存机构及产品快照失败：{exc}") from exc

@router.post("/api/org-product-tree/import-excel")
async def import_org_product_tree_excel(file: UploadFile = File(...)):
    if not file.filename or not str(file.filename).lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx/.xlsm/.xls 文件")
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（上限 15MB）")
    tree = _parse_org_product_tree_excel(raw, file.filename or "org_product.xlsx")
    return {"tree": tree}

@router.post("/api/org-product-tree/import-from-base-data")
async def import_org_product_tree_from_base_data():
    """从约定路径读取 基础数据/机构及产品.xlsx；若文件缺失则回退到 DB 快照。"""
    path = _resolve_org_product_tree_excel_path()
    if path:
        try:
            raw = path.read_bytes()
            tree = _parse_org_product_tree_excel(raw, path.name)
            return {"tree": tree, "source_path": str(path)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"读取 Excel 失败：{exc}") from exc
    # Excel 文件缺失 → 回退到 DB 快照
    db_path = common_db_path()
    if not db_path.exists():
        return {"tree": None, "source": "db_fallback", "found": False}
    try:
        with sqlite3.connect(db_path) as conn:
            _ensure_org_product_tree_table(conn)
            cur = conn.execute(
                "SELECT payload_json FROM org_product_tree_snapshot WHERE id=1"
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return {"tree": None, "source": "db_fallback", "found": False}
            tree = json.loads(row[0])
            return {"tree": tree, "source": "db_snapshot"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取 DB 快照失败：{exc}") from exc

@router.post("/api/org-product-tree/export-excel")
async def export_org_product_tree_excel(payload: OrgProductTreeSavePayload):
    try:
        root = payload.tree.model_dump()
        rows = _flatten_org_product_tree(root)
        if not rows:
            raise HTTPException(status_code=400, detail="机构及产品树为空，无法导出")
        wb = Workbook()
        ws = wb.active
        ws.title = "机构及产品"
        headers = ["层级", "机构及产品代码", "机构及产品名称", "上级代码", "上级名称"]
        ws.append(headers)
        for r in rows:
            ws.append(
                [
                    r.get("层级"),
                    r.get("机构及产品代码"),
                    r.get("机构及产品名称"),
                    r.get("上级代码"),
                    r.get("上级名称"),
                ]
            )
        header_font = Font(bold=True)
        for cell in ws[1]:
            cell.font = header_font
        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 28
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 28
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        download_name = "机构及产品.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": _attachment_content_disposition(
                    download_name, ascii_fallback="org_product_tree.xlsx"
                )
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"导出 Excel 失败：{exc}") from exc

