"""Budget-summary source loader for expense budget execution reports."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any

import app.core.aiosqlite_compat as aiosqlite
from app.db_bootstrap.budget_version import ensure_budget_version_schema
from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_actual_routing import route_actual_subject_by_caliber
from app.services.expense_budget_execution_caliber_catalog import (
    load_budget_caliber_catalog_map,
    load_catalog_subject_names,
    resolve_caliber_catalog_subject,
)
from app.services.expense_budget_execution_framework import (
    FrameworkContext,
    canonical_owner_name,
    canonical_subject,
    default_entity_name,
    default_group_name,
    text,
)


class BudgetSourceError(ValueError):
    """Raised when budget-summary source data cannot be loaded."""


def extract_runtime_metric_ref_name(data_code_name: str) -> str:
    raw_text = text(data_code_name)
    if not raw_text:
        return ""
    match = re.match(r"^[A-Za-z]*\d[\w.]*\s+(.+)$", raw_text)
    if match:
        return text(match.group(1))
    parts = raw_text.split(" ", 1)
    if len(parts) == 2 and re.match(r"^[A-Za-z]*\d[\w.]*$", parts[0]):
        return text(parts[1])
    return raw_text


def extract_product_department(product_code_name: str | None) -> str:
    raw_text = text(product_code_name)
    if not raw_text:
        return ""
    if "-" in raw_text:
        return text(raw_text.split("-", 1)[0])
    return raw_text


def parse_month(value: Any) -> int | None:
    raw_text = text(value)
    if not raw_text:
        return None
    tokens = re.findall(r"\d{1,2}", raw_text)
    for token in reversed(tokens):
        month = int(token)
        if 1 <= month <= 12:
            return month
    try:
        month = int(float(raw_text))
        return month if 1 <= month <= 12 else None
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def new_month_values() -> list[float]:
    return [0.0] * 12


def budget_year_from_db_path(budget_db: Path) -> int | None:
    match = re.search(r"budget_(\d{4})\.db$", budget_db.name)
    if not match:
        return None
    return int(match.group(1))


def _should_use_imported_prior_year_actuals(budget_db: Path) -> bool:
    try:
        return budget_db.parent.resolve() == common_db_path().parent.resolve()
    except OSError:
        return False


async def _table_columns(db: aiosqlite.Connection, table_name: str) -> set[str]:
    cur = await db.execute(f'PRAGMA table_info("{table_name}")')
    return {str(row[1]) for row in await cur.fetchall()}


async def _load_imported_prior_year_actual_by_owner_subject(
    ctx: FrameworkContext,
    *,
    current_month: int | None = None,
    entity_name: str = "",
    group_name: str = "",
    owner_name: str = "",
) -> tuple[dict[tuple[str, str], list[float]], str] | None:
    async with aiosqlite.connect(common_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expense_actual_detail_raw'"
        )
        if not await cur.fetchone():
            return None
        columns = await _table_columns(db, "expense_actual_detail_raw")
        required_columns = {"import_kind", "owner_name_mapped", "budget_subject_mapped", "period_ym", "amount"}
        if not required_columns.issubset(columns):
            return None
        cur = await db.execute(
            """
            SELECT owner_name_mapped, budget_subject_mapped, period_ym, amount
            FROM expense_actual_detail_raw
            WHERE COALESCE(import_kind, '') = 'prior_year_actual'
              AND owner_matched = 1
              AND subject_matched = 1
            ORDER BY owner_name_mapped, budget_subject_mapped, period_ym
            """
        )
        rows = await cur.fetchall()
    if not rows:
        return None

    selected_entity = text(entity_name)
    selected_group = text(group_name)
    selected_owner = text(owner_name)
    monthly_map: dict[tuple[str, str], list[float]] = defaultdict(new_month_values)
    for owner_raw, subject_raw, period_ym, value in rows:
        owner = canonical_owner_name(text(owner_raw), ctx)
        subject = canonical_subject(text(subject_raw), ctx)
        month_idx = parse_month(period_ym)
        if not owner or not subject or month_idx is None:
            continue
        resolved_entity = ctx.owner_to_entity.get(owner, default_entity_name())
        resolved_group = ctx.owner_to_group.get(owner, default_group_name(resolved_entity))
        if selected_entity and resolved_entity != selected_entity:
            continue
        if selected_group and resolved_group != selected_group:
            continue
        if selected_owner and owner != selected_owner:
            continue
        if current_month is not None and month_idx > current_month:
            continue
        monthly_map[(owner, subject)][month_idx - 1] += to_float(value)
    return (
        {
            key: [round(amount, 2) for amount in values]
            for key, values in monthly_map.items()
        },
        "费用执行明细导入-上年实际导入",
    )


async def _latest_expense_actual_batch(
    db: aiosqlite.Connection,
    import_kind: str,
) -> tuple[int, str, str] | None:
    cur = await db.execute(
        """
        SELECT id, file_name, created_at
        FROM expense_actual_import_batch
        WHERE COALESCE(import_kind, '') = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (import_kind,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    return int(row[0]), text(row[1]), text(row[2])


def _expense_import_source_label(
    latest_batch: tuple[int, str, str] | None,
    *,
    fallback: str,
) -> str:
    if not latest_batch:
        return fallback
    _batch_id, file_name, created_at = latest_batch
    return f"费用明细导入（来源 {file_name or '-'}，导入时间 {created_at or '-'}）"


async def load_imported_caliber_monthly_totals(
    import_kind: str,
) -> tuple[dict[str, list[float]], str]:
    monthly_totals: dict[str, list[float]] = defaultdict(new_month_values)
    async with aiosqlite.connect(common_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expense_actual_detail_raw'"
        )
        if not await cur.fetchone():
            return {}, "费用明细导入（尚未初始化）"
        columns = await _table_columns(db, "expense_actual_detail_raw")
        required_columns = {"import_kind", "budget_release_caliber_mapped", "period_ym", "amount"}
        if not required_columns.issubset(columns):
            return {}, "费用明细导入（缺少预算发布口径字段）"
        latest_batch = await _latest_expense_actual_batch(db, import_kind)
        cur = await db.execute(
            """
            SELECT budget_release_caliber_mapped, period_ym, amount
            FROM expense_actual_detail_raw
            WHERE COALESCE(import_kind, '') = ?
              AND TRIM(COALESCE(budget_release_caliber_mapped, '')) <> ''
            ORDER BY budget_release_caliber_mapped, period_ym
            """,
            (import_kind,),
        )
        rows = await cur.fetchall()
        catalog_names = await load_catalog_subject_names(db)
        caliber_catalog_map = await load_budget_caliber_catalog_map(db, catalog_names=catalog_names)
    for caliber, period_ym, amount in rows:
        caliber_name = resolve_caliber_catalog_subject(
            text(caliber),
            catalog_names=catalog_names,
            caliber_catalog_map=caliber_catalog_map,
        )
        month_idx = parse_month(period_ym)
        if not caliber_name or month_idx is None:
            continue
        monthly_totals[caliber_name][month_idx - 1] += to_float(amount)
    return (
        {
            key: [round(amount, 2) for amount in values]
            for key, values in monthly_totals.items()
        },
        _expense_import_source_label(latest_batch, fallback="费用明细导入"),
    )


async def load_imported_owner_caliber_monthly_totals(
    ctx: FrameworkContext,
    import_kind: str,
) -> tuple[dict[tuple[str, str], list[float]], str]:
    monthly_totals: dict[tuple[str, str], list[float]] = defaultdict(new_month_values)
    async with aiosqlite.connect(common_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expense_actual_detail_raw'"
        )
        if not await cur.fetchone():
            return {}, "费用明细导入（尚未初始化）"
        columns = await _table_columns(db, "expense_actual_detail_raw")
        required_columns = {
            "import_kind",
            "owner_name_mapped",
            "budget_release_caliber_mapped",
            "period_ym",
            "amount",
        }
        if not required_columns.issubset(columns):
            return {}, "费用明细导入（缺少预算发布口径字段）"
        latest_batch = await _latest_expense_actual_batch(db, import_kind)
        match_filter = "AND owner_matched = 1" if "owner_matched" in columns else ""
        cur = await db.execute(
            f"""
            SELECT owner_name_mapped, budget_release_caliber_mapped, period_ym, amount
            FROM expense_actual_detail_raw
            WHERE COALESCE(import_kind, '') = ?
              AND TRIM(COALESCE(owner_name_mapped, '')) <> ''
              AND TRIM(COALESCE(budget_release_caliber_mapped, '')) <> ''
              {match_filter}
            ORDER BY owner_name_mapped, budget_release_caliber_mapped, period_ym
            """,
            (import_kind,),
        )
        rows = await cur.fetchall()
        catalog_names = await load_catalog_subject_names(db)
        caliber_catalog_map = await load_budget_caliber_catalog_map(db, catalog_names=catalog_names)
    for owner_name, caliber, period_ym, amount in rows:
        owner = canonical_owner_name(text(owner_name), ctx)
        subject = resolve_caliber_catalog_subject(
            text(caliber),
            catalog_names=catalog_names,
            caliber_catalog_map=caliber_catalog_map,
        )
        subject = canonical_subject(subject, ctx)
        subject = route_actual_subject_by_caliber(subject, caliber)
        month_idx = parse_month(period_ym)
        if not owner or not subject or month_idx is None:
            continue
        monthly_totals[(owner, subject)][month_idx - 1] += to_float(amount)
    return (
        {
            key: [round(amount, 2) for amount in values]
            for key, values in monthly_totals.items()
        },
        _expense_import_source_label(latest_batch, fallback="费用明细导入"),
    )


def _resolve_product_scope(
    product_code_name: str | None,
    ctx: FrameworkContext,
) -> tuple[str, str, str]:
    product_department = extract_product_department(product_code_name)
    owner_name = canonical_owner_name(product_department or "未映射产品部门", ctx)
    group_name = ctx.owner_to_group.get(
        owner_name,
        default_group_name(ctx.owner_to_entity.get(owner_name, default_entity_name())),
    )
    entity_name = ctx.owner_to_entity.get(
        owner_name,
        ctx.group_to_entity.get(group_name, default_entity_name()),
    )
    return entity_name, group_name, owner_name


def _aggregate_budget_maps_from_owner(
    ctx: FrameworkContext,
    budget_by_owner: dict[tuple[str, str], float],
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    budget_by_entity: dict[tuple[str, str], float] = defaultdict(float)
    budget_by_group: dict[tuple[str, str], float] = defaultdict(float)
    for (owner_name, budget_subject), amount in budget_by_owner.items():
        entity_name = ctx.owner_to_entity.get(owner_name, default_entity_name())
        group_name = ctx.owner_to_group.get(owner_name, default_group_name(entity_name))
        numeric = round(float(amount or 0.0), 2)
        budget_by_entity[(entity_name, budget_subject)] += numeric
        budget_by_group[(group_name, budget_subject)] += numeric
    return (
        {key: round(value, 2) for key, value in budget_by_entity.items()},
        {key: round(value, 2) for key, value in budget_by_group.items()},
    )


async def load_budget_rows(
    ctx: FrameworkContext,
    budget_db: Path,
    version_id: int,
) -> tuple[
    str,
    int,
    dict[tuple[str, str], float],
    dict[tuple[str, str], float],
    dict[tuple[str, str], float],
    str | None,
]:
    async with aiosqlite.connect(budget_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_version_schema(db)
        cur = await db.execute(
            "SELECT version_name, current_month FROM version WHERE version_id = ?",
            (version_id,),
        )
        version_row = await cur.fetchone()
        if not version_row:
            raise BudgetSourceError(f"版本 {version_id} 不存在")
        version_name = text(version_row[0]) or f"V{version_id}"
        current_month = int(version_row[1])

    budget_by_owner: dict[tuple[str, str], float] = {}
    budget_source: str | None = None
    budget_year = budget_year_from_db_path(budget_db)
    if budget_year is not None:
        from app.services.expense_budget_entry_store import load_expense_budget_entry_by_owner_subject

        budget_by_owner, budget_source = await load_expense_budget_entry_by_owner_subject(
            ctx,
            budget_year=budget_year,
        )

    budget_by_entity, budget_by_group = _aggregate_budget_maps_from_owner(ctx, budget_by_owner)
    return version_name, current_month, budget_by_entity, budget_by_group, budget_by_owner, budget_source


async def load_previous_year_actual_subject_monthly(
    ctx: FrameworkContext,
    budget_db: Path,
    budget_year: int,
    current_month: int,
    entity_name: str = "",
    group_name: str = "",
    owner_name: str = "",
) -> tuple[dict[str, list[float]], dict[str, float], str]:
    if _should_use_imported_prior_year_actuals(budget_db):
        imported = await _load_imported_prior_year_actual_by_owner_subject(
            ctx,
            current_month=current_month,
            entity_name=entity_name,
            group_name=group_name,
            owner_name=owner_name,
        )
        if imported is not None:
            owner_subject_map, source = imported
            monthly_map: dict[str, list[float]] = defaultdict(new_month_values)
            for (_owner_name, subject), values in owner_subject_map.items():
                target = monthly_map[subject]
                for idx, amount in enumerate(values):
                    target[idx] += float(amount or 0.0)
            totals = {
                subject: round(sum(values[:current_month]), 2)
                for subject, values in monthly_map.items()
            }
            return (
                {subject: [round(amount, 2) for amount in values] for subject, values in monthly_map.items()},
                totals,
                source,
            )

    previous_year_db = budget_db.parent / f"budget_{budget_year - 1}.db"
    if not previous_year_db.exists():
        return {}, {}, f"{previous_year_db}（未找到上一年度库）"

    async with aiosqlite.connect(previous_year_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT version_id, version_name FROM version ORDER BY version_id DESC LIMIT 1")
        version_row = await cur.fetchone()
        if not version_row:
            return {}, {}, f"{previous_year_db}（缺少 version 配置）"
        version_id = int(version_row[0])
        version_name = text(version_row[1]) or f"V{version_id}"
        cur = await db.execute(
            """
            SELECT product_code_name, data_code_name, month, value
            FROM budget_summary
            WHERE version_id = ? AND budget_actual = 1
            """,
            (version_id,),
        )
        rows = await cur.fetchall()

    monthly_map: dict[str, list[float]] = defaultdict(new_month_values)
    selected_entity = text(entity_name)
    selected_group = text(group_name)
    selected_owner = text(owner_name)
    for product_code_name, data_code_name, month_text, value in rows:
        month_idx = parse_month(month_text)
        if month_idx is None:
            continue
        resolved_entity_name, resolved_group_name, resolved_owner_name = _resolve_product_scope(product_code_name, ctx)
        if selected_entity and resolved_entity_name != selected_entity:
            continue
        if selected_group and resolved_group_name != selected_group:
            continue
        if selected_owner and resolved_owner_name != selected_owner:
            continue
        budget_subject = canonical_subject(extract_runtime_metric_ref_name(text(data_code_name)), ctx)
        if not budget_subject:
            continue
        monthly_map[budget_subject][month_idx - 1] += to_float(value)
    totals = {
        subject: round(sum(values[:current_month]), 2)
        for subject, values in monthly_map.items()
    }
    return (
        {subject: [round(amount, 2) for amount in values] for subject, values in monthly_map.items()},
        totals,
        f"{previous_year_db} / {version_name}",
    )


async def load_previous_year_actual_by_owner_subject(
    ctx: FrameworkContext,
    budget_db: Path,
    budget_year: int,
) -> tuple[dict[tuple[str, str], list[float]], str]:
    if _should_use_imported_prior_year_actuals(budget_db):
        imported = await _load_imported_prior_year_actual_by_owner_subject(ctx)
        if imported is not None:
            return imported

    previous_year_db = budget_db.parent / f"budget_{budget_year - 1}.db"
    if not previous_year_db.exists():
        return {}, f"{previous_year_db}（未找到上一年度库）"

    async with aiosqlite.connect(previous_year_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT version_id, version_name FROM version ORDER BY version_id DESC LIMIT 1")
        version_row = await cur.fetchone()
        if not version_row:
            return {}, f"{previous_year_db}（缺少 version 配置）"
        version_id = int(version_row[0])
        version_name = text(version_row[1]) or f"V{version_id}"
        cur = await db.execute(
            """
            SELECT product_code_name, data_code_name, month, value
            FROM budget_summary
            WHERE version_id = ? AND budget_actual = 1
            """,
            (version_id,),
        )
        rows = await cur.fetchall()

    monthly_map: dict[tuple[str, str], list[float]] = defaultdict(new_month_values)
    for product_code_name, data_code_name, month_text, value in rows:
        month_idx = parse_month(month_text)
        if month_idx is None:
            continue
        _entity_name, _group_name, resolved_owner_name = _resolve_product_scope(product_code_name, ctx)
        budget_subject = canonical_subject(extract_runtime_metric_ref_name(text(data_code_name)), ctx)
        if not resolved_owner_name or not budget_subject:
            continue
        monthly_map[(resolved_owner_name, budget_subject)][month_idx - 1] += to_float(value)
    return (
        {
            key: [round(amount, 2) for amount in values]
            for key, values in monthly_map.items()
        },
        f"{previous_year_db} / {version_name}",
    )
