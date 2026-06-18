from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Awaitable, Callable

from app.budget_data_writer import (
    BudgetDataWriteItem,
    FORMULA_RESULT_POLICY,
    write_budget_data_items,
)
from app.runtime_metric_identity import product_code_from_runtime_metric_ref
from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path
from app.formula_refs import extract_formula_codes
from app.services.runtime_metric_rollup_formulas import sync_runtime_metric_rollup_formulas
from app.services.formula_engine import calculate_formula_value, normalize_formula
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte
from app.services.pivot_aggregate import (
    rebuild_budget_pivot_aggregate_for_version as default_rebuild_budget_pivot_aggregate_for_version,
    rebuild_compare_pivot_aggregate as default_rebuild_compare_pivot_aggregate,
)

BUDGET_FACT_REFRESH_ACTION_DESC = "预算事实刷新跑批"
LEGACY_BUDGET_ACTUAL_BATCH_ACTION_DESC = "预算/实际数据跑批"


@dataclass(frozen=True)
class BudgetActualBatchPlanRequest:
    product_code: str
    version_id: int | None
    budget_actuals: list[int]
    run_formula: bool = True
    rebuild_summary: bool = True
    sync_compare: bool = True
    rebuild_aggregate: bool = True


@dataclass
class BudgetActualBatchCommandResult:
    mode: str
    budget_year: int
    version_id: int
    product_code: str
    product_count: int
    data_account_count: int
    formula_task_count: int
    formula_cell_count: int
    manual_override_cell_count: int
    metric_rollup_task_count: int = 0
    metric_rollup_cell_count: int = 0
    metric_rollup_cells_written: int = 0
    metric_rollup_audit_items: list[dict[str, Any]] = field(default_factory=list)
    metric_rollup_audit_truncated: bool = False
    formula_rows_recalculated: int = 0
    summary_rows_rebuilt: int = 0
    budget_aggregate_rows_rebuilt: int = 0
    compare_rows_inserted: int = 0
    compare_aggregate_rows_rebuilt: int = 0
    selected_compare_versions: int = 0
    warnings: list[str] = field(default_factory=list)
    message: str = ""


@dataclass(frozen=True)
class BudgetActualBatchHistoryEntry:
    log_id: int
    create_time: str
    user_id: str | None = None
    version_id: int | None = None
    budget_year: int | None = None
    product_code: str = ""
    product_count: int = 0
    budget_actuals: list[int] = field(default_factory=list)
    run_formula: bool = False
    rebuild_summary: bool = False
    sync_compare: bool = False
    rebuild_aggregate: bool = False
    data_account_count: int = 0
    formula_task_count: int = 0
    formula_cell_count: int = 0
    manual_override_cell_count: int = 0
    metric_rollup_task_count: int = 0
    metric_rollup_cell_count: int = 0
    metric_rollup_cells_written: int = 0
    formula_rows_recalculated: int = 0
    summary_rows_rebuilt: int = 0
    budget_aggregate_rows_rebuilt: int = 0
    compare_rows_inserted: int = 0
    compare_aggregate_rows_rebuilt: int = 0
    selected_compare_versions: int = 0
    affected_rows: int = 0


@dataclass(frozen=True)
class BudgetActualBatchPreviewContext:
    response: BudgetActualBatchCommandResult
    budget_path: Path
    budget_year: int
    product_codes: list[str]


class BudgetActualBatchVersionNotFound(Exception):
    def __init__(self, version_id: int) -> None:
        self.version_id = int(version_id)
        super().__init__(f"版本 {self.version_id} 不存在")


class BudgetActualBatchProductNotFound(Exception):
    def __init__(self, product_code: str) -> None:
        self.product_code = product_code
        super().__init__(f"机构及产品不存在：{self.product_code}")


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    keys = getattr(row, "keys", None)
    if callable(keys) and key in keys():
        return row[key]
    return row[index]


