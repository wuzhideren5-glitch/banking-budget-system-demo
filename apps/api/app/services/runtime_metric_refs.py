"""Org-product metric runtime-ref row mapping and usage-count helpers."""
from __future__ import annotations

import json
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from pathlib import Path
import re
import tempfile
from typing import Any, Sequence

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path
from app.schemas import RuntimeMetricRefRow
from app.services.runtime_budget_paths import active_budget_database_files
from app.services.org_product_runtime_catalog import (
    org_product_runtime_products_cte,
    org_product_runtime_products_cte_for_db,
)

LOCAL_METRIC_CODE_PATTERN = r"\d{2}(?:\.\d{2})*(?:\.\d{3})?"
PRODUCT_PREFIXED_METRIC_CODE_RE = re.compile(
    rf"^[A-Z][A-Z0-9]*\.{LOCAL_METRIC_CODE_PATTERN}$"
)


def _normalize_metric_code(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _runtime_ref_tuple(row: Any) -> tuple[Any, ...]:
    return (
        _row_value(row, "data_acct_code", 0),
        _row_value(row, "data_acct_name", 1),
        _row_value(row, "metric_node_code", 2),
        _row_value(row, "node_name", 3),
        _row_value(row, "scope_type", 4),
        _row_value(row, "scope_code", 5),
        _row_value(row, "budget_formula", 6),
        _row_value(row, "actual_formula", 7),
        _row_value(row, "need_calc", 8),
        _row_value(row, "formula_calc_mode", 9),
        _row_value(row, "allow_manual_entry", 10),
        _row_value(row, "value_type", 11),
        _row_value(row, "remark", 12),
        _row_value(row, "product_name", 13),
    )


def _uses_mysql_path(path: Path | str, *, names: set[str] | None = None, budget: bool = False) -> bool:
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
    if budget:
        return re.fullmatch(r"budget_\d{4}\.db", candidate.name) is not None
    return names is not None and candidate.name in names


def _uses_mysql_common_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, names={"common.db"})


def _uses_mysql_budget_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, budget=True)


def _budget_year_from_path(path: Path | str) -> int | None:
    match = re.fullmatch(r"budget_(\d{4})\.db", Path(path).name)
    return int(match.group(1)) if match else None


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


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


def _runtime_ref_from_physical_metric(entity_code: str, metric: dict[str, Any]) -> str:
    metric_code = str(metric.get("code") or "").strip()
    derived = derive_runtime_ref_from_org_product_metric_code(
        entity_code=entity_code,
        metric_code=metric_code,
    )
    explicit = _normalize_metric_code(metric.get("data_acct_code"))
    if (
        explicit
        and PRODUCT_PREFIXED_METRIC_CODE_RE.fullmatch(explicit)
        and explicit.split(".", 1)[0] == _normalize_metric_code(entity_code)
    ):
        return explicit
    return derived


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


