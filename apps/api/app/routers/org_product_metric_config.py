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
from app.routers.org_product_helpers import (
    _ensure_metric_table_catalog,
    _load_metric_table_catalog_rows,
    _metric_table_catalog_row_to_dict,
    _normalize_text,
    _now_iso,
    _parse_metric_batch_upload,
    _parse_metric_upload,
    _parse_metric_workbook,
    _parse_metric_workbook_tables,
    _sanitize_metric_node_dicts_for_response,
    _sanitize_metric_nodes_for_save,
    _seed_metric_table_catalog,
)

def _build_entities_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 runtime_tree rows 转换为与 db-snapshot 一致的 entities 列表。"""
    entities: dict[str, dict[str, Any]] = {}
    for row in rows:
        entity_code = row.get("entity_code")
        entity_name = row.get("entity_name")
        table_name = row.get("table_name")
        payload_json = row.get("payload_json")
        code = str(entity_code or "").strip()
        if not code:
            continue
        ent = entities.setdefault(
            code,
            {
                "entity_code": code,
                "entity_name": str(entity_name or "").strip(),
                "tables": [],
            },
        )
        try:
            table_obj = json.loads(payload_json or "{}")
        except Exception:
            table_obj = {}
        table_obj["name"] = str(table_obj.get("name") or table_name or "").strip() or str(table_name or "").strip()
        metrics = table_obj.get("metrics") if isinstance(table_obj.get("metrics"), list) else []
        table_obj["metrics"] = _sanitize_metric_node_dicts_for_response(
            code,
            [item for item in metrics if isinstance(item, dict)],
        )
        ent["tables"].append(table_obj)
    return list(entities.values())


router = APIRouter()

@router.get("/api/org-product-metrics/bootstrap")
async def get_org_product_metric_seed():
    # 优先从 Excel 种子文件读取；若文件缺失则回退到数据库快照
    excel_missing = not ORG_METRIC_FILE.is_file() and not PRODUCT_METRIC_FILE.is_file()
    if not excel_missing:
        try:
            items: dict[str, list[dict[str, Any]]] = {}
            table_items: dict[str, list[dict[str, Any]]] = {}
            items.update(_parse_metric_workbook(ORG_METRIC_FILE))
            items.update(_parse_metric_workbook(PRODUCT_METRIC_FILE))
            table_items.update(_parse_metric_workbook_tables(ORG_METRIC_FILE))
            table_items.update(_parse_metric_workbook_tables(PRODUCT_METRIC_FILE))

            # Excel 分支也附加数据库 entities（供前端补充 orgTree，与 db-snapshot 一致）
            db_entities: list[dict[str, Any]] = []
            path = common_db_path()
            if path.exists():
                try:
                    with sqlite3.connect(path) as conn:
                        rows = load_org_product_metric_table_rows_from_runtime_tree(conn)
                        db_entities = _build_entities_from_rows(rows)
                except Exception:
                    db_entities = []

            return {
                "items": items,
                "table_items": table_items,
                "entities": db_entities,
                "sources": {
                    "org_metric_file": str(ORG_METRIC_FILE),
                    "product_metric_file": str(PRODUCT_METRIC_FILE),
                },
            }
        except FileNotFoundError:
            excel_missing = True  # 部分文件缺失，统一走 DB 回退
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"读取指标 Excel 失败：{exc}") from exc

    # DB 回退：从 common.db 读取已保存的指标
    path = common_db_path()
    if not path.exists():
        return {"items": {}, "table_items": {}, "entities": [], "sources": {"fallback": "db", "note": "数据库不存在"}}

    try:
        with sqlite3.connect(path) as conn:
            rows = load_org_product_metric_table_rows_from_runtime_tree(conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取数据库指标失败：{exc}") from exc

    db_entities = _build_entities_from_rows(rows)
    items: dict[str, list[dict[str, Any]]] = {}
    table_items: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        entity_code = str(row.get("entity_code") or "").strip()
        if not entity_code:
            continue
        payload_json = row.get("payload_json")
        try:
            table_obj = json.loads(payload_json or "{}")
        except Exception:
            table_obj = {}
        table_name = str(table_obj.get("name") or row.get("table_name") or "").strip() or "业务状况表"
        metrics = table_obj.get("metrics") if isinstance(table_obj.get("metrics"), list) else []
        sanitized = _sanitize_metric_node_dicts_for_response(
            entity_code,
            [item for item in metrics if isinstance(item, dict)],
        )
        table_dict = {"id": f"table-{table_name}-{entity_code}", "name": table_name, "metrics": sanitized}
        table_items.setdefault(entity_code, []).append(table_dict)
        # 第一张表的指标作为 items（与 Excel 解析行为一致）
        if entity_code not in items and sanitized:
            items[entity_code] = list(sanitized)

    return {
        "items": items,
        "table_items": table_items,
        "entities": db_entities,
        "sources": {"fallback": "db", "note": "Excel 种子文件未找到，已从数据库读取"},
    }

@router.get("/api/org-product-metrics/table-catalog")
async def get_metric_table_catalog(
    entity_scope: str | None = Query(None),
    status: str | None = Query(None),
):
    scope = _normalize_text(entity_scope).upper() if entity_scope else ""
    if scope and scope not in METRIC_TABLE_CATALOG_SCOPES:
        raise HTTPException(status_code=400, detail=f"entity_scope 无效：{scope}")
    status_norm = _normalize_text(status).lower() if status else ""
    if status_norm and status_norm not in METRIC_TABLE_CATALOG_STATUSES:
        raise HTTPException(status_code=400, detail=f"status 无效：{status_norm}")
    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            rows = _load_metric_table_catalog_rows(conn, entity_scope=scope or None)
            if status_norm:
                rows = [r for r in rows if str(r.get("status") or "") == status_norm]
            return {"items": rows}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取指标表目录失败：{exc}") from exc

@router.post("/api/org-product-metrics/table-catalog")
async def create_metric_table_catalog_item(payload: MetricTableCatalogCreatePayload):
    scope = _normalize_text(payload.entity_scope).upper()
    if scope not in METRIC_TABLE_CATALOG_SCOPES:
        raise HTTPException(status_code=400, detail=f"entity_scope 无效：{scope}")
    table_name = _normalize_text(payload.table_name)
    if not table_name:
        raise HTTPException(status_code=400, detail="table_name 不能为空")
    if not table_name.endswith("表"):
        raise HTTPException(status_code=400, detail="指标表名称须以「表」结尾")
    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            _ensure_metric_table_catalog(conn)
            _seed_metric_table_catalog(conn)
            sort_order = payload.sort_order
            if sort_order is None:
                cur = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) FROM org_product_metric_table_catalog WHERE entity_scope = ?",
                    (scope,),
                )
                sort_order = int(cur.fetchone()[0] or 0) + 10
            now = _now_iso()
            conn.execute(
                """
                INSERT INTO org_product_metric_table_catalog
                (entity_scope, table_name, sort_order, status, remark, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (scope, table_name, int(sort_order), _normalize_text(payload.remark), now),
            )
            row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            cur = conn.execute(
                """
                SELECT id, entity_scope, table_name, sort_order, status, remark, updated_at
                FROM org_product_metric_table_catalog WHERE id = ?
                """,
                (row_id,),
            )
            row = cur.fetchone()
            conn.commit()
            if not row:
                raise HTTPException(status_code=500, detail="创建后未能读取记录")
            return {"item": _metric_table_catalog_row_to_dict(row)}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该范围下已存在同名指标表") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"新增指标表目录失败：{exc}") from exc

