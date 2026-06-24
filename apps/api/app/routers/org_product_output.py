from __future__ import annotations

import json
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.core.db_paths import budget_db_path, common_db_path
from app.routers.org_product_helpers import *
from app.services.org_product_output_engine import OrgProductOutputRunEngine

router = APIRouter()

@router.post("/api/org-product-output/run")
async def run_org_product_output(payload: OrgProductOutputRunRequest):
    entity_code = (payload.entity_code or "").strip()
    if not entity_code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(payload.year, int) or payload.year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    version_id = int(payload.version_id)
    table_name = (payload.table_name or "").strip()

    path = common_db_path()
    if not path.exists():
        return {"entities": []}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_org_product_tree_table(conn)
            _ensure_data_entry_snapshot_table_v2(conn)

            entity_codes = [entity_code]
            entity_name_by_code: dict[str, str] = {}
            if payload.include_children:
                cur_tree = conn.execute(
                    "SELECT payload_json FROM org_product_tree_snapshot WHERE id=1"
                )
                row_tree = cur_tree.fetchone()
                tree_obj = json.loads(row_tree[0]) if row_tree and row_tree[0] else None
                if tree_obj:
                    target_codes: set[str] = set()

                    def walk_collect(node: dict[str, Any], active: bool) -> None:
                        code = str(node.get("code") or "").strip()
                        name = str(node.get("name") or "").strip()
                        next_active = active or (code == entity_code)
                        if next_active and code:
                            target_codes.add(code)
                            if name:
                                entity_name_by_code[code] = name
                        for c in list(node.get("children") or []):
                            if isinstance(c, dict):
                                walk_collect(c, next_active)

                    walk_collect(tree_obj, False)
                    if target_codes:
                        entity_codes = sorted(target_codes)
            if not entity_name_by_code:
                for row in load_org_product_metric_table_rows_from_runtime_tree(conn):
                    c = str(row.get("entity_code") or "").strip()
                    if c in entity_codes:
                        entity_name_by_code[c] = str(row.get("entity_name") or "").strip()

            table_rows = [
                row
                for row in load_org_product_metric_table_rows_from_runtime_tree(conn)
                if str(row.get("entity_code") or "").strip() in entity_codes
            ]

            output_entities: list[dict[str, Any]] = []
            run_engine = OrgProductOutputRunEngine(
                conn,
                year=int(payload.year),
                version_id=int(version_id),
            )
            for code, name in entity_name_by_code.items():
                run_engine._remember_entity_name(code, name)

            for row in table_rows:
                ec_s = str(row.get("entity_code") or "").strip()
                tn_s = str(row.get("table_name") or "").strip()
                if table_name and tn_s != table_name:
                    continue
                entity_name = str(row.get("entity_name") or "").strip() or entity_name_by_code.get(ec_s, "")
                output_entities.append(run_engine.run_entity(ec_s, entity_name, tn_s))
            return {"entities": output_entities}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"预测输出计算失败：{exc}") from exc

@router.post("/api/org-product-output/export")
async def export_org_product_output(payload: OrgProductOutputRunRequest):
    result = await run_org_product_output(payload)
    entities = list(result.get("entities") or [])
    if not entities:
        raise HTTPException(status_code=400, detail="没有可导出的预测输出数据，请先运行或检查机构/指标配置")

    wb = Workbook()
    wb.remove(wb.active)
    used_titles: set[str] = set()
    for ent in entities:
        ec = str(ent.get("entity_code") or "")
        en = str(ent.get("entity_name") or "")
        tn = str(ent.get("table_name") or "")
        title = _unique_sheet_title(used_titles, f"{ec}{en}_{tn}")
        ws = wb.create_sheet(title=title)
        _append_org_product_output_export_sheet(ws, list(ent.get("rows") or []), ec)
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 20
        ws.column_dimensions["D"].width = 36

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    table_name = (payload.table_name or "").strip()
    bulk = bool(payload.include_children and not table_name)
    if bulk:
        filename = f"预测输出_全量_{payload.entity_code}_{payload.year}_v{payload.version_id}.xlsx".replace(" ", "")
        ascii_fallback = f"org_product_output_bulk_{payload.entity_code}_{payload.year}_v{payload.version_id}.xlsx"
    elif table_name:
        filename = f"预测输出_{payload.entity_code}_{table_name}_{payload.year}_v{payload.version_id}.xlsx".replace(" ", "")
        ascii_fallback = f"org_product_output_{payload.entity_code}_{payload.year}_v{payload.version_id}.xlsx"
    else:
        filename = f"预测输出_{payload.entity_code}_{payload.year}_v{payload.version_id}.xlsx".replace(" ", "")
        ascii_fallback = f"org_product_output_{payload.entity_code}_{payload.year}_v{payload.version_id}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": _attachment_content_disposition(
                filename,
                ascii_fallback=ascii_fallback,
            )
        },
    )

