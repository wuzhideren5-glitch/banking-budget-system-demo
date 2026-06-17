"""Current default seed data routines for freshly created databases."""
from __future__ import annotations

import calendar
import json
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


def _quarter_for_month(month: int) -> str:
    if month <= 3:
        return "Q1"
    if month <= 6:
        return "Q2"
    if month <= 9:
        return "Q3"
    return "Q4"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SMART_PPT_CHART_CONFIGS = [
    {
        "config_code": "time_trend_line",
        "chart_type": "line",
        "metric_config_json": {
            "metric_code": "03.09.05.01.039",
            "metric_name": "营业收入",
            "group_by": "month",
            "top_n": 12,
            "conclusion_type": "trend",
        },
        "visual_config_json": {
            "title": "营业收入趋势",
            "palette": ["#1d4ed8"],
        },
        "remark": "时间趋势折线图",
    },
    {
        "config_code": "dept_compare_bar",
        "chart_type": "bar",
        "metric_config_json": {
            "metric_code": "05.01",
            "metric_name": "业务及管理费",
            "group_by": "dept",
            "top_n": 5,
            "conclusion_type": "ranking",
        },
        "visual_config_json": {
            "title": "多部门对比",
            "palette": ["#0f766e"],
        },
        "remark": "多部门对比柱状图",
    },
    {
        "config_code": "budget_vs_actual_dual_bar",
        "chart_type": "dual_bar",
        "metric_config_json": {
            "metric_codes": ["03.09.05.01.039", "08.04.01.01.001"],
            "metric_names": ["营业收入", "净利润"],
            "group_by": "metric",
            "conclusion_type": "budget_vs_actual",
        },
        "visual_config_json": {
            "title": "预算 vs 实际",
            "palette": ["#94a3b8", "#ea580c"],
        },
        "remark": "预算vs实际双柱图",
    },
    {
        "config_code": "product_share_donut",
        "chart_type": "donut",
        "metric_config_json": {
            "metric_code": "01.01.01.01.017",
            "metric_name": "贷款规模",
            "group_by": "product",
            "top_n": 5,
            "conclusion_type": "ranking",
        },
        "visual_config_json": {
            "title": "产品结构占比",
            "palette": ["#2563eb", "#0f766e", "#f59e0b", "#ef4444", "#7c3aed"],
        },
        "remark": "占比环形图",
    },
    {
        "config_code": "annual_bridge_waterfall",
        "chart_type": "waterfall",
        "metric_config_json": {
            "steps": [
                {"label": "营业收入", "metric_code": "03.09.05.01.039", "sign": 1},
                {"label": "业务及管理费", "metric_code": "05.01", "sign": -1},
                {"label": "资产减值损失", "metric_code": "06.01.01.01.001", "sign": -1},
                {"label": "其他业务净收入", "metric_code": "03.03.04", "sign": 1},
                {"label": "净利润", "metric_code": "08.04.01.01.001", "sign": 1, "is_total": True},
            ],
            "metric_name": "年度利润桥",
            "conclusion_type": "trend",
        },
        "visual_config_json": {
            "title": "年度利润桥",
            "palette": ["#2563eb", "#ef4444", "#ef4444", "#0f766e", "#1e293b"],
        },
        "remark": "瀑布图",
    },
]


