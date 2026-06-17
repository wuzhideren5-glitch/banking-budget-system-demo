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

router = APIRouter()

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
            now = _now_iso()
            payload_obj = _sanitize_data_entry_payload_mapping_refs(conn, payload.model_dump())
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
                    (payload.entity_name or "").strip(),
                    int(payload.year),
                    int(payload.month_index) if payload.month_index is not None else None,
                    (payload.table_id or "").strip(),
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
                    (payload.entity_name or "").strip(),
                    int(payload.year),
                    int(version_id),
                    version_name,
                    table_name,
                    int(payload.month_index) if payload.month_index is not None else None,
                    (payload.table_id or "").strip(),
                    payload_json,
                    now,
                ),
            )
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

def _build_org_product_budget_sync_plan(payload: OrgProductDataEntryBudgetSyncRequest) -> tuple[OrgProductBudgetSyncPlan, Path, Path]:
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

    with sqlite3.connect(common_path) as conn:
        payload_obj = _load_org_product_data_entry_payload_for_sync(
            conn,
            entity_code=code,
            year=int(payload.year),
            table_name=tn,
            entry_version_id=int(payload.entry_version_id),
        )
        period_month_map = load_budget_fact_period_month_map_sync(conn, year_label=f"Y{int(payload.year)}")
    try:
        with sqlite3.connect(bpath) as budget_conn:
            version_identity = load_budget_fact_version_identity_sync(budget_conn, int(payload.budget_version_id))
    except BudgetFactVersionNotFound as exc:
        raise HTTPException(status_code=400, detail=f"预算版本 {exc.version_id} 不存在") from exc
    plan = plan_org_product_budget_sync(
        payload=payload_obj,
        entity_code=code,
        table_name=tn,
        year=int(payload.year),
        budget_version_id=int(payload.budget_version_id),
        current_month=int(version_identity.current_month),
        period_month_map=period_month_map,
        budget_actuals=payload.budget_actuals,
    )
    return plan, common_path, bpath

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
    plan, common_path, bpath = _build_org_product_budget_sync_plan(payload)
    apply_result = await apply_org_product_budget_sync_plan(
        plan=plan,
        common_path=common_path,
        budget_path=bpath,
        budget_version_id=int(payload.budget_version_id),
        timestamp=_now_iso(),
    )
    write_result = apply_result.write_result
    response = plan.to_response()
    response.update(
        {
            "ok": True,
            "saved_cells": int(write_result.saved_cells),
            "skipped_cells": int(response.get("skipped_cells") or 0) + int(write_result.skipped_cells),
            "affected_products": sorted(write_result.affected_products),
            "written_data_accts": sorted(write_result.written_data_accts),
            "metric_rollup_cells_written": int(apply_result.metric_rollup_cells_written),
            "summary_rows": int(apply_result.summary_rows),
            "budget_aggregate_rows": int(apply_result.budget_aggregate_rows),
            "warnings": [*(response.get("warnings") or []), *write_result.warnings][:80],
            "errors": write_result.errors,
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

