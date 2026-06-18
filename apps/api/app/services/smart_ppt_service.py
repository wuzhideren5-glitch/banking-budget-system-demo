"""场景驱动的智能PPT服务 —— 场景编排 + 数据取数 + 图表生成 + PPT 组装"""

from __future__ import annotations

import io
import json
import math
import re
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.database import get_pool
from app.core.config import settings
from app.core.db_paths import budget_db_path, common_db_path
from app.schemas import (
    SmartPptChartConfigRow,
    SmartPptGenerateResponse,
    SmartPptInstanceRow,
    SmartPptSceneDetailResponse,
    SmartPptSceneRow,
    SmartPptSlidePreviewRow,
    SmartPptTemplateBindingConfigRow,
    SmartPptTemplateBindingConfigRequest,
    SmartPptTemplateBindingConfigResponse,
    SmartPptTemplateChartBlockResponse,
    SmartPptTemplateChartBlockRow,
    SmartPptTemplateGenerateRequest,
    SmartPptTemplateGenerateResponse,
    SmartPptTemplateInspectResponse,
    SmartPptTemplateObjectRow,
)
from app.services.ppt_template_composer import PptTemplateComposer
from app.services.ppt_template_inspector import PptTemplateInspector
from app.services.runtime_metric_refs import load_org_product_metric_refs_by_runtime_ref_code_sync
from app.services.smart_ppt_renderer import SUPPORTED_NATIVE_CHART_TYPES, SmartPptRenderer

_TEMPLATE_PARAM_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

_METRIC_LIBRARY: dict[str, dict[str, str]] = {
    "total_income": {"metric_code": "03.09.05.01.039", "metric_name": "营业收入"},
    "total_profit": {"metric_code": "08.04.01.01.001", "metric_name": "净利润"},
    "total_expense": {"metric_code": "05.01", "metric_name": "业务及管理费"},
    "loan_balance": {"metric_code": "01.01.01.01.017", "metric_name": "贷款规模"},
    "fee_income": {"metric_code": "03.04.01.01.003", "metric_name": "手续费净收入"},
}

_SUPPORTED_CHART_TYPES = SUPPORTED_NATIVE_CHART_TYPES


# ─── 模块辅助函数 ───

def _uses_mysql_path(path: Path | str) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
        data_dir = Path(settings.data_dir).expanduser().resolve()
        temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    except (TypeError, OSError):
        return False
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return candidate.name == "common.db" or re.fullmatch(r"budget_\d{4}\.db", candidate.name) is not None


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class _CursorAdapter:
    def __init__(self, rows: list[Any] | None = None, *, rowcount: int = 0, lastrowid: int | None = None):
        self._rows = rows or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    async def fetchone(self) -> Any | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[Any]:
        return list(self._rows)


class _SQLiteConnection:
    def __init__(self, path: Path):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    async def __aenter__(self) -> "_SQLiteConnection":
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._conn is not None:
            if exc_type is not None:
                self._conn.rollback()
            self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> _CursorAdapter:
        assert self._conn is not None
        cur = self._conn.execute(sql, tuple(params))
        return _CursorAdapter(
            cur.fetchall() if cur.description else [],
            rowcount=max(0, int(cur.rowcount or 0)),
            lastrowid=cur.lastrowid,
        )

    async def commit(self) -> None:
        assert self._conn is not None
        self._conn.commit()


class _MySQLConnection:
    def __init__(self):
        self._ctx: Any = None
        self._conn: Any = None

    async def __aenter__(self) -> "_MySQLConnection":
        self._ctx = get_pool().acquire()
        self._conn = await self._ctx.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None and self._conn is not None:
            rollback = getattr(self._conn, "rollback", None)
            if rollback is not None:
                await rollback()
        if self._ctx is not None:
            await self._ctx.__aexit__(exc_type, exc, tb)
            self._ctx = None
            self._conn = None

    async def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> _CursorAdapter:
        assert self._conn is not None
        if sql.strip().lower().startswith("pragma foreign_keys"):
            return _CursorAdapter([(1,)])
        async with self._conn.cursor() as cur:
            await cur.execute(_mysql_sql(sql), tuple(params))
            rows = await cur.fetchall() if cur.description else []
            return _CursorAdapter(
                list(rows),
                rowcount=max(0, int(cur.rowcount or 0)),
                lastrowid=getattr(cur, "lastrowid", None),
            )

    async def commit(self) -> None:
        if self._conn is not None:
            await self._conn.commit()


@asynccontextmanager
async def _connect_db(path: Path):
    if _uses_mysql_path(path):
        async with _MySQLConnection() as db:
            yield db
    else:
        async with _SQLiteConnection(path) as db:
            yield db

def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_number(value: float) -> str:
    if abs(value) >= 10000:
        return f"{value:,.2f}"
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _format_signed(value: float) -> str:
    return f"{value:+,.2f}" if abs(value) >= 10000 else f"{value:+.2f}"


def _format_percent(value: float | None, *, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}%"


def _plain_year(value: Any) -> int:
    text = str(value or "").strip()
    match = re.search(r"(\d{4})", text)
    return int(match.group(1)) if match else datetime.now().year


def _year_label(value: Any) -> str:
    year = _plain_year(value)
    return f"Y{year}"


def _month_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text.startswith("M"):
        text = text[1:]
    if text.isdigit():
        month = int(text)
        if 1 <= month <= 12:
            return month
    return None


def _month_label(value: Any) -> str | None:
    month = _month_int(value)
    return f"M{month:02d}" if month else None


def _quarter_of_month(month: int | None) -> str:
    if not month:
        return "Q1"
    return f"Q{((month - 1) // 3) + 1}"


def _quarter_bounds(quarter: str | None) -> tuple[int, int]:
    text = str(quarter or "").strip().upper()
    mapping = {
        "Q1": (1, 3),
        "Q2": (4, 6),
        "Q3": (7, 9),
        "Q4": (10, 12),
    }
    return mapping.get(text, (1, 3))


def _safe_pct(current: float, previous: float) -> float | None:
    if abs(previous) < 1e-9:
        return None
    return ((current - previous) / abs(previous)) * 100


# ─── 场景与模板管理 ───