def _uses_mysql_path(path: Path | str) -> bool:
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
    return candidate.name == "common.db" or candidate.name == "compare.db" or (
        candidate.name.startswith("budget_") and candidate.suffix == ".db"
    )


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


async def _fetch_all_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_all(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchall()


async def _fetch_one_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_one(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchone()


def metric_rollup_audit_items(raw_result: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in getattr(raw_result, "audit_items", []) or []:
        if isinstance(item, dict):
            items.append(item)
        elif is_dataclass(item):
            items.append(asdict(item))
    return items


async def ensure_budget_actual_batch_version_exists(budget_path: Path, version_id: int) -> None:
    row = await _fetch_one_for_path(budget_path, "SELECT 1 FROM version WHERE version_id = ?", (int(version_id),))
    if not row:
        raise BudgetActualBatchVersionNotFound(version_id)


async def period_count_for_budget_year(budget_year: int, *, common_path: Path | None = None) -> int:
    row = await _fetch_one_for_path(
        common_path or common_db_path(),
        "SELECT COUNT(*) AS period_count FROM period WHERE year = ?",
        (f"Y{int(budget_year)}",),
    )
    return int(_row_value(row, "period_count", 0) or 0) if row else 0


async def list_budget_actual_batch_history(
    *,
    common_path: Path | None = None,
    limit: int = 30,
) -> list[BudgetActualBatchHistoryEntry]:
    rows = await _fetch_all_for_path(
        common_path or common_db_path(),
        """
        SELECT log_id, user_id, affected_rows, after_data, create_time
        FROM operation_log
        WHERE action_type = 'BATCH_RUN'
          AND action_desc IN (?, ?)
        ORDER BY log_id DESC
        LIMIT ?
        """,
        (BUDGET_FACT_REFRESH_ACTION_DESC, LEGACY_BUDGET_ACTUAL_BATCH_ACTION_DESC, int(limit)),
    )
    result: list[BudgetActualBatchHistoryEntry] = []
    for row in rows:
        log_id = _row_value(row, "log_id", 0)
        user_id = _row_value(row, "user_id", 1)
        affected_rows = _row_value(row, "affected_rows", 2)
        after_data_raw = _row_value(row, "after_data", 3)
        create_time = _row_value(row, "create_time", 4)
        payload: dict[str, Any] = {}
        if after_data_raw:
            try:
                loaded = json.loads(str(after_data_raw))
                if isinstance(loaded, dict):
                    payload = loaded
            except json.JSONDecodeError:
                payload = {}
        result.append(
            BudgetActualBatchHistoryEntry(
                log_id=int(log_id),
                create_time=str(create_time or ""),
                user_id=str(user_id) if user_id is not None else None,
                version_id=(int(payload["version_id"]) if payload.get("version_id") is not None else None),
                budget_year=(int(payload["budget_year"]) if payload.get("budget_year") is not None else None),
                product_code=str(payload.get("product_code") or ""),
                product_count=int(payload.get("product_count") or 0),
                budget_actuals=[int(v) for v in payload.get("budget_actuals", []) if int(v) in (0, 1)],
                run_formula=bool(payload.get("run_formula")),
                rebuild_summary=bool(payload.get("rebuild_summary")),
                sync_compare=bool(payload.get("sync_compare")),
                rebuild_aggregate=bool(payload.get("rebuild_aggregate")),
                data_account_count=int(payload.get("data_account_count") or 0),
                formula_task_count=int(payload.get("formula_task_count") or 0),
                formula_cell_count=int(payload.get("formula_cell_count") or 0),
                manual_override_cell_count=int(payload.get("manual_override_cell_count") or 0),
                metric_rollup_task_count=int(payload.get("metric_rollup_task_count") or 0),
                metric_rollup_cell_count=int(payload.get("metric_rollup_cell_count") or 0),
                metric_rollup_cells_written=int(payload.get("metric_rollup_cells_written") or 0),
                formula_rows_recalculated=int(payload.get("formula_rows_recalculated") or 0),
                summary_rows_rebuilt=int(payload.get("summary_rows_rebuilt") or 0),
                budget_aggregate_rows_rebuilt=int(payload.get("budget_aggregate_rows_rebuilt") or 0),
                compare_rows_inserted=int(payload.get("compare_rows_inserted") or 0),
                compare_aggregate_rows_rebuilt=int(payload.get("compare_aggregate_rows_rebuilt") or 0),
                selected_compare_versions=int(payload.get("selected_compare_versions") or 0),
                affected_rows=int(affected_rows or 0),
            )
        )
    return result


async def load_budget_actual_batch_product_graph(
    *, common_path: Path | None = None
) -> tuple[dict[str, str], dict[str, list[str]]]:
    db_path = common_path or common_db_path()
    rows = await _fetch_all_for_path(
        db_path,
        f"""
        {org_product_runtime_products_cte(dialect='mysql' if _uses_mysql_path(db_path) else 'sqlite')}
        SELECT product_code, product_name, parent_code
        FROM org_product_runtime_products
        WHERE product_code <> '' AND product_name <> ''
        ORDER BY product_code
        """,
    )
    product_name_map: dict[str, str] = {}
    children_by_parent: dict[str, list[str]] = {}
    for row in rows:
        code_raw = _row_value(row, "product_code", 0)
        name_raw = _row_value(row, "product_name", 1)
        parent_raw = _row_value(row, "parent_code", 2)
        code = str(code_raw or "").strip().upper()
        if not code:
            continue
        product_name_map[code] = str(name_raw or code)
        parent = str(parent_raw or "").strip().upper()
        if parent:
            children_by_parent.setdefault(parent, []).append(code)
    for children in children_by_parent.values():
        children.sort()
    return product_name_map, children_by_parent


def collect_budget_actual_batch_leaf_products(
    product_code: str, children_by_parent: dict[str, list[str]]
) -> list[str]:
    children = children_by_parent.get(product_code, [])
    if not children:
        return [product_code]
    result: list[str] = []
    for child in children:
        result.extend(collect_budget_actual_batch_leaf_products(child, children_by_parent))
    return sorted(set(result))


async def resolve_budget_actual_batch_product_selection(
    product_code: str, *, common_path: Path | None = None
) -> list[str]:
    product_name_map, children_by_parent = await load_budget_actual_batch_product_graph(common_path=common_path)
    code = product_code.strip().upper()
    if code in {"ALL", "__ALL__"}:
        return sorted(product for product in product_name_map if product)
    if code not in product_name_map:
        raise BudgetActualBatchProductNotFound(code)
    selected = set(collect_budget_actual_batch_leaf_products(code, children_by_parent))
    selected.add(code)
    return sorted(product for product in selected if product)


async def manual_override_count_for_budget_actual_batch(
    *,
    budget_path: Path,
    version_id: int,
    product_codes: list[str],
    data_acct_codes: list[str],
    budget_actuals: list[int],
) -> int:
    if not product_codes or not data_acct_codes or not budget_actuals:
        return 0
    product_placeholders = ",".join(["?"] * len(product_codes))
    data_placeholders = ",".join(["?"] * len(data_acct_codes))
    actual_placeholders = ",".join(["?"] * len(budget_actuals))
    row = await _fetch_one_for_path(
        budget_path,
        f"""
        SELECT COUNT(*) AS manual_override_count
        FROM budget_data
        WHERE version_id = ?
          AND product_code IN ({product_placeholders})
          AND data_acct_code IN ({data_placeholders})
          AND budget_actual IN ({actual_placeholders})
          AND manual_value IS NOT NULL
        """,
        (int(version_id), *product_codes, *data_acct_codes, *budget_actuals),
    )
    return int(_row_value(row, "manual_override_count", 0) or 0) if row else 0


async def sync_budget_actual_batch_rollup_accounts(*, common_path: Path | None = None) -> None:
    await sync_runtime_metric_rollup_formulas(None)


def order_budget_actual_batch_formula_rows_by_dependency(
    rows: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    formula_by_code = {code: formula for code, formula in rows}
    original_index = {code: idx for idx, (code, _formula) in enumerate(rows)}
    ordered: list[tuple[str, str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(code: str) -> None:
        if code in visited:
            return
        if code in visiting:
            return
        visiting.add(code)
        refs = sorted(
            (
                ref
                for ref in extract_formula_codes(formula_by_code.get(code, ""))
                if ref in formula_by_code and ref != code
            ),
            key=lambda ref: original_index.get(ref, 0),
        )
        for ref in refs:
            visit(ref)
        visiting.remove(code)
        visited.add(code)
        ordered.append((code, formula_by_code[code]))

    for code, _formula in rows:
        visit(code)
    return ordered


async def formula_rows_for_budget_actual_batch_product(
    product_code: str,
    budget_actual: int,
    *,
    common_path: Path | None = None,
) -> list[tuple[str, str]]:
    path = common_path if common_path is not None else common_db_path()
    pc = product_code.strip().upper()
    formula_col = "budget_formula" if int(budget_actual) == 0 else "actual_formula"
    rows = await _fetch_all_for_path(
        path,
        f"""
        SELECT d.data_acct_code, d.{formula_col}, MIN(b.sort_order) AS binding_sort_order
        FROM data_account_metric_binding b
        JOIN data_account d ON d.data_acct_code = b.data_acct_code
        WHERE b.is_active = 1
          AND UPPER(b.scope_code) = ?
          AND COALESCE(TRIM(d.{formula_col}), '') <> ''
        GROUP BY d.data_acct_code, d.{formula_col}
        ORDER BY binding_sort_order, d.data_acct_code
        """,
        (pc,),
    )
    formula_rows = [
        (str(_row_value(row, "data_acct_code", 0)).strip().upper(), formula)
        for row in rows
        if (formula := normalize_formula(_row_value(row, formula_col, 1)))
    ]
    return order_budget_actual_batch_formula_rows_by_dependency(formula_rows)


async def period_ids_for_budget_actual_batch_year(
    budget_year: int,
    *,
    common_path: Path | None = None,
) -> list[int]:
    year_label = f"Y{int(budget_year)}"
    rows = await _fetch_all_for_path(
        common_path or common_db_path(),
        """
        SELECT period_id
        FROM period
        WHERE year = ?
        ORDER BY period_id
        """,
        (year_label,),
    )
    return [int(_row_value(row, "period_id", 0)) for row in rows]


async def recalculate_budget_actual_batch_formula_account(
    *,
    data_acct_code: str,
    formula: str | None,
    version_id: int,
    budget_actual: int,
    product_code: str,
    budget_path: Path,
    budget_year: int,
    common_path: Path | None = None,
) -> int:
    resolved_common_path = common_path or common_db_path()
    period_ids = await period_ids_for_budget_actual_batch_year(
        budget_year,
        common_path=resolved_common_path,
    )
    if not period_ids:
        return 0

    ref_codes = sorted(extract_formula_codes(formula))
    pc_norm = product_code.strip().upper()
    value_map: dict[tuple[str, int], float] = {}
    ref_product_by_code = {
        code: product
        for code in ref_codes
        if (product := product_code_from_runtime_metric_ref(code))
    }
    write_items: list[BudgetDataWriteItem] = []
    if ref_codes and ref_product_by_code:
        period_placeholders = ",".join(["?"] * len(period_ids))
        code_placeholders = ",".join(["?"] * len(ref_codes))
        product_placeholders = ",".join(["?"] * len(set(ref_product_by_code.values())))
        rows = await _fetch_all_for_path(
            budget_path,
            f"""
            SELECT data_acct_code, period_id, value
            FROM budget_data
            WHERE version_id = ?
              AND budget_actual = ?
              AND product_code IN ({product_placeholders})
              AND period_id IN ({period_placeholders})
              AND data_acct_code IN ({code_placeholders})
            """,
            (
                int(version_id),
                int(budget_actual),
                *sorted(set(ref_product_by_code.values())),
                *period_ids,
                *ref_codes,
            ),
        )
        for row in rows:
            value_map[
                (
                    str(_row_value(row, "data_acct_code", 0)),
                    int(_row_value(row, "period_id", 1)),
                )
            ] = float(_row_value(row, "value", 2) or 0.0)

    for period_id in period_ids:
        refs_for_period = {code: value_map.get((code, period_id), 0.0) for code in ref_codes}
        value = calculate_formula_value(formula, refs_for_period)
        write_items.append(
            BudgetDataWriteItem(
                data_acct_code=data_acct_code,
                product_code=pc_norm,
                period_id=period_id,
                budget_actual=int(budget_actual),
                version_id=int(version_id),
                value=value,
                source_ref=f"公式重算 {data_acct_code}/{pc_norm}/period={period_id}",
            )
        )
    write_result = await write_budget_data_items(
        budget_path=budget_path,
        common_path=resolved_common_path,
        items=write_items,
        policy=FORMULA_RESULT_POLICY,
    )
    return write_result.saved_cells


async def recalculate_budget_actual_batch_product_formula_rows(
    *,
    product_code: str,
    version_id: int,
    budget_actual: int,
    budget_path: Path,
    budget_year: int,
    common_path: Path | None = None,
) -> int:
    resolved_common_path = common_path or common_db_path()
    await sync_budget_actual_batch_rollup_accounts(common_path=resolved_common_path)
    formulas = await formula_rows_for_budget_actual_batch_product(
        product_code,
        budget_actual,
        common_path=resolved_common_path,
    )
    if not formulas:
        return 0
    recalculated = 0
    pc = product_code.strip().upper()
    for code, formula in formulas:
        recalculated += await recalculate_budget_actual_batch_formula_account(
            data_acct_code=code,
            formula=formula,
            version_id=version_id,
            budget_actual=budget_actual,
            product_code=pc,
            budget_path=budget_path,
            budget_year=budget_year,
            common_path=resolved_common_path,
        )
    return recalculated


async def preview_budget_actual_batch_context(
    request: BudgetActualBatchPlanRequest,
    *,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    ensure_version_exists: Callable[[Path, int], Awaitable[None]] = ensure_budget_actual_batch_version_exists,
    sync_rollup_accounts: Callable[[], Awaitable[None]] = sync_budget_actual_batch_rollup_accounts,
    resolve_product_selection: Callable[[str], Awaitable[list[str]]] = resolve_budget_actual_batch_product_selection,
    period_count_for_year: Callable[[int], Awaitable[int]] = period_count_for_budget_year,
    formula_rows_for_product: Callable[..., Awaitable[list[tuple[str, str]]]],
    manual_override_count: Callable[..., Awaitable[int]] = manual_override_count_for_budget_actual_batch,
    estimate_metric_tree_rollups: Callable[..., Awaitable[Any]],
) -> BudgetActualBatchPreviewContext:
    editable_budget_path, editable_year, editable_vid = await editable_context_provider()
    version_id = int(request.version_id if request.version_id is not None else editable_vid)
    await ensure_version_exists(editable_budget_path, version_id)
    await sync_rollup_accounts()
    product_codes = await resolve_product_selection(request.product_code)
    if not product_codes:
        raise ValueError("未选中任何可跑批的明细产品")

    formula_task_count = 0
    data_acct_codes: set[str] = set()
    for product_code in product_codes:
        for budget_actual in request.budget_actuals:
            formulas = await formula_rows_for_product(product_code, int(budget_actual))
            formula_task_count += len(formulas)
            data_acct_codes.update(code for code, _formula in formulas)

    period_count = await period_count_for_year(editable_year)
    formula_cell_count = formula_task_count * period_count
    manual_overrides = await manual_override_count(
        budget_path=editable_budget_path,
        version_id=version_id,
        product_codes=product_codes,
        data_acct_codes=sorted(data_acct_codes),
        budget_actuals=request.budget_actuals,
    )
    metric_rollup_estimate = await estimate_metric_tree_rollups(
        budget_year=editable_year,
        product_codes=product_codes,
        budget_actuals=request.budget_actuals,
    )
    warnings: list[str] = []
    if manual_overrides > 0:
        warnings.append(f"存在 {manual_overrides} 个手工补录单元格；跑批会刷新公式值，但最终展示仍以手工值优先。")
    metric_rollup_tasks = int(getattr(metric_rollup_estimate, "rollup_task_count", 0) or 0)
    metric_rollup_cells = int(getattr(metric_rollup_estimate, "rollup_cell_count", 0) or 0)
    if metric_rollup_tasks > 0:
        warnings.append(f"指标树父节点汇总任务 {metric_rollup_tasks} 个，预计写入 {metric_rollup_cells} 个 rollup 单元格。")
    warnings.extend(
        str(item)
        for item in getattr(metric_rollup_estimate, "warnings", []) or []
        if str(item).strip()
    )
    return BudgetActualBatchPreviewContext(
        response=BudgetActualBatchCommandResult(
            mode="preview",
            budget_year=editable_year,
            version_id=version_id,
            product_code=request.product_code,
            product_count=len(product_codes),
            data_account_count=len(data_acct_codes),
            formula_task_count=formula_task_count,
            formula_cell_count=formula_cell_count,
            manual_override_cell_count=manual_overrides,
            metric_rollup_task_count=metric_rollup_tasks,
            metric_rollup_cell_count=metric_rollup_cells,
            metric_rollup_audit_items=metric_rollup_audit_items(metric_rollup_estimate),
            metric_rollup_audit_truncated=bool(getattr(metric_rollup_estimate, "audit_truncated", False)),
            warnings=warnings,
            message="preview ok",
        ),
        budget_path=editable_budget_path,
        budget_year=editable_year,
        product_codes=product_codes,
    )


async def preview_budget_actual_batch_command(
    request: BudgetActualBatchPlanRequest,
    **kwargs: Any,
) -> BudgetActualBatchCommandResult:
    context = await preview_budget_actual_batch_context(request, **kwargs)
    return context.response


async def run_budget_actual_batch_command(
    request: BudgetActualBatchPlanRequest,
    *,
    preview_context_provider: Callable[[BudgetActualBatchPlanRequest], Awaitable[BudgetActualBatchPreviewContext]]
    | None = None,
    recalculate_product_formula_rows: Callable[..., Awaitable[int]],
    rebuild_metric_tree_rollups: Callable[..., Awaitable[Any]],
    rebuild_budget_summary_for_version: Callable[[int, Path | None], Awaitable[int]],
    sync_compare_budget_summary: Callable[..., Awaitable[Any]],
    set_budget_refresh_time: Callable[[Path, str], Awaitable[None]],
    iso_now: Callable[[], str],
    write_operation_log: Callable[..., Awaitable[None]],
    rebuild_budget_pivot_aggregate_for_version: Callable[
        [int, Path | None], Awaitable[int]
    ] = default_rebuild_budget_pivot_aggregate_for_version,
    rebuild_compare_pivot_aggregate: Callable[[], Awaitable[int]] = default_rebuild_compare_pivot_aggregate,
    **preview_kwargs: Any,
) -> BudgetActualBatchCommandResult:
    if preview_context_provider is None:
        preview_context = await preview_budget_actual_batch_context(request, **preview_kwargs)
    else:
        preview_context = await preview_context_provider(request)

    response = preview_context.response
    product_codes = preview_context.product_codes
    budget_path = preview_context.budget_path
    budget_year = preview_context.budget_year

    recalculated = 0
    if request.run_formula:
        for product_code in product_codes:
            for budget_actual in request.budget_actuals:
                recalculated += await recalculate_product_formula_rows(
                    product_code=product_code,
                    version_id=response.version_id,
                    budget_actual=int(budget_actual),
                    budget_path=budget_path,
                    budget_year=budget_year,
                )

    metric_rollup_result = await rebuild_metric_tree_rollups(
        budget_year=budget_year,
        version_id=response.version_id,
        product_codes=product_codes,
        budget_actuals=request.budget_actuals,
        budget_path=budget_path,
    )
    metric_rollup_written = int(getattr(metric_rollup_result, "written_cells", 0) or 0)
    metric_rollup_warnings = [
        str(item)
        for item in getattr(metric_rollup_result, "warnings", []) or []
        if str(item).strip()
    ]

    summary_rows = 0
    budget_aggregate_rows = 0
    if request.rebuild_summary:
        summary_rows = await rebuild_budget_summary_for_version(response.version_id, budget_path)
        await set_budget_refresh_time(budget_path, iso_now())
        if request.rebuild_aggregate:
            budget_aggregate_rows = await rebuild_budget_pivot_aggregate_for_version(
                response.version_id,
                budget_path,
            )

    compare_inserted = 0
    compare_aggregate_rows = 0
    selected_compare_versions = 0
    if request.sync_compare:
        compare_result = await sync_compare_budget_summary(trigger_source="budget_fact_refresh_batch")
        compare_inserted = int(getattr(compare_result, "inserted_rows", 0) or 0)
        selected_compare_versions = int(getattr(compare_result, "selected_versions", 0) or 0)
        if request.rebuild_aggregate:
            compare_aggregate_rows = await rebuild_compare_pivot_aggregate()

    await write_operation_log(
        action_type="BATCH_RUN",
        action_desc=BUDGET_FACT_REFRESH_ACTION_DESC,
        target_table="budget_data,budget_summary,budget_pivot_aggregate,compare_budget_summary,compare_pivot_aggregate",
        affected_rows=(
            recalculated
            + metric_rollup_written
            + summary_rows
            + budget_aggregate_rows
            + compare_inserted
            + compare_aggregate_rows
        ),
        after_data={
            "version_id": response.version_id,
            "budget_year": budget_year,
            "product_code": request.product_code,
            "product_count": len(product_codes),
            "budget_actuals": request.budget_actuals,
            "run_formula": request.run_formula,
            "rebuild_summary": request.rebuild_summary,
            "sync_compare": request.sync_compare,
            "rebuild_aggregate": request.rebuild_aggregate,
            "data_account_count": response.data_account_count,
            "formula_task_count": response.formula_task_count,
            "formula_cell_count": response.formula_cell_count,
            "manual_override_cell_count": response.manual_override_cell_count,
            "metric_rollup_task_count": response.metric_rollup_task_count,
            "metric_rollup_cell_count": response.metric_rollup_cell_count,
            "metric_rollup_cells_written": metric_rollup_written,
            "metric_rollup_audit_truncated": response.metric_rollup_audit_truncated,
            "formula_rows_recalculated": recalculated,
            "summary_rows_rebuilt": summary_rows,
            "budget_aggregate_rows_rebuilt": budget_aggregate_rows,
            "compare_rows_inserted": compare_inserted,
            "compare_aggregate_rows_rebuilt": compare_aggregate_rows,
            "selected_compare_versions": selected_compare_versions,
        },
    )
    metric_rollup_run_items = metric_rollup_audit_items(metric_rollup_result)
    return replace(
        response,
        mode="run",
        warnings=[*response.warnings, *metric_rollup_warnings],
        formula_rows_recalculated=recalculated,
        metric_rollup_cells_written=metric_rollup_written,
        metric_rollup_audit_items=metric_rollup_run_items or response.metric_rollup_audit_items,
        metric_rollup_audit_truncated=bool(
            getattr(metric_rollup_result, "audit_truncated", response.metric_rollup_audit_truncated)
        ),
        summary_rows_rebuilt=summary_rows,
        budget_aggregate_rows_rebuilt=budget_aggregate_rows,
        compare_rows_inserted=compare_inserted,
        compare_aggregate_rows_rebuilt=compare_aggregate_rows,
        selected_compare_versions=selected_compare_versions,
        message="run ok",
    )
