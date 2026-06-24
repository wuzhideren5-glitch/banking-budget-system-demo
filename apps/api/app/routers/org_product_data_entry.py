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
from app.services.org_product_budget_sync import load_data_account_value_types_sync
from app.services.runtime_metric_refs import derive_runtime_ref_from_org_product_metric_code

router = APIRouter()


def _persist_data_entry_snapshot(conn: sqlite3.Connection, payload_obj: dict[str, Any]) -> str:
    entity_code = _normalize_text(payload_obj.get("entity_code"))
    table_name = _normalize_text(payload_obj.get("table_name"))
    version_id = int(payload_obj.get("version_id") or 0)
    version_name = _normalize_text(payload_obj.get("version_name"))
    now = _now_iso()
    payload_json = json.dumps(payload_obj, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO org_product_data_entry_snapshot(entity_code, entity_name, year, month_index, table_id, table_name, payload_json, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_code, year) DO UPDATE SET
          entity_name=excluded.entity_name,
          month_index=excluded.month_index,
          table_id=excluded.table_id,
          table_name=excluded.table_name,
          payload_json=excluded.payload_json,
          updated_at=excluded.updated_at
        """,
        (
            entity_code,
            _normalize_text(payload_obj.get("entity_name")),
            int(payload_obj.get("year")),
            int(payload_obj.get("month_index")) if payload_obj.get("month_index") is not None else None,
            _normalize_text(payload_obj.get("table_id")),
            table_name,
            payload_json,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO org_product_data_entry_snapshot_v2(
          entity_code, entity_name, year, version_id, version_name, table_name, month_index, table_id, payload_json, updated_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_code, year, version_id, table_name) DO UPDATE SET
          entity_name=excluded.entity_name,
          version_name=excluded.version_name,
          month_index=excluded.month_index,
          table_id=excluded.table_id,
          payload_json=excluded.payload_json,
          updated_at=excluded.updated_at
        """,
        (
            entity_code,
            _normalize_text(payload_obj.get("entity_name")),
            int(payload_obj.get("year")),
            int(version_id),
            version_name,
            table_name,
            int(payload_obj.get("month_index")) if payload_obj.get("month_index") is not None else None,
            _normalize_text(payload_obj.get("table_id")),
            payload_json,
            now,
        ),
    )
    return now


@router.post("/api/org-product-data-entry/save-refresh")
async def save_org_product_data_entry_snapshot(payload: DataEntrySavePayload):
    entity_code = (payload.entity_code or "").strip()
    if not entity_code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(payload.year, int) or payload.year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    table_name = (payload.table_name or "").strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="table_name 不能为空")
    version_id = int(payload.version_id) if payload.version_id is not None else 0
    version_name = (payload.version_name or "").strip()

    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_snapshot_table(conn)
            _ensure_data_entry_snapshot_table_v2(conn)
            payload_obj = _sanitize_data_entry_payload_mapping_refs(conn, payload.model_dump())
            now = _persist_data_entry_snapshot(conn, payload_obj)
            conn.commit()
            return {"ok": True, "updated_at": now}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存数据录入快照失败：{exc}") from exc

@router.post("/api/org-product-data-entry/export")
async def export_org_product_data_entry(payload: DataEntrySavePayload):
    entity_code = (payload.entity_code or "").strip()
    if not entity_code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(payload.year, int) or payload.year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    table_name = (payload.table_name or "").strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="table_name 不能为空")

    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            payload_obj = _sanitize_data_entry_payload_mapping_refs(conn, payload.model_dump())
        wb = _build_data_entry_export_workbook(payload_obj)
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        filename = f"机构产品数据录入_{entity_code}_{table_name}_{payload.year}.xlsx".replace(" ", "")
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": _attachment_content_disposition(
                    filename,
                    ascii_fallback=f"org_product_data_entry_{entity_code}_{payload.year}.xlsx",
                )
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"导出数据录入底稿失败：{exc}") from exc