class SmartPptService:
    def __init__(self, *, data_dir: Path, smart_report_service: Any = None) -> None:
        self.data_dir = data_dir
        self.output_dir = data_dir / "smart_report_outputs"
        self.binding_dir = data_dir / "smart_ppt_template_bindings"
        self.smart_report_service = smart_report_service
        self.renderer = SmartPptRenderer()
        self.template_inspector = PptTemplateInspector()
        self.template_composer = PptTemplateComposer()

    # ── 场景管理 ──────────────────────────────────────────────

    async def list_scenes(self) -> list[SmartPptSceneRow]:
        async with _connect_db(common_db_path()) as db:
            cur = await db.execute(
                """SELECT scene_id, scene_code, scene_name, scene_type,
                          description, slide_template_json, default_params_json,
                          sort_order, status, created_at, updated_at
                   FROM smart_ppt_scene
                   WHERE status = 'active'
                   ORDER BY sort_order, scene_id"""
            )
            rows = await cur.fetchall()
        return [
            SmartPptSceneRow(
                scene_id=int(r[0]),
                scene_code=str(r[1]),
                scene_name=str(r[2]),
                scene_type=str(r[3]),
                description=str(r[4]) if r[4] else None,
                slide_template_json=json.loads(r[5]) if r[5] else {},
                default_params_json=json.loads(r[6]) if r[6] else {},
                sort_order=int(r[7] or 0),
                status=str(r[8]),
                created_at=str(r[9]),
                updated_at=str(r[10]),
            )
            for r in rows
        ]

    async def get_scene(self, scene_id: int) -> SmartPptSceneRow:
        async with _connect_db(common_db_path()) as db:
            cur = await db.execute("SELECT * FROM smart_ppt_scene WHERE scene_id = ?", (scene_id,))
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="场景不存在")
        return SmartPptSceneRow(
            scene_id=int(row[0]),
            scene_code=str(row[1]),
            scene_name=str(row[2]),
            scene_type=str(row[3]),
            description=str(row[4]) if row[4] else None,
            slide_template_json=json.loads(row[5]) if row[5] else {},
            default_params_json=json.loads(row[6]) if row[6] else {},
            sort_order=int(row[7] or 0),
            status=str(row[8]),
            created_at=str(row[9]),
            updated_at=str(row[10]),
        )

    async def get_chart_config_by_code(self, config_code: str) -> SmartPptChartConfigRow | None:
        async with _connect_db(common_db_path()) as db:
            cur = await db.execute(
                """SELECT config_id, config_code, chart_type, metric_config_json,
                          visual_config_json, remark, created_at, updated_at
                   FROM smart_ppt_chart_config
                   WHERE config_code = ?""",
                (config_code,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return SmartPptChartConfigRow(
            config_id=int(row[0]),
            config_code=str(row[1]),
            chart_type=str(row[2]),
            metric_config_json=json.loads(row[3]) if row[3] else {},
            visual_config_json=json.loads(row[4]) if row[4] else {},
            remark=str(row[5]) if row[5] else None,
            created_at=str(row[6]),
            updated_at=str(row[7]),
        )

    # ── 场景预览与生成 ────────────────────────────────────────

    async def preview(self, scene_id: int, params: dict[str, Any]) -> SmartPptSceneDetailResponse:
        scene = await self.get_scene(scene_id)
        merged_params = self._prepare_scene_params(scene.default_params_json, params)
        slide_specs = scene.slide_template_json.get("slides", [])
        payloads, _warnings = await self._build_slide_payloads(slide_specs, merged_params, include_charts=False)
        previews = [payload["preview"] for payload in payloads]
        return SmartPptSceneDetailResponse(scene=scene, slide_previews=previews)

    async def generate(
        self,
        scene_id: int,
        params: dict[str, Any],
        instance_name: str = "",
    ) -> SmartPptGenerateResponse:
        scene = await self.get_scene(scene_id)
        merged_params = self._prepare_scene_params(scene.default_params_json, params)
        now = _iso_now()
        name = instance_name or f"{scene.scene_name} {now}"

        async with _connect_db(common_db_path()) as db:
            cur = await db.execute(
                """INSERT INTO smart_ppt_instance (
                     scene_id, instance_name, parameter_values_json,
                     generation_status, created_at, updated_at
                   ) VALUES (?, ?, ?, 'running', ?, ?)""",
                (scene_id, name, json.dumps(merged_params, ensure_ascii=False), now, now),
            )
            instance_id = int(cur.lastrowid)
            await db.commit()

        slide_specs = scene.slide_template_json.get("slides", [])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_filename = f"smart_ppt_{instance_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"
        output_path = self.output_dir / output_filename

        payloads: list[dict[str, Any]] = []
        warnings: list[str] = []

        try:
            payloads, warnings = await self._build_slide_payloads(
                slide_specs,
                merged_params,
                include_charts=True,
            )
            self._compose_pptx(scene, payloads, output_path)
            finished = _iso_now()
            async with _connect_db(common_db_path()) as db:
                await db.execute(
                    """UPDATE smart_ppt_instance
                       SET output_file_path = ?, generation_status = 'success',
                           last_generated_at = ?, updated_at = ?
                       WHERE instance_id = ?""",
                    (str(output_path), finished, finished, instance_id),
                )
                await db.commit()
        except Exception as exc:
            finished = _iso_now()
            async with _connect_db(common_db_path()) as db:
                await db.execute(
                    """UPDATE smart_ppt_instance
                       SET generation_status = 'failed', error_message = ?, updated_at = ?
                       WHERE instance_id = ?""",
                    (str(exc), finished, instance_id),
                )
                await db.commit()
            raise HTTPException(status_code=500, detail=f"PPT 生成失败：{exc}") from exc

        return SmartPptGenerateResponse(
            instance_id=instance_id,
            output_filename=output_filename,
            download_url=f"/api/smart-ppt/instances/{instance_id}/download",
            generated_at=finished,
            slide_previews=[payload["preview"] for payload in payloads],
            warnings=warnings,
        )

    async def _build_slide_payloads(
        self,
        slide_specs: list[dict[str, Any]],
        params: dict[str, Any],
        *,
        include_charts: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        payloads: list[dict[str, Any]] = []
        warnings: list[str] = []

        for index, slide_spec in enumerate(slide_specs, start=1):
            chart_config = None
            chart_title = None
            chart_type = slide_spec.get("chart_type")
            chart_code = str(slide_spec.get("chart_config_code") or "").strip()
            if chart_code:
                chart_config = await self.get_chart_config_by_code(chart_code)
                if chart_config:
                    chart_type = chart_config.chart_type
                    chart_title = str(chart_config.visual_config_json.get("title") or "") or None

            metrics = await self.fetch_slide_metrics(slide_spec, params)
            title = self._render_template(str(slide_spec.get("title") or ""), params)
            subtitle = self._render_template(str(slide_spec.get("subtitle") or ""), params) or None
            narrative = self._generate_narrative(slide_spec, params, metrics)

            if include_charts and chart_code and chart_config:
                if chart_config.chart_type not in _SUPPORTED_CHART_TYPES:
                    warnings.append(f"{title}：暂未启用 {chart_config.chart_type} 图表，已按文本页输出。")

            preview = SmartPptSlidePreviewRow(
                slide_index=index,
                slide_type=str(slide_spec.get("type") or "text"),
                title=title,
                subtitle=subtitle,
                chart_type=chart_type,
                chart_title=chart_title,
                narrative=narrative,
                metric_cards=metrics.get("metric_cards", []),
                table_headers=metrics.get("table_headers", []),
                table_rows=metrics.get("table_rows", []),
            )
            payloads.append(
                {
                    "slide_spec": slide_spec,
                    "title": title,
                    "subtitle": subtitle,
                    "narrative": narrative,
                    "chart_type": chart_type,
                    "chart_title": chart_title,
                    "chart_config": chart_config,
                    "metrics": metrics,
                    "preview": preview,
                }
            )

        return payloads, warnings

    # ── 数据取数 ──────────────────────────────────────────────

    async def fetch_slide_metrics(self, slide_spec: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        effective_params = self._params_for_range(slide_spec, params)
        slide_type = str(slide_spec.get("type") or "text")

        if slide_type == "dashboard":
            return await self._fetch_dashboard_metrics(slide_spec, effective_params)

        chart_code = str(slide_spec.get("chart_config_code") or "").strip()
        if not chart_code:
            return {"values": [], "labels": [], "growth_pct": None, "budget_pct": None}

        chart_config = await self.get_chart_config_by_code(chart_code)
        if not chart_config:
            return {"values": [], "labels": [], "growth_pct": None, "budget_pct": None}

        if chart_config.chart_type == "line":
            return await self._fetch_line_metrics(slide_spec, chart_config, effective_params)
        if chart_config.chart_type == "bar":
            return await self._fetch_bar_metrics(slide_spec, chart_config, effective_params)
        if chart_config.chart_type == "dual_bar":
            return await self._fetch_dual_bar_metrics(slide_spec, chart_config, effective_params)
        if chart_config.chart_type == "donut":
            return await self._fetch_donut_metrics(slide_spec, chart_config, effective_params)

        return {
            "values": [],
            "labels": [],
            "growth_pct": None,
            "budget_pct": None,
            "metric_name": slide_spec.get("metric_name"),
            "table_headers": [],
            "table_rows": [],
        }

    async def _fetch_dashboard_metrics(self, slide_spec: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        metric_keys = slide_spec.get("metrics", [])
        metric_cards: list[dict[str, str]] = []
        values: list[float] = []
        labels: list[str] = []
        first_growth: float | None = None
        first_budget_pct: float | None = None

        for metric_key in metric_keys:
            metric_def = _METRIC_LIBRARY.get(str(metric_key), {"metric_code": str(metric_key), "metric_name": str(metric_key)})
            metric_code = metric_def.get("metric_code") or str(metric_key)
            metric_name = metric_def["metric_name"]
            actual = await self._sum_metric_value(metric_code, params, budget_actual=1)
            budget = await self._sum_metric_value(metric_code, params, budget_actual=0)
            previous = await self._sum_metric_value(metric_code, self._previous_year_params(params), budget_actual=1)
            growth_pct = _safe_pct(actual, previous)
            budget_pct = (actual / budget * 100) if abs(budget) > 1e-9 else None
            diff = actual - budget

            if first_growth is None:
                first_growth = growth_pct
            if first_budget_pct is None:
                first_budget_pct = budget_pct

            labels.append(metric_name)
            values.append(actual)
            metric_cards.append(
                {
                    "指标": metric_name,
                    "实际": _format_number(actual),
                    "预算": _format_number(budget),
                    "差异": _format_signed(diff),
                    "完成率": _format_percent(budget_pct),
                    "同比": _format_percent(growth_pct),
                }
            )

        return {
            "labels": labels,
            "values": values,
            "growth_pct": first_growth,
            "budget_pct": first_budget_pct,
            "metric_cards": metric_cards,
            "table_headers": ["指标", "实际", "预算", "差异", "完成率", "同比"],
            "table_rows": [[card["指标"], card["实际"], card["预算"], card["差异"], card["完成率"], card["同比"]] for card in metric_cards],
        }

    async def _fetch_line_metrics(
        self,
        slide_spec: dict[str, Any],
        chart_config: SmartPptChartConfigRow,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        metric_config = {**chart_config.metric_config_json, **slide_spec}
        metric_code = str(metric_config.get("metric_code") or "")
        metric_name = str(metric_config.get("metric_name") or "指标")
        months = self._selected_months(params)
        actual_rows = await self._group_metric_values(metric_code, params, budget_actual=1, group_by="month")
        budget_rows = await self._group_metric_values(metric_code, params, budget_actual=0, group_by="month")
        actual_map = {label: value for label, value in actual_rows}
        budget_map = {label: value for label, value in budget_rows}

        labels = [f"M{month:02d}" for month in months]
        actual_values = [float(actual_map.get(label, 0.0)) for label in labels]
        budget_values = [float(budget_map.get(label, 0.0)) for label in labels]
        total_actual = sum(actual_values)
        total_budget = sum(budget_values)
        previous_total = await self._sum_metric_value(metric_code, self._previous_year_params(params), budget_actual=1)

        peak_index = max(range(len(actual_values)), key=lambda idx: actual_values[idx]) if actual_values else 0
        peak_label = labels[peak_index] if labels else None
        peak_value = actual_values[peak_index] if actual_values else 0.0

        return {
            "labels": labels,
            "values": actual_values,
            "budget_values": budget_values,
            "growth_pct": _safe_pct(total_actual, previous_total),
            "budget_pct": (total_actual / total_budget * 100) if abs(total_budget) > 1e-9 else None,
            "metric_name": metric_name,
            "total_actual": total_actual,
            "total_budget": total_budget,
            "peak_label": peak_label,
            "peak_value": peak_value,
            "table_headers": ["月份", "实际", "预算"],
            "table_rows": [[label, _format_number(actual), _format_number(budget)] for label, actual, budget in zip(labels, actual_values, budget_values)],
        }

    async def _fetch_bar_metrics(
        self,
        slide_spec: dict[str, Any],
        chart_config: SmartPptChartConfigRow,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        metric_config = {**chart_config.metric_config_json, **slide_spec}
        metric_code = str(metric_config.get("metric_code") or "")
        metric_name = str(metric_config.get("metric_name") or "指标")
        group_by = str(metric_config.get("group_by") or "dept")
        top_n = int(metric_config.get("top_n") or 5)

        actual_rows = await self._group_metric_values(metric_code, params, budget_actual=1, group_by=group_by, top_n=top_n)
        budget_rows = await self._group_metric_values(metric_code, params, budget_actual=0, group_by=group_by)
        budget_map = {label: value for label, value in budget_rows}

        threshold_pct = float(slide_spec.get("threshold_pct") or 0)
        labels: list[str] = []
        values: list[float] = []
        budget_values: list[float] = []
        diff_values: list[float] = []
        alert_rows: list[dict[str, Any]] = []

        for label, actual in actual_rows:
            budget = float(budget_map.get(label, 0.0))
            diff = actual - budget
            variance_pct = _safe_pct(actual, budget)
            if slide_spec.get("type") == "risk_alert" and variance_pct is not None and abs(variance_pct) < threshold_pct:
                continue
            labels.append(label)
            values.append(actual)
            budget_values.append(budget)
            diff_values.append(diff)
            alert_rows.append(
                {
                    "label": label,
                    "actual": actual,
                    "budget": budget,
                    "diff": diff,
                    "variance_pct": variance_pct,
                }
            )

        if not labels:
            labels = [label for label, _value in actual_rows[:top_n]]
            values = [value for _label, value in actual_rows[:top_n]]
            budget_values = [float(budget_map.get(label, 0.0)) for label in labels]
            diff_values = [actual - budget for actual, budget in zip(values, budget_values)]

        total_actual = sum(values)
        total_budget = sum(budget_values)
        top_label = labels[0] if labels else None
        top_value = values[0] if values else 0.0

        return {
            "labels": labels,
            "values": values,
            "budget_values": budget_values,
            "diff_values": diff_values,
            "growth_pct": _safe_pct(total_actual, total_budget),
            "budget_pct": (total_actual / total_budget * 100) if abs(total_budget) > 1e-9 else None,
            "metric_name": metric_name,
            "top_label": top_label,
            "top_value": top_value,
            "alerts": alert_rows,
            "table_headers": ["对象", "实际", "预算", "差异", "偏差率"],
            "table_rows": [
                [label, _format_number(actual), _format_number(budget), _format_signed(diff), _format_percent(_safe_pct(actual, budget))]
                for label, actual, budget, diff in zip(labels, values, budget_values, diff_values)
            ],
        }

    async def _fetch_dual_bar_metrics(
        self,
        slide_spec: dict[str, Any],
        chart_config: SmartPptChartConfigRow,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        metric_config = {**chart_config.metric_config_json, **slide_spec}
        metric_codes = list(metric_config.get("metric_codes") or [])
        metric_names = list(metric_config.get("metric_names") or [])

        labels: list[str] = []
        actual_values: list[float] = []
        budget_values: list[float] = []
        diff_values: list[float] = []

        for index, metric_code in enumerate(metric_codes):
            metric_name = str(metric_names[index]) if index < len(metric_names) else str(metric_code)
            actual = await self._sum_metric_value(str(metric_code), params, budget_actual=1)
            budget = await self._sum_metric_value(str(metric_code), params, budget_actual=0)
            labels.append(metric_name)
            actual_values.append(actual)
            budget_values.append(budget)
            diff_values.append(actual - budget)

        total_actual = sum(actual_values)
        total_budget = sum(budget_values)
        biggest_gap_index = max(range(len(diff_values)), key=lambda idx: abs(diff_values[idx])) if diff_values else 0

        return {
            "labels": labels,
            "values": actual_values,
            "actual_values": actual_values,
            "budget_values": budget_values,
            "diff_values": diff_values,
            "growth_pct": _safe_pct(total_actual, await self._sum_multi_metric_values(metric_codes, self._previous_year_params(params), budget_actual=1)),
            "budget_pct": (total_actual / total_budget * 100) if abs(total_budget) > 1e-9 else None,
            "total_actual": total_actual,
            "total_budget": total_budget,
            "highlight_label": labels[biggest_gap_index] if labels else None,
            "highlight_diff": diff_values[biggest_gap_index] if diff_values else 0.0,
            "table_headers": ["指标", "实际", "预算", "差异", "完成率"],
            "table_rows": [
                [
                    label,
                    _format_number(actual),
                    _format_number(budget),
                    _format_signed(diff),
                    _format_percent((actual / budget * 100) if abs(budget) > 1e-9 else None),
                ]
                for label, actual, budget, diff in zip(labels, actual_values, budget_values, diff_values)
            ],
        }

    async def _fetch_donut_metrics(
        self,
        slide_spec: dict[str, Any],
        chart_config: SmartPptChartConfigRow,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        metric_config = {**chart_config.metric_config_json, **slide_spec}
        metric_code = str(metric_config.get("metric_code") or "")
        metric_name = str(metric_config.get("metric_name") or "指标")
        top_n = int(metric_config.get("top_n") or 5)

        actual_rows = await self._group_metric_values(metric_code, params, budget_actual=1, group_by="product", top_n=top_n)
        budget_rows = await self._group_metric_values(metric_code, params, budget_actual=0, group_by="product")
        budget_map = {label: value for label, value in budget_rows}

        labels = [label for label, _value in actual_rows]
        values = [value for _label, value in actual_rows]
        budget_values = [float(budget_map.get(label, 0.0)) for label in labels]
        total_actual = sum(values)
        total_budget = sum(budget_values)
        top_share_pct = (values[0] / total_actual * 100) if values and abs(total_actual) > 1e-9 else None

        return {
            "labels": labels,
            "values": values,
            "budget_values": budget_values,
            "growth_pct": _safe_pct(total_actual, await self._sum_metric_value(metric_code, self._previous_year_params(params), budget_actual=1)),
            "budget_pct": (total_actual / total_budget * 100) if abs(total_budget) > 1e-9 else None,
            "metric_name": metric_name,
            "top_label": labels[0] if labels else None,
            "top_value": values[0] if values else 0.0,
            "top_share_pct": top_share_pct,
            "table_headers": ["产品", "实际", "预算", "占比"],
            "table_rows": [
                [
                    label,
                    _format_number(value),
                    _format_number(budget),
                    _format_percent((value / total_actual * 100) if abs(total_actual) > 1e-9 else None),
                ]
                for label, value, budget in zip(labels, values, budget_values)
            ],
        }

    async def _sum_multi_metric_values(self, metric_codes: list[Any], params: dict[str, Any], *, budget_actual: int) -> float:
        total = 0.0
        for metric_code in metric_codes:
            total += await self._sum_metric_value(str(metric_code), params, budget_actual=budget_actual)
        return total

    async def _sum_metric_value(self, metric_code: str, params: dict[str, Any], *, budget_actual: int) -> float:
        where, values = self._budget_summary_where(params, budget_actual=budget_actual, metric_code=metric_code)
        path = budget_db_path(_plain_year(params.get("year")))
        if not _uses_mysql_path(path) and not path.exists():
            return 0.0
        async with _connect_db(path) as db:
            cur = await db.execute(
                f"SELECT COALESCE(SUM(value), 0) FROM budget_summary WHERE {' AND '.join(where)}",
                values,
            )
            row = await cur.fetchone()
        return float(row[0] or 0.0) if row else 0.0

    async def _group_metric_values(
        self,
        metric_code: str,
        params: dict[str, Any],
        *,
        budget_actual: int,
        group_by: str,
        top_n: int | None = None,
    ) -> list[tuple[str, float]]:
        where, values = self._budget_summary_where(params, budget_actual=budget_actual, metric_code=metric_code)
        path = budget_db_path(_plain_year(params.get("year")))
        if not _uses_mysql_path(path) and not path.exists():
            return []

        if group_by == "month":
            label_sql = "month"
            order_sql = "ORDER BY CAST(SUBSTR(month, 2) AS UNSIGNED)"
        elif group_by == "product":
            label_sql = "COALESCE(NULLIF(product_code_name, ''), '未分产品')"
            order_sql = "ORDER BY total DESC, label"
        else:
            label_sql = "COALESCE(NULLIF(dept_level1, ''), NULLIF(dept_level2, ''), NULLIF(dept_level3, ''), '未分部门')"
            order_sql = "ORDER BY total DESC, label"

        async with _connect_db(path) as db:
            cur = await db.execute(
                f"""
                SELECT {label_sql} AS label, COALESCE(SUM(value), 0) AS total
                FROM budget_summary
                WHERE {' AND '.join(where)}
                GROUP BY label
                {order_sql}
                """,
                values,
            )
            rows = await cur.fetchall()

        result = [(str(row[0]), float(row[1] or 0.0)) for row in rows if row and row[0] is not None]
        if group_by != "month":
            non_zero = [item for item in result if abs(item[1]) > 1e-9]
            result = non_zero or result
            if top_n is not None:
                result = result[:top_n]
        return result

    def _budget_summary_where(
        self,
        params: dict[str, Any],
        *,
        budget_actual: int,
        metric_code: str | None = None,
    ) -> tuple[list[str], list[Any]]:
        where = ["year = ?", "budget_actual = ?"]
        values: list[Any] = [_year_label(params.get("year")), budget_actual]

        start_month = _month_int(params.get("start_month"))
        end_month = _month_int(params.get("end_month"))
        month = _month_label(params.get("month"))
        if start_month or end_month:
            left = start_month or 1
            right = end_month or 12
            if left > right:
                left, right = right, left
            where.append("CAST(SUBSTR(month, 2) AS UNSIGNED) BETWEEN ? AND ?")
            values.extend([left, right])
        elif month:
            where.append("month = ?")
            values.append(month)
        else:
            quarter = str(params.get("quarter") or "").strip().upper()
            if quarter:
                where.append("quarter = ?")
                values.append(quarter)

        version_id: Any = None
        if budget_actual == 0:
            version_id = params.get("version_id")
        else:
            version_id = params.get("actual_version_id")
        if version_id is not None and str(version_id).strip() != "":
            where.append("version_id = ?")
            values.append(int(version_id))

        if metric_code:
            parts: list[str] = []
            for column in ("metric_level1", "metric_level2", "metric_level3", "metric_level4", "metric_level5"):
                parts.append(f"{column} = ?")
                values.append(metric_code)
                parts.append(f"{column} LIKE ?")
                values.append(f"{metric_code} %")
            where.append(f"({' OR '.join(parts)})")

        dept = params.get("dept_code") or params.get("dept")
        if dept:
            where.append("(IFNULL(dept_level1, '') || IFNULL(dept_level2, '') || IFNULL(dept_level3, '')) LIKE ?")
            values.append(f"%{str(dept).strip()}%")

        product = params.get("product_code") or params.get("product")
        if product:
            where.append("IFNULL(product_code_name, '') LIKE ?")
            values.append(f"%{str(product).strip()}%")

        return where, values

    # ── 图表渲染 ──────────────────────────────────────────────

    async def render_chart_image(
        self,
        config_code: str,
        params: dict[str, Any],
        *,
        metrics: dict[str, Any] | None = None,
    ) -> bytes:
        chart_config = await self.get_chart_config_by_code(config_code)
        if not chart_config:
            raise HTTPException(status_code=404, detail=f"图表配置不存在：{config_code}")
        if chart_config.chart_type not in _SUPPORTED_CHART_TYPES:
            raise ValueError(f"暂不支持图表类型：{chart_config.chart_type}")

        if metrics is None:
            metrics = await self.fetch_slide_metrics({"chart_config_code": config_code, **chart_config.metric_config_json}, params)

        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        plt.rcParams["font.sans-serif"] = ["PingFang SC", "Arial Unicode MS", "SimHei", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        fig, ax = plt.subplots(figsize=(10, 4.8), dpi=160)
        palette = chart_config.visual_config_json.get("palette") or ["#1d4ed8", "#ea580c", "#0f766e", "#7c3aed"]
        labels = list(metrics.get("labels") or [])
        values = [float(value) for value in metrics.get("values") or []]
        title = str(chart_config.visual_config_json.get("title") or chart_config.remark or config_code)

        if chart_config.chart_type == "line":
            budget_values = [float(value) for value in metrics.get("budget_values") or []]
            if labels:
                ax.plot(labels, values, marker="o", linewidth=2.5, color=palette[0], label="实际")
                if budget_values:
                    ax.plot(labels, budget_values, linestyle="--", linewidth=2, color=palette[1] if len(palette) > 1 else "#94a3b8", label="预算")
                ax.fill_between(labels, values, color=palette[0], alpha=0.12)
                ax.legend(frameon=False, loc="upper left")
            else:
                ax.text(0.5, 0.5, "暂无可绘制数据", ha="center", va="center", transform=ax.transAxes)
        elif chart_config.chart_type == "bar":
            if labels:
                bars = ax.bar(labels, values, color=palette[0], alpha=0.92)
                for bar, value in zip(bars, values):
                    ax.text(bar.get_x() + bar.get_width() / 2, value, _format_number(value), ha="center", va="bottom", fontsize=8)
            else:
                ax.text(0.5, 0.5, "暂无可绘制数据", ha="center", va="center", transform=ax.transAxes)
        elif chart_config.chart_type == "dual_bar":
            budget_values = [float(value) for value in metrics.get("budget_values") or []]
            if labels:
                x_positions = list(range(len(labels)))
                width = 0.35
                actual_bars = ax.bar([x - width / 2 for x in x_positions], values, width=width, color=palette[1] if len(palette) > 1 else "#ea580c", label="实际")
                budget_bars = ax.bar([x + width / 2 for x in x_positions], budget_values, width=width, color=palette[0], label="预算")
                ax.set_xticks(x_positions)
                ax.set_xticklabels(labels)
                for bar_set in (actual_bars, budget_bars):
                    for bar in bar_set:
                        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), _format_number(bar.get_height()), ha="center", va="bottom", fontsize=8)
                ax.legend(frameon=False, loc="upper left")
            else:
                ax.text(0.5, 0.5, "暂无可绘制数据", ha="center", va="center", transform=ax.transAxes)
        elif chart_config.chart_type == "donut":
            if labels and not math.isclose(sum(abs(value) for value in values), 0.0):
                wedges, _texts, autotexts = ax.pie(
                    values,
                    labels=labels,
                    colors=palette[: len(labels)],
                    autopct=lambda pct: f"{pct:.1f}%" if pct >= 4 else "",
                    startangle=90,
                    wedgeprops={"width": 0.42, "edgecolor": "white"},
                    pctdistance=0.8,
                )
                ax.add_artist(plt.Circle((0, 0), 0.46, fc="white"))
                for autotext in autotexts:
                    autotext.set_fontsize(8)
                ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
            else:
                ax.text(0.5, 0.5, "暂无可绘制数据", ha="center", va="center", transform=ax.transAxes)

        ax.set_title(title, fontsize=14, fontweight="bold", loc="left")
        if chart_config.chart_type != "donut":
            ax.grid(axis="y", linestyle="--", alpha=0.2)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#cbd5e1")
            ax.spines["bottom"].set_color("#cbd5e1")
        else:
            ax.set_aspect("equal")
        fig.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return buffer.getvalue()

    # ── PPT 组装 ─────────────────────────────────────────────

    def _compose_pptx(self, scene: SmartPptSceneRow, slides: list[dict[str, Any]], output_path: Path) -> None:
        self.renderer.compose(scene, slides, output_path)

    # ── AI 叙事引擎（规则模板） ────────────────────────────────

    def _generate_narrative(self, slide_spec: dict[str, Any], params: dict[str, Any], metrics: dict[str, Any] | None = None) -> str:
        metrics = metrics or {}
        slide_type = str(slide_spec.get("type") or "text")
        metric_name = str(metrics.get("metric_name") or slide_spec.get("metric_name") or "指标")
        range_label = self._range_label(params)

        if slide_type == "cover":
            quarter = params.get("quarter") or ""
            return f"{params.get('year')}年度{quarter}经营分析报告，覆盖截至{params.get('month_label')}月的核心经营数据。"

        if slide_type == "dashboard":
            cards = metrics.get("metric_cards", [])
            if cards:
                snippets = [f"{card['指标']}{card['实际']}" for card in cards[:3] if "指标" in card and "实际" in card]
                return f"截至{params.get('month_label')}月，{'，'.join(snippets)}。"
            return f"本报告覆盖核心经营指标，统计范围为{range_label}。"

        if slide_type == "trend_chart":
            growth_pct = metrics.get("growth_pct")
            direction = "增长" if (growth_pct or 0) >= 0 else "下降"
            peak_label = metrics.get("peak_label") or "本期"
            peak_value = _format_number(float(metrics.get("peak_value") or 0.0))
            return (
                f"{metric_name}{range_label}累计{_format_number(float(metrics.get('total_actual') or sum(metrics.get('values') or [0.0])))}，"
                f"较上年同期{direction}{_format_percent(abs(growth_pct) if growth_pct is not None else None)}，"
                f"峰值出现在{peak_label}，单月达到{peak_value}。"
            )

        if slide_type == "budget_vs_actual":
            budget_pct = metrics.get("budget_pct")
            diff = float(metrics.get("highlight_diff") or 0.0)
            status = "超预算" if diff > 0 else "低于预算"
            return (
                f"关键指标{range_label}预算完成率{_format_percent(budget_pct)}，"
                f"其中{metrics.get('highlight_label') or '重点指标'}{status}{_format_number(abs(diff))}，"
                f"建议结合执行进度及时校准。"
            )

        if slide_type in {"ranking_chart", "share_chart"}:
            top_label = metrics.get("top_label") or "重点对象"
            top_value = _format_number(float(metrics.get("top_value") or 0.0))
            top_share_pct = metrics.get("top_share_pct")
            if slide_type == "share_chart":
                return f"{metric_name}{range_label}主要集中在{top_label}，规模{top_value}，占比{_format_percent(top_share_pct)}。"
            return f"{metric_name}{range_label}排名靠前的是{top_label}，贡献值{top_value}，需重点跟踪头部表现。"

        if slide_type == "risk_alert":
            alerts = metrics.get("alerts", [])
            if alerts:
                top_alert = alerts[0]
                variance_pct = top_alert.get("variance_pct")
                variance_text = _format_percent(abs(float(variance_pct))) if variance_pct is not None else "-"
                return f"{top_alert.get('label')}在{metric_name}上偏差最明显，较预算偏离{variance_text}，需要尽快复核原因。"
            return f"{metric_name}{range_label}暂无超过阈值的异常对象。"

        return self._render_template(str(slide_spec.get("title") or ""), params)

    # ── 配置管理 ──────────────────────────────────────────────

    async def list_chart_configs(self) -> list[SmartPptChartConfigRow]:
        async with _connect_db(common_db_path()) as db:
            cur = await db.execute(
                """SELECT config_id, config_code, chart_type, metric_config_json,
                          visual_config_json, remark, created_at, updated_at
                   FROM smart_ppt_chart_config
                   ORDER BY config_id"""
            )
            rows = await cur.fetchall()
        return [
            SmartPptChartConfigRow(
                config_id=int(r[0]),
                config_code=str(r[1]),
                chart_type=str(r[2]),
                metric_config_json=json.loads(r[3]) if r[3] else {},
                visual_config_json=json.loads(r[4]) if r[4] else {},
                remark=str(r[5]) if r[5] else None,
                created_at=str(r[6]),
                updated_at=str(r[7]),
            )
            for r in rows
        ]

    # ── 实例管理 ──────────────────────────────────────────────

    async def list_instances(self) -> list[SmartPptInstanceRow]:
        async with _connect_db(common_db_path()) as db:
            cur = await db.execute(
                """SELECT i.instance_id, i.scene_id, s.scene_name, i.instance_name,
                          i.parameter_values_json, i.generation_status, i.output_file_path,
                          i.error_message, i.last_generated_at, i.created_at, i.updated_at
                   FROM smart_ppt_instance i
                   LEFT JOIN smart_ppt_scene s ON s.scene_id = i.scene_id
                   ORDER BY i.updated_at DESC LIMIT 100"""
            )
            rows = await cur.fetchall()
        return [
            SmartPptInstanceRow(
                instance_id=int(r[0]),
                scene_id=int(r[1]),
                scene_name=str(r[2]) if r[2] else None,
                instance_name=str(r[3]),
                parameter_values=json.loads(r[4]) if r[4] else {},
                generation_status=str(r[5]),
                output_file_path=str(r[6]) if r[6] else None,
                error_message=str(r[7]) if r[7] else None,
                last_generated_at=str(r[8]) if r[8] else None,
                created_at=str(r[9]),
                updated_at=str(r[10]),
            )
            for r in rows
        ]

    async def instance_output_path(self, instance_id: int) -> Path:
        async with _connect_db(common_db_path()) as db:
            cur = await db.execute("SELECT output_file_path FROM smart_ppt_instance WHERE instance_id = ?", (instance_id,))
            row = await cur.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="PPT 实例没有可下载文件")
        path = Path(str(row[0]))
        if not path.exists():
            raise HTTPException(status_code=404, detail="PPT 文件不存在")
        return path

    def inspect_template_file(self, template_file_name: str) -> SmartPptTemplateInspectResponse:
        template_path = self._resolve_template_path(template_file_name)
        try:
            return self.template_inspector.inspect(template_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PPT 模板解析失败：{exc}") from exc

    def get_template_bindings(self, template_file_name: str) -> SmartPptTemplateBindingConfigResponse:
        name = self._normalize_template_file_name(template_file_name)
        path = self._binding_config_path(name)
        if not path.exists():
            return SmartPptTemplateBindingConfigResponse(template_file_name=name, bindings=[], updated_at=None)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return SmartPptTemplateBindingConfigResponse(
                template_file_name=name,
                bindings=payload.get("bindings", []),
                updated_at=payload.get("updated_at"),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"模板绑定配置读取失败：{exc}") from exc

    def save_template_bindings(
        self,
        body: SmartPptTemplateBindingConfigRequest,
    ) -> SmartPptTemplateBindingConfigResponse:
        name = self._normalize_template_file_name(body.template_file_name)
        self._resolve_template_path(name)
        self._validate_template_binding_org_product_refs(body.bindings)
        self.binding_dir.mkdir(parents=True, exist_ok=True)
        updated_at = _iso_now()
        response = SmartPptTemplateBindingConfigResponse(
            template_file_name=name,
            bindings=body.bindings,
            updated_at=updated_at,
        )
        path = self._binding_config_path(name)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return response

    def _validate_template_binding_org_product_refs(
        self,
        bindings: list[SmartPptTemplateBindingConfigRow],
    ) -> None:
        requested_codes = {
            str(binding.org_product_data_acct_code or "").strip().upper()
            for binding in bindings
            if str(binding.org_product_data_acct_code or "").strip()
        }
        if not requested_codes:
            return
        try:
            with sqlite3.connect(common_db_path()) as conn:
                refs_by_code = load_org_product_metric_refs_by_runtime_ref_code_sync(conn)
        except sqlite3.Error as exc:
            raise HTTPException(status_code=500, detail=f"机构及产品指标主表读取失败：{exc}") from exc
        missing_codes = sorted(requested_codes - set(refs_by_code))
        if missing_codes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "PPT 模板绑定指标未在机构及产品指标主表中确认："
                    f"{'、'.join(missing_codes[:10])}"
                ),
            )
        for binding in bindings:
            data_code = str(binding.org_product_data_acct_code or "").strip().upper()
            source_ref = str(binding.org_product_metric_ref or "").strip()
            if not data_code or not source_ref:
                continue
            allowed_refs = {
                str(label).split(maxsplit=1)[0]
                for label in refs_by_code.get(data_code, ())
            }
            if source_ref not in allowed_refs:
                raise HTTPException(
                    status_code=400,
                    detail=f"PPT 模板绑定机构产品引用与机构及产品指标编码不匹配：{source_ref}",
                )

    async def suggest_template_chart_blocks(
        self,
        template_file_name: str,
        *,
        max_slides: int = 10,
    ) -> SmartPptTemplateChartBlockResponse:
        report = self.inspect_template_file(template_file_name)
        chart_configs = [item for item in await self.list_chart_configs() if item.chart_type in _SUPPORTED_CHART_TYPES]
        blocks: list[SmartPptTemplateChartBlockRow] = []
        chart_index = 0

        for slide in report.slides:
            if slide.slide_index > max_slides:
                continue
            section = self._clean_block_text(slide.title) or f"第 {slide.slide_index} 页"
            chart_objects = sorted(
                [obj for obj in slide.objects if obj.object_type == "chart"],
                key=lambda item: (item.top or 0, item.left or 0),
            )
            for chart_number, chart in enumerate(chart_objects, start=1):
                nearby_title = self._nearest_title_for_chart(slide.objects, chart)
                chart_config = self._suggest_chart_config_for_template(chart.chart_type, chart_configs, chart_index)
                chart_index += 1
                block_id = f"slide_{slide.slide_index:02d}_chart_{chart_number:02d}"
                nearby_text = self._clean_block_text(nearby_title.text_excerpt if nearby_title else None)
                block_name = f"{section} / {nearby_text}" if nearby_text and nearby_text != section else f"{section} / 图表 {chart_number}"
                binding = SmartPptTemplateBindingConfigRow(
                    object_id=chart.object_id,
                    slide_index=slide.slide_index,
                    object_type="chart",
                    binding_type="chart",
                    target_key=block_id,
                    data_source="budget_summary",
                    chart_config_code=chart_config.config_code if chart_config else None,
                    prompt=block_name,
                    enabled=True,
                )
                blocks.append(
                    SmartPptTemplateChartBlockRow(
                        block_id=block_id,
                        block_name=block_name,
                        section=section,
                        slide_index=slide.slide_index,
                        chart_object_id=chart.object_id,
                        chart_type=chart.chart_type,
                        nearby_title_object_id=nearby_title.object_id if nearby_title else None,
                        nearby_title=nearby_text,
                        default_chart_config_code=chart_config.config_code if chart_config else None,
                        binding=binding,
                    )
                )

        return SmartPptTemplateChartBlockResponse(template_file_name=report.template_file_name, blocks=blocks)

    async def generate_from_template_bindings(
        self,
        body: SmartPptTemplateGenerateRequest,
    ) -> SmartPptTemplateGenerateResponse:
        name = self._normalize_template_file_name(body.template_file_name)
        template_path = self._resolve_template_path(name)
        bindings = body.bindings if body.bindings is not None else self.get_template_bindings(name).bindings
        chart_payloads, chart_warnings = await self._build_template_chart_payloads(bindings, body.params)
        max_slides = self._normalize_max_slides(body.max_slides)

        output_filename = f"template_studio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"
        output_path = self.output_dir / output_filename
        compose_result = self.template_composer.compose(
            template_path=template_path,
            output_path=output_path,
            bindings=bindings,
            params=body.params,
            chart_payloads=chart_payloads,
            max_slides=max_slides,
        )
        return SmartPptTemplateGenerateResponse(
            output_filename=output_filename,
            download_url=f"/api/smart-ppt/template-studio/download/{output_filename}",
            generated_at=_iso_now(),
            applied_count=compose_result.applied_count,
            slide_count=compose_result.slide_count,
            warnings=[*chart_warnings, *compose_result.warnings],
        )

    async def _build_template_chart_payloads(
        self,
        bindings: list[Any],
        params: dict[str, Any],
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        payloads: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for binding in bindings:
            if not binding.enabled or binding.binding_type != "chart":
                continue
            chart_code = str(binding.chart_config_code or "").strip()
            if not chart_code:
                warnings.append(f"{binding.object_id}：缺少 chart_config_code，无法替换原生图表数据。")
                continue
            chart_config = await self.get_chart_config_by_code(chart_code)
            if chart_config is None:
                warnings.append(f"{binding.object_id}：未找到图表规则 {chart_code}。")
                continue

            slide_spec: dict[str, Any] = {
                "type": self._template_chart_slide_type(chart_config.chart_type),
                "chart_config_code": chart_code,
            }
            if binding.metric_code:
                slide_spec["metric_code"] = binding.metric_code
            metrics = await self.fetch_slide_metrics(slide_spec, params)
            payloads[binding.object_id] = self._template_chart_payload(binding, chart_config, metrics)
        return payloads, warnings

    def _template_chart_slide_type(self, chart_type: str) -> str:
        if chart_type == "line":
            return "trend_chart"
        if chart_type == "donut":
            return "share_chart"
        if chart_type == "dual_bar":
            return "budget_vs_actual"
        return "ranking_chart"

    def _template_chart_payload(
        self,
        binding: Any,
        chart_config: SmartPptChartConfigRow,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        labels = [str(label) for label in metrics.get("labels") or []]
        values = [float(value or 0) for value in metrics.get("values") or metrics.get("actual_values") or []]
        budget_values = [float(value or 0) for value in metrics.get("budget_values") or []]
        metric_name = str(metrics.get("metric_name") or binding.target_key or chart_config.config_code)

        series: list[dict[str, Any]] = []
        if values:
            series.append({"name": "实际" if budget_values else metric_name, "values": values})
        if budget_values and chart_config.chart_type in {"line", "bar", "dual_bar"}:
            series.append({"name": "预算", "values": budget_values})
        if not series:
            labels = labels or ["暂无数据"]
            series.append({"name": metric_name, "values": [0.0 for _ in labels]})

        return {
            "labels": labels,
            "series": series,
            "series_name": metric_name,
        }

    def template_studio_output_path(self, output_filename: str) -> Path:
        name = (output_filename or "").strip()
        if "/" in name or "\\" in name or not name.lower().endswith(".pptx"):
            raise HTTPException(status_code=400, detail="输出文件名不合法")
        path = self.output_dir / name
        if not path.exists():
            raise HTTPException(status_code=404, detail="PPT 文件不存在")
        return path

    def _normalize_template_file_name(self, template_file_name: str) -> str:
        name = (template_file_name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="模板文件名不能为空")
        if "/" in name or "\\" in name or not name.lower().endswith(".pptx"):
            raise HTTPException(status_code=400, detail="模板文件名不合法")
        return name

    def _resolve_template_path(self, template_file_name: str) -> Path:
        name = self._normalize_template_file_name(template_file_name)
        search_dirs = [
            settings.business_inputs_dir,
            self.data_dir / "smart_report_templates",
            self.data_dir / "templates",
        ]
        template_path = next((directory / name for directory in search_dirs if (directory / name).exists()), None)
        if not template_path:
            raise HTTPException(status_code=404, detail=f"未找到 PPT 模板：{name}")
        return template_path

    def _binding_config_path(self, template_file_name: str) -> Path:
        safe_stem = Path(template_file_name).stem.replace(" ", "_")
        return self.binding_dir / f"{safe_stem}.bindings.json"

    def _normalize_max_slides(self, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1:
            raise HTTPException(status_code=400, detail="max_slides 必须大于 0")
        return min(int(value), 200)

    def _nearest_title_for_chart(
        self,
        objects: list[SmartPptTemplateObjectRow],
        chart: SmartPptTemplateObjectRow,
    ) -> SmartPptTemplateObjectRow | None:
        text_objects = [
            obj
            for obj in objects
            if obj.object_type == "text" and obj.text_excerpt and obj.top is not None and obj.left is not None
        ]
        if not text_objects or chart.top is None or chart.left is None:
            return None

        chart_center_x = (chart.left or 0) + (chart.width or 0) / 2

        def score(text: SmartPptTemplateObjectRow) -> float:
            text_bottom = (text.top or 0) + (text.height or 0)
            text_center_x = (text.left or 0) + (text.width or 0) / 2
            vertical = abs((chart.top or 0) - text_bottom)
            if (text.top or 0) > (chart.top or 0):
                vertical *= 2.5
            horizontal = abs(chart_center_x - text_center_x) * 0.35
            return vertical + horizontal

        return min(text_objects, key=score)

    def _clean_block_text(self, value: str | None) -> str | None:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return None
        return text if len(text) <= 32 else f"{text[:31]}..."

    def _suggest_chart_config_for_template(
        self,
        template_chart_type: str | None,
        chart_configs: list[SmartPptChartConfigRow],
        fallback_index: int,
    ) -> SmartPptChartConfigRow | None:
        if not chart_configs:
            return None

        text = str(template_chart_type or "").upper()
        preferred_type = "bar"
        if "LINE" in text:
            preferred_type = "line"
        elif "PIE" in text or "DOUGHNUT" in text:
            preferred_type = "donut"
        elif "STACKED" in text:
            preferred_type = "dual_bar"

        preferred = [item for item in chart_configs if item.chart_type == preferred_type]
        if preferred:
            return preferred[fallback_index % len(preferred)]
        return chart_configs[fallback_index % len(chart_configs)]

    # ── 参数与模板辅助 ────────────────────────────────────────

    def _prepare_scene_params(self, defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {**defaults, **overrides}
        year = str(params.get("year") or datetime.now().year)
        start_month = _month_int(params.get("start_month"))
        end_month = _month_int(params.get("end_month"))
        month = _month_int(params.get("month"))
        quarter = str(params.get("quarter") or "").strip().upper()

        if not quarter:
            quarter = _quarter_of_month(month or end_month or start_month or 3)
        if start_month is None or end_month is None:
            if month is not None:
                start_month = start_month or month
                end_month = end_month or month
            else:
                quarter_start, quarter_end = _quarter_bounds(quarter)
                start_month = start_month or quarter_start
                end_month = end_month or quarter_end
        if month is None:
            month = end_month

        params["year"] = year
        params["quarter"] = quarter
        params["start_month"] = str(start_month or 1)
        params["end_month"] = str(end_month or 12)
        params["month"] = str(month or end_month or start_month or 12)
        params["month_label"] = f"{int(params['month']):02d}"
        params["product_label"] = str(
            params.get("product_label") or params.get("product") or params.get("product_code") or "全部产品"
        )
        return params

    def _params_for_range(self, slide_spec: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        effective = dict(params)
        range_mode = str(slide_spec.get("range_mode") or "").strip().lower()
        if range_mode == "month":
            month = _month_int(params.get("month") or params.get("end_month") or params.get("start_month"))
            if month:
                effective["month"] = str(month)
                effective["start_month"] = str(month)
                effective["end_month"] = str(month)
        elif range_mode == "quarter":
            if not params.get("start_month") or not params.get("end_month"):
                start_month, end_month = _quarter_bounds(str(params.get("quarter") or "Q1"))
                effective["start_month"] = str(start_month)
                effective["end_month"] = str(end_month)
        elif range_mode == "ytd":
            month = _month_int(params.get("month") or params.get("end_month") or 12) or 12
            effective["start_month"] = "1"
            effective["end_month"] = str(month)
        elif range_mode == "full_year":
            effective["start_month"] = "1"
            effective["end_month"] = "12"
        return effective

    def _previous_year_params(self, params: dict[str, Any]) -> dict[str, Any]:
        previous = dict(params)
        previous["year"] = str(_plain_year(params.get("year")) - 1)
        return previous

    def _selected_months(self, params: dict[str, Any]) -> list[int]:
        start_month = _month_int(params.get("start_month"))
        end_month = _month_int(params.get("end_month"))
        month = _month_int(params.get("month"))
        if start_month or end_month:
            left = start_month or 1
            right = end_month or 12
            if left > right:
                left, right = right, left
            return list(range(left, right + 1))
        if month:
            return [month]
        quarter = str(params.get("quarter") or "").strip().upper()
        left, right = _quarter_bounds(quarter or "Q1")
        return list(range(left, right + 1))

    def _range_label(self, params: dict[str, Any]) -> str:
        start_month = _month_int(params.get("start_month"))
        end_month = _month_int(params.get("end_month"))
        if start_month and end_month and start_month != end_month:
            return f"{start_month:02d}-{end_month:02d}月"
        if end_month:
            return f"{end_month:02d}月"
        return str(params.get("quarter") or "")

    def _render_template(self, template: str, params: dict[str, Any]) -> str:
        if not template:
            return ""

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(params.get(key, ""))

        rendered = _TEMPLATE_PARAM_RE.sub(replace, template)
        try:
            return rendered.format(**params)
        except Exception:
            return rendered
