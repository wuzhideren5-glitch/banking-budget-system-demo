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

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import app.core.aiosqlite_compat as aiosqlite
# ── 规则常量 ──────────────────────────────────────────────
RULE_SUM = "SUM"
RULE_AVG = "AVG"
RULE_LAST = "LAST"
RULE_WGT = "WGT"
VALID_RULES = {RULE_SUM, RULE_AVG, RULE_LAST, RULE_WGT}


def compute_annual(monthly_values: list[float], rule: str) -> float | None:
    """从 1-12 月数值计算年度聚合值。

    Args:
        monthly_values: 12 个月的值列表，None/缺失视为 0
        rule: SUM | AVG | LAST | WGT

    Returns:
        年度聚合值，无法计算时返回 None
    """
    rule = str(rule or "").strip().upper()
    if rule not in VALID_RULES:
        return None

    # 补齐 12 个月
    padded = list(monthly_values[:12]) + [0.0] * max(0, 12 - len(monthly_values))
    non_zero = [v for v in padded if v != 0.0]

    if rule == RULE_SUM:
        return sum(padded)

    if rule == RULE_AVG:
        if not non_zero:
            return 0.0
        return sum(padded) / len(non_zero)

    if rule == RULE_LAST:
        # 从后往前找最后一个非零值
        for v in reversed(padded):
            if v != 0.0:
                return v
        return padded[-1] if padded else 0.0

    if rule == RULE_WGT:
        # 加权平均 - 当前无权重列，按简单均值
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
                for r in self.results[:50]  # 限制返回数量
            ],
        }


async def aggregate_single_metric(
    common_path: Path,
    budget_path: Path,
    data_acct_code: str,
    budget_actual: int = 0,  # 0=budget, 1=actual
    year: int = 2026,
) -> AnnualAggregationResult:
    """计算单个指标的年度聚合值"""
    result = AnnualAggregationResult(data_acct_code=data_acct_code)

    async with aiosqlite.connect(common_path) as db:
        # 获取聚合规则
        cur = await db.execute(
            """SELECT n.annual_agg_rule
               FROM data_account_metric_node n
               JOIN data_account_metric_binding b ON b.metric_node_code = n.node_code
               WHERE b.data_acct_code = ? AND b.is_active = 1
               LIMIT 1""",
            (data_acct_code.upper(),),
        )
        row = await cur.fetchone()
        if not row:
            # 尝试直接查 node_code
            cur2 = await db.execute(
                """SELECT annual_agg_rule FROM data_account_metric_node
                   WHERE node_code = ? LIMIT 1""",
                (data_acct_code.upper(),),
            )
            row = await cur2.fetchone()

    rule = str(row[0] or "").strip().upper() if row else ""
    result.rule = rule

    if rule not in VALID_RULES:
        result.error = f"无有效聚合规则: {rule!r}"
        return result

    async with aiosqlite.connect(budget_path) as budget_db:
        # ATTACH common.db for period table access
        await budget_db.execute(f"ATTACH DATABASE ? AS common_db", (str(common_path),))
        try:
            cur = await budget_db.execute(
                """SELECT p.month, bd.value
                   FROM budget_data bd
                   JOIN common_db.period p ON bd.period_id = p.period_id
                   WHERE bd.data_acct_code = ?
                     AND bd.budget_actual = ?
                     AND p.year = ?
                   ORDER BY p.month""",
                (data_acct_code.upper(), budget_actual, f"Y{year}"),
            )
            rows = await cur.fetchall()
        finally:
            await budget_db.execute("DETACH DATABASE common_db")

    monthly = {}
    for month_str, value in rows:
        try:
            m = int(str(month_str).replace("M", "").replace("m", ""))
            if 1 <= m <= 12:
                monthly[m] = float(value or 0.0)
        except (ValueError, TypeError):
            continue

    values = [monthly.get(m, 0.0) for m in range(1, 13)]
    result.month_count = sum(1 for v in values if v != 0.0)
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

    async with aiosqlite.connect(common_path) as db:
        # 一次性查询所有规则的规则
        placeholders = ",".join("?" for _ in data_acct_codes)
        cur = await db.execute(
            f"""SELECT n.node_code, n.annual_agg_rule
                FROM data_account_metric_node n
                WHERE n.node_code IN ({placeholders})""",
            tuple(c.upper() for c in data_acct_codes),
        )
        rule_map = {str(r[0] or "").strip().upper(): str(r[1] or "").strip().upper()
                     for r in await cur.fetchall()}

    # 同样也通过 binding 查
    async with aiosqlite.connect(common_path) as db:
        cur = await db.execute(
            f"""SELECT b.data_acct_code, n.annual_agg_rule
                FROM data_account_metric_binding b
                JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
                WHERE b.data_acct_code IN ({placeholders}) AND b.is_active = 1""",
            tuple(c.upper() for c in data_acct_codes),
        )
        for code, rule in await cur.fetchall():
            rule_map[str(code or "").strip().upper()] = str(rule or "").strip().upper()

    async with aiosqlite.connect(budget_path) as budget_db:
        await budget_db.execute(f"ATTACH DATABASE ? AS common_db", (str(common_path),))
        try:
            for code in data_acct_codes:
                result = AnnualAggregationResult(data_acct_code=code)
                rule = rule_map.get(code.upper(), "")
                result.rule = rule

                if rule not in VALID_RULES:
                    result.error = f"无有效聚合规则: {rule!r}" if rule else "未配置规则"
                    report.skipped += 1
                    report.results.append(result)
                    continue

                cur = await budget_db.execute(
                    """SELECT p.month, bd.value
                       FROM budget_data bd
                       JOIN common_db.period p ON bd.period_id = p.period_id
                       WHERE bd.data_acct_code = ?
                         AND bd.budget_actual = ?
                         AND p.year = ?
                       ORDER BY p.month""",
                    (code.upper(), budget_actual, f"Y{year}"),
                )
                rows = await cur.fetchall()

                monthly = {}
                for month_str, value in rows:
                    try:
                        m = int(str(month_str).replace("M", "").replace("m", ""))
                        if 1 <= m <= 12:
                            monthly[m] = float(value or 0.0)
                    except (ValueError, TypeError):
                        continue

                values = [monthly.get(m, 0.0) for m in range(1, 13)]
                result.month_count = sum(1 for v in values if v != 0.0)
                result.annual_value = compute_annual(values, rule)
                report.computed += 1
                report.results.append(result)
        finally:
            await budget_db.execute("DETACH DATABASE common_db")

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