@router.post("/api/org-product-data-entry/export-batch")
async def export_org_product_data_entry_batch(payload: DataEntryBatchExportRequest):
    if not isinstance(payload.year, int) or payload.year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    if not payload.items:
        raise HTTPException(status_code=400, detail="请至少选择一个机构/产品与指标表")
    month_index = max(1, min(12, int(payload.month_index or 1)))

    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        export_payloads: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        with sqlite3.connect(path) as conn:
            for item in payload.items:
                entity_code = (item.entity_code or "").strip()
                table_name = (item.table_name or "").strip()
                if not entity_code or not table_name:
                    skipped.append(
                        {
                            "entity_code": entity_code,
                            "table_name": table_name,
                            "reason": "entity_code 或 table_name 为空",
                        }
                    )
                    continue
                try:
                    export_payloads.append(
                        _build_data_entry_export_payload_from_runtime(
                            conn,
                            entity_code=entity_code,
                            entity_name=(item.entity_name or "").strip(),
                            table_name=table_name,
                            year=int(payload.year),
                            month_index=month_index,
                            version_id=payload.version_id,
                            include_saved_values=bool(payload.include_saved_values),
                        )
                    )
                except ValueError as exc:
                    skipped.append(
                        {
                            "entity_code": entity_code,
                            "table_name": table_name,
                            "reason": str(exc),
                        }
                    )
            export_payloads = [
                _sanitize_data_entry_payload_mapping_refs(conn, item) for item in export_payloads
            ]
        if not export_payloads:
            raise HTTPException(status_code=400, detail="没有可导出的指标表，请检查所选机构/产品与指标表配置")
        wb = _build_data_entry_batch_export_workbook(export_payloads)
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        filename = f"机构产品数据录入批量模板_{payload.year}.xlsx".replace(" ", "")
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": _attachment_content_disposition(
                    filename,
                    ascii_fallback=f"org_product_data_entry_batch_{payload.year}.xlsx",
                ),
                "X-Export-Sheet-Count": str(len(export_payloads)),
                "X-Export-Skipped-Count": str(len(skipped)),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"批量导出数据录入模板失败：{exc}") from exc