@router.patch("/api/org-product-metrics/table-catalog/{item_id}")
async def patch_metric_table_catalog_item(item_id: int, payload: MetricTableCatalogPatchPayload):
    if item_id <= 0:
        raise HTTPException(status_code=400, detail="id 不合法")
    status_norm = _normalize_text(payload.status).lower() if payload.status is not None else ""
    if status_norm and status_norm not in METRIC_TABLE_CATALOG_STATUSES:
        raise HTTPException(status_code=400, detail=f"status 无效：{status_norm}")
    path = common_db_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="指标表目录不存在")
    try:
        with sqlite3.connect(path) as conn:
            _ensure_metric_table_catalog(conn)
            cur = conn.execute(
                "SELECT id FROM org_product_metric_table_catalog WHERE id = ?",
                (item_id,),
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="记录不存在")
            updates: list[str] = []
            params: list[Any] = []
            if payload.sort_order is not None:
                updates.append("sort_order = ?")
                params.append(int(payload.sort_order))
            if status_norm:
                updates.append("status = ?")
                params.append(status_norm)
            if payload.remark is not None:
                updates.append("remark = ?")
                params.append(_normalize_text(payload.remark))
            if not updates:
                raise HTTPException(status_code=400, detail="未提供可更新字段")
            updates.append("updated_at = ?")
            params.append(_now_iso())
            params.append(item_id)
            conn.execute(
                f"UPDATE org_product_metric_table_catalog SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            cur = conn.execute(
                """
                SELECT id, entity_scope, table_name, sort_order, status, remark, updated_at
                FROM org_product_metric_table_catalog WHERE id = ?
                """,
                (item_id,),
            )
            row = cur.fetchone()
            conn.commit()
            if not row:
                raise HTTPException(status_code=500, detail="更新后未能读取记录")
            return {"item": _metric_table_catalog_row_to_dict(row)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新指标表目录失败：{exc}") from exc

@router.post("/api/org-product-metrics/import")
async def import_org_product_metrics(file: UploadFile = File(...)):
    content = await file.read()
    metrics, row_count = _parse_metric_upload(content, file.filename or "metrics.xlsx")
    return {
        "row_count": row_count,
        "metrics": metrics,
    }

@router.post("/api/org-product-metrics/import-batch")
async def import_org_product_metrics_batch(file: UploadFile = File(...), table_names: str = Form(...)):
    try:
        parsed_table_names = json.loads(table_names)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"指标表名称参数无法解析：{exc}") from exc

    if not isinstance(parsed_table_names, list) or not all(isinstance(name, str) and name.strip() for name in parsed_table_names):
        raise HTTPException(status_code=400, detail="指标表名称参数格式不正确")

    content = await file.read()
    imported_tables, missing_tables, ignored_sheets = _parse_metric_batch_upload(
        content,
        file.filename or "metrics.xlsx",
        [name.strip() for name in parsed_table_names],
    )
    return {
        "imported_tables": imported_tables,
        "missing_tables": missing_tables,
        "ignored_sheets": ignored_sheets,
    }

