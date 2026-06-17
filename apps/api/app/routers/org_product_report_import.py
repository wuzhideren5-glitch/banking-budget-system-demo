from __future__ import annotations

import json
import sqlite3
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.core.db_paths import budget_db_path, common_db_path
from app.routers.org_product_helpers import *

router = APIRouter()

@router.post("/api/org-product-metrics/import-report")
async def import_org_product_metrics_report(
    file: UploadFile = File(...),
    candidates_json: str = Form(""),
    strict_import: str = Form("true"),
):
    content = await file.read()
    try:
        workbook = load_workbook(filename=BytesIO(content), data_only=False, read_only=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无法读取Excel文件：{exc}") from exc

    candidates: list[tuple[str, str, str]] = []
    seen_candidate_keys: set[str] = set()

    def _add_candidate(code: str, name: str, table_name: str) -> None:
        c = _normalize_text(code).upper()
        t = _normalize_text(table_name)
        if not c or not t:
            return
        key = f"{c}::{t}"
        if key in seen_candidate_keys:
            return
        seen_candidate_keys.add(key)
        candidates.append((c, _normalize_text(name), t))

    if candidates_json.strip():
        try:
            parsed = json.loads(candidates_json)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"candidates_json 无效：{exc}") from exc
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                _add_candidate(
                    str(item.get("entity_code") or ""),
                    str(item.get("entity_name") or ""),
                    str(item.get("table_name") or ""),
                )

    path = common_db_path()
    if path.exists():
        try:
            with sqlite3.connect(path) as conn:
                _ensure_metric_table_catalog(conn)
                _seed_metric_table_catalog(conn)
                known_names = _canonical_import_table_names(conn)
                for entity_code, entity_name, table_name in _import_report_catalog_candidates(conn):
                    _add_candidate(entity_code, entity_name, _canonical_import_table_name(table_name, known_names=known_names))
                for entity_code, entity_name, table_name in _import_report_saved_metric_candidates(conn):
                    _add_candidate(entity_code, entity_name, _canonical_import_table_name(table_name, known_names=known_names))
        except Exception:
            for table_name in (
                "业务状况表",
                "损益表",
                "资产负债表（余额）",
                "资产负债表（日均）",
                "资产质量表",
                "利息净收入表",
                "净利息收入表",
            ):
                _add_candidate("AA", "微众银行", table_name)
    else:
        for table_name in (
            "业务状况表",
            "损益表",
            "资产负债表（余额）",
            "资产负债表（日均）",
            "资产质量表",
            "利息净收入表",
            "净利息收入表",
        ):
            _add_candidate("AA", "微众银行", table_name)

    imported_entities: list[dict[str, Any]] = []
    ignored_sheets: list[str] = []
    ignored_details: list[dict[str, str]] = []
    formula_convert_errors: list[dict[str, Any]] = []
    prefix = re.sub(r"[^A-Za-z0-9]+", "-", Path(file.filename or "report.xlsx").stem) or "report"
    strict_flag = _parse_strict_import_flag(strict_import)

    def _ignore_sheet(sheet: str, reason: str) -> None:
        ignored_sheets.append(sheet)
        ignored_details.append({"sheet_name": sheet, "reason": reason})

    sheet_contexts: list[SheetFormulaContext] = []
    for sheet_name in workbook.sheetnames:
        ws = workbook[sheet_name]
        _prepare_metric_worksheet(ws)
        resolved = _resolve_import_sheet_entity_table(sheet_name, candidates, strict=True)
        if not resolved:
            continue
        entity_code, table_name, _entity_name = resolved
        header_row_idx, header_map, _header_mode, _header_source = _find_header_row(
            ws, entity_code, strict=strict_flag, sheet_title=sheet_name
        )
        code_col = header_map.get("科目代码") if header_row_idx else None
        name_col = header_map.get("科目名称") if header_row_idx else None
        code_col, _name_col = _maybe_swap_metric_code_name_columns(
            ws,
            header_row_idx=header_row_idx or 1,
            entity_code=entity_code,
            code_col=code_col,
            name_col=name_col,
        )
        if not header_row_idx or not code_col:
            continue
        row_limit = _sheet_scan_row_limit(ws, header_row_idx)
        sheet_contexts.append(
            build_sheet_formula_context(
                sheet_name,
                entity_code,
                table_name,
                header_row_idx,
                code_col,
                lambda r, c, _ws=ws: _ws_cell_value(_ws, r, c),
                _normalize_metric_code,
                row_limit,
            )
        )
    all_sheet_contexts = index_sheet_contexts(sheet_contexts)

    for sheet_name in workbook.sheetnames:
        ws = workbook[sheet_name]
        _prepare_metric_worksheet(ws)

        resolved = _resolve_import_sheet_entity_table(sheet_name, candidates, strict=True)
        if not resolved:
            _ignore_sheet(
                sheet_name,
                "工作表名未匹配到机构/指标表（标准格式：代码+表名，如 AA资产质量表）",
            )
            continue
        entity_code, table_name, entity_name = resolved

        sheet_ctx = all_sheet_contexts.get(normalize_sheet_lookup_key(sheet_name))

        metrics, row_count, parse_error, header_map = _parse_metric_worksheet_basic(
            ws,
            f"{prefix}-{sheet_name}",
            entity_code=entity_code,
            strict=strict_flag,
            sheet_formula_context=sheet_ctx,
            all_sheet_contexts=all_sheet_contexts,
            formula_convert_errors=formula_convert_errors,
        )
        if parse_error:
            detail = parse_error
            if header_map:
                detail += f"；列映射={header_map}"
            _ignore_sheet(sheet_name, detail)
            continue

        if row_count > 0 and len(metrics) <= 0:
            _ignore_sheet(sheet_name, "解析到行数但科目树为空，请检查科目层级/代码列")
            continue

        imported_entities.append(
            {
                "sheet_name": sheet_name,
                "entity_code": entity_code,
                "entity_name": entity_name,
                "table_name": table_name,
                "row_count": row_count,
                "has_formula_column": bool(
                    header_map.get("取数公式")
                    or header_map.get("年预算公式")
                    or header_map.get("年预测公式")
                    or header_map.get("实际月公式")
                    or header_map.get("预测月公式")
                ),
                "metrics": metrics,
            }
        )

    return {
        "imported_entities": imported_entities,
        "ignored_sheets": ignored_sheets,
        "ignored_details": ignored_details,
        "formula_convert_errors": formula_convert_errors,
    }

