from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Literal

from app.budget_window import budget_actual_allowed_for_month
from app.core.config import settings
from app.core.database import get_pool
from app.runtime_metric_identity import product_code_from_runtime_metric_ref
from app.db_bootstrap.budget_version import ensure_budget_version_schema_sync


InvalidMode = Literal["error", "skip"]
ValueKind = Literal["manual", "formula", "rollup"]


@dataclass(frozen=True)
class BudgetDataWriteItem:
    data_acct_code: str
    product_code: str
    period_id: int
    budget_actual: int
    version_id: int
    value: float
    source_ref: str | None = None


@dataclass(frozen=True)
class BudgetDataWritePolicy:
    name: str
    need_calc: int
    value_kind: ValueKind = "manual"
    invalid_mode: InvalidMode = "error"
    allow_formula_runtime_refs: bool = False
    enforce_month_window: bool = True


@dataclass
class BudgetDataWriteResult:
    saved_cells: int = 0
    skipped_cells: int = 0
    written_keys: set[tuple[str, str, int, int, int]] = field(default_factory=set)
    affected_products: set[str] = field(default_factory=set)
    written_data_accts: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def note_for_source(self, source_ref: str) -> str | None:
        messages = [*self.warnings, *self.errors]
        prefix = f"{source_ref}:"
        for message in messages:
            if message.startswith(prefix):
                return message
        return messages[0] if messages else None


@dataclass
class BudgetDataDeleteResult:
    deleted_rows: int = 0
    deleted_by_budget_file: dict[str, int] = field(default_factory=dict)


class BudgetDataWriteError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__(errors[0] if errors else "预算明细写入失败")
        self.errors = errors


MANUAL_INPUT_POLICY = BudgetDataWritePolicy(
    name="manual_input",
    need_calc=1,
    invalid_mode="error",
    allow_formula_runtime_refs=False,
)

FORECAST_INPUT_POLICY = BudgetDataWritePolicy(
    name="forecast_input",
    need_calc=0,
    invalid_mode="skip",
    allow_formula_runtime_refs=False,
)

IMPORT_INPUT_POLICY = BudgetDataWritePolicy(
    name="import_input",
    need_calc=1,
    invalid_mode="skip",
    allow_formula_runtime_refs=False,
)

ORG_PRODUCT_BUDGET_SYNC_POLICY = BudgetDataWritePolicy(
    name="org_product_budget_sync",
    need_calc=1,
    invalid_mode="skip",
    allow_formula_runtime_refs=True,
    enforce_month_window=False,
)

FORMULA_RESULT_POLICY = BudgetDataWritePolicy(
    name="formula_result",
    need_calc=0,
    value_kind="formula",
    invalid_mode="skip",
    allow_formula_runtime_refs=True,
)

ROLLUP_RESULT_POLICY = BudgetDataWritePolicy(
    name="metric_tree_rollup_result",
    need_calc=0,
    value_kind="rollup",
    invalid_mode="skip",
    allow_formula_runtime_refs=True,
)


def _uses_mysql_path(path: Path | str, *, names: set[str] | None = None, budget: bool = False) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
    except TypeError:
        return False
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    data_dir = Path(settings.data_dir).expanduser().resolve()
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    if budget:
        return re.fullmatch(r"budget_\d{4}\.db", candidate.name) is not None
    return names is not None and candidate.name in names


def _uses_mysql_budget_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, budget=True)


def _uses_mysql_common_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, names={"common.db"})


def _budget_year_from_path(path: Path | str) -> int:
    match = re.fullmatch(r"budget_(\d{4})\.db", Path(path).name)
    return int(match.group(1)) if match else int(settings.budget_year)


def _row_value(row: object, key: str, index: int) -> object:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        return row[index]  # type: ignore[index]


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    )