@router.post("/api/org-product-metrics/save-table")
async def save_org_product_metrics_table(payload: MetricSaveTablePayload):
    entity_code = payload.entity_code.strip()
    table_name = payload.table_name.strip()
    if not entity_code:
        raise HTTPException(status_code=400, detail="entity_code 不能为空")
    if not table_name:
        raise HTTPException(status_code=400, detail="table_name 不能为空")

    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            metrics = _sanitize_metric_nodes_for_save(entity_code, payload.metrics)
            sync_org_product_metric_runtime_refs(
                conn,
                entity_code=entity_code,
                table_name=table_name,
                metrics=metrics,
                overwrite_existing_metadata=True,
            )
            conn.commit()
    except OrgProductMetricRuntimeSyncError as exc:
        raise HTTPException(status_code=400, detail=f"保存失败：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存失败：{exc}") from exc

    return {"saved_tables": 1}

@router.post("/api/org-product-metrics/save-refresh")
async def save_org_product_metrics(payload: MetricSavePayload):
    if not payload.entities:
        raise HTTPException(status_code=400, detail="entities 不能为空")

    path = common_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    saved_entities = 0
    saved_tables = 0
    try:
        with sqlite3.connect(path) as conn:
            for entity in payload.entities:
                if not entity.entity_code.strip():
                    continue
                if not entity.tables:
                    continue
                saved_entities += 1
                for table in entity.tables:
                    table_name = (table.name or "").strip() or "业务状况表"
                    metrics = _sanitize_metric_nodes_for_save(entity.entity_code.strip(), table.metrics)
                    sync_org_product_metric_runtime_refs(
                        conn,
                        entity_code=entity.entity_code.strip(),
                        table_name=table_name,
                        metrics=metrics,
                        overwrite_existing_metadata=True,
                    )
                    saved_tables += 1
            conn.commit()
    except OrgProductMetricRuntimeSyncError as exc:
        raise HTTPException(status_code=400, detail=f"保存失败：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存失败：{exc}") from exc

    return {"saved_entities": saved_entities, "saved_tables": saved_tables}