@router.post("/api/org-product-metrics/export")
async def export_org_product_metrics(payload: MetricExportPayload):
    wb = Workbook()
    ws = wb.active
    sheet_name = f"{payload.entity_code}{payload.entity_name}{payload.table_name}".replace("/", "_").replace("\\", "_")
    ws.title = (sheet_name or "机构及产品指标")[:31]

    headers = [
        "科目层级",
        "科目性质",
        "科目代码",
        "科目名称",
        "数值类型",
        "允许手工录入",
        "指标解释",
        "录入粒度",
        "年预算公式",
        "年预测公式",
        "实际月公式",
        "预测月公式",
        "公式说明",
        "横向汇总",
        "纵向汇总",
        "逻辑码",
    ]
    ws.append(headers)

    rows: list[dict[str, str]] = []
    _build_metric_rows([item.model_dump() for item in payload.metrics], rows, payload.entity_code)
    for row in rows:
        actual = row["formula_actual"] or row["formula"]
        forecast = row["formula_forecast"] or row["formula"]
        ws.append(
            [
                row["levelLabel"],
                row["nature"],
                row["code"],
                row["name"],
                row["value_type"],
                _allow_manual_entry_label(row["allow_manual_entry"]),
                row["note"],
                _entry_granularity_label(row["entry_granularity"]),
                row["formula_budget_annual"],
                row["formula_forecast_annual"],
                actual,
                forecast,
                row["formula_note"],
                _rollup_flag_label(row["horizontal_rollup"]),
                _rollup_flag_label(row["vertical_rollup"]),
                row["logic_code"],
            ]
        )

    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 36
    ws.column_dimensions["E"].width = 24
    ws.column_dimensions["F"].width = 20
    ws.column_dimensions["G"].width = 20
    ws.column_dimensions["H"].width = 40
    ws.column_dimensions["I"].width = 14
    ws.column_dimensions["J"].width = 48
    ws.column_dimensions["K"].width = 48
    ws.column_dimensions["L"].width = 16

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"{payload.entity_code}_{payload.entity_name}_{payload.table_name}.xlsx".replace(" ", "")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post("/api/org-product-metrics/export-report")
async def export_org_product_metrics_report(payload: MetricReportExportPayload):
    if not payload.sheets:
        raise HTTPException(status_code=400, detail="sheets 不能为空")

    wb = Workbook()
    wb.remove(wb.active)

    used_titles: set[str] = set()
    for sheet in payload.sheets:
        entity_code = _normalize_text(sheet.entity_code).upper()
        table_name = _normalize_text(sheet.table_name)
        if not entity_code or not table_name:
            continue
        title = _unique_sheet_title(used_titles, f"{entity_code}{table_name}")
        ws = wb.create_sheet(title=title)

        headers = [
            "科目层级",
            "科目性质",
            "科目代码",
            "科目名称",
            "数值类型",
            "允许手工录入",
            "录入粒度",
            "年预算公式",
            "年预测公式",
            "实际月公式",
            "预测月公式",
            "公式说明",
            "横向汇总",
            "纵向汇总",
            "逻辑码",
        ]
        ws.append(headers)

        rows: list[dict[str, str]] = []
        _build_metric_rows([item.model_dump() for item in sheet.metrics], rows, sheet.entity_code)
        for row in rows:
            actual = row["formula_actual"] or row["formula"]
            forecast = row["formula_forecast"] or row["formula"]
            ws.append(
                [
                    row["levelLabel"],
                    row["nature"],
                    row["code"],
                    row["name"],
                    row["value_type"],
                    _allow_manual_entry_label(row["allow_manual_entry"]),
                    _entry_granularity_label(row["entry_granularity"]),
                    row["formula_budget_annual"],
                    row["formula_forecast_annual"],
                    actual,
                    forecast,
                    row["formula_note"],
                    _rollup_flag_label(row["horizontal_rollup"]),
                    _rollup_flag_label(row["vertical_rollup"]),
                    row["logic_code"],
                ]
            )

        for cell in ws[1]:
            cell.font = cell.font.copy(bold=True)
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 20
        ws.column_dimensions["D"].width = 36
        ws.column_dimensions["E"].width = 24
        ws.column_dimensions["F"].width = 20
        ws.column_dimensions["G"].width = 20
        ws.column_dimensions["H"].width = 14
        ws.column_dimensions["I"].width = 48
        ws.column_dimensions["J"].width = 48
        ws.column_dimensions["K"].width = 16

    if not wb.sheetnames:
        raise HTTPException(status_code=400, detail="没有可导出的工作表")

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = "机构及产品指标.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _attachment_content_disposition(filename, ascii_fallback="org_product_metrics.xlsx")},
    )