@router.get("/api/org-product-output/versions")
async def list_org_product_output_versions(entity_code: str, year: int, input_version_id: int, table_name: str):
    code = (entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(year, int) or year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    tn = (table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")
    if not isinstance(input_version_id, int) or input_version_id <= 0:
        raise HTTPException(status_code=400, detail="input_version_id 不合法")

    path = common_db_path()
    if not path.exists():
        return {"items": []}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_org_product_output_snapshot_table(conn)
            cur = conn.execute(
                """
                SELECT output_version_id, output_version_name, MAX(updated_at) AS updated_at
                FROM org_product_output_snapshot_v1
                WHERE entity_code=? AND year=? AND input_version_id=? AND table_name=?
                GROUP BY output_version_id, output_version_name
                ORDER BY output_version_id DESC
                """,
                (code, int(year), int(input_version_id), tn),
            )
            rows = cur.fetchall()
        return {
            "items": [
                {"output_version_id": int(r[0]), "output_version_name": str(r[1] or "").strip(), "updated_at": str(r[2] or "")}
                for r in rows
            ]
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取输出版本列表失败：{exc}") from exc

@router.get("/api/org-product-output/db-snapshot")
async def get_org_product_output_snapshot(entity_code: str, year: int, input_version_id: int, output_version_id: int, table_name: str):
    code = (entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(year, int) or year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    tn = (table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")
    if not isinstance(input_version_id, int) or input_version_id <= 0:
        raise HTTPException(status_code=400, detail="input_version_id 不合法")
    if not isinstance(output_version_id, int) or output_version_id <= 0:
        raise HTTPException(status_code=400, detail="output_version_id 不合法")

    path = common_db_path()
    if not path.exists():
        return {"found": False}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_org_product_output_snapshot_table(conn)
            cur = conn.execute(
                """
                SELECT payload_json, updated_at
                FROM org_product_output_snapshot_v1
                WHERE entity_code=? AND year=? AND input_version_id=? AND output_version_id=? AND table_name=?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (code, int(year), int(input_version_id), int(output_version_id), tn),
            )
            row = cur.fetchone()
            if not row:
                return {"found": False}
            payload_obj = json.loads(row[0]) if row[0] else None
            payload_obj = _sanitize_output_payload_for_response(
                payload_obj,
                entity_code=code,
                table_name=tn,
            )
            return {"found": True, "payload": payload_obj, "updated_at": row[1]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取输出快照失败：{exc}") from exc

@router.post("/api/org-product-output/commit")
async def commit_org_product_output(payload: OrgProductOutputCommitRequest):
    code = (payload.entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(payload.year, int) or payload.year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    input_version_id = int(payload.input_version_id)
    if input_version_id <= 0:
        raise HTTPException(status_code=400, detail="input_version_id 不合法")
    tn = (payload.table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")

    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            _ensure_org_product_output_snapshot_table(conn)
            cur = conn.execute(
                """
                SELECT MAX(output_version_id)
                FROM org_product_output_snapshot_v1
                WHERE entity_code=? AND year=? AND input_version_id=? AND table_name=?
                """,
                (code, int(payload.year), int(input_version_id), tn),
            )
            row = cur.fetchone()
            max_id = int(row[0]) if row and row[0] is not None else 0
            next_id = max_id + 1
        output_version_id = int(payload.output_version_id) if payload.output_version_id is not None else int(next_id)

        run_result = await run_org_product_output(
            OrgProductOutputRunRequest(
                entity_code=code,
                year=int(payload.year),
                version_id=int(input_version_id),
                table_name=tn,
                include_children=False,
            )
        )
        entities = list(run_result.get("entities") or [])
        if not entities:
            raise HTTPException(status_code=400, detail="未生成任何输出结果")
        entity = _sanitize_org_product_output_entity_for_snapshot(dict(entities[0]))
        rows = list(entity.get("rows") or [])
        error_count = 0
        for r in rows:
            for err in list(r.get("month_errors") or []):
                if err:
                    error_count += 1
        if error_count > 0 and not payload.force:
            raise HTTPException(status_code=400, detail=f"检测到 {error_count} 个公式错误，建议先校验修复后再保存。")

        now = _now_iso()
        payload_json = json.dumps(entity, ensure_ascii=False)
        with sqlite3.connect(path) as conn:
            _ensure_org_product_output_snapshot_table(conn)
            conn.execute(
                """
                INSERT INTO org_product_output_snapshot_v1(
                  entity_code, entity_name, year, input_version_id, output_version_id, output_version_name, table_name, payload_json, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_code, year, input_version_id, output_version_id, table_name) DO UPDATE SET
                  entity_name=excluded.entity_name,
                  output_version_name=excluded.output_version_name,
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                (
                    str(entity.get("entity_code") or code),
                    str(entity.get("entity_name") or ""),
                    int(payload.year),
                    int(input_version_id),
                    int(output_version_id),
                    (payload.output_version_name or "").strip(),
                    tn,
                    payload_json,
                    now,
                ),
            )
            conn.commit()
        return {"ok": True, "output_version_id": int(output_version_id), "updated_at": now}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存输出版本失败：{exc}") from exc

@router.post("/api/org-product-data-entry/import-preview")
async def preview_org_product_data_entry_import(file: UploadFile = File(...)):
    if not file.filename or not str(file.filename).lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xlsm 文件")
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（上限 15MB）")
    headers, rows = _parse_simple_excel_table(raw, file.filename or "import.xlsx", "科目代码")
    return {
        "columns": headers,
        "preview_rows": rows[:20],
        "row_count": len(rows),
    }

@router.post("/api/org-product-data-entry/import-apply")
async def apply_org_product_data_entry_import(file: UploadFile = File(...)):
    if not file.filename or not str(file.filename).lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xlsm 文件")
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（上限 15MB）")
    headers, rows = _parse_simple_excel_table(raw, file.filename or "import.xlsx", "科目代码")
    return {
        "columns": headers,
        "rows": rows,
        "row_count": len(rows),
    }

@router.post("/api/org-product-data-entry/import-workbook")
async def import_org_product_data_entry_workbook(
    file: UploadFile = File(...),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
):
    if not file.filename or not str(file.filename).lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xlsm 文件")
    if not isinstance(year, int) or year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（上限 15MB）")

    candidates: list[tuple[str, str, str]] = []
    path = common_db_path()
    if path.exists():
        try:
            with sqlite3.connect(path) as conn:
                candidates = [
                    (
                        str(row.get("entity_code") or "").strip(),
                        str(row.get("entity_name") or "").strip(),
                        str(row.get("table_name") or "").strip(),
                    )
                    for row in load_org_product_metric_table_rows_from_runtime_tree(conn)
                    if str(row.get("entity_code") or "").strip()
                    and str(row.get("table_name") or "").strip()
                ]
        except Exception:
            candidates = []

    sheets = _parse_data_entry_workbook(raw, file.filename or "import.xlsx", int(year), int(month), candidates)
    return {"sheets": sheets, "sheet_count": len(sheets)}

