"""
年度聚合引擎 - 根据 annual_agg_rule 将月度数据聚合为年度值。

规则:
  SUM     - 12个月求和 (损益类金额)
  AVG     - 12个月均值 (日均余额)
  LAST    - 取最后一个月 (时点余额)
  WGT     - 加权平均 (需权重指标，暂按简单均值)
  ''/None - 无规则，年度值手工录入

用法:
  compute_annual(monthly_values, rule) -> float | None
  aggregate_metrics(common_path, budget_path, ...) -> 批量计算
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.core.config import settings
from app.core.database import get_pool

# ── 规则常量 ──────────────────────────────────────────────
RULE_SUM = "SUM"
RULE_AVG = "AVG"
RULE_LAST = "LAST"
RULE_WGT = "WGT"
VALID_RULES = {RULE_SUM, RULE_AVG, RULE_LAST, RULE_WGT}


def _uses_mysql_path(path: Path | str, *, names: set[str] | None = None, budget: bool = False) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
        data_dir = Path(settings.data_dir).expanduser().resolve()
    except (TypeError, OSError):
        return False
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    if budget:
        return re.fullmatch(r"budget_\d{4}\.db", candidate.name) is not None
    return names is not None and candidate.name in names


def _uses_mysql_common_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, names={"common.db"})


def _uses_mysql_budget_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, budget=True)


def _budget_year_from_path(path: Path | str) -> int:
    match = re.fullmatch(r"budget_(\d{4})\.db", Path(path).name)
    return int(match.group(1)) if match else int(settings.budget_year)


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _month_values_from_rows(rows: list[Any]) -> list[float]:
    monthly: dict[int, float] = {}
    for row in rows:
        month_raw = _row_value(row, "month", 0)
        value_raw = _row_value(row, "value", 1)
        try:
            month = int(str(month_raw).replace("M", "").replace("m", ""))
        except (TypeError, ValueError):
            continue
        if 1 <= month <= 12:
            monthly[month] = float(value_raw or 0.0)
    return [monthly.get(month, 0.0) for month in range(1, 13)]


def compute_annual(monthly_values: list[float], rule: str) -> float | None:
    """从 1-12 月数值计算年度聚合值。"""
    rule = str(rule or "").strip().upper()
    if rule not in VALID_RULES:
        return None

    padded = list(monthly_values[:12]) + [0.0] * max(0, 12 - len(monthly_values))
    non_zero = [v for v in padded if v != 0.0]

    if rule == RULE_SUM:
        return sum(padded)

    if rule == RULE_AVG:
        if not non_zero:
            return 0.0
        return sum(padded) / len(non_zero)

    if rule == RULE_LAST:
        for value in reversed(padded):
            if value != 0.0:
                return value
        return padded[-1] if padded else 0.0

    if rule == RULE_WGT:
        if not non_zero:
            return 0.0
        return sum(padded) / len(non_zero)

    return None


@dataclass
class AnnualAggregationResult:
    """单个指标聚合结果"""
    data_acct_code: str
    annual_value: float | None = None
    rule: str = ""
    month_count: int = 0
    error: str | None = None


@dataclass
class AnnualAggregationReport:
    results: list[AnnualAggregationResult] = field(default_factory=list)
    computed: int = 0
    skipped: int = 0
    errors: int = 0

    def to_summary(self) -> dict[str, Any]:
        return {
            "computed": self.computed,
            "skipped": self.skipped,
            "errors": self.errors,
            "results": [
                {
                    "code": r.data_acct_code,
                    "annual_value": r.annual_value,
                    "rule": r.rule,
                    "months": r.month_count,
                    "error": r.error,
                }
                for r in self.results[:50]
            ],
        }


async def _fetch_rule(common_path: Path, data_acct_code: str) -> str:
    code = data_acct_code.upper()
    if _uses_mysql_common_path(common_path):
        pool = get_pool()
        row = await pool.fetch_one(
            """SELECT n.annual_agg_rule
               FROM data_account_metric_node n
               JOIN data_account_metric_binding b ON b.metric_node_code = n.node_code
               WHERE b.data_acct_code = %s AND b.is_active = 1
               LIMIT 1""",
            (code,),
        )
        if row is None:
            row = await pool.fetch_one(
                """SELECT annual_agg_rule
                   FROM data_account_metric_node
                   WHERE node_code = %s
                   LIMIT 1""",
                (code,),
            )
        return str(_row_value(row, "annual_agg_rule", 0) or "").strip().upper() if row else ""

    with sqlite3.connect(common_path) as db:
        row = db.execute(
            """SELECT n.annual_agg_rule
               FROM data_account_metric_node n
               JOIN data_account_metric_binding b ON b.metric_node_code = n.node_code
               WHERE b.data_acct_code = ? AND b.is_active = 1
               LIMIT 1""",
            (code,),
        ).fetchone()
        if row is None:
            row = db.execute(
                """SELECT annual_agg_rule
                   FROM data_account_metric_node
                   WHERE node_code = ?
                   LIMIT 1""",
                (code,),
            ).fetchone()
    return str(_row_value(row, "annual_agg_rule", 0) or "").strip().upper() if row else ""


async def _fetch_rule_map(common_path: Path, data_acct_codes: list[str]) -> dict[str, str]:
    if not data_acct_codes:
        return {}
    codes = tuple(code.upper() for code in data_acct_codes)
    rule_map: dict[str, str] = {}

    if _uses_mysql_common_path(common_path):
        placeholders = ",".join("%s" for _ in codes)
        pool = get_pool()
        node_rows = await pool.fetch_all(
            f"""SELECT n.node_code, n.annual_agg_rule
                FROM data_account_metric_node n
                WHERE n.node_code IN ({placeholders})""",
            codes,
        )
        for row in node_rows:
            rule_map[str(_row_value(row, "node_code", 0) or "").strip().upper()] = str(
                _row_value(row, "annual_agg_rule", 1) or ""
            ).strip().upper()

        binding_rows = await pool.fetch_all(
            f"""SELECT b.data_acct_code, n.annual_agg_rule
                FROM data_account_metric_binding b
                JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
                WHERE b.data_acct_code IN ({placeholders}) AND b.is_active = 1""",
            codes,
        )
        for row in binding_rows:
            rule_map[str(_row_value(row, "data_acct_code", 0) or "").strip().upper()] = str(
                _row_value(row, "annual_agg_rule", 1) or ""
            ).strip().upper()
        return rule_map

    placeholders = ",".join("?" for _ in codes)
    with sqlite3.connect(common_path) as db:
        node_rows = db.execute(
            f"""SELECT n.node_code, n.annual_agg_rule
                FROM data_account_metric_node n
                WHERE n.node_code IN ({placeholders})""",
            codes,
        ).fetchall()
        for row in node_rows:
            rule_map[str(_row_value(row, "node_code", 0) or "").strip().upper()] = str(
                _row_value(row, "annual_agg_rule", 1) or ""
            ).strip().upper()

        binding_rows = db.execute(
            f"""SELECT b.data_acct_code, n.annual_agg_rule
                FROM data_account_metric_binding b
                JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
                WHERE b.data_acct_code IN ({placeholders}) AND b.is_active = 1""",
            codes,
        ).fetchall()
        for row in binding_rows:
            rule_map[str(_row_value(row, "data_acct_code", 0) or "").strip().upper()] = str(
                _row_value(row, "annual_agg_rule", 1) or ""
            ).strip().upper()
    return rule_map


async def _fetch_monthly_rows(
    common_path: Path,
    budget_path: Path,
    *,
    data_acct_code: str,
    budget_actual: int,
    year: int,
    version_id: int | None = None,
) -> list[Any]:
    year_label = f"Y{int(year)}"
    code = data_acct_code.upper()
    if _uses_mysql_budget_path(budget_path) and _uses_mysql_common_path(common_path):
        budget_year = _budget_year_from_path(budget_path)
        version_filter = "AND bd.version_id = %s" if version_id is not None else ""
        params: tuple[Any, ...] = (code, int(budget_actual), budget_year, year_label)
        if version_id is not None:
            params = params + (int(version_id),)
        return await get_pool().fetch_all(
            f"""SELECT p.month, bd.value
                FROM budget_data bd
                JOIN period p ON bd.period_id = p.period_id
                WHERE bd.data_acct_code = %s
                  AND bd.budget_actual = %s
                  AND bd.budget_year = %s
                  AND p.year = %s
                  {version_filter}
                ORDER BY p.month""",
            params,
        )

    with sqlite3.connect(budget_path) as db:
        db.execute("ATTACH DATABASE ? AS common_db", (str(common_path),))
        try:
            version_filter = "AND bd.version_id = ?" if version_id is not None else ""
            params = (code, int(budget_actual), year_label)
            if version_id is not None:
                params = params + (int(version_id),)
            return db.execute(
                f"""SELECT p.month, bd.value
                    FROM budget_data bd
                    JOIN common_db.period p ON bd.period_id = p.period_id
                    WHERE bd.data_acct_code = ?
                      AND bd.budget_actual = ?
                      AND p.year = ?
                      {version_filter}
                    ORDER BY p.month""",
                params,
            ).fetchall()
        finally:
            db.execute("DETACH DATABASE common_db")


async def aggregate_single_metric(
    common_path: Path,
    budget_path: Path,
    data_acct_code: str,
    budget_actual: int = 0,
    year: int = 2026,
) -> AnnualAggregationResult:
    """计算单个指标的年度聚合值"""
    result = AnnualAggregationResult(data_acct_code=data_acct_code)
    rule = await _fetch_rule(common_path, data_acct_code)
    result.rule = rule

    if rule not in VALID_RULES:
        result.error = f"无有效聚合规则: {rule!r}"
        return result

    rows = await _fetch_monthly_rows(
        common_path,
        budget_path,
        data_acct_code=data_acct_code,
        budget_actual=budget_actual,
        year=year,
    )
    values = _month_values_from_rows(rows)
    result.month_count = sum(1 for value in values if value != 0.0)
    result.annual_value = compute_annual(values, rule)
    return result


async def aggregate_batch(
    common_path: Path,
    budget_path: Path,
    data_acct_codes: list[str],
    budget_actual: int = 0,
    year: int = 2026,
) -> AnnualAggregationReport:
    """批量计算年度聚合值"""
    report = AnnualAggregationReport()
    rule_map = await _fetch_rule_map(common_path, data_acct_codes)

    for code in data_acct_codes:
        result = AnnualAggregationResult(data_acct_code=code)
        rule = rule_map.get(code.upper(), "")
        result.rule = rule

        if rule not in VALID_RULES:
            result.error = f"无有效聚合规则: {rule!r}" if rule else "未配置规则"
            report.skipped += 1
            report.results.append(result)
            continue

        rows = await _fetch_monthly_rows(
            common_path,
            budget_path,
            data_acct_code=code,
            budget_actual=budget_actual,
            year=year,
        )
        values = _month_values_from_rows(rows)
        result.month_count = sum(1 for value in values if value != 0.0)
        result.annual_value = compute_annual(values, rule)
        report.computed += 1
        report.results.append(result)

    return report


# ── 年度聚合缓存表（budget_2026.db）────────────────────────

ANNUAL_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS budget_annual_aggregate (
    data_acct_code  TEXT NOT NULL,
    product_code    TEXT NOT NULL DEFAULT '',
    year            INTEGER NOT NULL,
    budget_actual   INTEGER NOT NULL,
    version_id      INTEGER NOT NULL,
    annual_value    REAL NOT NULL DEFAULT 0,
    agg_rule        TEXT NOT NULL DEFAULT '',
    month_count     INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (data_acct_code, year, budget_actual, version_id)
)
"""