@router.post("/api/org-product-data-entry/import-workbook-apply")
async def apply_org_product_data_entry_workbook(
    file: UploadFile = File(...),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    version_id: int | None = Query(None),
    version_name: str = Query(""),
    entry_status: str = Query("draft"),
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
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_snapshot_table(conn)
            _ensure_data_entry_snapshot_table_v2(conn)
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
            sheets = _parse_data_entry_workbook(raw, file.filename or "import.xlsx", int(year), int(month), candidates)
            saved: list[dict[str, Any]] = []
            unmatched: list[dict[str, Any]] = []
            status = (entry_status or "draft").strip() or "draft"
            resolved_version_id = int(version_id) if version_id is not None else 0
            resolved_version_name = (version_name or "").strip()
            for sheet in sheets:
                if not sheet.get("matched"):
                    unmatched.append(
                        {
                            "sheet_name": sheet.get("sheet_name"),
                            "entity_code": sheet.get("entity_code"),
                            "table_name": sheet.get("table_name"),
                            "row_count": sheet.get("row_count"),
                            "reason": "未能根据工作表名称匹配机构/产品与指标表",
                        }
                    )
                    continue
                entity_code = str(sheet.get("entity_code") or "").strip()
                table_name = str(sheet.get("table_name") or "").strip()
                entity_name = _resolve_data_entry_entity_name(conn, entity_code)
                payload_obj = {
                    "entity_code": entity_code,
                    "entity_name": entity_name,
                    "year": int(year),
                    "month_index": int(month),
                    "version_id": resolved_version_id,
                    "version_name": resolved_version_name,
                    "table_name": table_name,
                    "entry_status": status,
                    "metrics": list(sheet.get("metrics") or []),
                }
                payload_obj = _sanitize_data_entry_payload_mapping_refs(conn, payload_obj)
                updated_at = _persist_data_entry_snapshot(conn, payload_obj)
                saved.append(
                    {
                        "sheet_name": sheet.get("sheet_name"),
                        "entity_code": entity_code,
                        "entity_name": entity_name,
                        "table_name": table_name,
                        "row_count": sheet.get("row_count"),
                        "updated_at": updated_at,
                    }
                )
            conn.commit()
        return {
            "saved": saved,
            "unmatched": unmatched,
            "saved_count": len(saved),
            "unmatched_count": len(unmatched),
            "sheet_count": len(sheets),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"批量导入数据录入失败：{exc}") from exc

@router.get("/api/org-product-data-entry/db-snapshot")
async def get_org_product_data_entry_snapshot(entity_code: str, year: int, version_id: int | None = None, table_name: str | None = None):
    code = (entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(year, int) or year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    resolved_version_id = int(version_id) if version_id is not None else None
    resolved_table_name = (table_name or "").strip() if table_name is not None else ""

    path = common_db_path()
    if not path.exists():
        return {"found": False}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_snapshot_table(conn)
            _ensure_data_entry_snapshot_table_v2(conn)
            if resolved_version_id is not None and resolved_table_name:
                cur = conn.execute(
                    """
                    SELECT entity_code, entity_name, year, version_id, version_name, table_name, month_index, table_id, payload_json, updated_at
                    FROM org_product_data_entry_snapshot_v2
                    WHERE entity_code=? AND year=? AND version_id=? AND table_name=?
                    """,
                    (code, int(year), int(resolved_version_id), resolved_table_name),
                )
                row = cur.fetchone()
                if not row:
                    return {"found": False}
                payload_obj = json.loads(row[8]) if row[8] else None
                payload_obj = _sanitize_data_entry_payload_for_response(
                    conn,
                    payload_obj,
                    entity_code=row[0],
                    table_name=row[5],
                )
                return {
                    "found": True,
                    "entity_code": row[0],
                    "entity_name": row[1],
                    "year": row[2],
                    "version_id": row[3],
                    "version_name": row[4],
                    "table_name": row[5],
                    "month_index": row[6],
                    "table_id": row[7],
                    "payload": payload_obj,
                    "updated_at": row[9],
                }
            if resolved_version_id is not None and not resolved_table_name:
                cur = conn.execute(
                    """
                    SELECT entity_code, entity_name, year, version_id, version_name, table_name, month_index, table_id, payload_json, updated_at
                    FROM org_product_data_entry_snapshot_v2
                    WHERE entity_code=? AND year=? AND version_id=?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (code, int(year), int(resolved_version_id)),
                )
                row = cur.fetchone()
                if not row:
                    return {"found": False}
                payload_obj = json.loads(row[8]) if row[8] else None
                payload_obj = _sanitize_data_entry_payload_for_response(
                    conn,
                    payload_obj,
                    entity_code=row[0],
                    table_name=row[5],
                )
                return {
                    "found": True,
                    "entity_code": row[0],
                    "entity_name": row[1],
                    "year": row[2],
                    "version_id": row[3],
                    "version_name": row[4],
                    "table_name": row[5],
                    "month_index": row[6],
                    "table_id": row[7],
                    "payload": payload_obj,
                    "updated_at": row[9],
                }

            cur = conn.execute(
                """
                SELECT entity_code, entity_name, year, month_index, table_id, table_name, payload_json, updated_at
                FROM org_product_data_entry_snapshot
                WHERE entity_code=? AND year=?
                """,
                (code, int(year)),
            )
            row = cur.fetchone()
            if not row:
                return {"found": False}
            payload_obj = json.loads(row[6]) if row[6] else None
            payload_obj = _sanitize_data_entry_payload_for_response(
                conn,
                payload_obj,
                entity_code=row[0],
                table_name=row[5],
            )
            return {
                "found": True,
                "entity_code": row[0],
                "entity_name": row[1],
                "year": row[2],
                "month_index": row[3],
                "table_id": row[4],
                "table_name": row[5],
                "payload": payload_obj,
                "updated_at": row[7],
            }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取数据录入快照失败：{exc}") from exc

@router.get("/api/org-product-data-entry/next-version-id")
async def next_org_product_data_entry_version_id(entity_code: str, year: int, table_name: str):
    code = (entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(year, int) or year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    tn = (table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")
    path = common_db_path()
    if not path.exists():
        return {"next_version_id": 1}
    try:
        with sqlite3.connect(path) as conn:
            next_id = _next_data_entry_version_id(conn, code, int(year), tn)
        return {"next_version_id": int(next_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取下一个版本号失败：{exc}") from exc

class DataEntryDraftSavePayload(DataEntrySavePayload):
    user_id: int
    user_display_name: str = ""

@router.post("/api/org-product-data-entry/draft/save")
async def save_org_product_data_entry_draft(payload: DataEntryDraftSavePayload):
    entity_code = (payload.entity_code or "").strip()
    if not entity_code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(payload.year, int) or payload.year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    table_name = (payload.table_name or "").strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="table_name 不能为空")
    if not isinstance(payload.user_id, int) or payload.user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id 不合法")

    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_draft_table(conn)
            now = _now_iso()
            payload_obj = _sanitize_data_entry_payload_mapping_refs(conn, payload.model_dump())
            payload_json = json.dumps(payload_obj, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO org_product_data_entry_draft(
                  user_id, user_display_name, entity_code, entity_name, year, table_name, payload_json, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, entity_code, year, table_name) DO UPDATE SET
                  user_display_name=excluded.user_display_name,
                  entity_name=excluded.entity_name,
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                (
                    int(payload.user_id),
                    (payload.user_display_name or "").strip(),
                    entity_code,
                    (payload.entity_name or "").strip(),
                    int(payload.year),
                    table_name,
                    payload_json,
                    now,
                ),
            )
            conn.commit()
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存草稿失败：{exc}") from exc

@router.get("/api/org-product-data-entry/draft/get")
async def get_org_product_data_entry_draft(entity_code: str, year: int, table_name: str, user_id: int):
    code = (entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(year, int) or year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    tn = (table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")
    if not isinstance(user_id, int) or user_id <= 0:
        raise HTTPException(status_code=400, detail="user_id 不合法")

    path = common_db_path()
    if not path.exists():
        return {"found": False}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_draft_table(conn)
            cur = conn.execute(
                """
                SELECT payload_json, updated_at
                FROM org_product_data_entry_draft
                WHERE user_id=? AND entity_code=? AND year=? AND table_name=?
                """,
                (int(user_id), code, int(year), tn),
            )
            row = cur.fetchone()
            if not row:
                return {"found": False}
            payload_obj = json.loads(row[0]) if row[0] else None
            payload_obj = _sanitize_data_entry_payload_for_response(
                conn,
                payload_obj,
                entity_code=code,
                table_name=tn,
            )
            return {"found": True, "payload": payload_obj, "updated_at": row[1]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取草稿失败：{exc}") from exc

@router.get("/api/org-product-data-entry/draft/list")
async def list_org_product_data_entry_drafts(entity_code: str, year: int, table_name: str):
    code = (entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(year, int) or year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    tn = (table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")

    path = common_db_path()
    if not path.exists():
        return {"items": []}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_draft_table(conn)
            cur = conn.execute(
                """
                SELECT user_id, user_display_name, updated_at
                FROM org_product_data_entry_draft
                WHERE entity_code=? AND year=? AND table_name=?
                ORDER BY updated_at DESC
                """,
                (code, int(year), tn),
            )
            rows = cur.fetchall()
        return {
            "items": [
                {"user_id": int(r[0]), "user_display_name": str(r[1] or "").strip(), "updated_at": str(r[2] or "")}
                for r in rows
            ]
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取草稿列表失败：{exc}") from exc

def _load_org_product_data_entry_payload_for_sync(
    conn: sqlite3.Connection,
    *,
    entity_code: str,
    year: int,
    table_name: str,
    entry_version_id: int,
) -> dict[str, Any]:
    _ensure_data_entry_snapshot_table_v2(conn)
    cur = conn.execute(
        """
        SELECT payload_json
        FROM org_product_data_entry_snapshot_v2
        WHERE entity_code=? AND year=? AND version_id=? AND table_name=?
        """,
        (entity_code, int(year), int(entry_version_id), table_name),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="未找到机构产品数据录入版本")
    try:
        payload_obj = json.loads(row[0] or "{}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="机构产品数据录入版本 payload 无法解析") from exc
    if not isinstance(payload_obj, dict):
        raise HTTPException(status_code=500, detail="机构产品数据录入版本 payload 格式不正确")
    return _sanitize_data_entry_payload_for_response(
        conn,
        payload_obj,
        entity_code=entity_code,
        table_name=table_name,
    )


def _load_edit_show_version_ids_for_year(conn: sqlite3.Connection, year: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT e.edit_show_sign, e.version_id
        FROM edit_show_version e
        JOIN `databases` d ON d.id = e.data_file_id
        WHERE d.year = ? AND e.edit_show_sign IN (1, 5)
        ORDER BY e.edit_show_sign
        """,
        (int(year),),
    ).fetchall()
    out: list[int] = []
    seen: set[int] = set()
    for row in rows:
        version_id = int(row[1] if not isinstance(row, dict) else row.get("version_id") or 0)
        if version_id <= 0 or version_id in seen:
            continue
        seen.add(version_id)
        out.append(version_id)
    return out


def _resolve_budget_sync_target_version_ids(
    budget_path: Path,
    *,
    year: int,
    requested_version_id: int,
    common_path: Path,
) -> list[int]:
    """Resolve budget fact version ids for data-entry sync.

    Frontend historically passed entry slot ids like 1 for ``202603v1``; budget facts
    use ids like 2026000003. When the requested id is not a budget version, fall back
    to edit/show mapping (sign 1=展示预测, sign 5=展示预算) for the selected year.
    """
    with sqlite3.connect(budget_path) as budget_conn:
        try:
            load_budget_fact_version_identity_sync(budget_conn, int(requested_version_id))
            return [int(requested_version_id)]
        except BudgetFactVersionNotFound:
            pass

    with sqlite3.connect(common_path) as conn:
        mapped = _load_edit_show_version_ids_for_year(conn, year)
    if not mapped:
        raise HTTPException(
            status_code=400,
            detail=f"预算版本 {requested_version_id} 不存在，且 {year} 年未配置 edit/show 版本映射",
        )
    return mapped


def _build_org_product_budget_sync_plans(
    payload: OrgProductDataEntryBudgetSyncRequest,
) -> tuple[list[tuple[int, OrgProductBudgetSyncPlan]], Path, Path]:
    code = (payload.entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(payload.year, int) or payload.year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    tn = (payload.table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")
    if not isinstance(payload.entry_version_id, int) or payload.entry_version_id <= 0:
        raise HTTPException(status_code=400, detail="entry_version_id 不合法")
    if not isinstance(payload.budget_version_id, int) or payload.budget_version_id <= 0:
        raise HTTPException(status_code=400, detail="budget_version_id 不合法")

    common_path = common_db_path()
    if not common_path.exists():
        raise HTTPException(status_code=404, detail="common.db 不存在")
    bpath = budget_db_path(int(payload.year))
    if not bpath.exists():
        raise HTTPException(status_code=404, detail=f"budget_{int(payload.year)}.db 不存在")

    target_version_ids = _resolve_budget_sync_target_version_ids(
        bpath,
        year=int(payload.year),
        requested_version_id=int(payload.budget_version_id),
        common_path=common_path,
    )
    with sqlite3.connect(common_path) as conn:
        payload_obj = _load_org_product_data_entry_payload_for_sync(
            conn,
            entity_code=code,
            year=int(payload.year),
            table_name=tn,
            entry_version_id=int(payload.entry_version_id),
        )
        period_month_map = load_budget_fact_period_month_map_sync(conn, year_label=f"Y{int(payload.year)}")

    data_acct_codes: set[str] = set()
    metrics = payload_obj.get("metrics") if isinstance(payload_obj, dict) else []
    if isinstance(metrics, list):
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            metric_code = str(metric.get("metric_code") or metric.get("code") or "").strip().upper()
            data_acct_code = derive_runtime_ref_from_org_product_metric_code(
                entity_code=code,
                metric_code=metric_code,
            )
            if data_acct_code:
                data_acct_codes.add(data_acct_code)
    value_type_by_code = load_data_account_value_types_sync(common_path, data_acct_codes)

    plans: list[tuple[int, OrgProductBudgetSyncPlan]] = []
    with sqlite3.connect(bpath) as budget_conn:
        for version_id in target_version_ids:
            version_identity = load_budget_fact_version_identity_sync(budget_conn, int(version_id))
            plan = plan_org_product_budget_sync(
                payload=payload_obj,
                entity_code=code,
                table_name=tn,
                year=int(payload.year),
                budget_version_id=int(version_id),
                current_month=int(version_identity.current_month),
                period_month_map=period_month_map,
                budget_actuals=payload.budget_actuals,
                value_type_by_code=value_type_by_code,
            )
            plans.append((int(version_id), plan))
    return plans, common_path, bpath


def _merge_org_product_budget_sync_plans(plans: list[OrgProductBudgetSyncPlan]) -> OrgProductBudgetSyncPlan:
    merged = OrgProductBudgetSyncPlan()
    for plan in plans:
        merged.write_items.extend(plan.write_items)
        merged.candidate_rows += plan.candidate_rows
        merged.unbound_rows += plan.unbound_rows
        merged.non_confirmed_rows += plan.non_confirmed_rows
        merged.empty_rows += plan.empty_rows
        merged.skipped_cells += plan.skipped_cells
        merged.warnings.extend(plan.warnings)
    return merged


def _build_org_product_budget_sync_plan(payload: OrgProductDataEntryBudgetSyncRequest) -> tuple[OrgProductBudgetSyncPlan, Path, Path]:
    plans, common_path, bpath = _build_org_product_budget_sync_plans(payload)
    return _merge_org_product_budget_sync_plans([plan for _, plan in plans]), common_path, bpath

@router.post("/api/org-product-data-entry/commit/preview")
async def preview_org_product_data_entry_commit(payload: OrgProductDataEntryCommitRequest):
    code = (payload.entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(payload.year, int) or payload.year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    tn = (payload.table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")

    path = common_db_path()
    if not path.exists():
        return {"draft_count": 0, "conflict_count": 0, "conflicts": [], "merged_payload": None, "suggested_version_id": 1}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_draft_table(conn)
            user_ids = payload.user_ids or []
            if user_ids:
                placeholders = ",".join(["?"] * len(user_ids))
                cur = conn.execute(
                    f"""
                    SELECT user_id, user_display_name, payload_json, updated_at
                    FROM org_product_data_entry_draft
                    WHERE entity_code=? AND year=? AND table_name=? AND user_id IN ({placeholders})
                    ORDER BY updated_at DESC
                    """,
                    (code, int(payload.year), tn, *[int(x) for x in user_ids]),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT user_id, user_display_name, payload_json, updated_at
                    FROM org_product_data_entry_draft
                    WHERE entity_code=? AND year=? AND table_name=?
                    ORDER BY updated_at DESC
                    """,
                    (code, int(payload.year), tn),
                )
            rows = cur.fetchall()
            draft_items: list[dict[str, Any]] = []
            for uid, udisp, pjson, updated_at in rows:
                try:
                    pobj = json.loads(pjson or "{}")
                except Exception:
                    pobj = None
                draft_items.append(
                    {
                        "user_id": int(uid),
                        "user_display_name": str(udisp or "").strip(),
                        "updated_at": str(updated_at or ""),
                        "payload": pobj,
                    }
                )
            merged_payload, conflicts = _merge_data_entry_drafts(draft_items)
            merged_payload = _sanitize_data_entry_payload_mapping_refs(conn, merged_payload)
            suggested_version_id = _next_data_entry_version_id(conn, code, int(payload.year), tn)
        return {
            "draft_count": len(draft_items),
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "merged_payload": merged_payload,
            "suggested_version_id": int(suggested_version_id),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"预览提交失败：{exc}") from exc

@router.post("/api/org-product-data-entry/commit/apply")
async def apply_org_product_data_entry_commit(payload: OrgProductDataEntryCommitRequest):
    preview = await preview_org_product_data_entry_commit(payload)
    merged_payload = preview.get("merged_payload")
    if not merged_payload:
        raise HTTPException(status_code=400, detail="未找到可提交的草稿")
    conflict_count = int(preview.get("conflict_count") or 0)
    if conflict_count > 0 and not payload.force:
        raise HTTPException(status_code=400, detail=f"检测到 {conflict_count} 处冲突，请先处理或勾选强制提交。")

    code = (payload.entity_code or "").strip()
    tn = (payload.table_name or "").strip()
    version_id = int(payload.version_id) if payload.version_id is not None else int(preview.get("suggested_version_id") or 1)
    version_name = (payload.version_name or "").strip()
    merged_payload["version_id"] = version_id
    merged_payload["version_name"] = version_name

    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_snapshot_table(conn)
            _ensure_data_entry_snapshot_table_v2(conn)
            now = _now_iso()
            merged_payload = _sanitize_data_entry_payload_mapping_refs(conn, merged_payload)
            payload_json = json.dumps(merged_payload, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO org_product_data_entry_snapshot(entity_code, entity_name, year, month_index, table_id, table_name, payload_json, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_code, year) DO UPDATE SET
                  entity_name=excluded.entity_name,
                  month_index=excluded.month_index,
                  table_id=excluded.table_id,
                  table_name=excluded.table_name,
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                (
                    code,
                    str(merged_payload.get("entity_name") or ""),
                    int(merged_payload.get("year") or 0),
                    int(merged_payload.get("month_index")) if merged_payload.get("month_index") is not None else None,
                    str(merged_payload.get("table_id") or ""),
                    tn,
                    payload_json,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO org_product_data_entry_snapshot_v2(
                  entity_code, entity_name, year, version_id, version_name, table_name, month_index, table_id, payload_json, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_code, year, version_id, table_name) DO UPDATE SET
                  entity_name=excluded.entity_name,
                  version_name=excluded.version_name,
                  month_index=excluded.month_index,
                  table_id=excluded.table_id,
                  payload_json=excluded.payload_json,
                  updated_at=excluded.updated_at
                """,
                (
                    code,
                    str(merged_payload.get("entity_name") or ""),
                    int(merged_payload.get("year") or 0),
                    int(version_id),
                    version_name,
                    tn,
                    int(merged_payload.get("month_index")) if merged_payload.get("month_index") is not None else None,
                    str(merged_payload.get("table_id") or ""),
                    payload_json,
                    now,
                ),
            )
            conn.commit()
        return {"ok": True, "version_id": int(version_id), "updated_at": _now_iso()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"提交版本失败：{exc}") from exc

@router.post("/api/org-product-data-entry/budget-sync/preview")
async def preview_org_product_data_entry_budget_sync(payload: OrgProductDataEntryBudgetSyncRequest):
    plan, _common_path, _budget_path = _build_org_product_budget_sync_plan(payload)
    return plan.to_response()

@router.post("/api/org-product-data-entry/budget-sync/apply")
async def apply_org_product_data_entry_budget_sync(payload: OrgProductDataEntryBudgetSyncRequest):
    version_plans, common_path, bpath = _build_org_product_budget_sync_plans(payload)
    merged_response = _merge_org_product_budget_sync_plans([plan for _, plan in version_plans]).to_response()
    total_saved = 0
    total_skipped = 0
    all_warnings: list[str] = list(merged_response.get("warnings") or [])
    all_errors: list[str] = []
    affected_products: set[str] = set()
    written_data_accts: set[str] = set()
    metric_rollup_cells_written = 0
    summary_rows = 0
    budget_aggregate_rows = 0
    timestamp = _now_iso()

    for budget_version_id, plan in version_plans:
        apply_result = await apply_org_product_budget_sync_plan(
            plan=plan,
            common_path=common_path,
            budget_path=bpath,
            budget_version_id=int(budget_version_id),
            timestamp=timestamp,
        )
        write_result = apply_result.write_result
        total_saved += int(write_result.saved_cells or 0)
        total_skipped += int(write_result.skipped_cells or 0)
        metric_rollup_cells_written += int(apply_result.metric_rollup_cells_written or 0)
        summary_rows += int(apply_result.summary_rows or 0)
        budget_aggregate_rows += int(apply_result.budget_aggregate_rows or 0)
        affected_products.update(write_result.affected_products or [])
        written_data_accts.update(write_result.written_data_accts or [])
        all_warnings.extend(write_result.warnings or [])
        all_errors.extend(write_result.errors or [])

    response = merged_response
    response.update(
        {
            "ok": True,
            "target_version_ids": [int(vid) for vid, _ in version_plans],
            "saved_cells": int(total_saved),
            "skipped_cells": int(response.get("skipped_cells") or 0) + int(total_skipped),
            "affected_products": sorted(affected_products),
            "written_data_accts": sorted(written_data_accts),
            "metric_rollup_cells_written": int(metric_rollup_cells_written),
            "summary_rows": int(summary_rows),
            "budget_aggregate_rows": int(budget_aggregate_rows),
            "warnings": all_warnings[:80],
            "errors": all_errors,
        }
    )
    return response

@router.get("/api/org-product-data-entry/versions")
async def list_org_product_data_entry_versions(entity_code: str, year: int, table_name: str):
    code = (entity_code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not isinstance(year, int) or year <= 0:
        raise HTTPException(status_code=400, detail="year 不合法")
    tn = (table_name or "").strip()
    if not tn:
        raise HTTPException(status_code=400, detail="table_name 不能为空")

    path = common_db_path()
    if not path.exists():
        return {"items": []}
    try:
        with sqlite3.connect(path) as conn:
            _ensure_data_entry_snapshot_table_v2(conn)
            cur = conn.execute(
                """
                SELECT version_id, version_name, MAX(updated_at) AS updated_at
                FROM org_product_data_entry_snapshot_v2
                WHERE entity_code=? AND year=? AND table_name=?
                GROUP BY version_id, version_name
                ORDER BY version_id DESC
                """,
                (code, int(year), tn),
            )
            rows = cur.fetchall()
        return {
            "items": [
                {"version_id": int(r[0]), "version_name": str(r[1] or "").strip(), "updated_at": str(r[2] or "")}
                for r in rows
            ]
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取数据录入版本列表失败：{exc}") from exc