SMART_PPT_SCENES = [
    {
        "scene_code": "board_quarterly",
        "scene_name": "董事会季度汇报",
        "scene_type": "board",
        "description": "3-5页结论先行，覆盖核心指标、趋势、预算执行与风险提示。",
        "slide_template_json": {
            "slides": [
                {"type": "cover", "title": "{{year}}年{{quarter}}董事会经营分析报告", "subtitle": "Finance Narrative Engine"},
                {
                    "type": "dashboard",
                    "title": "核心指标概览",
                    "range_mode": "quarter",
                    "metrics": ["total_income", "total_profit", "total_expense"],
                },
                {
                    "type": "trend_chart",
                    "title": "营业收入趋势分析",
                    "chart_config_code": "time_trend_line",
                    "range_mode": "quarter",
                    "metric_code": "03.09.05.01.039",
                    "metric_name": "营业收入",
                },
                {
                    "type": "budget_vs_actual",
                    "title": "预算执行情况",
                    "chart_config_code": "budget_vs_actual_dual_bar",
                    "range_mode": "quarter",
                    "metric_codes": ["03.09.05.01.039", "08.04.01.01.001"],
                    "metric_names": ["营业收入", "净利润"],
                },
                {
                    "type": "risk_alert",
                    "title": "风险提示",
                    "chart_config_code": "dept_compare_bar",
                    "range_mode": "quarter",
                    "metric_code": "05.01",
                    "metric_name": "业务及管理费",
                    "threshold_pct": 5,
                },
            ]
        },
        "default_params_json": {"year": "2026", "quarter": "Q1", "month": "3", "version_id": "1", "budget_actual": "1"},
        "sort_order": 1,
    },
    {
        "scene_code": "monthly_ops_review",
        "scene_name": "月度经营分析会",
        "scene_type": "monthly",
        "description": "适合经营例会，输出当月表现、部门排名与预算偏差。",
        "slide_template_json": {
            "slides": [
                {"type": "cover", "title": "{{year}}年{{month_label}}月经营分析会", "subtitle": "Monthly Operations Review"},
                {
                    "type": "dashboard",
                    "title": "当月经营仪表盘",
                    "range_mode": "month",
                    "metrics": ["total_income", "total_profit", "total_expense"],
                },
                {
                    "type": "trend_chart",
                    "title": "净利润月度趋势",
                    "chart_config_code": "time_trend_line",
                    "range_mode": "ytd",
                    "metric_code": "08.04.01.01.001",
                    "metric_name": "净利润",
                },
                {
                    "type": "ranking_chart",
                    "title": "部门费用排名",
                    "chart_config_code": "dept_compare_bar",
                    "range_mode": "month",
                    "metric_code": "05.01",
                    "metric_name": "业务及管理费",
                },
                {
                    "type": "budget_vs_actual",
                    "title": "月度预算执行",
                    "chart_config_code": "budget_vs_actual_dual_bar",
                    "range_mode": "month",
                    "metric_codes": ["03.09.05.01.039", "05.01"],
                    "metric_names": ["营业收入", "业务及管理费"],
                },
            ]
        },
        "default_params_json": {"year": "2026", "month": "4", "version_id": "1", "budget_actual": "1"},
        "sort_order": 2,
    },
    {
        "scene_code": "product_line_focus",
        "scene_name": "条线专题分析",
        "scene_type": "product",
        "description": "聚焦产品/条线结构，展示规模占比、排名和趋势。",
        "slide_template_json": {
            "slides": [
                {"type": "cover", "title": "{{year}}年条线专题分析", "subtitle": "{{product_label}}"},
                {
                    "type": "dashboard",
                    "title": "条线核心指标",
                    "range_mode": "ytd",
                    "metrics": ["loan_balance", "fee_income", "total_profit"],
                },
                {
                    "type": "share_chart",
                    "title": "产品结构占比",
                    "chart_config_code": "product_share_donut",
                    "range_mode": "ytd",
                    "metric_code": "01.01.01.01.017",
                    "metric_name": "贷款规模",
                },
                {
                    "type": "ranking_chart",
                    "title": "产品贡献排名",
                    "chart_config_code": "dept_compare_bar",
                    "range_mode": "ytd",
                    "group_by": "product",
                    "metric_code": "03.04.01.01.003",
                    "metric_name": "手续费净收入",
                },
                {
                    "type": "trend_chart",
                    "title": "贷款规模趋势",
                    "chart_config_code": "time_trend_line",
                    "range_mode": "ytd",
                    "metric_code": "01.01.01.01.017",
                    "metric_name": "贷款规模",
                },
            ]
        },
        "default_params_json": {"year": "2026", "month": "6", "version_id": "1", "budget_actual": "1"},
        "sort_order": 3,
    },
    {
        "scene_code": "budget_alert_brief",
        "scene_name": "预算预警简报",
        "scene_type": "alert",
        "description": "面向管理层的短报，聚焦偏差、异常部门与重点风险。",
        "slide_template_json": {
            "slides": [
                {"type": "cover", "title": "{{year}}年{{month_label}}预算预警简报", "subtitle": "Budget Alert Brief"},
                {
                    "type": "budget_vs_actual",
                    "title": "关键指标预算偏差",
                    "chart_config_code": "budget_vs_actual_dual_bar",
                    "range_mode": "month",
                    "metric_codes": ["05.01", "06.01.01.01.001"],
                    "metric_names": ["业务及管理费", "资产减值损失"],
                },
                {
                    "type": "risk_alert",
                    "title": "异常部门预警",
                    "chart_config_code": "dept_compare_bar",
                    "range_mode": "month",
                    "metric_code": "05.01",
                    "metric_name": "业务及管理费",
                    "threshold_pct": 3,
                },
                {
                    "type": "ranking_chart",
                    "title": "重点异常项",
                    "chart_config_code": "dept_compare_bar",
                    "range_mode": "month",
                    "metric_code": "06.01.01.01.001",
                    "metric_name": "资产减值损失",
                },
            ]
        },
        "default_params_json": {"year": "2026", "month": "5", "version_id": "1", "budget_actual": "1"},
        "sort_order": 4,
    },
    {
        "scene_code": "annual_summary",
        "scene_name": "年度总结",
        "scene_type": "board",
        "description": "年度复盘模板，覆盖规模、利润桥和经营结构变化。",
        "slide_template_json": {
            "slides": [
                {"type": "cover", "title": "{{year}}年度经营总结", "subtitle": "Annual Summary"},
                {
                    "type": "dashboard",
                    "title": "年度核心指标",
                    "range_mode": "full_year",
                    "metrics": ["total_income", "total_profit", "loan_balance"],
                },
                {
                    "type": "trend_chart",
                    "title": "全年营业收入趋势",
                    "chart_config_code": "time_trend_line",
                    "range_mode": "full_year",
                    "metric_code": "03.09.05.01.039",
                    "metric_name": "营业收入",
                },
                {
                    "type": "waterfall_chart",
                    "title": "利润桥分析",
                    "chart_config_code": "annual_bridge_waterfall",
                    "range_mode": "full_year",
                },
                {
                    "type": "share_chart",
                    "title": "年末产品结构",
                    "chart_config_code": "product_share_donut",
                    "range_mode": "full_year",
                    "metric_code": "01.01.01.01.017",
                    "metric_name": "贷款规模",
                },
            ]
        },
        "default_params_json": {"year": "2026", "month": "12", "version_id": "1", "budget_actual": "1"},
        "sort_order": 5,
    },
]