MYSQL_ANNUAL_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS budget_annual_aggregate (
    id INT AUTO_INCREMENT PRIMARY KEY,
    budget_year INT NOT NULL,
    data_acct_code VARCHAR(255) NOT NULL,
    product_code VARCHAR(64) NOT NULL DEFAULT '',
    year INT NOT NULL,
    budget_actual TINYINT(1) NOT NULL,
    version_id INT NOT NULL,
    annual_value DOUBLE NOT NULL DEFAULT 0,
    agg_rule VARCHAR(32) NOT NULL DEFAULT '',
    month_count INT NOT NULL DEFAULT 0,
    updated_at VARCHAR(64) NOT NULL DEFAULT '',
    UNIQUE KEY uq_budget_annual_aggregate (
        budget_year, data_acct_code, year, budget_actual, version_id
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


async def ensure_annual_table(budget_path: Path) -> None:
    """确保年度聚合缓存表存在"""
    if _uses_mysql_budget_path(budget_path):
        await get_pool().execute(MYSQL_ANNUAL_TABLE_DDL)
        return

    with sqlite3.connect(budget_path) as db:
        db.execute(ANNUAL_TABLE_DDL)
        db.commit()


async def upsert_annual_aggregate(
    budget_path: Path,
    data_acct_code: str,
    product_code: str,
    year: int,
    budget_actual: int,
    version_id: int,
    annual_value: float,
    agg_rule: str,
    month_count: int,
) -> None:
    """写入或更新单条年度聚合值"""
    now = datetime.now(timezone.utc).isoformat()
    if _uses_mysql_budget_path(budget_path):
        await ensure_annual_table(budget_path)
        await get_pool().execute(
            """INSERT INTO budget_annual_aggregate
               (budget_year, data_acct_code, product_code, year, budget_actual, version_id,
                annual_value, agg_rule, month_count, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 annual_value = VALUES(annual_value),
                 agg_rule = VALUES(agg_rule),
                 month_count = VALUES(month_count),
                 updated_at = VALUES(updated_at)""",
            (
                _budget_year_from_path(budget_path),
                data_acct_code.upper(),
                product_code,
                year,
                budget_actual,
                version_id,
                annual_value,
                agg_rule,
                month_count,
                now,
            ),
        )
        return

    with sqlite3.connect(budget_path) as db:
        db.execute(ANNUAL_TABLE_DDL)
        db.execute(
            """INSERT INTO budget_annual_aggregate
               (data_acct_code, product_code, year, budget_actual, version_id,
                annual_value, agg_rule, month_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(data_acct_code, year, budget_actual, version_id)
               DO UPDATE SET
                 annual_value = excluded.annual_value,
                 agg_rule = excluded.agg_rule,
                 month_count = excluded.month_count,
                 updated_at = excluded.updated_at""",
            (
                data_acct_code.upper(),
                product_code,
                year,
                budget_actual,
                version_id,
                annual_value,
                agg_rule,
                month_count,
                now,
            ),
        )
        db.commit()


async def _fetch_refresh_metric_rows(common_path: Path, product_codes: list[str]) -> list[Any]:
    if not product_codes:
        return []
    if _uses_mysql_common_path(common_path):
        placeholders = ",".join("%s" for _ in product_codes)
        return await get_pool().fetch_all(
            f"""SELECT n.node_code, n.annual_agg_rule, n.product_code
                FROM data_account_metric_node n
                WHERE n.product_code IN ({placeholders})
                  AND n.annual_agg_rule != ''
                  AND n.annual_agg_rule IS NOT NULL
                  AND n.is_active = 1""",
            tuple(product_codes),
        )

    placeholders = ",".join("?" for _ in product_codes)
    with sqlite3.connect(common_path) as db:
        return db.execute(
            f"""SELECT n.node_code, n.annual_agg_rule, n.product_code
                FROM data_account_metric_node n
                WHERE n.product_code IN ({placeholders})
                  AND n.annual_agg_rule != ''
                  AND n.annual_agg_rule IS NOT NULL
                  AND n.is_active = 1""",
            tuple(product_codes),
        ).fetchall()


async def refresh_annual_aggregates_for_products(
    common_path: Path,
    budget_path: Path,
    *,
    product_codes: list[str],
    budget_actuals: list[int],
    year: int,
    version_id: int,
) -> dict[str, Any]:
    """保存钩子：月度数据写入后刷新年度聚合。"""
    metric_rows = await _fetch_refresh_metric_rows(common_path, product_codes)
    if not metric_rows:
        return {"refreshed": 0}

    refreshed = 0
    for row in metric_rows:
        node_code = str(_row_value(row, "node_code", 0) or "").strip().upper()
        rule = str(_row_value(row, "annual_agg_rule", 1) or "").strip().upper()
        product_code = str(_row_value(row, "product_code", 2) or "")
        if not node_code or rule not in VALID_RULES:
            continue

        for budget_actual in budget_actuals:
            rows = await _fetch_monthly_rows(
                common_path,
                budget_path,
                data_acct_code=node_code,
                budget_actual=int(budget_actual),
                year=year,
                version_id=version_id,
            )
            values = _month_values_from_rows(rows)
            month_count = sum(1 for value in values if value != 0.0)
            annual_value = compute_annual(values, rule)

            if annual_value is None:
                continue
            await upsert_annual_aggregate(
                budget_path=budget_path,
                data_acct_code=node_code,
                product_code=product_code,
                year=year,
                budget_actual=int(budget_actual),
                version_id=version_id,
                annual_value=annual_value,
                agg_rule=rule,
                month_count=month_count,
            )
            refreshed += 1

    return {"refreshed": refreshed}


async def get_cached_annual_values(
    budget_path: Path,
    *,
    data_acct_codes: list[str],
    year: int,
    budget_actual: int,
    version_id: int,
) -> dict[str, dict[str, Any]]:
    """从缓存表读取年度聚合值"""
    if not data_acct_codes:
        return {}

    if _uses_mysql_budget_path(budget_path):
        await ensure_annual_table(budget_path)
        placeholders = ",".join("%s" for _ in data_acct_codes)
        rows = await get_pool().fetch_all(
            f"""SELECT data_acct_code, annual_value, agg_rule, month_count, updated_at
                FROM budget_annual_aggregate
                WHERE budget_year = %s
                  AND data_acct_code IN ({placeholders})
                  AND year = %s
                  AND budget_actual = %s
                  AND version_id = %s""",
            (_budget_year_from_path(budget_path),)
            + tuple(code.upper() for code in data_acct_codes)
            + (year, budget_actual, version_id),
        )
    else:
        placeholders = ",".join("?" for _ in data_acct_codes)
        with sqlite3.connect(budget_path) as db:
            db.execute(ANNUAL_TABLE_DDL)
            rows = db.execute(
                f"""SELECT data_acct_code, annual_value, agg_rule, month_count, updated_at
                    FROM budget_annual_aggregate
                    WHERE data_acct_code IN ({placeholders})
                      AND year = ? AND budget_actual = ? AND version_id = ?""",
                tuple(code.upper() for code in data_acct_codes) + (year, budget_actual, version_id),
            ).fetchall()

    return {
        str(_row_value(row, "data_acct_code", 0) or "").strip().upper(): {
            "annual_value": _row_value(row, "annual_value", 1),
            "agg_rule": _row_value(row, "agg_rule", 2),
            "month_count": _row_value(row, "month_count", 3),
            "updated_at": _row_value(row, "updated_at", 4),
        }
        for row in rows
    }
