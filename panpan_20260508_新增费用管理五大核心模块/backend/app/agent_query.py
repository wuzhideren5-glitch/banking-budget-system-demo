from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

# 仅读查询白名单：年度库事实表/维度表
BUDGET_SQL_TABLES: frozenset[str] = frozenset(
    {
        "budget_data",
        "budget_summary",
        "version",
        "period",
        "data_account",
        "report_account",
        "dept_account",
        "product_type",
        "report_data_mapping",
        "dept_product_mapping",
    }
)
# 多年度对比只读库
COMPARE_SQL_TABLES: frozenset[str] = frozenset({"compare_budget_summary"})


class ReadOnlySqlExecutor:
    def __init__(self, budget_db_path: Path, common_db_path: Path, max_rows: int = 5000):
        self.budget_db_path = budget_db_path
        self.common_db_path = common_db_path
        self.max_rows = max_rows
        self.repo_root = budget_db_path.parent.parent
        self.allowed_tables = set(BUDGET_SQL_TABLES)
        self.table_name_zh = {
            "budget_data": "预算明细表",
            "budget_summary": "预算汇总表",
            "version": "版本表",
            "period": "期间表",
            "data_account": "数据科目表",
            "report_account": "报告科目表",
            "dept_account": "部门科目表",
            "product_type": "产品科目表",
            "report_data_mapping": "报告-数据映射表",
            "dept_product_mapping": "部门-产品映射表",
        }
        self.field_name_zh = {
            "product_code": "产品科目代码",
            "applies_to_all_products": "是否适用所有产品",
            "month": "月份",
            "year": "年度",
            "quarter": "季度",
            "budget_actual": "预算/实际口径",
            "total_value": "金额合计",
            "value": "金额",
            "dept_level1": "一级部门",
            "dept_level2": "二级部门",
            "dept_level3": "三级部门",
            "data_code_name": "数据科目",
            "product_code_name": "产品科目",
            "version_name": "预算版本",
            "version_id": "版本编号",
            "report_level1": "一级报告科目",
            "report_level2": "二级报告科目",
            "report_level3": "三级报告科目",
            "report_level4": "四级报告科目",
            "report_level5": "五级报告科目",
            "show_level": "展示层级",
            "source_year": "来源年度",
            "source_version_id": "来源版本号",
            "source_version_name": "来源版本名称",
            "sync_time": "同步时间",
        }
        self._load_name_mapping_overrides()
        self.data_name_value_type = self._load_data_value_type_mapping()

    def _load_name_mapping_overrides(self) -> None:
        mapping_file = self.repo_root / "knowledge_base" / "01_data_semantics" / "field_table_name_mapping_zh.json"
        if not mapping_file.exists():
            return
        try:
            data = json.loads(mapping_file.read_text(encoding="utf-8"))
            table_map = data.get("table_name_mapping") or {}
            field_map = data.get("field_name_mapping") or {}
            if isinstance(table_map, dict):
                self.table_name_zh.update({str(k): str(v) for k, v in table_map.items()})
            if isinstance(field_map, dict):
                self.field_name_zh.update({str(k): str(v) for k, v in field_map.items()})
        except Exception:
            return

    def _to_zh_column(self, col: str) -> str:
        return self.field_name_zh.get(col, col)

    def _load_data_value_type_mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        if not self.common_db_path.exists():
            return mapping
        conn = sqlite3.connect(self.common_db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT data_acct_name, value_type
                FROM data_account
                WHERE data_acct_name IS NOT NULL
                """
            ).fetchall()
            for r in rows:
                name = str(r["data_acct_name"] or "").strip()
                vtype = str(r["value_type"] or "").strip()
                if name:
                    mapping[name] = vtype
        except Exception:
            return mapping
        finally:
            conn.close()
        return mapping

    @staticmethod
    def _map_budget_actual(value: Any) -> Any:
        if value == 0:
            return "预算值"
        if value == 1:
            return "实际值"
        return value

    @staticmethod
    def _fmt_amount(v: float) -> str:
        return f"{v:,.2f}"

    @staticmethod
    def _fmt_period_month_display(raw: Any) -> Any:
        """M03 -> 3月，Y2026 -> 2026年（便于用户阅读，不改变数值计算列）。"""
        if raw is None:
            return raw
        s = str(raw).strip()
        m = re.match(r"^M(\d{1,2})$", s, flags=re.I)
        if m:
            mm = int(m.group(1))
            if 1 <= mm <= 12:
                return f"{mm}月"
        m2 = re.match(r"^Y(\d{4})$", s, flags=re.I)
        if m2:
            return f"{m2.group(1)}年"
        if re.match(r"^Q[1-4]$", s, flags=re.I):
            return s.upper()
        return raw

    @staticmethod
    def _fmt_percent(v: float) -> str:
        # 兼容两类存储：0.123 / 12.3
        pct = v * 100.0 if abs(v) <= 1 else v
        return f"{pct:,.2f}%"

    def _format_by_value_type(self, value: Any, *, value_type: str | None = None, column: str = "") -> Any:
        if not isinstance(value, (int, float)):
            return value
        vt = (value_type or "").strip()
        col = str(column or "")
        is_percent_col = bool(re.search(r"(rate|ratio|percent|比例|占比|%|率$)", col, flags=re.I))
        is_amount_col = col in {
            "value",
            "total_value",
            "预算值",
            "实际值",
            "基准值",
            "比较值",
            "同比变化量",
            "金额",
            "金额合计",
        } or bool(re.search(r"(金额|变化量|值$|(?:^|_)(value|amount|amt)$|delta|change)", col, flags=re.I))
        if "百分比" in vt or is_percent_col:
            return self._fmt_percent(float(value))
        if vt in {"金额", "数值", "数量"}:
            return self._fmt_amount(float(value))
        if not vt and is_amount_col:
            return self._fmt_amount(float(value))
        return value

    def _to_display_rows(self, cols: list[str], rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        display_rows: list[dict[str, Any]] = []
        for row in rows:
            item: dict[str, Any] = {}
            row_value_type = ""
            if "value_type" in cols:
                row_value_type = str(row["value_type"] or "").strip()
            if not row_value_type and "data_code_name" in cols:
                row_value_type = self.data_name_value_type.get(str(row["data_code_name"] or "").strip(), "")
            for col in cols:
                name = self._to_zh_column(col)
                value = row[col]
                if col == "budget_actual":
                    value = self._map_budget_actual(value)
                elif col in ("month", "year", "quarter"):
                    value = self._fmt_period_month_display(value)
                else:
                    value = self._format_by_value_type(value, value_type=row_value_type, column=col)
                item[name] = value
            display_rows.append(item)
        return display_rows

    @staticmethod
    def _extract_year_from_text(text: str) -> int | None:
        m = re.search(r"(20\d{2})", text or "")
        if not m:
            return None
        return int(m.group(1))

    @staticmethod
    def _extract_month_index_from_text(text: str) -> int | None:
        t = text or ""
        m = re.search(r"(\d{1,2})月", t)
        if m:
            mm = int(m.group(1))
            if 1 <= mm <= 12:
                return mm
        if re.search(r"(一季度|q1|Q1)", t):
            return 3
        if re.search(r"(二季度|q2|Q2)", t):
            return 6
        if re.search(r"(三季度|q3|Q3)", t):
            return 9
        if re.search(r"(四季度|q4|Q4)", t):
            return 12
        return None

    def resolve_version_context(self, *, query: str, time_period: str | None = None) -> dict[str, Any]:
        """默认 L1 展示版本；若与用户年度不符则回退到当前可编辑数据库的当前版本。"""
        requested_year = self._extract_year_from_text(query) or self._extract_year_from_text(time_period or "")
        requested_month = self._extract_month_index_from_text(query) or self._extract_month_index_from_text(time_period or "")

        show_l1: dict[str, Any] | None = None
        editable: dict[str, Any] | None = None
        conn = sqlite3.connect(self.common_db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT e.edit_show_sign, e.version_id, d.data_file_name, d.year
                FROM edit_show_version e
                JOIN databases d ON d.id = e.data_file_id
                """
            ).fetchall()
            for r in rows:
                sign = int(r["edit_show_sign"] or 0)
                item = {
                    "version_id": int(r["version_id"] or 0),
                    "db_path": self.common_db_path.parent / str(r["data_file_name"]),
                    "year": int(r["year"] or 0),
                }
                if sign == 1:
                    show_l1 = item
                elif sign == 0:
                    editable = item
        finally:
            conn.close()

        base = show_l1 or editable
        if not base:
            # legacy fallback
            latest_id = 0
            if self.budget_db_path.exists():
                c = sqlite3.connect(self.budget_db_path)
                try:
                    row = c.execute("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1").fetchone()
                    latest_id = int(row[0]) if row else 0
                finally:
                    c.close()
            return {
                "source": "legacy_default",
                "db_path": self.budget_db_path,
                "year": self._extract_year_from_text(str(self.budget_db_path.name)) or 0,
                "version_id": latest_id,
                "requested_year": requested_year,
            }

        use = dict(base)
        source = "show_level1_default" if show_l1 and base is show_l1 else "editable_default"
        if requested_year and show_l1 and int(show_l1["year"]) != requested_year and editable:
            use = dict(editable)
            source = "editable_fallback_due_to_year_mismatch"

        if show_l1 and source.startswith("show_level1") and requested_month and editable:
            cshow = sqlite3.connect(show_l1["db_path"])
            try:
                row = cshow.execute(
                    "SELECT current_month FROM version WHERE version_id = ?",
                    (int(show_l1["version_id"]),),
                ).fetchone()
                show_current_month = int(row[0]) if row and row[0] is not None else 12
            finally:
                cshow.close()
            if requested_month > show_current_month:
                use = dict(editable)
                source = "editable_fallback_due_to_time_mismatch"

        # 规则2：可编辑库取“当前版本”（最新 version_id）；展示库按指定版本。
        if source.startswith("editable"):
            c = sqlite3.connect(use["db_path"])
            try:
                row = c.execute("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1").fetchone()
                use["version_id"] = int(row[0]) if row else int(use["version_id"])
            finally:
                c.close()

        return {
            "source": source,
            "db_path": Path(use["db_path"]),
            "year": int(use["year"]),
            "version_id": int(use["version_id"]),
            "requested_year": requested_year,
            "requested_month": requested_month,
        }

    def _build_data_quality_note(self, cols: list[str], rows: list[sqlite3.Row]) -> str:
        if not rows:
            return "当前查询未返回数据，可能是筛选条件过严或该口径下暂无数据。"

        col_set = set(cols)
        notes: list[str] = []

        # Detect common all-zero issue for totals.
        numeric_cols = [c for c in ("total_value", "value") if c in col_set]
        for nc in numeric_cols:
            nums = []
            for r in rows:
                v = r[nc]
                if isinstance(v, (int, float)):
                    nums.append(float(v))
            if nums and all(abs(v) < 1e-9 for v in nums):
                notes.append(f"{self._to_zh_column(nc)}均为 0，建议核对录入进度或筛选口径。")

        # Specific check for budget vs actual split.
        if "budget_actual" in col_set and any(c in col_set for c in ("total_value", "value")):
            value_col = "total_value" if "total_value" in col_set else "value"
            budget_vals = []
            actual_vals = []
            for r in rows:
                val = r[value_col]
                if not isinstance(val, (int, float)):
                    continue
                if r["budget_actual"] == 0:
                    budget_vals.append(float(val))
                elif r["budget_actual"] == 1:
                    actual_vals.append(float(val))
            if budget_vals and actual_vals:
                if any(abs(v) > 1e-9 for v in budget_vals) and all(abs(v) < 1e-9 for v in actual_vals):
                    notes.append("预算值存在但实际值全为 0，可能尚未完成实际数据回补。")

        # Incomplete month coverage（单月明细查询不提示“不完整”）。
        if "month" in col_set:
            months = sorted({str(r["month"]) for r in rows if r["month"] is not None})
            if 1 < len(months) < 12:
                notes.append(f"当前仅覆盖 {len(months)} 个月份，数据可能不完整。")

        if not notes:
            return "数据口径整体可用，建议结合业务背景继续做部门/产品层钻取。"
        return "；".join(notes)

    def _normalize_sql(self, sql: str) -> str:
        text = (sql or "").strip()
        if not text:
            raise ValueError("SQL 不能为空")
        # Only allow one statement.
        if ";" in text.rstrip(";"):
            raise ValueError("只允许单条只读 SQL")
        return text.rstrip(";")

    def _guard(
        self,
        sql: str,
        *,
        forced_version_id: int | None = None,
        forced_show_level: int | list[int] | tuple[int, ...] | None = None,
        sql_profile: str = "budget",
    ) -> str:
        normalized = self._normalize_sql(sql)
        lowered = normalized.lower()
        if not (lowered.startswith("select") or lowered.startswith("with")):
            raise ValueError("仅允许 SELECT/WITH 查询")

        if sql_profile not in ("budget", "compare"):
            raise ValueError("sql_profile 仅支持 budget / compare")

        blocked = re.search(
            r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|truncate)\b",
            lowered,
        )
        if blocked:
            raise ValueError("检测到非只读关键字，已拒绝执行")

        allowed = COMPARE_SQL_TABLES if sql_profile == "compare" else BUDGET_SQL_TABLES
        # 允许 WITH 子句中定义的 CTE 名称出现在 FROM/JOIN 位置，
        # 避免把 "WITH base AS (...)" 的 base 误判为未授权物理表。
        cte_names = {
            m.group(1).lower()
            for m in re.finditer(
                r"(?:\bwith\b(?:\s+recursive)?|,)\s*([a-zA-Z_][\w]*)\s+as\s*\(",
                lowered,
            )
        }
        tables = re.findall(r"\b(?:from|join)\s+([a-zA-Z_][\w\.]*)", lowered)
        for table in tables:
            t = table.split(".")[-1]
            if t in cte_names:
                continue
            if t not in allowed:
                raise ValueError(f"检测到未授权表: {t}")

        if sql_profile == "compare":
            if forced_show_level is not None:
                if isinstance(forced_show_level, (list, tuple, set)):
                    allowed_levels = {int(x) for x in forced_show_level if int(x) > 0}
                else:
                    allowed_levels = {int(forced_show_level)}
                if not allowed_levels:
                    raise ValueError("compare 查询缺少 show_level 上下文")
                eq_hits = [int(x) for x in re.findall(r"\bshow_level\s*=\s*(\d+)", lowered)]
                in_hits_raw = re.findall(r"\bshow_level\s+in\s*\(([^)]*)\)", lowered)
                in_hits: list[int] = []
                for raw in in_hits_raw:
                    in_hits.extend([int(x) for x in re.findall(r"\d+", raw)])
                all_hits = eq_hits + in_hits
                if not all_hits:
                    raise ValueError("查询必须绑定 show_level 条件")
                if any(level not in allowed_levels for level in all_hits):
                    raise ValueError("查询中的 show_level 与当前上下文不一致")
        elif forced_version_id is not None:
            hits = re.findall(r"\bversion_id\s*=\s*(\d+)", lowered)
            if len(hits) != 1:
                raise ValueError("查询必须且只能绑定一个 version_id 条件")
            if int(hits[0]) != int(forced_version_id):
                raise ValueError("查询版本与当前上下文版本不一致")

        if " limit " not in lowered:
            normalized = f"{normalized} LIMIT {self.max_rows}"
        return normalized

    def execute(
        self,
        sql: str,
        *,
        budget_db_path: Path | None = None,
        forced_version_id: int | None = None,
        forced_show_level: int | list[int] | tuple[int, ...] | None = None,
        sql_profile: str = "budget",
    ) -> dict[str, Any]:
        safe_sql = self._guard(
            sql,
            forced_version_id=forced_version_id,
            forced_show_level=forced_show_level,
            sql_profile=sql_profile,
        )
        db_path = budget_db_path or self.budget_db_path
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("ATTACH DATABASE ? AS common", (str(self.common_db_path),))
            cur = conn.execute(safe_sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        finally:
            conn.close()

        preview = []
        for row in rows[:30]:
            preview.append({k: row[k] for k in cols})
        display_rows = self._to_display_rows(cols, rows[:30])
        data_quality_note = self._build_data_quality_note(cols, rows)
        return {
            "sql": safe_sql,
            "row_count": len(rows),
            "columns": cols,
            "preview_rows": preview,
            "display_columns": [self._to_zh_column(c) for c in cols],
            "display_preview_rows": display_rows,
            "data_quality_note": data_quality_note,
        }