async def ensure_annual_table(budget_path: Path) -> None:
    """确保年度聚合缓存表存在"""
    async with aiosqlite.connect(budget_path) as db:
        await db.execute(ANNUAL_TABLE_DDL)
        await db.commit()


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
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(budget_path) as db:
        await db.execute(ANNUAL_TABLE_DDL)
        await db.execute(
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
            (data_acct_code.upper(), product_code, year, budget_actual,
             version_id, annual_value, agg_rule, month_count, now),
        )
        await db.commit()


async def refresh_annual_aggregates_for_products(
    common_path: Path,
    budget_path: Path,
    *,
    product_codes: list[str],
    budget_actuals: list[int],
    year: int,
    version_id: int,
) -> dict[str, Any]:
    """保存钩子：月度数据写入后刷新年度聚合。

    遍历指定产品的所有 metric，对设有 annual_agg_rule 的指标
    从月度数据计算年度值并写入缓存表。
    """
    if not product_codes:
        return {"refreshed": 0}

    # 获取这些产品下设有聚合规则的指标
    placeholders_p = ",".join("?" for _ in product_codes)
    async with aiosqlite.connect(common_path) as db:
        cur = await db.execute(
            f"""SELECT n.node_code, n.annual_agg_rule, n.product_code
                FROM data_account_metric_node n
                WHERE n.product_code IN ({placeholders_p})
                  AND n.annual_agg_rule != ''
                  AND n.annual_agg_rule IS NOT NULL
                  AND n.is_active = 1""",
            tuple(product_codes),
        )
        metric_rows = await cur.fetchall()

    if not metric_rows:
        return {"refreshed": 0}

    refreshed = 0
    for node_code, rule, product_code in metric_rows:
        rule = str(rule or "").strip().upper()
        if rule not in VALID_RULES:
            continue

        for ba in budget_actuals:
            async with aiosqlite.connect(budget_path) as budget_db:
                await budget_db.execute(f"ATTACH DATABASE ? AS common_db", (str(common_path),))
                try:
                    cur = await budget_db.execute(
                        """SELECT p.month, bd.value
                           FROM budget_data bd
                           JOIN common_db.period p ON bd.period_id = p.period_id
                           WHERE bd.data_acct_code = ?
                             AND bd.budget_actual = ?
                             AND p.year = ?
                           ORDER BY p.month""",
                        (node_code.upper(), int(ba), f"Y{year}"),
                    )
                    rows = await cur.fetchall()
                finally:
                    await budget_db.execute("DETACH DATABASE common_db")

            monthly = {}
            for month_str, value in rows:
                try:
                    m = int(str(month_str).replace("M", "").replace("m", ""))
                    if 1 <= m <= 12:
                        monthly[m] = float(value or 0.0)
                except (ValueError, TypeError):
                    continue

            values = [monthly.get(m, 0.0) for m in range(1, 13)]
            month_count = sum(1 for v in values if v != 0.0)
            annual_value = compute_annual(values, rule)

            if annual_value is not None:
                await upsert_annual_aggregate(
                    budget_path=budget_path,
                    data_acct_code=node_code,
                    product_code=str(product_code or ""),
                    year=year,
                    budget_actual=int(ba),
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

    placeholders = ",".join("?" for _ in data_acct_codes)
    async with aiosqlite.connect(budget_path) as db:
        await db.execute(ANNUAL_TABLE_DDL)
        cur = await db.execute(
            f"""SELECT data_acct_code, annual_value, agg_rule, month_count, updated_at
                FROM budget_annual_aggregate
                WHERE data_acct_code IN ({placeholders})
                  AND year = ? AND budget_actual = ? AND version_id = ?""",
            tuple(c.upper() for c in data_acct_codes) + (year, budget_actual, version_id),
        )
        rows = await cur.fetchall()

    return {
        str(r[0] or "").strip().upper(): {
            "annual_value": r[1],
            "agg_rule": r[2],
            "month_count": r[3],
            "updated_at": r[4],
        }
        for r in rows
    }
