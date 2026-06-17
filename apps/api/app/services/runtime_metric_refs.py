"""Org-product metric runtime-ref row mapping and usage-count helpers."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import re
from typing import Any, Sequence

import aiosqlite

from app.core.db_paths import common_db_path
from app.schemas import RuntimeMetricRefRow
from app.services.runtime_budget_paths import active_budget_database_files
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte

LOCAL_METRIC_CODE_PATTERN = r"\d{2}(?:\.\d{2})*(?:\.\d{3})?"
PRODUCT_PREFIXED_METRIC_CODE_RE = re.compile(
    rf"^[A-Z][A-Z0-9]*\.{LOCAL_METRIC_CODE_PATTERN}$"
)


def _normalize_metric_code(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def split_compact_metric_local_code(local_code: Any) -> str:
    cleaned = _normalize_metric_code(local_code).replace(".", "")
    if not cleaned or not cleaned.isdigit():
        return ""
    if len(cleaned) % 2 == 0:
        parts = [cleaned[idx : idx + 2] for idx in range(0, len(cleaned), 2)]
    elif len(cleaned) >= 3 and (len(cleaned) - 3) % 2 == 0:
        prefix = cleaned[:-3]
        parts = [prefix[idx : idx + 2] for idx in range(0, len(prefix), 2)] + [cleaned[-3:]]
    else:
        return ""
    return ".".join(parts)


def compact_org_product_metric_code(code: Any) -> str:
    return _normalize_metric_code(code).replace(".", "")


def normalize_org_product_metric_code(entity_code: Any, metric_code: Any) -> str:
    entity = _normalize_metric_code(entity_code)
    code = _normalize_metric_code(metric_code)
    if not code:
        return ""
    if entity and code == entity:
        return entity
    if entity and code.startswith(f"{entity}."):
        return code
    if entity and code.startswith(entity):
        local = code[len(entity) :].lstrip(".")
        if not local:
            return entity
        if "." in local:
            return f"{entity}.{local}"
        dotted_local = split_compact_metric_local_code(local)
        return f"{entity}.{dotted_local}" if dotted_local else code
    if entity and code.isdigit():
        dotted_local = split_compact_metric_local_code(code)
        return f"{entity}.{dotted_local}" if dotted_local else f"{entity}{code}"
    if entity and re.fullmatch(LOCAL_METRIC_CODE_PATTERN, code):
        return f"{entity}.{code}"
    return code


def derive_runtime_ref_from_org_product_metric_code(*, entity_code: Any, metric_code: Any) -> str:
    """Return the runtime ref that mirrors the org-product metric primary code."""
    entity = _normalize_metric_code(entity_code)
    code = normalize_org_product_metric_code(entity, metric_code)
    if not entity or not code:
        return ""
    if PRODUCT_PREFIXED_METRIC_CODE_RE.fullmatch(code) and code.split(".", 1)[0] == entity:
        return code
    if not code.startswith(entity):
        return ""
    local_compact = code[len(entity) :]
    if not local_compact or not local_compact.isdigit():
        return ""
    if len(local_compact) % 2 == 0:
        parts = [local_compact[idx : idx + 2] for idx in range(0, len(local_compact), 2)]
    elif len(local_compact) >= 3 and (len(local_compact) - 3) % 2 == 0:
        prefix = local_compact[:-3]
        parts = [prefix[idx : idx + 2] for idx in range(0, len(prefix), 2)] + [local_compact[-3:]]
    else:
        return ""
    runtime_ref = f"{entity}.{'.'.join(parts)}"
    return runtime_ref if PRODUCT_PREFIXED_METRIC_CODE_RE.fullmatch(runtime_ref) else ""


def _budget_database_files(budget_paths: Sequence[Path | str] | None = None) -> list[Path]:
    if budget_paths is None:
        return active_budget_database_files()
    return [Path(path) for path in budget_paths]


def row_to_runtime_ref(row: tuple[Any, ...]) -> RuntimeMetricRefRow:
    if len(row) != 14:
        raise ValueError("当前机构及产品指标兼容 read model 必须包含 14 个字段")
    return RuntimeMetricRefRow(
        data_acct_code=row[0],
        data_acct_name=row[1],
        metric_node_code=row[2],
        metric_node_name=row[3],
        scope_type=row[4],
        scope_code=row[5],
        budget_formula=row[6],
        actual_formula=row[7],
        need_calc=int(row[8] or 0),
        formula_calc_mode=int(row[9] or 0),
        allow_manual_entry=int(1 if row[10] is None else row[10]),
        value_type=row[11] or "金额",
        remark=row[12],
        product_name=row[13],
        has_budget_data_records=False,
    )


async def fetch_runtime_ref_detail(db: aiosqlite.Connection, code: str) -> RuntimeMetricRefRow | None:
    cur = await db.execute(
        f"""
        {org_product_runtime_products_cte()}
        SELECT d.data_acct_code, d.data_acct_name,
               b.metric_node_code, n.node_name, b.scope_type, b.scope_code,
               d.budget_formula, d.actual_formula, d.need_calc, d.formula_calc_mode, d.allow_manual_entry,
               d.value_type, d.remark,
               p.product_name
        FROM data_account d
        LEFT JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
        LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
        LEFT JOIN org_product_runtime_products p ON b.scope_type = 'PRODUCT' AND p.product_code = b.scope_code
        WHERE d.data_acct_code = ?
        """,
        (code,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    return row_to_runtime_ref(tuple(row))


async def fetch_runtime_ref_list(
    db: aiosqlite.Connection,
    budget_ref_counts: dict[str, int],
) -> list[RuntimeMetricRefRow]:
    cur = await db.execute(
        f"""
        {org_product_runtime_products_cte()}
        SELECT d.data_acct_code, d.data_acct_name,
               b.metric_node_code, n.node_name, b.scope_type, b.scope_code,
               d.budget_formula, d.actual_formula, d.need_calc, d.formula_calc_mode, d.allow_manual_entry,
               d.value_type, d.remark,
               p.product_name
        FROM data_account d
        LEFT JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
        LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
        LEFT JOIN org_product_runtime_products p ON b.scope_type = 'PRODUCT' AND p.product_code = b.scope_code
        ORDER BY d.data_acct_code
        """
    )
    rows = await cur.fetchall()
    cur = await db.execute(
        """
        SELECT data_acct_code, COUNT(*)
        FROM data_account_metric_binding
        GROUP BY data_acct_code
        """
    )
    binding_rows = await cur.fetchall()
    metric_binding_counts = {str(row[0]): int(row[1] or 0) for row in binding_rows if row[0]}
    org_product_ref_counts = await load_org_product_metric_ref_counts(db)

    accounts: list[RuntimeMetricRefRow] = []
    for row in rows:
        account = row_to_runtime_ref(tuple(row))
        budget_ref_count = budget_ref_counts.get(account.data_acct_code, 0)
        metric_binding_ref_count = metric_binding_counts.get(account.data_acct_code, 0)
        org_product_ref_count = org_product_ref_counts.get(account.data_acct_code.upper(), 0)
        account.budget_data_ref_count = budget_ref_count
        account.metric_binding_ref_count = metric_binding_ref_count
        account.org_product_metric_ref_count = org_product_ref_count
        account.has_budget_data_records = budget_ref_count > 0
        accounts.append(account)
    return accounts


async def list_runtime_refs(
    common_db: Path | str | None = None,
    *,
    budget_paths: Sequence[Path | str] | None = None,
) -> list[RuntimeMetricRefRow]:
    path = common_db if common_db is not None else common_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        budget_ref_counts = await load_budget_data_ref_counts(budget_paths=budget_paths)
        return await fetch_runtime_ref_list(db, budget_ref_counts)


async def load_budget_data_ref_counts(
    *,
    budget_paths: Sequence[Path | str] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _budget_database_files(budget_paths):
        if not path.exists():
            continue
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='budget_data'"
            )
            if not await cur.fetchone():
                continue
            cur = await db.execute(
                """
                SELECT data_acct_code, COUNT(*)
                FROM budget_data
                WHERE data_acct_code IS NOT NULL
                GROUP BY data_acct_code
                """
            )
            for row in await cur.fetchall():
                if not row[0]:
                    continue
                code = str(row[0])
                counts[code] = counts.get(code, 0) + int(row[1] or 0)
    return counts


async def count_budget_runtime_ref_refs(
    code: str,
    *,
    budget_paths: Sequence[Path | str] | None = None,
) -> int:
    total = 0
    for path in _budget_database_files(budget_paths):
        if not path.exists():
            continue
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='budget_data'"
            )
            if not await cur.fetchone():
                continue
            cur = await db.execute(
                "SELECT COUNT(*) FROM budget_data WHERE data_acct_code = ?",
                (code,),
            )
            total += int((await cur.fetchone())[0] or 0)
    return total


async def count_runtime_binding_refs(
    code: str,
    *,
    common_db: Path | str | None = None,
) -> int:
    path = common_db if common_db is not None else common_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT COUNT(*) FROM data_account_metric_binding WHERE data_acct_code = ?",
            (code,),
        )
        return int((await cur.fetchone())[0] or 0)


def _is_05_code(raw_code: Any, *, entity_code: str = "") -> bool:
    code = str(raw_code or "").strip().upper().replace(" ", "")
    if not code:
        return False
    if "." in code:
        parts = [part for part in code.split(".") if part]
        return bool(parts) and (parts[0] == "05" or (len(parts) >= 2 and parts[1] == "05"))
    owner = str(entity_code or "").strip().upper()
    if owner and code.startswith(owner):
        remainder = code[len(owner) :]
    elif code.startswith(("AA", "AB")):
        remainder = code[2:]
    else:
        remainder = code[3:] if len(code) >= 3 else ""
    return len(remainder) >= 2 and remainder[:2] == "05"


def _org_product_metric_children(metric: dict[str, Any]) -> list[dict[str, Any]]:
    children = metric.get("children")
    return [item for item in children if isinstance(item, dict)] if isinstance(children, list) else []


async def load_org_product_metric_ref_counts(db: aiosqlite.Connection) -> dict[str, int]:
    refs_by_code = await load_org_product_metric_refs_by_runtime_ref_code(db)
    return {code: len(refs) for code, refs in refs_by_code.items()}


async def load_confirmed_org_product_runtime_ref_codes(db: aiosqlite.Connection) -> set[str]:
    refs_by_code = await load_org_product_metric_refs_by_runtime_ref_code(db)
    return set(refs_by_code)


async def load_org_product_metric_refs_by_runtime_ref_code(db: aiosqlite.Connection) -> dict[str, list[str]]:
    cur = await db.execute(
        """
        SELECT node_code, node_name, product_code, functional_group_code
        FROM data_account_metric_node
        WHERE is_active = 1
          AND runtime_account_enabled = 1
          AND COALESCE(product_code, '') <> ''
          AND COALESCE(functional_group_code, '') <> ''
        """
    )
    refs_by_code: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in await cur.fetchall():
        data_acct_code = str(row[0] or "").strip().upper()
        metric_name = str(row[1] or "").strip()
        entity_code = str(row[2] or "").strip().upper()
        table_name = str(row[3] or "").strip()
        if not data_acct_code or not entity_code or not table_name:
            continue
        source_ref = f"{entity_code}:{table_name}:{data_acct_code}"
        label = f"{source_ref} {metric_name}".strip()
        dedupe_key = (data_acct_code, source_ref)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        refs_by_code.setdefault(data_acct_code, []).append(label)
    return {code: sorted(refs) for code, refs in refs_by_code.items()}


def load_org_product_metric_refs_by_runtime_ref_code_sync(conn: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    cur = conn.execute(
        """
        SELECT node_code, node_name, product_code, functional_group_code
        FROM data_account_metric_node
        WHERE is_active = 1
          AND runtime_account_enabled = 1
          AND COALESCE(product_code, '') <> ''
          AND COALESCE(functional_group_code, '') <> ''
        """
    )
    refs_by_code: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in cur.fetchall():
        data_acct_code = str(row[0] or "").strip().upper()
        metric_name = str(row[1] or "").strip()
        entity_code = str(row[2] or "").strip().upper()
        table_name = str(row[3] or "").strip()
        if not data_acct_code or not entity_code or not table_name:
            continue
        source_ref = f"{entity_code}:{table_name}:{data_acct_code}"
        label = f"{source_ref} {metric_name}".strip()
        dedupe_key = (data_acct_code, source_ref)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        refs_by_code.setdefault(data_acct_code, []).append(label)
    return {code: tuple(sorted(refs)) for code, refs in refs_by_code.items()}


def load_confirmed_org_product_runtime_ref_codes_sync(conn: sqlite3.Connection) -> set[str]:
    refs_by_code = load_org_product_metric_refs_by_runtime_ref_code_sync(conn)
    return set(refs_by_code)


async def count_org_product_metric_refs(
    code: str,
    *,
    common_db: Path | str | None = None,
) -> int:
    path = common_db if common_db is not None else common_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        counts = await load_org_product_metric_ref_counts(db)
    return counts.get(str(code or "").strip().upper(), 0)


async def enrich_account_usage_flags(
    account: RuntimeMetricRefRow,
    *,
    common_db: Path | str | None = None,
    budget_paths: Sequence[Path | str] | None = None,
) -> RuntimeMetricRefRow:
    budget_ref_count = await count_budget_runtime_ref_refs(
        account.data_acct_code,
        budget_paths=budget_paths,
    )
    metric_binding_ref_count = await count_runtime_binding_refs(
        account.data_acct_code,
        common_db=common_db,
    )
    org_product_ref_count = await count_org_product_metric_refs(
        account.data_acct_code,
        common_db=common_db,
    )
    account.budget_data_ref_count = budget_ref_count
    account.metric_binding_ref_count = metric_binding_ref_count
    account.org_product_metric_ref_count = org_product_ref_count
    account.has_budget_data_records = budget_ref_count > 0
    return account


async def get_runtime_ref_row(
    db: aiosqlite.Connection, code: str
) -> dict[str, Any] | None:
    cur = await db.execute(
        """
        SELECT d.data_acct_code, d.data_acct_name, b.metric_node_code, n.node_name,
               b.scope_type, b.scope_code, d.budget_formula, d.actual_formula,
               d.need_calc, d.formula_calc_mode, d.allow_manual_entry, d.value_type, d.remark
        FROM data_account d
        LEFT JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
        LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
        WHERE d.data_acct_code = ?
        """,
        (code,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    return {
        "data_acct_code": row[0],
        "data_acct_name": row[1],
        "metric_node_code": row[2],
        "metric_node_name": row[3],
        "scope_type": row[4],
        "scope_code": row[5],
        "budget_formula": row[6],
        "actual_formula": row[7],
        "need_calc": int(row[8] or 0),
        "formula_calc_mode": int(row[9] or 0),
        "allow_manual_entry": int(1 if row[10] is None else row[10]),
        "value_type": row[11],
        "remark": row[12],
    }