def seed_periods(conn: sqlite3.Connection, calendar_year: int) -> None:
    for month in range(1, 13):
        year_label = f"Y{calendar_year}"
        month_label = f"M{month:02d}"
        year_month = f"{calendar_year}-{month:02d}"
        days = calendar.monthrange(calendar_year, month)[1]
        quarter = _quarter_for_month(month)
        conn.execute(
            """
            INSERT OR IGNORE INTO period (year, month, quarter, year_month, days)
            VALUES (?, ?, ?, ?, ?)
            """,
            (year_label, month_label, quarter, year_month, days),
        )


def seed_smart_ppt_defaults(
    conn: sqlite3.Connection,
    chart_configs: Sequence[Mapping[str, Any]],
    scenes: Sequence[Mapping[str, Any]],
) -> None:
    now = _iso_now()
    for item in chart_configs:
        conn.execute(
            """
            INSERT INTO smart_ppt_chart_config (
              config_code, chart_type, metric_config_json, visual_config_json,
              remark, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(config_code) DO UPDATE SET
              chart_type = excluded.chart_type,
              metric_config_json = excluded.metric_config_json,
              visual_config_json = excluded.visual_config_json,
              remark = excluded.remark,
              updated_at = excluded.updated_at
            """,
            (
                item["config_code"],
                item["chart_type"],
                json.dumps(item["metric_config_json"], ensure_ascii=False),
                json.dumps(item["visual_config_json"], ensure_ascii=False),
                item.get("remark"),
                now,
                now,
            ),
        )

    for item in scenes:
        conn.execute(
            """
            INSERT INTO smart_ppt_scene (
              scene_code, scene_name, scene_type, description, slide_template_json,
              default_params_json, sort_order, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(scene_code) DO UPDATE SET
              scene_name = excluded.scene_name,
              scene_type = excluded.scene_type,
              description = excluded.description,
              slide_template_json = excluded.slide_template_json,
              default_params_json = excluded.default_params_json,
              sort_order = excluded.sort_order,
              status = excluded.status,
              updated_at = excluded.updated_at
            """,
            (
                item["scene_code"],
                item["scene_name"],
                item["scene_type"],
                item.get("description"),
                json.dumps(item["slide_template_json"], ensure_ascii=False),
                json.dumps(item["default_params_json"], ensure_ascii=False),
                int(item.get("sort_order", 0)),
                now,
                now,
            ),
        )


def seed_default_smart_ppt(conn: sqlite3.Connection) -> None:
    """Seed the current built-in Smart PPT chart configs and scenes."""
    seed_smart_ppt_defaults(conn, SMART_PPT_CHART_CONFIGS, SMART_PPT_SCENES)