@router.get("/api/org-product-metrics/db-snapshot")
async def get_org_product_metrics_snapshot():
    path = common_db_path()
    if not path.exists():
        return {"entities": []}
    try:
        with sqlite3.connect(path) as conn:
            rows = load_org_product_metric_table_rows_from_runtime_tree(conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取失败：{exc}") from exc

    entities: dict[str, dict[str, Any]] = {}
    for row in rows:
        entity_code = row.get("entity_code")
        entity_name = row.get("entity_name")
        table_name = row.get("table_name")
        payload_json = row.get("payload_json")
        code = str(entity_code or "").strip()
        if not code:
            continue
        ent = entities.setdefault(
            code,
            {
                "entity_code": code,
                "entity_name": str(entity_name or "").strip(),
                "tables": [],
            },
        )
        try:
            table_obj = json.loads(payload_json or "{}")
        except Exception:
            table_obj = {}
        table_obj["name"] = str(table_obj.get("name") or table_name or "").strip() or str(table_name or "").strip()
        metrics = table_obj.get("metrics") if isinstance(table_obj.get("metrics"), list) else []
        table_obj["metrics"] = _sanitize_metric_node_dicts_for_response(
            code,
            [item for item in metrics if isinstance(item, dict)],
        )
        ent["tables"].append(table_obj)

    return {"entities": list(entities.values())}

@router.post("/api/org-product-metrics/annual-aggregate")
async def compute_annual_aggregation(
    data_acct_codes: list[str] = Body(..., embed=True),
    budget_actual: int = Query(0, ge=0, le=1),
    year: int = Query(2026),
):
    """批量计算年度聚合值。返回每个指标的年度聚合结果。"""
    from app.services.annual_aggregation import aggregate_batch

    common = common_db_path()
    budget = budget_db_path(int(year))
    if not common.exists():
        raise HTTPException(status_code=500, detail="common.db 不存在")
    if not budget.exists():
        raise HTTPException(status_code=500, detail="budget.db 不存在")

    report = await aggregate_batch(
        common_path=common,
        budget_path=budget,
        data_acct_codes=data_acct_codes,
        budget_actual=int(budget_actual),
        year=int(year),
    )
    return report.to_summary()

@router.get("/api/org-product-metrics/{metric_code}/annual-aggregate")
async def get_single_annual_aggregation(
    metric_code: str,
    budget_actual: int = Query(0, ge=0, le=1),
    year: int = Query(2026),
):
    """获取单个指标的年度聚合值"""
    from app.services.annual_aggregation import aggregate_single_metric

    common = common_db_path()
    budget = budget_db_path()
    if not common.exists():
        raise HTTPException(status_code=500, detail="common.db 不存在")
    if not budget.exists():
        raise HTTPException(status_code=500, detail="budget.db 不存在")

    result = await aggregate_single_metric(
        common_path=common,
        budget_path=budget,
        data_acct_code=metric_code,
        budget_actual=int(budget_actual),
        year=int(year),
    )
    return {
        "code": result.data_acct_code,
        "annual_value": result.annual_value,
        "rule": result.rule,
        "month_count": result.month_count,
        "error": result.error,
    }