async def _load_version_months(
    budget_path: Path,
    version_ids: set[int],
) -> dict[int, int]:
    if not version_ids:
        return {}
    sorted_ids = tuple(sorted(version_ids))
    if _uses_mysql_budget_path(budget_path):
        placeholders = ",".join(["%s"] * len(sorted_ids))
        rows = await get_pool().fetch_all(
            f"""
            SELECT version_id, current_month
            FROM version
            WHERE budget_year = %s
              AND version_id IN ({placeholders})
            """,
            (_budget_year_from_path(budget_path), *sorted_ids),
        )
    else:
        placeholders = ",".join(["?"] * len(sorted_ids))
        with sqlite3.connect(budget_path) as db:
            ensure_budget_version_schema_sync(db)
            rows = db.execute(
                f"SELECT version_id, current_month FROM version WHERE version_id IN ({placeholders})",
                sorted_ids,
            ).fetchall()
    return {
        int(_row_value(row, "version_id", 0)): int(_row_value(row, "current_month", 1))
        for row in rows
    }


async def _load_period_months(
    common_path: Path,
    period_ids: set[int],
) -> dict[int, int]:
    if not period_ids:
        return {}
    sorted_ids = tuple(sorted(period_ids))
    if _uses_mysql_common_path(common_path):
        placeholders = ",".join(["%s"] * len(sorted_ids))
        rows = await get_pool().fetch_all(
            f"SELECT period_id, month FROM period WHERE period_id IN ({placeholders})",
            sorted_ids,
        )
    else:
        placeholders = ",".join(["?"] * len(sorted_ids))
        with sqlite3.connect(common_path) as db:
            rows = db.execute(
                f"SELECT period_id, month FROM period WHERE period_id IN ({placeholders})",
                sorted_ids,
            ).fetchall()

    result: dict[int, int] = {}
    for row in rows:
        period_id = _row_value(row, "period_id", 0)
        raw = str(_row_value(row, "month", 1) or "").strip().upper()
        if raw.startswith("M"):
            raw = raw[1:]
        try:
            result[int(period_id)] = int(raw)
        except ValueError:
            result[int(period_id)] = 0
    return result