async def fetch_runtime_ref_detail(db: Any, code: str) -> RuntimeMetricRefRow | None:
    cur = await db.execute(
        f"""
        {org_product_runtime_products_cte_for_db(db)}
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
    db: Any,
    budget_ref_counts: dict[str, int],
) -> list[RuntimeMetricRefRow]:
    cur = await db.execute(
        f"""
        {org_product_runtime_products_cte_for_db(db)}
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


def _runtime_ref_list_sql(*, dialect: str) -> str:
    return f"""
        {org_product_runtime_products_cte(dialect=dialect)}
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


def _binding_count_sql(*, filtered: bool) -> str:
    where = "WHERE data_acct_code = %s" if filtered else ""
    return f"""
        SELECT data_acct_code, COUNT(*) AS ref_count
        FROM data_account_metric_binding
        {where}
        GROUP BY data_acct_code
        """


async def _load_binding_ref_counts_from_path(common_path: Path | str, code: str | None = None) -> dict[str, int]:
    if _uses_mysql_common_path(common_path):
        rows = await get_pool().fetch_all(
            _binding_count_sql(filtered=bool(code)),
            (_normalize_metric_code(code),) if code else (),
        )
    else:
        sql = _binding_count_sql(filtered=bool(code)).replace("%s", "?")
        with sqlite3.connect(common_path) as conn:
            rows = conn.execute(
                sql,
                (_normalize_metric_code(code),) if code else (),
            ).fetchall()
    return {
        str(_row_value(row, "data_acct_code", 0)): int(_row_value(row, "ref_count", 1) or 0)
        for row in rows
        if _row_value(row, "data_acct_code", 0)
    }


async def _fetch_runtime_ref_list_from_path(
    common_path: Path | str,
    budget_ref_counts: dict[str, int],
) -> list[RuntimeMetricRefRow]:
    if _uses_mysql_common_path(common_path):
        rows = await get_pool().fetch_all(_runtime_ref_list_sql(dialect="mysql"))
    else:
        with sqlite3.connect(common_path) as conn:
            rows = conn.execute(_runtime_ref_list_sql(dialect="sqlite")).fetchall()
    metric_binding_counts = await _load_binding_ref_counts_from_path(common_path)
    org_product_ref_counts = await load_org_product_metric_ref_counts_from_path(common_path)

    accounts: list[RuntimeMetricRefRow] = []
    for row in rows:
        account = row_to_runtime_ref(_runtime_ref_tuple(row))
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
    budget_ref_counts = await load_budget_data_ref_counts(budget_paths=budget_paths)
    return await _fetch_runtime_ref_list_from_path(path, budget_ref_counts)


async def load_budget_data_ref_counts(
    *,
    budget_paths: Sequence[Path | str] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    paths = _budget_database_files(budget_paths)
    mysql_years = sorted({
        year
        for path in paths
        if _uses_mysql_budget_path(path) and (year := _budget_year_from_path(path)) is not None
    })
    if mysql_years:
        placeholders = ",".join("%s" for _ in mysql_years)
        rows = await get_pool().fetch_all(
            f"""
            SELECT data_acct_code, COUNT(*) AS ref_count
            FROM budget_data
            WHERE budget_year IN ({placeholders})
              AND data_acct_code IS NOT NULL
            GROUP BY data_acct_code
            """,
            tuple(mysql_years),
        )
        for row in rows:
            code = str(_row_value(row, "data_acct_code", 0) or "")
            if code:
                counts[code] = counts.get(code, 0) + int(_row_value(row, "ref_count", 1) or 0)

    for path in paths:
        if _uses_mysql_budget_path(path):
            continue
        if not path.exists():
            continue
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            if not _sqlite_table_exists(db, "budget_data"):
                continue
            rows = db.execute(
                """
                SELECT data_acct_code, COUNT(*) AS ref_count
                FROM budget_data
                WHERE data_acct_code IS NOT NULL
                GROUP BY data_acct_code
                """
            ).fetchall()
            for row in rows:
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
    normalized_code = _normalize_metric_code(code)
    paths = _budget_database_files(budget_paths)
    mysql_years = sorted({
        year
        for path in paths
        if _uses_mysql_budget_path(path) and (year := _budget_year_from_path(path)) is not None
    })
    if mysql_years:
        placeholders = ",".join("%s" for _ in mysql_years)
        rows = await get_pool().fetch_all(
            f"""
            SELECT data_acct_code, COUNT(*) AS ref_count
            FROM budget_data
            WHERE budget_year IN ({placeholders})
              AND data_acct_code = %s
            GROUP BY data_acct_code
            """,
            (*mysql_years, normalized_code),
        )
        total += sum(int(_row_value(row, "ref_count", 1) or 0) for row in rows)

    for path in paths:
        if _uses_mysql_budget_path(path):
            continue
        if not path.exists():
            continue
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            if not _sqlite_table_exists(db, "budget_data"):
                continue
            row = db.execute(
                "SELECT COUNT(*) FROM budget_data WHERE data_acct_code = ?",
                (normalized_code,),
            ).fetchone()
            total += int(row[0] or 0) if row else 0
    return total


async def count_runtime_binding_refs(
    code: str,
    *,
    common_db: Path | str | None = None,
) -> int:
    path = common_db if common_db is not None else common_db_path()
    counts = await _load_binding_ref_counts_from_path(path, code)
    return counts.get(_normalize_metric_code(code), 0)


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


async def load_org_product_metric_ref_counts(db: Any) -> dict[str, int]:
    refs_by_code = await load_org_product_metric_refs_by_runtime_ref_code(db)
    return {code: len(refs) for code, refs in refs_by_code.items()}


async def load_confirmed_org_product_runtime_ref_codes(db: Any) -> set[str]:
    refs_by_code = await load_org_product_metric_refs_by_runtime_ref_code(db)
    return set(refs_by_code)


def _org_product_metric_refs_from_rows(rows: list[Any]) -> dict[str, list[str]]:
    refs_by_code: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        data_acct_code = str(_row_value(row, "node_code", 0) or "").strip().upper()
        metric_name = str(_row_value(row, "node_name", 1) or "").strip()
        entity_code = str(_row_value(row, "product_code", 2) or "").strip().upper()
        table_name = str(_row_value(row, "metric_table_name", 3) or "").strip()
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


def _org_product_metric_refs_sql() -> str:
    return """
        SELECT node_code, node_name, product_code, metric_table_name
        FROM data_account_metric_node
        WHERE is_active = 1
          AND runtime_account_enabled = 1
          AND COALESCE(product_code, '') <> ''
          AND COALESCE(metric_table_name, '') <> ''
        """


async def load_org_product_metric_refs_by_runtime_ref_code_from_path(
    common_path: Path | str,
) -> dict[str, list[str]]:
    try:
        if _uses_mysql_common_path(common_path):
            rows = await get_pool().fetch_all(_org_product_metric_refs_sql())
        else:
            with sqlite3.connect(common_path) as conn:
                rows = conn.execute(_org_product_metric_refs_sql()).fetchall()
    except Exception:
        if _uses_mysql_common_path(common_path):
            return {}
        with sqlite3.connect(common_path) as conn:
            return {
                code: list(refs)
                for code, refs in _load_org_product_metric_refs_from_physical_table_sync(conn).items()
            }
    return _org_product_metric_refs_from_rows(list(rows))


async def load_org_product_metric_ref_counts_from_path(common_path: Path | str) -> dict[str, int]:
    refs_by_code = await load_org_product_metric_refs_by_runtime_ref_code_from_path(common_path)
    return {code: len(refs) for code, refs in refs_by_code.items()}


async def load_org_product_metric_refs_by_runtime_ref_code(db: Any) -> dict[str, list[str]]:
    try:
        cur = await db.execute(_org_product_metric_refs_sql())
    except Exception:
        return await _load_org_product_metric_refs_from_physical_table(db)
    return _org_product_metric_refs_from_rows(await cur.fetchall())


async def _load_org_product_metric_refs_from_physical_table(
    db: Any,
) -> dict[str, list[str]]:
    try:
        cur = await db.execute(
            """
            SELECT entity_code, table_name, payload_json
            FROM org_product_metric_table
            """
        )
    except Exception:
        return {}

    refs_by_code: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    stack: list[tuple[str, str, dict[str, Any]]] = []
    for row in await cur.fetchall():
        entity_code = str(_row_value(row, "entity_code", 0) or "").strip().upper()
        table_name = str(_row_value(row, "table_name", 1) or "").strip()
        try:
            payload = json.loads(str(_row_value(row, "payload_json", 2) or "{}"))
        except Exception:
            continue
        metrics = payload.get("metrics")
        if isinstance(metrics, list):
            stack.extend((entity_code, table_name, metric) for metric in metrics if isinstance(metric, dict))

    while stack:
        entity_code, table_name, metric = stack.pop()
        children = metric.get("children")
        if isinstance(children, list):
            stack.extend((entity_code, table_name, child) for child in children if isinstance(child, dict))
        if str(metric.get("mapping_status") or "").strip().upper() == "ORG_PRODUCT_ONLY_OR_CREATE_LATER":
            continue
        metric_code = str(metric.get("code") or "").strip()
        data_acct_code = _runtime_ref_from_physical_metric(entity_code, metric)
        if not data_acct_code:
            continue
        source_ref = f"{entity_code}:{table_name}:{metric_code}"
        metric_name = str(metric.get("name") or "").strip()
        label = f"{source_ref} {metric_name}".strip()
        dedupe_key = (data_acct_code, source_ref)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        refs_by_code.setdefault(data_acct_code, []).append(label)
    return {code: sorted(refs) for code, refs in refs_by_code.items()}


def load_org_product_metric_refs_by_runtime_ref_code_sync(conn: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    try:
        cur = conn.execute(_org_product_metric_refs_sql())
    except Exception:
        return _load_org_product_metric_refs_from_physical_table_sync(conn)
    refs_by_code = _org_product_metric_refs_from_rows(cur.fetchall())
    return {code: tuple(sorted(refs)) for code, refs in refs_by_code.items()}


def _load_org_product_metric_refs_from_physical_table_sync(
    conn: sqlite3.Connection,
) -> dict[str, tuple[str, ...]]:
    try:
        cur = conn.execute(
            """
            SELECT entity_code, table_name, payload_json
            FROM org_product_metric_table
            """
        )
    except Exception:
        return {}

    refs_by_code: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    stack: list[tuple[str, str, dict[str, Any]]] = []
    for row in cur.fetchall():
        entity_code = str(row[0] or "").strip().upper()
        table_name = str(row[1] or "").strip()
        try:
            payload = json.loads(str(row[2] or "{}"))
        except Exception:
            continue
        metrics = payload.get("metrics")
        if isinstance(metrics, list):
            stack.extend((entity_code, table_name, metric) for metric in metrics if isinstance(metric, dict))

    while stack:
        entity_code, table_name, metric = stack.pop()
        children = metric.get("children")
        if isinstance(children, list):
            stack.extend((entity_code, table_name, child) for child in children if isinstance(child, dict))
        if str(metric.get("mapping_status") or "").strip().upper() == "ORG_PRODUCT_ONLY_OR_CREATE_LATER":
            continue
        metric_code = str(metric.get("code") or "").strip()
        data_acct_code = _runtime_ref_from_physical_metric(entity_code, metric)
        if not data_acct_code:
            continue
        source_ref = f"{entity_code}:{table_name}:{metric_code}"
        metric_name = str(metric.get("name") or "").strip()
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
    counts = await load_org_product_metric_ref_counts_from_path(path)
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
    db: Any, code: str
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
