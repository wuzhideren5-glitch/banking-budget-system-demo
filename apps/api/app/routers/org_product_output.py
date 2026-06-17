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
            for row in table_rows:
                ec = row.get("entity_code")
                en = row.get("entity_name")
                tn = row.get("table_name")
                payload_json = row.get("payload_json")
                ec_s = str(ec or "").strip()
                tn_s = str(tn or "").strip()
                if table_name and tn_s != table_name:
                    continue
                entity_name = str(en or "").strip() or entity_name_by_code.get(ec_s, "")
                try:
                    table_obj = json.loads(payload_json or "{}")
                except Exception:
                    table_obj = {}
                nodes = list(table_obj.get("metrics") or [])
                flat = _flatten_metric_nodes(nodes)
                children_by_code: dict[str, list[str]] = {}

                def collect_children_by_code(items: list[dict[str, Any]]) -> None:
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        parent_code = _normalize_text(item.get("code"))
                        children = [c for c in list(item.get("children") or []) if isinstance(c, dict)]
                        if parent_code:
                            children_by_code[parent_code] = [
                                _normalize_text(c.get("code")) for c in children if _normalize_text(c.get("code"))
                            ]
                        collect_children_by_code(children)

                collect_children_by_code([n for n in nodes if isinstance(n, dict)])
                metrics = [
                    {
                        "id": str(x.get("id") or ""),
                        "levelLabel": _normalize_text(x.get("levelLabel")),
                        "nature": _normalize_nature(x.get("nature")),
                        "code": _normalize_text(x.get("code")),
                        "name": _normalize_text(x.get("name")),
                        "formula": _normalize_text(x.get("formula")),
                        "formula_budget_annual": _normalize_text(x.get("formula_budget_annual")),
                        "formula_forecast_annual": _normalize_text(x.get("formula_forecast_annual")),
                        "formula_actual": _normalize_text(x.get("formula_actual")),
                        "formula_forecast": _normalize_text(x.get("formula_forecast")),
                        "formula_note": _normalize_text(x.get("formula_note")),
                        "value_type": _normalize_metric_value_type(x.get("value_type"), x.get("nature")),
                        "horizontal_rollup": _normalize_rollup_flag(x.get("horizontal_rollup")),
                        "vertical_rollup": _normalize_rollup_flag(x.get("vertical_rollup")),
                        "logic_code": _derive_metric_logic_code(ec_s, x.get("code"), x.get("logic_code")),
                    }
                    for x in flat
                    if _normalize_text(x.get("code")) and _normalize_text(x.get("name"))
                ]
                metric_by_code = {m["code"]: m for m in metrics}

                cur_snap = conn.execute(
                    """
                    SELECT payload_json, month_index
                    FROM org_product_data_entry_snapshot_v2
                    WHERE entity_code=? AND year=? AND version_id=? AND table_name=?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (ec_s, int(payload.year), int(version_id), tn_s),
                )
                snap_row = cur_snap.fetchone()
                snap_obj = json.loads(snap_row[0]) if snap_row and snap_row[0] else None
                rolling_month = 3
                if snap_row and snap_row[1] is not None:
                    try:
                        rolling_month = max(1, min(12, int(snap_row[1])))
                    except Exception:
                        rolling_month = 3
                elif isinstance(snap_obj, dict) and snap_obj.get("month_index") is not None:
                    try:
                        rolling_month = max(1, min(12, int(snap_obj.get("month_index"))))
                    except Exception:
                        rolling_month = 3
                entry_metrics = (
                    list((snap_obj or {}).get("metrics") or [])
                    if isinstance(snap_obj, dict)
                    else []
                )
                entry_by_code: dict[str, list[float | None]] = {}
                for r in entry_metrics:
                    if not isinstance(r, dict):
                        continue
                    mc = str(r.get("metric_code") or "").strip()
                    mid = str(r.get("metric_id") or "").strip()
                    key = mc or mid
                    if not key:
                        continue
                    v = r.get("values") if isinstance(r.get("values"), dict) else {}
                    months = [_parse_data_entry_month_value(v, m) for m in range(1, 13)]
                    entry_by_code[key] = months

                cache: dict[tuple[str, int], tuple[float, str | None]] = {}
                visiting: set[tuple[str, int]] = set()

                def resolve_ref_value(ref: str, month_idx: int) -> tuple[float, str | None]:
                    if "/" in ref:
                        parts = ref.split("/")
                        if len(parts) == 2:
                            ref_table_name, ref_code = parts[0], parts[1]
                            if ref_table_name == tn_s:
                                val, err = compute_metric_value(ref_code, month_idx)
                                return float(val), err
                            cur_other = conn.execute(
                                """
                                SELECT payload_json
                                FROM org_product_data_entry_snapshot_v2
                                WHERE entity_code=? AND year=? AND version_id=? AND table_name=?
                                ORDER BY updated_at DESC
                                LIMIT 1
                                """,
                                (ec_s, int(payload.year), int(version_id), ref_table_name),
                            )
                            other_row = cur_other.fetchone()
                            other_obj = json.loads(other_row[0]) if other_row and other_row[0] else None
                            other_entry = (
                                list((other_obj or {}).get("metrics") or [])
                                if isinstance(other_obj, dict)
                                else []
                            )
                            tmp_map: dict[str, list[float | None]] = {}
                            for rr in other_entry:
                                if not isinstance(rr, dict):
                                    continue
                                km = str(rr.get("metric_code") or "").strip() or str(rr.get("metric_id") or "").strip()
                                if not km:
                                    continue
                                vv = rr.get("values") if isinstance(rr.get("values"), dict) else {}
                                tmp_map[km] = [_parse_data_entry_month_value(vv, m) for m in range(1, 13)]
                            base = tmp_map.get(ref_code)
                            if base is not None:
                                val = base[month_idx - 1]
                                return (float(val) if val is not None else 0.0), None
                            return 0.0, None
                        if len(parts) != 3:
                            return 0.0, "#REF!"
                        ref_entity_code, ref_table_name, ref_code = parts[0], parts[1], parts[2]
                        if ref_entity_code != ec_s or ref_table_name != tn_s:
                            cur_other = conn.execute(
                                """
                                SELECT payload_json
                                FROM org_product_data_entry_snapshot_v2
                                WHERE entity_code=? AND year=? AND version_id=? AND table_name=?
                                ORDER BY updated_at DESC
                                LIMIT 1
                                """,
                                (ref_entity_code, int(payload.year), int(version_id), ref_table_name),
                            )
                            other_row = cur_other.fetchone()
                            other_obj = json.loads(other_row[0]) if other_row and other_row[0] else None
                            other_entry = (
                                list((other_obj or {}).get("metrics") or [])
                                if isinstance(other_obj, dict)
                                else []
                            )
                            tmp_map: dict[str, list[float | None]] = {}
                            for rr in other_entry:
                                if not isinstance(rr, dict):
                                    continue
                                km = str(rr.get("metric_code") or "").strip() or str(rr.get("metric_id") or "").strip()
                                if not km:
                                    continue
                                vv = rr.get("values") if isinstance(rr.get("values"), dict) else {}
                                tmp_map[km] = [_parse_data_entry_month_value(vv, m) for m in range(1, 13)]
                            base = tmp_map.get(ref_code)
                            if base is not None:
                                val = base[month_idx - 1]
                                return (float(val) if val is not None else 0.0), None
                            return 0.0, None
                        val, err = compute_metric_value(ref_code, month_idx)
                        return float(val), err
                    val, err = compute_metric_value(ref, month_idx)
                    return float(val), err

                def compute_metric_value(code_key: str, month_idx: int) -> tuple[float, str | None]:
                    k = (code_key, month_idx)
                    if k in cache:
                        return cache[k]
                    if k in visiting:
                        return 0.0, "#CYCLE!"
                    visiting.add(k)
                    try:
                        meta = metric_by_code.get(code_key)
                        if not meta:
                            base = entry_by_code.get(code_key)
                            if base is not None:
                                v = base[month_idx - 1]
                                return (float(v) if v is not None else 0.0), None
                            return 0.0, None
                        formula = _resolve_metric_formula_for_month(meta, month_idx, rolling_month)
                        if formula:
                            expr = _prepare_metric_formula_expression(formula)
                            refs = _extract_metric_formula_refs(expr)
                            ref_values: dict[str, float] = {}
                            ref_err: str | None = None
                            for r in refs:
                                v, err = resolve_ref_value(r, month_idx)
                                ref_values[r] = float(v)
                                if err and not ref_err:
                                    ref_err = err
                            val, calc_err = _try_calculate_metric_formula_value(expr, ref_values)
                            final_err = calc_err or ref_err
                            cache[k] = (float(val), final_err)
                            return cache[k]
                        if _normalize_rollup_flag(meta.get("vertical_rollup")):
                            child_codes = children_by_code.get(code_key) or []
                            if child_codes:
                                total = 0.0
                                child_err: str | None = None
                                for child_code in child_codes:
                                    v, err = compute_metric_value(child_code, month_idx)
                                    total += float(v)
                                    if err and not child_err:
                                        child_err = err
                                cache[k] = (total, child_err)
                                return cache[k]
                        base = entry_by_code.get(code_key) or entry_by_code.get(meta.get("id") or "")
                        if base is not None:
                            v = base[month_idx - 1]
                            cache[k] = (float(v) if v is not None else 0.0, None)
                            return cache[k]
                        cache[k] = (0.0, None)
                        return cache[k]
                    finally:
                        visiting.discard(k)

                month_results: dict[str, tuple[list[float], list[str | None]]] = {}
                for m in metrics:
                    code_key = m["code"]
                    computed = [compute_metric_value(code_key, mi) for mi in range(1, 13)]
                    months = [float(v) for v, _ in computed]
                    month_errors = [err for _, err in computed]
                    month_results[code_key] = (months, month_errors)

                annual_cache: dict[str, float | None] = {}
                annual_visiting: set[str] = set()
                run_year = int(payload.year)

                def _entry_months_for_entity_table(
                    entity: str, table: str
                ) -> dict[str, list[float | None]]:
                    cur_local = conn.execute(
                        """
                        SELECT payload_json
                        FROM org_product_data_entry_snapshot_v2
                        WHERE entity_code=? AND year=? AND version_id=? AND table_name=?
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (entity, run_year, int(version_id), table),
                    )
                    row_local = cur_local.fetchone()
                    obj_local = json.loads(row_local[0]) if row_local and row_local[0] else None
                    out_map: dict[str, list[float | None]] = {}
                    for rr in list((obj_local or {}).get("metrics") or []):
                        if not isinstance(rr, dict):
                            continue
                        km = str(rr.get("metric_code") or "").strip() or str(rr.get("metric_id") or "").strip()
                        if not km:
                            continue
                        vv = rr.get("values") if isinstance(rr.get("values"), dict) else {}
                        out_map[km] = [_parse_data_entry_month_value(vv, mi) for mi in range(1, 13)]
                    return out_map

                def compute_metric_annual(code_key: str) -> float | None:
                    if code_key in annual_cache:
                        return annual_cache[code_key]
                    if code_key in annual_visiting:
                        return None
                    meta = metric_by_code.get(code_key)
                    months_pack = month_results.get(code_key)
                    if not months_pack:
                        annual_cache[code_key] = None
                        return None
                    months, _errs = months_pack
                    month_vals: list[float | None] = list(months)

                    if not meta:
                        annual_cache[code_key] = _annual_summary_by_nature("", month_vals, run_year)
                        return annual_cache[code_key]

                    nature = str(meta.get("nature") or "")
                    formula = str(meta.get("formula") or "").strip()

                    if _normalize_rollup_flag(meta.get("vertical_rollup")):
                        child_codes = children_by_code.get(code_key) or []
                        if child_codes:
                            annual_visiting.add(code_key)
                            try:
                                total = 0.0
                                found_any = False
                                for child_code in child_codes:
                                    av = compute_metric_annual(child_code)
                                    if av is not None:
                                        total += float(av)
                                        found_any = True
                                annual_cache[code_key] = total if found_any else None
                                return annual_cache[code_key]
                            finally:
                                annual_visiting.discard(code_key)

                    if _should_annual_recompute_via_formula(nature, formula):
                        annual_visiting.add(code_key)
                        try:
                            expr = _prepare_metric_formula_expression(formula)
                            refs = _extract_metric_formula_refs(expr)
                            ref_values: dict[str, float] = {}
                            for r in refs:
                                if "/" in r:
                                    parts = r.split("/")
                                    if len(parts) == 2:
                                        ref_table_name, ref_code = parts[0], parts[1]
                                        if ref_table_name == tn_s:
                                            av = compute_metric_annual(ref_code)
                                        else:
                                            other_map = _entry_months_for_entity_table(ec_s, ref_table_name)
                                            other_months = other_map.get(ref_code)
                                            av = (
                                                _annual_summary_by_nature("", other_months, run_year)
                                                if other_months is not None
                                                else None
                                            )
                                        ref_values[r] = float(av) if av is not None else 0.0
                                        continue
                                    if len(parts) != 3:
                                        ref_values[r] = 0.0
                                        continue
                                    ref_entity_code, ref_table_name, ref_code = parts
                                    if ref_entity_code == ec_s and ref_table_name == tn_s:
                                        av = compute_metric_annual(ref_code)
                                    else:
                                        other_map = _entry_months_for_entity_table(
                                            ref_entity_code, ref_table_name
                                        )
                                        other_months = other_map.get(ref_code)
                                        if other_months is None:
                                            av = None
                                        else:
                                            av = _annual_summary_by_nature(
                                                "", other_months, run_year
                                            )
                                    ref_values[r] = float(av) if av is not None else 0.0
                                else:
                                    av = compute_metric_annual(r)
                                    ref_values[r] = float(av) if av is not None else 0.0
                            val, _calc_err = _try_calculate_metric_formula_value(expr, ref_values)
                            annual_cache[code_key] = float(val)
                            return annual_cache[code_key]
                        finally:
                            annual_visiting.discard(code_key)

                    annual_cache[code_key] = _annual_summary_by_nature(nature, month_vals, run_year)
                    return annual_cache[code_key]

                out_rows: list[dict[str, Any]] = []
                for m in metrics:
                    code_key = m["code"]
                    months, month_errors = month_results[code_key]
                    annual = compute_metric_annual(code_key)
                    formula = str(m.get("formula") or "").strip()
                    out_rows.append(
                        {
                            "id": m["id"],
                            "levelLabel": m["levelLabel"],
                            "nature": m["nature"],
                            "code": m["code"],
                            "name": m["name"],
                            "value_type": m["value_type"],
                            "formula": formula,
                            "months": months,
                            "month_errors": month_errors,
                            "annual": annual,
                            "annual_method": _annual_method_label(m["nature"], formula),
                        }
                    )

                output_entities.append(
                    {
                        "entity_code": ec_s,
                        "entity_name": entity_name,
                        "table_name": tn_s,
                        "rows": out_rows,
                    }
                )
        return {"entities": output_entities}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"预测输出计算失败：{exc}") from exc

@router.post("/api/org-product-output/export")
async def export_org_product_output(payload: OrgProductOutputRunRequest):
    result = await run_org_product_output(payload)
    entities = list(result.get("entities") or [])
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
    filename = f"预测输出_{payload.entity_code}_{payload.year}_v{payload.version_id}.xlsx".replace(" ", "")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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