async def _load_formula_runtime_refs(
    common_path: Path,
    data_acct_codes: set[str],
) -> dict[tuple[str, int], bool]:
    if not data_acct_codes:
        return {}
    sorted_codes = tuple(sorted(data_acct_codes))
    if _uses_mysql_common_path(common_path):
        table_rows = await get_pool().fetch_all(
            """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ('data_account_metric_binding', 'data_account_metric_node')
            """
        )
        tables = {str(_row_value(row, "TABLE_NAME", 0)) for row in table_rows}
        if {"data_account_metric_binding", "data_account_metric_node"}.issubset(tables):
            join_sql = """
            LEFT JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
            LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
            """
            node_type_expr = "COALESCE(n.node_type, 'METRIC')"
        else:
            join_sql = ""
            node_type_expr = "'METRIC'"
        placeholders = ",".join(["%s"] * len(sorted_codes))
        rows = await get_pool().fetch_all(
            f"""
            SELECT d.data_acct_code, d.budget_formula, d.actual_formula,
                   COALESCE(d.allow_manual_entry, 1) AS allow_manual_entry,
                   {node_type_expr} AS node_type
            FROM data_account d
            {join_sql}
            WHERE d.data_acct_code IN ({placeholders})
            """,
            sorted_codes,
        )
    else:
        placeholders = ",".join(["?"] * len(sorted_codes))
        with sqlite3.connect(common_path) as db:
            cur_tables = db.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name IN ('data_account_metric_binding', 'data_account_metric_node')
                """
            )
            tables = {str(r[0]) for r in cur_tables.fetchall()}
            if {"data_account_metric_binding", "data_account_metric_node"}.issubset(tables):
                join_sql = """
                LEFT JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
                LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
                """
                node_type_expr = "COALESCE(n.node_type, 'METRIC')"
            else:
                join_sql = ""
                node_type_expr = "'METRIC'"
            rows = db.execute(
                f"""
                SELECT d.data_acct_code, d.budget_formula, d.actual_formula,
                       COALESCE(d.allow_manual_entry, 1),
                       {node_type_expr}
                FROM data_account d
                {join_sql}
                WHERE d.data_acct_code IN ({placeholders})
                """,
                sorted_codes,
            ).fetchall()
    result: dict[tuple[str, int], bool] = {}
    for row in rows:
        code = _row_value(row, "data_acct_code", 0)
        budget_formula = _row_value(row, "budget_formula", 1)
        actual_formula = _row_value(row, "actual_formula", 2)
        allow_manual_entry = _row_value(row, "allow_manual_entry", 3)
        node_type = _row_value(row, "node_type", 4)
        normalized = str(code or "").strip().upper()
        can_manual_entry = int(1 if allow_manual_entry is None else allow_manual_entry) == 1
        is_parent_metric_node = str(node_type or "METRIC").strip().upper() != "METRIC"
        result[(normalized, 0)] = (not can_manual_entry) or (
            bool(str(budget_formula or "").strip()) and not can_manual_entry
        ) or is_parent_metric_node
        result[(normalized, 1)] = (not can_manual_entry) or (
            bool(str(actual_formula or "").strip()) and not can_manual_entry
        ) or is_parent_metric_node
    return result


async def _budget_data_table_exists(db: object) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'budget_data'"
    )
    return await cur.fetchone() is not None


def _message(prefix: str | None, detail: str) -> str:
    return f"{prefix}: {detail}" if prefix else detail


async def delete_budget_data_for_runtime_ref(
    *,
    budget_paths: list[Path],
    data_acct_code: str,
) -> BudgetDataDeleteResult:
    result = BudgetDataDeleteResult()
    normalized_code = str(data_acct_code or "").strip().upper()
    if not normalized_code:
        return result

    for budget_path in budget_paths:
        if _uses_mysql_budget_path(budget_path):
            deleted = await get_pool().execute(
                """
                DELETE FROM budget_data
                WHERE budget_year = %s
                  AND data_acct_code = %s
                """,
                (_budget_year_from_path(budget_path), normalized_code),
            )
            if deleted:
                result.deleted_rows += deleted
                result.deleted_by_budget_file[str(budget_path)] = deleted
            continue
        if not budget_path.exists():
            continue
        with sqlite3.connect(budget_path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            if not _sqlite_table_exists(db, "budget_data"):
                continue
            cur = db.execute(
                "DELETE FROM budget_data WHERE data_acct_code = ?",
                (normalized_code,),
            )
            deleted = max(0, int(cur.rowcount or 0))
            if deleted:
                result.deleted_rows += deleted
                result.deleted_by_budget_file[str(budget_path)] = deleted
            db.commit()
    return result


async def delete_budget_data_for_version(
    db: object,
    *,
    version_id: int,
) -> int:
    if not await _budget_data_table_exists(db):
        return 0
    cur = await db.execute(
        "DELETE FROM budget_data WHERE version_id = ?",
        (int(version_id),),
    )
    return max(0, int(cur.rowcount or 0))


async def _delete_budget_data_for_period_ids(
    db: object,
    *,
    version_id: int,
    budget_actual: int,
    period_ids: list[int],
) -> int:
    if not period_ids:
        return 0
    placeholders = ",".join(["?"] * len(period_ids))
    cur = await db.execute(
        f"""
        DELETE FROM budget_data
        WHERE version_id = ?
          AND budget_actual = ?
          AND period_id IN ({placeholders})
        """,
        (int(version_id), int(budget_actual), *period_ids),
    )
    return max(0, int(cur.rowcount or 0))


async def purge_disallowed_budget_data_for_version(
    db: object,
    version_id: int,
    current_month: int,
    period_month_map: dict[int, int],
) -> int:
    if not period_month_map or not await _budget_data_table_exists(db):
        return 0

    deleted = 0
    current_month = max(1, min(13, int(current_month)))
    if current_month == 13:
        period_ids = [pid for pid, month in period_month_map.items() if 1 <= month <= 12]
        return await _delete_budget_data_for_period_ids(
            db,
            version_id=version_id,
            budget_actual=0,
            period_ids=period_ids,
        )
    if current_month == 1:
        period_ids = [pid for pid, month in period_month_map.items() if 1 <= month <= 12]
        return await _delete_budget_data_for_period_ids(
            db,
            version_id=version_id,
            budget_actual=1,
            period_ids=period_ids,
        )

    budget_period_ids = [
        pid for pid, month in period_month_map.items() if 1 <= month < current_month
    ]
    actual_period_ids = [
        pid for pid, month in period_month_map.items() if current_month <= month <= 12
    ]
    deleted += await _delete_budget_data_for_period_ids(
        db,
        version_id=version_id,
        budget_actual=0,
        period_ids=budget_period_ids,
    )
    deleted += await _delete_budget_data_for_period_ids(
        db,
        version_id=version_id,
        budget_actual=1,
        period_ids=actual_period_ids,
    )
    return deleted


async def delete_rollup_budget_data_rows(
    *,
    budget_path: Path,
    version_id: int,
    data_acct_codes: list[str],
    product_codes: list[str],
    budget_actuals: list[int],
) -> int:
    normalized_codes = [str(code or "").strip().upper() for code in data_acct_codes if str(code or "").strip()]
    normalized_products = [
        str(code or "").strip().upper() for code in product_codes if str(code or "").strip()
    ]
    normalized_actuals: list[int] = []
    for value in budget_actuals:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized in (0, 1):
            normalized_actuals.append(normalized)
    if not normalized_codes or not normalized_products or not normalized_actuals:
        return 0

    if _uses_mysql_budget_path(budget_path):
        code_placeholders = ",".join("%s" for _ in normalized_codes)
        product_placeholders = ",".join("%s" for _ in normalized_products)
        actual_placeholders = ",".join("%s" for _ in normalized_actuals)
        return await get_pool().execute(
            f"""
            DELETE FROM budget_data
            WHERE budget_year = %s
              AND version_id = %s
              AND data_acct_code IN ({code_placeholders})
              AND product_code IN ({product_placeholders})
              AND budget_actual IN ({actual_placeholders})
              AND value_source = 'rollup'
            """,
            (
                _budget_year_from_path(budget_path),
                int(version_id),
                *normalized_codes,
                *normalized_products,
                *normalized_actuals,
            ),
        )
    code_placeholders = ",".join("?" for _ in normalized_codes)
    product_placeholders = ",".join("?" for _ in normalized_products)
    actual_placeholders = ",".join("?" for _ in normalized_actuals)
    with sqlite3.connect(budget_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        if not _sqlite_table_exists(db, "budget_data"):
            return 0
        cur = db.execute(
            f"""
            DELETE FROM budget_data
            WHERE version_id = ?
              AND data_acct_code IN ({code_placeholders})
              AND product_code IN ({product_placeholders})
              AND budget_actual IN ({actual_placeholders})
              AND value_source = 'rollup'
            """,
            (
                int(version_id),
                *normalized_codes,
                *normalized_products,
                *normalized_actuals,
            ),
        )
        deleted = max(0, int(cur.rowcount or 0))
        db.commit()
    return deleted


async def write_budget_data_items(
    *,
    budget_path: Path,
    common_path: Path,
    items: list[BudgetDataWriteItem],
    policy: BudgetDataWritePolicy,
) -> BudgetDataWriteResult:
    result = BudgetDataWriteResult()
    if not items:
        return result

    normalized_items = [
        BudgetDataWriteItem(
            data_acct_code=item.data_acct_code.strip().upper(),
            product_code=item.product_code.strip().upper(),
            period_id=int(item.period_id),
            budget_actual=int(item.budget_actual),
            version_id=int(item.version_id),
            value=float(item.value),
            source_ref=item.source_ref,
        )
        for item in items
    ]

    version_months = await _load_version_months(
        budget_path,
        {item.version_id for item in normalized_items},
    )
    period_months = await _load_period_months(
        common_path,
        {item.period_id for item in normalized_items},
    )
    formula_runtime_refs = (
        {}
        if policy.allow_formula_runtime_refs
        else await _load_formula_runtime_refs(
            common_path,
            {item.data_acct_code for item in normalized_items},
        )
    )

    accepted: list[BudgetDataWriteItem] = []
    for item in normalized_items:
        if item.budget_actual not in (0, 1):
            result.errors.append(_message(item.source_ref, "budget_actual 必须为 0（预算）或 1（实际）"))
            continue
        current_month = version_months.get(item.version_id)
        if current_month is None:
            result.errors.append(_message(item.source_ref, f"版本 {item.version_id} 不存在"))
            continue
        month = period_months.get(item.period_id, 0)
        if not 1 <= month <= 12:
            result.errors.append(_message(item.source_ref, f"期间 {item.period_id} 月份无效"))
            continue
        expected_product = product_code_from_runtime_metric_ref(item.data_acct_code) or ""
        if expected_product and expected_product != item.product_code:
            msg = f"机构及产品指标编码 {item.data_acct_code} 只能写入机构及产品 {expected_product}，不能写入 {item.product_code}"
            if policy.invalid_mode == "skip":
                result.warnings.append(_message(item.source_ref, msg))
                result.skipped_cells += 1
                continue
            result.errors.append(_message(item.source_ref, msg))
            continue
        if policy.enforce_month_window and not budget_actual_allowed_for_month(
            item.budget_actual, month, current_month
        ):
            kind = "预算值" if item.budget_actual == 0 else "实际值"
            msg = f"当前版本月份窗口限制：{kind}不允许写入 {month} 月（current_month={current_month}）"
            if policy.invalid_mode == "skip":
                result.warnings.append(_message(item.source_ref, msg))
                result.skipped_cells += 1
                continue
            result.errors.append(_message(item.source_ref, msg))
            continue
        if formula_runtime_refs.get((item.data_acct_code, item.budget_actual), False):
            msg = f"机构及产品指标编码 {item.data_acct_code} 的手工补录开关已关闭，不允许手工录入"
            if policy.invalid_mode == "skip":
                result.warnings.append(_message(item.source_ref, msg))
                result.skipped_cells += 1
                continue
            result.errors.append(_message(item.source_ref, msg))
            continue
        accepted.append(item)

    if result.errors and policy.invalid_mode == "error":
        raise BudgetDataWriteError(result.errors)

    if not accepted:
        return result

    if _uses_mysql_budget_path(budget_path):
        budget_year = _budget_year_from_path(budget_path)
        if policy.value_kind in {"formula", "rollup"}:
            source = "rollup" if policy.value_kind == "rollup" else "formula"
            await get_pool().execute_many(
                """
                INSERT INTO budget_data (
                  budget_year, data_acct_code, product_code, period_id, budget_actual, version_id,
                  value, formula_value, manual_value, value_source, need_calc,
                  create_time, update_time
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE
                  formula_value = VALUES(formula_value),
                  value = CASE
                    WHEN VALUES(value_source) = 'rollup' THEN VALUES(formula_value)
                    WHEN budget_data.manual_value IS NOT NULL THEN budget_data.manual_value
                    ELSE VALUES(formula_value)
                  END,
                  value_source = CASE
                    WHEN VALUES(value_source) = 'rollup' THEN 'rollup'
                    WHEN budget_data.manual_value IS NOT NULL THEN 'manual'
                    WHEN VALUES(formula_value) IS NOT NULL THEN 'formula'
                    ELSE 'none'
                  END,
                  need_calc = VALUES(need_calc),
                  update_time = CURRENT_TIMESTAMP
                """,
                [
                    (
                        budget_year,
                        item.data_acct_code,
                        item.product_code,
                        item.period_id,
                        item.budget_actual,
                        item.version_id,
                        item.value,
                        item.value,
                        source,
                        1 if policy.need_calc else 0,
                    )
                    for item in accepted
                ],
            )
        else:
            await get_pool().execute_many(
                """
                INSERT INTO budget_data (
                  budget_year, data_acct_code, product_code, period_id, budget_actual, version_id,
                  value, formula_value, manual_value, value_source, need_calc,
                  create_time, update_time
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, 'manual', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE
                  manual_value = VALUES(manual_value),
                  value = VALUES(manual_value),
                  value_source = 'manual',
                  need_calc = VALUES(need_calc),
                  update_time = CURRENT_TIMESTAMP
                """,
                [
                    (
                        budget_year,
                        item.data_acct_code,
                        item.product_code,
                        item.period_id,
                        item.budget_actual,
                        item.version_id,
                        item.value,
                        item.value,
                        1 if policy.need_calc else 0,
                    )
                    for item in accepted
                ],
            )
    else:
        with sqlite3.connect(budget_path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            if policy.value_kind in {"formula", "rollup"}:
                source = "rollup" if policy.value_kind == "rollup" else "formula"
                db.executemany(
                    """
                    INSERT INTO budget_data (
                      data_acct_code, product_code, period_id, budget_actual, version_id,
                      value, formula_value, manual_value, value_source, need_calc,
                      create_time, update_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(data_acct_code, product_code, period_id, version_id, budget_actual)
                    DO UPDATE SET
                      formula_value = excluded.formula_value,
                      value = CASE
                        WHEN excluded.value_source = 'rollup' THEN excluded.formula_value
                        WHEN budget_data.manual_value IS NOT NULL THEN budget_data.manual_value
                        ELSE excluded.formula_value
                      END,
                      value_source = CASE
                        WHEN excluded.value_source = 'rollup' THEN 'rollup'
                        WHEN budget_data.manual_value IS NOT NULL THEN 'manual'
                        WHEN excluded.formula_value IS NOT NULL THEN 'formula'
                        ELSE 'none'
                      END,
                      need_calc = excluded.need_calc,
                      update_time = CURRENT_TIMESTAMP
                    """,
                    [
                        (
                            item.data_acct_code,
                            item.product_code,
                            item.period_id,
                            item.budget_actual,
                            item.version_id,
                            item.value,
                            item.value,
                            source,
                            1 if policy.need_calc else 0,
                        )
                        for item in accepted
                    ],
                )
            else:
                db.executemany(
                    """
                    INSERT INTO budget_data (
                      data_acct_code, product_code, period_id, budget_actual, version_id,
                      value, formula_value, manual_value, value_source, need_calc,
                      create_time, update_time
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'manual', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(data_acct_code, product_code, period_id, version_id, budget_actual)
                    DO UPDATE SET
                      manual_value = excluded.manual_value,
                      value = excluded.manual_value,
                      value_source = 'manual',
                      need_calc = excluded.need_calc,
                      update_time = CURRENT_TIMESTAMP
                    """,
                    [
                        (
                            item.data_acct_code,
                            item.product_code,
                            item.period_id,
                            item.budget_actual,
                            item.version_id,
                            item.value,
                            item.value,
                            1 if policy.need_calc else 0,
                        )
                        for item in accepted
                    ],
                )
            db.commit()

    result.saved_cells = len(accepted)
    for item in accepted:
        key = (
            item.data_acct_code,
            item.product_code,
            item.period_id,
            item.version_id,
            item.budget_actual,
        )
        result.written_keys.add(key)
        result.written_data_accts.add(item.data_acct_code)
        if item.product_code:
            result.affected_products.add(item.product_code)
    return result
