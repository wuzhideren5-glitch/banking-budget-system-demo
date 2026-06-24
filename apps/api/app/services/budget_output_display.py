from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from collections.abc import Iterator, Mapping
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.core.database import get_pool
from app.db_bootstrap.budget_version import ensure_budget_version_schema
from app.db_bootstrap.report_display import ensure_budget_output_display_item_schema
from app.core.db_paths import common_db_path
from app.formula_refs import extract_formula_codes
from app.schemas import (
    BudgetOutputDisplayCandidateDto,
    BudgetOutputDisplayConfigItemDto,
    BudgetOutputDisplayReportResponse,
    BudgetOutputProductBlockDto,
    BudgetOutputProductNodeDto,
    BudgetOutputReportNodeDto,
    BudgetOutputReportRowDto,
    BudgetOutputVersionDto,
    BudgetOutputVersionMetricDto,
)
from app.services.runtime_metric_refs import (
    derive_runtime_ref_from_org_product_metric_code,
    load_confirmed_org_product_runtime_ref_codes,
)
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte_for_db


MONTH_COUNT = 12
CORE_PRODUCT_NAME_HINTS = ("开鑫贷", "企业金融", "金融市场")
BUDGET_BASELINE_HINTS = ("全年预算", "年初预算", "董事会预算", "内部预算")


# ─── 数据结构与辅助函数 ───

def _uses_mysql_path(path: Path | str | None) -> bool:
    if path is None:
        return False
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


def _path_available(path: Path | None) -> bool:
    return bool(path and (_uses_mysql_path(path) or path.exists()))


def _budget_year_from_path(budget_path: Path) -> int | None:
    match = re.fullmatch(r"budget_(\d{4})\.db", budget_path.name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _mysql_sql(sql: str) -> str:
    stripped = sql.strip()
    lowered = stripped.lower()
    if lowered.startswith("pragma foreign_keys"):
        return "SET FOREIGN_KEY_CHECKS = 0" if "off" in lowered else "SET FOREIGN_KEY_CHECKS = 1"
    translated = re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT IGNORE", sql, flags=re.IGNORECASE)
    translated = translated.replace(
        "'org_product_runtime_ref:' || d.data_acct_code",
        "CONCAT('org_product_runtime_ref:', d.data_acct_code)",
    )
    placeholder = "\u0000MYSQL_PARAM\u0000"
    return translated.replace("?", placeholder).replace("%", "%%").replace(placeholder, "%s")


class _Row(Mapping[str, Any]):
    def __init__(self, keys: list[str], values: tuple[Any, ...]):
        self._keys = keys
        self._values = values
        self._by_key = {key: values[idx] for idx, key in enumerate(keys)}

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._by_key[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def get(self, key: str, default: Any = None) -> Any:
        return self._by_key.get(key, default)


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
    row_factory: Any = None

    def __init__(self, path: Path):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    async def __aenter__(self) -> "_SQLiteConnection":
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
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
    row_factory: Any = None

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
        stripped = sql.strip()
        lowered = stripped.lower()
        if lowered.startswith("create table if not exists") or lowered.startswith("create index if not exists"):
            return _CursorAdapter()
        if lowered.startswith("pragma table_info"):
            table_match = re.search(
                r"pragma\s+table_info\s*\(\s*[\"`']?([A-Za-z_][A-Za-z0-9_]*)[\"`']?\s*\)",
                stripped,
                re.IGNORECASE,
            )
            table_name = table_match.group(1) if table_match else ""
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT COLUMN_NAME, DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (table_name,),
                )
                rows = await cur.fetchall()
            return _CursorAdapter([
                _Row(["cid", "name", "type", "notnull", "dflt_value", "pk"], (idx, row[0], row[1], 0, None, 0))
                for idx, row in enumerate(rows)
            ])
        async with self._conn.cursor() as cur:
            await cur.execute(_mysql_sql(sql), tuple(params))
            keys = [item[0] for item in cur.description] if cur.description else []
            rows = [_Row(keys, tuple(row)) for row in await cur.fetchall()] if cur.description else []
            return _CursorAdapter(
                rows,
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

@dataclass
class DisplayVersionSpec:
    dto: BudgetOutputVersionDto
    db_path: Path | None
    version_id: int | None
    mode: str


def _parse_code_name(raw: str | None) -> tuple[str, str]:
    text = str(raw or "").strip()
    if not text:
        return "", ""
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], parts[1]


def _parse_month(raw: str | None) -> int | None:
    text = str(raw or "").strip().upper()
    if text.startswith("M"):
        text = text[1:]
    try:
        month = int(text)
    except ValueError:
        return None
    if 1 <= month <= MONTH_COUNT:
        return month
    return None


def _month_uses_actual(month: int, current_month: int) -> bool:
    if current_month >= 13:
        return True
    if current_month <= 1:
        return False
    return month < current_month


def _empty_metric() -> dict[str, list[float]]:
    return {
        "stitched": [0.0] * MONTH_COUNT,
        "budget": [0.0] * MONTH_COUNT,
        "actual": [0.0] * MONTH_COUNT,
    }


def _metric_to_dto(metric: dict[str, list[float]]) -> BudgetOutputVersionMetricDto:
    annual_value = sum(metric["stitched"])
    budget_value = sum(metric["budget"])
    return BudgetOutputVersionMetricDto(
        annual_value=annual_value,
        budget_value=budget_value,
        variance_to_budget=annual_value - budget_value,
        monthly_values=metric["stitched"],
        monthly_budget_values=metric["budget"],
        monthly_actual_values=metric["actual"],
    )


def _build_product_tree(rows: list[tuple[str, str, str | None, int]]) -> tuple[list[BudgetOutputProductNodeDto], dict[str, BudgetOutputProductNodeDto]]:
    nodes: dict[str, BudgetOutputProductNodeDto] = {
        code: BudgetOutputProductNodeDto(
            product_code=code,
            product_name=name,
            parent_code=parent_code,
            level=int(level or 1),
        )
        for code, name, parent_code, level in rows
    }
    roots: list[BudgetOutputProductNodeDto] = []
    for code, _name, parent_code, _level in rows:
        node = nodes[code]
        if parent_code and parent_code in nodes and parent_code != code:
            nodes[parent_code].children.append(node)
        else:
            roots.append(node)

    def sort_rec(items: list[BudgetOutputProductNodeDto]) -> None:
        items.sort(key=lambda n: n.product_code)
        for item in items:
            sort_rec(item.children)

    sort_rec(roots)
    return roots, nodes



def _metric_display_level(code: str, fallback_level: int) -> int:
    if code == "00":
        return 0
    if "." in code or code.isdigit():
        return code.count(".") + 1
    return max(1, int(fallback_level or 1) - 1)


def _build_metric_report_tree(rows: list[tuple[str, str, str | None, int, str, int]]) -> tuple[list[BudgetOutputReportNodeDto], dict[str, BudgetOutputReportNodeDto]]:
    node_types = {code: node_type for code, _name, _parent, _level, node_type, _sort in rows}
    children_by_parent: dict[str | None, list[str]] = defaultdict(list)
    for code, _name, parent_code, _level, _node_type, _sort in rows:
        if code == "00":
            continue
        parent = None if parent_code == "00" else parent_code
        children_by_parent[parent].append(code)

    nodes: dict[str, BudgetOutputReportNodeDto] = {}
    for code, name, parent_code, level, node_type, _sort in rows:
        if code == "00":
            continue
        parent = None if parent_code == "00" else parent_code
        nodes[code] = BudgetOutputReportNodeDto(
            row_key=code,
            display_name=name,
            parent_row_key=parent,
            level=_metric_display_level(code, int(level or 1)),
            is_summary=node_type != "METRIC" or bool(children_by_parent.get(code)),
            is_minus=name.startswith("减") or name in {"FTP成本", "利息支出", "手续费支出"},
        )

    roots: list[BudgetOutputReportNodeDto] = []
    for code, _name, parent_code, _level, _node_type, _sort in rows:
        if code == "00" or code not in nodes:
            continue
        parent = None if parent_code == "00" else parent_code
        if parent and parent in nodes:
            nodes[parent].children.append(nodes[code])
        else:
            roots.append(nodes[code])

    sort_orders = {code: sort_order for code, _name, _parent, _level, _type, sort_order in rows}

    def sort_rec(items: list[BudgetOutputReportNodeDto]) -> None:
        items.sort(key=lambda n: (sort_orders.get(n.row_key, 0), n.row_key))
        for item in items:
            sort_rec(item.children)

    sort_rec(roots)
    return roots, nodes


# ─── 配置读取与候选 ───

async def _fetch_display_config_items(db: Any, *, active_only: bool = True) -> list[dict[str, Any]]:
    await ensure_budget_output_display_item_schema(db)
    where = "WHERE i.is_active = 1" if active_only else ""
    cur = await db.execute(
        f"""
        {org_product_runtime_products_cte_for_db(db)}
        SELECT i.row_key, i.display_view, i.parent_row_key,
               i.data_acct_code, i.org_product_ref, i.org_product_entity_code,
               i.org_product_table_name, i.org_product_metric_code, i.org_product_metric_name,
               i.row_type, i.display_name, i.value_type, i.level,
               i.sort_order, i.is_active,
               d.data_acct_name, d.value_type AS data_value_type,
               d.budget_formula, d.actual_formula, d.formula_calc_mode, d.allow_manual_entry,
               b.metric_node_code,
               b.scope_type AS source_scope_type, b.scope_code AS source_scope_code,
               n.node_name AS metric_node_name,
               p.product_name AS scope_name
        FROM budget_output_display_item i
        LEFT JOIN data_account d ON d.data_acct_code = i.data_acct_code
        LEFT JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
        LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
        LEFT JOIN org_product_runtime_products p ON p.product_code = b.scope_code
        {where}
        ORDER BY CASE
                   WHEN i.display_view = 'TOTAL' THEN 1
                   WHEN i.display_view = 'OVERVIEW' THEN 2
                   WHEN i.display_view LIKE 'PRODUCT.%' THEN 3
                   ELSE 9
                 END,
                 i.display_view, i.sort_order, i.row_key
        """
    )
    return [dict(row) for row in await cur.fetchall()]


async def _fetch_display_config_candidates(db: Any) -> list[dict[str, Any]]:
    await ensure_budget_output_display_item_schema(db)
    confirmed_codes = sorted(await load_confirmed_org_product_runtime_ref_codes(db))
    placeholders = ",".join("?" for _ in confirmed_codes)
    if not confirmed_codes:
        data_account_rows: list[dict[str, Any]] = []
    else:
        cur = await db.execute(
            f"""
            {org_product_runtime_products_cte_for_db(db)}
            SELECT 'org_product_runtime_ref:' || d.data_acct_code AS candidate_key,
                   d.data_acct_code, d.data_acct_name, d.value_type,
                   b.metric_node_code, b.scope_type, b.scope_code,
                   n.node_name AS metric_node_name,
                   p.product_name AS scope_name,
                   'org_product_runtime_ref' AS source_type,
                   '机构及产品指标编码' AS source_label,
                   NULL AS source_ref,
                   CASE WHEN EXISTS (
                     SELECT 1
                     FROM budget_output_display_item i
                     WHERE i.data_acct_code = d.data_acct_code AND i.is_active = 1
                   ) THEN 1 ELSE 0 END AS selected
            FROM data_account d
            JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
            JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
            LEFT JOIN org_product_runtime_products p ON p.product_code = b.scope_code
            WHERE UPPER(d.data_acct_code) IN ({placeholders})
            ORDER BY n.sort_order, b.sort_order, d.data_acct_code
            """,
            tuple(confirmed_codes),
        )
        data_account_rows = [dict(row) for row in await cur.fetchall()]
    cur = await db.execute(
        """
        SELECT DISTINCT org_product_ref
        FROM budget_output_display_item
        WHERE is_active = 1 AND COALESCE(org_product_ref, '') != ''
        """
    )
    selected_org_product_refs = {str(row["org_product_ref"] or "").strip() for row in await cur.fetchall()}
    return [
        *_org_product_display_candidates(
            data_account_rows,
            await _load_org_product_metric_payloads(db),
            selected_org_product_refs=selected_org_product_refs,
        ),
        *data_account_rows,
    ]


def _is_org_product_fee05_metric_code(entity_code: str, raw_code: Any) -> bool:
    code = str(raw_code or "").strip().upper().replace(" ", "")
    if not code:
        return False
    if "." in code:
        parts = [part for part in code.split(".") if part]
        return len(parts) >= 2 and parts[1] == "05"
    owner = str(entity_code or "").strip().upper()
    if owner and code.startswith(owner):
        remainder = code[len(owner) :]
    elif code.startswith(("AA", "AB")):
        remainder = code[2:]
    else:
        remainder = code[3:] if len(code) >= 3 else ""
    return len(remainder) >= 2 and remainder[:2] == "05"


async def _load_org_product_metric_payloads(db: Any) -> list[dict[str, Any]]:
    try:
        cur = await db.execute(
            """
            SELECT node_code, node_name, product_code, metric_table_name
            FROM data_account_metric_node
            WHERE is_active = 1
              AND runtime_account_enabled = 1
              AND COALESCE(product_code, '') <> ''
              AND COALESCE(metric_table_name, '') <> ''
            ORDER BY product_code, metric_table_name, node_code
            """
        )
    except Exception:
        return await _load_org_product_metric_payloads_from_physical_table(db)
    records = await cur.fetchall()
    rows: list[dict[str, Any]] = []
    for record in records:
        metric_code = str(record["node_code"] or "").strip().upper()
        if not metric_code:
            continue
        rows.append(
            {
                "entity_code": str(record["product_code"] or "").strip().upper(),
                "table_name": str(record["metric_table_name"] or "").strip(),
                "metric_code": metric_code,
                "metric_name": str(record["node_name"] or "").strip(),
                "metric_node_code": metric_code,
                "data_acct_code": metric_code,
            }
        )
    rows.sort(key=lambda row: (str(row.get("entity_code") or ""), str(row.get("data_acct_code") or "")))
    return rows


async def _load_org_product_metric_payloads_from_physical_table(
    db: Any,
) -> list[dict[str, Any]]:
    try:
        cur = await db.execute(
            """
            SELECT entity_code, table_name, payload_json
            FROM org_product_metric_table
            """
        )
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    stack: list[tuple[str, str, dict[str, Any]]] = []
    for record in await cur.fetchall():
        entity_code = str(record["entity_code"] or "").strip().upper()
        table_name = str(record["table_name"] or "").strip()
        try:
            payload = json.loads(str(record["payload_json"] or "{}"))
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
        metric_code = str(metric.get("code") or "").strip().upper()
        data_acct_code = derive_runtime_ref_from_org_product_metric_code(
            entity_code=entity_code,
            metric_code=metric_code,
        )
        if not metric_code or not data_acct_code:
            continue
        rows.append(
            {
                "entity_code": entity_code,
                "table_name": table_name,
                "metric_code": metric_code,
                "metric_name": str(metric.get("name") or "").strip(),
                "metric_node_code": data_acct_code,
                "data_acct_code": data_acct_code,
            }
        )
    return rows


def _org_product_display_candidates(
    data_account_rows: list[dict[str, Any]],
    org_product_rows: list[dict[str, Any]],
    *,
    selected_org_product_refs: set[str],
) -> list[dict[str, Any]]:
    account_by_code = {str(row.get("data_acct_code") or "").upper(): row for row in data_account_rows}
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in org_product_rows:
        data_acct_code = str(row.get("data_acct_code") or "").upper()
        account = account_by_code.get(data_acct_code)
        if not account:
            continue
        source_ref = f"{row['entity_code']}:{row['table_name']}:{row['metric_code']}"
        key = f"org_product:{source_ref}:{data_acct_code}"
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                **account,
                "candidate_key": key,
                "data_acct_name": row.get("metric_name") or account.get("data_acct_name"),
                "metric_node_code": row.get("metric_node_code") or account.get("metric_node_code"),
                "metric_node_name": account.get("metric_node_name") or row.get("metric_name"),
                "source_type": "org_product_metric",
                "source_label": "机构产品指标",
                "source_ref": source_ref,
                "org_product_ref": source_ref,
                "org_product_entity_code": row.get("entity_code"),
                "org_product_table_name": row.get("table_name"),
                "org_product_metric_code": row.get("metric_code"),
                "org_product_metric_name": row.get("metric_name"),
                "selected": source_ref in selected_org_product_refs,
            }
        )
    candidates.sort(key=lambda row: (str(row.get("entity_code") or ""), str(row.get("data_acct_code") or "")))
    return candidates


def _display_config_item_to_dto(row: dict[str, Any]) -> BudgetOutputDisplayConfigItemDto:
    source_scope_code = str(row.get("source_scope_code") or "")
    return BudgetOutputDisplayConfigItemDto(
        row_key=str(row["row_key"]),
        display_view=str(row["display_view"]),
        parent_row_key=row.get("parent_row_key"),
        data_acct_code=row.get("data_acct_code"),
        data_acct_name=row.get("data_acct_name"),
        org_product_ref=row.get("org_product_ref"),
        org_product_entity_code=row.get("org_product_entity_code"),
        org_product_table_name=row.get("org_product_table_name"),
        org_product_metric_code=row.get("org_product_metric_code"),
        org_product_metric_name=row.get("org_product_metric_name"),
        row_type=str(row["row_type"]),
        display_name=str(row["display_name"]),
        metric_node_code=row.get("metric_node_code"),
        metric_node_name=row.get("metric_node_name"),
        source_scope_type=row.get("source_scope_type"),
        source_scope_code=source_scope_code or None,
        scope_name=("全行" if source_scope_code == "CORP" else row.get("scope_name")),
        value_type=row.get("value_type") or row.get("data_value_type"),
        level=int(row["level"] or 1),
        sort_order=int(row["sort_order"] or 0),
        is_active=int(row["is_active"] or 0),
    )


def _display_candidate_to_dto(row: dict[str, Any]) -> BudgetOutputDisplayCandidateDto:
    scope_code = str(row.get("scope_code") or "")
    return BudgetOutputDisplayCandidateDto(
        candidate_key=row.get("candidate_key"),
        data_acct_code=str(row["data_acct_code"]),
        data_acct_name=str(row["data_acct_name"]),
        metric_node_code=str(row["metric_node_code"]),
        metric_node_name=str(row["metric_node_name"]),
        scope_type=str(row["scope_type"]),
        scope_code=scope_code,
        scope_name=("全行" if scope_code == "CORP" else row.get("scope_name")),
        value_type=str(row["value_type"]),
        source_type=str(row.get("source_type") or "org_product_runtime_ref"),
        source_label=str(row.get("source_label") or "机构及产品指标编码"),
        source_ref=row.get("source_ref"),
        org_product_ref=row.get("org_product_ref") or row.get("source_ref"),
        org_product_entity_code=row.get("org_product_entity_code"),
        org_product_table_name=row.get("org_product_table_name"),
        org_product_metric_code=row.get("org_product_metric_code"),
        org_product_metric_name=row.get("org_product_metric_name"),
        selected=bool(row.get("selected")),
    )


def _leaf_product_codes_for_scope(product_code: str, product_nodes: dict[str, BudgetOutputProductNodeDto]) -> list[str]:
    descendants = _collect_descendant_product_codes(product_code, product_nodes)
    return [code for code in descendants if code in product_nodes and not product_nodes[code].children]


def _group_code_for_product(product_code: str, product_nodes: dict[str, BudgetOutputProductNodeDto]) -> str | None:
    node = product_nodes.get(product_code)
    while node:
        if node.parent_code == "CORP" and len(node.product_code) == 1:
            return node.product_code
        if not node.parent_code:
            break
        node = product_nodes.get(node.parent_code)
    if product_code and product_code[0] in {"A", "B", "C", "D", "E", "F"}:
        return product_code[0]
    return None



def _collect_descendant_product_codes(
    product_code: str,
    product_nodes: dict[str, BudgetOutputProductNodeDto],
) -> list[str]:
    node = product_nodes.get(product_code)
    if not node:
        return [product_code]
    codes: list[str] = []

    def walk(item: BudgetOutputProductNodeDto) -> None:
        codes.append(item.product_code)
        for child in item.children:
            walk(child)

    walk(node)
    return codes


def _leaf_product_codes(product_nodes: dict[str, BudgetOutputProductNodeDto]) -> list[str]:
    return sorted(
        [
            code
            for code, node in product_nodes.items()
            if code != "CORP" and not node.children
        ]
    )


def _product_overview_codes(product_tree: list[BudgetOutputProductNodeDto]) -> list[str]:
    result: list[str] = []

    def walk(node: BudgetOutputProductNodeDto) -> None:
        if node.product_code != "CORP":
            result.append(node.product_code)
        for child in node.children:
            walk(child)

    for root in product_tree:
        walk(root)
    return result


def _default_product_codes(product_nodes: dict[str, BudgetOutputProductNodeDto]) -> list[str]:
    selected: list[str] = []
    for hint in CORE_PRODUCT_NAME_HINTS:
        match = next(
            (
                node.product_code
                for node in product_nodes.values()
                if hint in node.product_name and node.product_code not in selected
            ),
            None,
        )
        if match:
            selected.append(match)
    if selected:
        return selected[:4]
    roots = [n for n in product_nodes.values() if not n.parent_code or n.parent_code not in product_nodes]
    roots.sort(key=lambda n: n.product_code)
    return [n.product_code for n in roots[:4]]


# ─── 报表构建与版本管理 ───

async def _fetch_version_info(budget_path: Path, version_id: int) -> tuple[str, int]:
    async with _connect_db(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT version_name, current_month FROM version WHERE version_id = ?",
            (version_id,),
        )
        row = await cur.fetchone()
    if not row:
        return (f"V{version_id}", 1)
    return (str(row[0] or f"V{version_id}"), max(1, min(13, int(row[1] or 1))))


async def _fetch_budget_database_rows() -> list[dict[str, Any]]:
    async with _connect_db(common_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, data_file_name, year
            FROM `databases`
            ORDER BY year DESC, id ASC
            """
        )
        rows = await cur.fetchall()
    return [
        {
            "data_file_id": int(row[0]),
            "data_file_name": str(row[1]),
            "year": int(row[2]),
        }
        for row in rows
    ]


def _choose_database_for_year(
    database_rows: list[dict[str, Any]],
    year: int,
    data_dir: Path,
) -> dict[str, Any] | None:
    candidates = [row for row in database_rows if int(row["year"]) == int(year)]
    if not candidates:
        return None
    exact_name = f"budget_{year}.db"
    exact = next((row for row in candidates if str(row["data_file_name"]) == exact_name), None)
    if exact and _path_available(data_dir / str(exact["data_file_name"])):
        return exact
    existing = next((row for row in candidates if _path_available(data_dir / str(row["data_file_name"]))), None)
    return existing or candidates[0]


async def _fetch_versions_for_budget_file(budget_path: Path) -> list[dict[str, Any]]:
    if not _path_available(budget_path):
        return []
    budget_year = _budget_year_from_path(budget_path)
    async with _connect_db(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_version_schema(db)
        if budget_year is not None and _uses_mysql_path(budget_path):
            cur = await db.execute(
                """
                SELECT version_id, version_name, current_month, version_date_time
                FROM version
                WHERE budget_year = ?
                ORDER BY version_id
                """,
                (int(budget_year),),
            )
        else:
            cur = await db.execute(
                """
                SELECT version_id, version_name, current_month, version_date_time
                FROM version
                ORDER BY version_id
                """
            )
        rows = await cur.fetchall()
    return [
        {
            "version_id": int(row[0]),
            "version_name": str(row[1] or f"V{int(row[0])}"),
            "current_month": int(row[2]),
            "version_date_time": str(row[3] or ""),
        }
        for row in rows
    ]


def _choose_budget_baseline_version(versions: list[dict[str, Any]]) -> int | None:
    baseline_candidates = [item for item in versions if int(item["current_month"]) == 1]
    hinted = [
        item
        for item in baseline_candidates
        if any(hint in str(item["version_name"]) for hint in BUDGET_BASELINE_HINTS)
    ]
    pool = hinted or baseline_candidates or versions
    if not pool:
        return None
    return int(sorted(pool, key=lambda item: (int(item["version_id"]), str(item["version_date_time"])))[0]["version_id"])


def _choose_default_forecast_versions(versions: list[dict[str, Any]], budget_version_id: int | None) -> list[int]:
    forecasts = [
        item
        for item in versions
        if int(item["version_id"]) != int(budget_version_id or 0)
        and int(item["current_month"]) > 1
    ]
    if not forecasts:
        forecasts = [item for item in versions if int(item["version_id"]) != int(budget_version_id or 0)]
    if not forecasts:
        return []
    latest = sorted(
        forecasts,
        key=lambda item: (int(item["current_month"]), str(item["version_date_time"]), int(item["version_id"])),
        reverse=True,
    )[0]
    return [int(latest["version_id"])]


def _version_dto(
    *,
    key: str,
    source: str,
    year: int,
    version: dict[str, Any],
    selected_by_default: bool,
) -> BudgetOutputVersionDto:
    label_prefix = "年初预算" if source == "budget" else "预测版本"
    return BudgetOutputVersionDto(
        key=key,
        label=f"{label_prefix} · V{int(version['version_id'])} {version['version_name']}",
        source=source,  # type: ignore[arg-type]
        year=year,
        version_id=int(version["version_id"]),
        version_name=str(version["version_name"]),
        current_month=int(version["current_month"]),
        selected_by_default=selected_by_default,
    )


def _selected_version_dtos(
    *,
    year: int,
    versions: list[dict[str, Any]],
    budget_version_id: int | None,
    forecast_version_ids: list[int],
) -> list[BudgetOutputVersionDto]:
    result: list[BudgetOutputVersionDto] = []
    for item in versions:
        vid = int(item["version_id"])
        if vid == budget_version_id:
            result.append(
                _version_dto(
                    key=f"budget-{vid}",
                    source="budget",
                    year=year,
                    version=item,
                    selected_by_default=True,
                )
            )
    for item in versions:
        vid = int(item["version_id"])
        if vid in forecast_version_ids:
            result.append(
                _version_dto(
                    key=f"forecast-{vid}",
                    source="forecast",
                    year=year,
                    version=item,
                    selected_by_default=True,
                )
            )
    for item in versions:
        vid = int(item["version_id"])
        if vid == budget_version_id or vid in forecast_version_ids:
            continue
        result.append(
            _version_dto(
                key=f"option-{vid}",
                source="forecast" if int(item["current_month"]) > 1 else "budget",
                year=year,
                version=item,
                selected_by_default=False,
            )
        )
    return result


def _version_lookup(versions: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(item["version_id"]): item for item in versions}


def _choose_latest_version(versions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not versions:
        return None
    return sorted(
        versions,
        key=lambda item: (int(item["current_month"]), str(item["version_date_time"]), int(item["version_id"])),
        reverse=True,
    )[0]


def _display_version_dto(
    *,
    key: str,
    source: str,
    year: int,
    version_id: int,
    version_name: str,
    current_month: int,
    show_level: int | None = None,
    selected_by_default: bool = True,
) -> BudgetOutputVersionDto:
    return BudgetOutputVersionDto(
        key=key,
        label=version_name,
        source=source,  # type: ignore[arg-type]
        show_level=show_level,
        year=year,
        version_id=version_id,
        version_name=version_name,
        current_month=current_month,
        selected_by_default=selected_by_default,
    )


async def _build_display_version_specs(
    *,
    selected_year: int,
    database_rows: list[dict[str, Any]],
    data_dir: Path,
    budget_version_id: int | None,
    forecast_version_ids: list[int] | None,
) -> tuple[list[BudgetOutputVersionDto], dict[str, DisplayVersionSpec], int | None, list[int]]:
    specs: dict[str, DisplayVersionSpec] = {}
    versions: list[BudgetOutputVersionDto] = []

    for offset, actual_year in enumerate((selected_year - 2, selected_year - 1), start=1):
        database = _choose_database_for_year(database_rows, actual_year, data_dir)
        db_path = data_dir / str(database["data_file_name"]) if database else None
        raw_versions = await _fetch_versions_for_budget_file(db_path) if db_path else []
        chosen = _choose_latest_version(raw_versions)
        version_id = int(chosen["version_id"]) if chosen else -actual_year
        name = f"{str(actual_year)[-2:]}年实际"
        dto = _display_version_dto(
            key=f"actual-{actual_year}",
            source="show",
            show_level=offset,
            year=actual_year,
            version_id=version_id,
            version_name=name,
            current_month=13,
        )
        versions.append(dto)
        specs[dto.key] = DisplayVersionSpec(dto=dto, db_path=db_path if _path_available(db_path) else None, version_id=version_id if chosen else None, mode="actual")

    selected_database = _choose_database_for_year(database_rows, selected_year, data_dir)
    selected_db_path = data_dir / str(selected_database["data_file_name"]) if selected_database else None
    selected_versions = await _fetch_versions_for_budget_file(selected_db_path) if selected_db_path else []
    versions_by_id = _version_lookup(selected_versions)
    selected_budget_version_id = (
        int(budget_version_id)
        if budget_version_id is not None and int(budget_version_id) in versions_by_id
        else _choose_budget_baseline_version(selected_versions)
    )
    selected_forecast_version_ids = [
        int(version_id)
        for version_id in (forecast_version_ids or [])
        if int(version_id) in versions_by_id and int(version_id) != int(selected_budget_version_id or 0)
    ]
    if not selected_forecast_version_ids:
        selected_forecast_version_ids = _choose_default_forecast_versions(selected_versions, selected_budget_version_id)

    if selected_budget_version_id is not None and selected_budget_version_id in versions_by_id:
        raw = versions_by_id[selected_budget_version_id]
        dto = _display_version_dto(
            key=f"budget-{selected_budget_version_id}",
            source="budget",
            year=selected_year,
            version_id=selected_budget_version_id,
            version_name=f"{str(selected_year)[-2:]}年预算",
            current_month=int(raw["current_month"]),
        )
        versions.append(dto)
        specs[dto.key] = DisplayVersionSpec(dto=dto, db_path=selected_db_path if _path_available(selected_db_path) else None, version_id=selected_budget_version_id, mode="budget")

    for version_id in selected_forecast_version_ids:
        raw = versions_by_id.get(version_id)
        if not raw:
            continue
        dto = _display_version_dto(
            key=f"forecast-{version_id}",
            source="forecast",
            year=selected_year,
            version_id=version_id,
            version_name=f"{str(selected_year)[-2:]}年预测",
            current_month=int(raw["current_month"]),
        )
        versions.append(dto)
        specs[dto.key] = DisplayVersionSpec(dto=dto, db_path=selected_db_path if _path_available(selected_db_path) else None, version_id=version_id, mode="forecast")

    return versions, specs, selected_budget_version_id, selected_forecast_version_ids


async def _fetch_show_version_configs() -> list[dict[str, Any]]:
    async with _connect_db(common_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT e.edit_show_sign, d.id, d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign BETWEEN 1 AND 5
            ORDER BY e.edit_show_sign
            """
        )
        rows = await cur.fetchall()
    return [
        (
            {
                "show_level": int(show_level),
                "data_file_id": int(data_file_id),
                "data_file_name": str(data_file_name),
                "year": int(year),
                "version_id": int(version_id),
            }
        )
        for show_level, data_file_id, data_file_name, year, version_id in rows
    ]


def _add_month_value(
    metric: dict[str, list[float]],
    *,
    month: int,
    budget_actual: int,
    value: float,
    current_month: int,
) -> None:
    idx = month - 1
    if budget_actual == 0:
        metric["budget"][idx] += value
    if budget_actual == 1:
        metric["actual"][idx] += value
    should_use = budget_actual == (1 if _month_uses_actual(month, current_month) else 0)
    if should_use:
        metric["stitched"][idx] += value


async def _build_configured_display_report(
    *,
    selected_year: int,
    available_years: list[int],
    versions: list[BudgetOutputVersionDto],
    version_specs: dict[str, DisplayVersionSpec],
    selected_budget_version_id: int | None,
    selected_forecast_version_ids: list[int],
    product_tree: list[BudgetOutputProductNodeDto],
    product_nodes: dict[str, BudgetOutputProductNodeDto],
    period_to_month: dict[int, int | None],
    config_items: list[dict[str, Any]],
    product_codes: list[str] | None,
) -> BudgetOutputDisplayReportResponse:
    requested_product_codes = [
        str(code).strip()
        for code in (product_codes or [])
        if str(code).strip() in product_nodes
    ]
    selected_products = [product_nodes[code] for code in requested_product_codes]

    overview_scope_codes = requested_product_codes or _product_overview_codes(product_tree)
    overview_scope_codes = [code for code in overview_scope_codes if code in product_nodes and code != "CORP"]

    leaf_products = _leaf_product_codes(product_nodes)
    if requested_product_codes:
        detail_scope_codes: list[str] = []
        for code in requested_product_codes:
            descendants = _leaf_product_codes_for_scope(code, product_nodes)
            detail_scope_codes.extend(descendants or [code])
    else:
        detail_scope_codes = leaf_products
    detail_scope_codes = [code for code in detail_scope_codes if code in product_nodes]

    total_product_filter: set[str] | None = None
    if requested_product_codes:
        total_product_filter = set()
        for code in requested_product_codes:
            total_product_filter.update(_collect_descendant_product_codes(code, product_nodes))

    scope_descendants = {
        code: set(_collect_descendant_product_codes(code, product_nodes))
        for code in set(overview_scope_codes + detail_scope_codes)
    }

    selected_version_meta: dict[str, BudgetOutputVersionDto] = {
        key: spec.dto
        for key, spec in version_specs.items()
        if spec.dto.selected_by_default
    }

    total_values: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(lambda: defaultdict(_empty_metric))
    overview_values: dict[str, dict[str, dict[str, dict[str, list[float]]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(_empty_metric)))
    detail_values: dict[str, dict[str, dict[str, dict[str, list[float]]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(_empty_metric)))

    data_code_bindings: dict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)

    def code_suffix(data_acct_code: str) -> str:
        code = str(data_acct_code or "").strip().upper()
        return code.split(".", 1)[1] if "." in code else ""

    for item in config_items:
        data_acct_code = str(item.get("data_acct_code") or "").strip().upper()
        if not data_acct_code:
            continue
        display_view = str(item.get("display_view") or "").strip().upper()
        if display_view == "OVERVIEW":
            suffix = code_suffix(data_acct_code)
            if not suffix:
                continue
            for scope_code in overview_scope_codes:
                data_code_bindings[f"{scope_code}.{suffix}"].append((item, scope_code))
            continue
        source_scope_code = str(item.get("source_scope_code") or "").strip().upper()
        data_code_bindings[data_acct_code].append((item, source_scope_code))

    query_data_codes = sorted(data_code_bindings)

    def can_roll_up_to_scope(source_scope_code: str, *, target_scope_code: str, row_product_code: str) -> bool:
        source_scope_code = str(source_scope_code or "").strip().upper()
        if target_scope_code == "TOTAL":
            return source_scope_code == "AA" and row_product_code == "AA"
        return source_scope_code == target_scope_code and row_product_code == target_scope_code

    if query_data_codes:
        placeholders = ",".join("?" for _ in query_data_codes)
        for version_key, spec in version_specs.items():
            if not spec.db_path or not spec.version_id:
                continue
            where = f"WHERE version_id = ? AND data_acct_code IN ({placeholders})"
            params: list[Any] = [spec.version_id, *query_data_codes]
            if spec.mode == "actual":
                where += " AND budget_actual = 1"
            elif spec.mode == "budget":
                where += " AND budget_actual = 0"
            async with _connect_db(spec.db_path) as bdb:
                await bdb.execute("PRAGMA foreign_keys = ON")
                cur = await bdb.execute(
                    f"""
                    SELECT data_acct_code, product_code, period_id, budget_actual, value
                    FROM budget_data
                    {where}
                    """,
                    tuple(params),
                )
                rows_fetched = 0
                rows_matched = 0
                rows_binding_hit = 0
                for row in await cur.fetchall():
                    data_acct_code = str(row["data_acct_code"] or "")
                    product_code = str(row["product_code"] or "").strip()
                    month = period_to_month.get(int(row["period_id"] or 0))
                    rows_fetched += 1
                    if not month or product_code not in product_nodes:
                        continue
                    rows_matched += 1
                    budget_actual = int(row["budget_actual"] or 0)
                    value = float(row["value"] or 0.0)
                    current_month = 13 if spec.mode == "actual" else int(spec.dto.current_month)
                    if data_acct_code not in data_code_bindings:
                        continue
                    rows_binding_hit += 1
                    linked_items = data_code_bindings.get(data_acct_code, [])
                    if total_product_filter is None or product_code in total_product_filter:
                        for item, effective_scope_code in linked_items:
                            if not can_roll_up_to_scope(effective_scope_code, target_scope_code="TOTAL", row_product_code=product_code):
                                continue
                            _add_month_value(
                                total_values[str(item["row_key"])][version_key],
                                month=month,
                                budget_actual=budget_actual,
                                value=value,
                                current_month=current_month,
                            )
                    for scope_code in overview_scope_codes:
                        if product_code in scope_descendants.get(scope_code, set()):
                            for item, effective_scope_code in linked_items:
                                if not can_roll_up_to_scope(effective_scope_code, target_scope_code=scope_code, row_product_code=product_code):
                                    continue
                                _add_month_value(
                                    overview_values[scope_code][str(item["row_key"])][version_key],
                                    month=month,
                                    budget_actual=budget_actual,
                                    value=value,
                                    current_month=current_month,
                                )
                    for scope_code in detail_scope_codes:
                        if product_code in scope_descendants.get(scope_code, set()):
                            for item, effective_scope_code in linked_items:
                                if not can_roll_up_to_scope(effective_scope_code, target_scope_code=scope_code, row_product_code=product_code):
                                    continue
                                _add_month_value(
                                    detail_values[scope_code][str(item["row_key"])][version_key],
                                    month=month,
                                    budget_actual=budget_actual,
                                    value=value,
                                    current_month=current_month,
                                )
    items_by_key = {str(item["row_key"]): item for item in config_items}
    children_by_parent: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for item in config_items:
        parent = item.get("parent_row_key")
        if parent not in items_by_key:
            parent = None
        children_by_parent[parent].append(item)
    for siblings in children_by_parent.values():
        siblings.sort(key=lambda item: (int(item.get("sort_order") or 0), str(item.get("row_key") or "")))

    def make_tree(display_view: str) -> list[BudgetOutputReportNodeDto]:
        allowed_items = [
            item
            for item in config_items
            if str(item.get("display_view") or "") == display_view
        ]
        if not allowed_items and display_view.startswith("PRODUCT."):
            allowed_items = [
                item
                for item in config_items
                if str(item.get("display_view") or "") == "TOTAL"
            ]
        allowed_keys = {str(item["row_key"]) for item in allowed_items}

        def build(parent_key: str | None = None) -> list[BudgetOutputReportNodeDto]:
            nodes: list[BudgetOutputReportNodeDto] = []
            for item in children_by_parent.get(parent_key, []):
                row_key = str(item["row_key"])
                if row_key not in allowed_keys:
                    continue
                children = build(row_key)
                value_type = str(item.get("value_type") or "")
                display_name = str(item["display_name"])
                nodes.append(
                    BudgetOutputReportNodeDto(
                        row_key=row_key,
                        display_name=display_name,
                        parent_row_key=item.get("parent_row_key") if item.get("parent_row_key") in allowed_keys else None,
                        level=int(item.get("level") or 1),
                        is_summary=bool(children) or str(item.get("row_type") or "") == "GROUP",
                        is_minus=value_type == "支出" or display_name.startswith(("减：", "减:")),
                        children=children,
                    )
                )
            return nodes

        return build(None)

    def flatten_tree_keys(nodes: list[BudgetOutputReportNodeDto]) -> list[str]:
        keys: list[str] = []
        for node in nodes:
            keys.append(node.row_key)
            keys.extend(flatten_tree_keys(node.children))
        return keys

    def make_row(item: dict[str, Any], value_map: dict[str, dict[str, list[float]]]) -> BudgetOutputReportRowDto:
        value_type = str(item.get("value_type") or "") or None
        display_name = str(item["display_name"])
        row_type = str(item.get("row_type") or "METRIC")
        row_values = {} if row_type == "GROUP" else value_map
        source_scope_code = item.get("source_scope_code")
        source_scope_name = item.get("scope_name") or ("全行" if source_scope_code == "CORP" else None)
        return BudgetOutputReportRowDto(
            row_key=str(item["row_key"]),
            display_name=display_name,
            data_acct_code=item.get("data_acct_code"),
            data_acct_name=item.get("data_acct_name"),
            org_product_ref=item.get("org_product_ref"),
            org_product_entity_code=item.get("org_product_entity_code"),
            org_product_table_name=item.get("org_product_table_name"),
            org_product_metric_code=item.get("org_product_metric_code"),
            org_product_metric_name=item.get("org_product_metric_name"),
            metric_node_code=item.get("metric_node_code"),
            metric_node_name=item.get("metric_node_name"),
            source_scope_type=item.get("source_scope_type"),
            source_scope_code=source_scope_code,
            source_scope_name=source_scope_name,
            budget_formula=item.get("budget_formula"),
            actual_formula=item.get("actual_formula"),
            formula_calc_mode=int(item.get("formula_calc_mode") or 0),
            allow_manual_entry=int(item.get("allow_manual_entry") if item.get("allow_manual_entry") is not None else 1),
            value_type=value_type,
            row_type=row_type,
            level=int(item.get("level") or 1),
            parent_row_key=item.get("parent_row_key") if item.get("parent_row_key") in items_by_key else None,
            is_summary=bool(children_by_parent.get(str(item["row_key"]))) or row_type == "GROUP",
            is_minus=value_type == "支出" or display_name.startswith(("减：", "减:")),
            values_by_version={
                version_key: _metric_to_dto(row_values.get(version_key, _empty_metric()))
                for version_key in selected_version_meta
            },
        )

    dependency_meta_by_code: dict[str, dict[str, Any] | None] = {}
    dependency_values_by_code: dict[str, dict[str, dict[str, list[float]]]] = {}

    async def ensure_dependency_meta(codes: set[str]) -> None:
        missing = sorted(code for code in codes if code and code not in dependency_meta_by_code)
        if not missing:
            return
        for code in missing:
            dependency_meta_by_code[code] = None
        placeholders = ",".join("?" for _ in missing)
        async with _connect_db(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                f"""
                {org_product_runtime_products_cte_for_db(db)}
                SELECT d.data_acct_code, d.data_acct_name, d.value_type,
                       d.budget_formula, d.actual_formula, d.formula_calc_mode, d.allow_manual_entry,
                       b.metric_node_code, b.scope_type, b.scope_code,
                       n.node_name AS metric_node_name,
                       p.product_name AS scope_name
                FROM data_account d
                JOIN data_account_metric_binding b ON b.data_acct_code = d.data_acct_code AND b.is_active = 1
                JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
                LEFT JOIN org_product_runtime_products p ON p.product_code = b.scope_code
                WHERE d.data_acct_code IN ({placeholders})
                """,
                tuple(missing),
            )
            for row in await cur.fetchall():
                dependency_meta_by_code[str(row["data_acct_code"])] = dict(row)

    async def resolve_dependency_codes(rows: list[BudgetOutputReportRowDto]) -> list[str]:
        visible_codes = {str(row.data_acct_code) for row in rows if row.data_acct_code}
        needed: set[str] = set()
        frontier: set[str] = set()
        for row in rows:
            frontier.update(extract_formula_codes(row.budget_formula))
            frontier.update(extract_formula_codes(row.actual_formula))
        frontier -= visible_codes
        while frontier:
            await ensure_dependency_meta(frontier)
            current = sorted(frontier)
            frontier = set()
            for code in current:
                if code in visible_codes or code in needed:
                    continue
                meta = dependency_meta_by_code.get(code)
                if not meta:
                    continue
                needed.add(code)
                next_refs = extract_formula_codes(meta.get("budget_formula")) | extract_formula_codes(meta.get("actual_formula"))
                frontier.update(next_refs - visible_codes - needed)
        return sorted(needed)

    async def ensure_dependency_values(codes: list[str]) -> None:
        missing = [code for code in codes if code not in dependency_values_by_code]
        if not missing:
            return
        await ensure_dependency_meta(set(missing))
        for code in missing:
            dependency_values_by_code[code] = {
                version_key: _empty_metric()
                for version_key in selected_version_meta
            }
        valid_codes = [code for code in missing if dependency_meta_by_code.get(code)]
        if not valid_codes:
            return
        valid_code_set = set(valid_codes)
        placeholders = ",".join("?" for _ in valid_codes)
        for version_key, spec in version_specs.items():
            if version_key not in selected_version_meta or not spec.db_path or not spec.version_id:
                continue
            where = f"WHERE version_id = ? AND data_acct_code IN ({placeholders})"
            params: list[Any] = [spec.version_id, *valid_codes]
            if spec.mode == "actual":
                where += " AND budget_actual = 1"
            elif spec.mode == "budget":
                where += " AND budget_actual = 0"
            async with _connect_db(spec.db_path) as bdb:
                await bdb.execute("PRAGMA foreign_keys = ON")
                cur = await bdb.execute(
                    f"""
                    SELECT data_acct_code, product_code, period_id, budget_actual, value
                    FROM budget_data
                    {where}
                    """,
                    tuple(params),
                )
                for raw in await cur.fetchall():
                    data_acct_code = str(raw["data_acct_code"] or "")
                    if data_acct_code not in valid_code_set:
                        continue
                    meta = dependency_meta_by_code.get(data_acct_code) or {}
                    source_scope_code = str(meta.get("scope_code") or "").strip()
                    product_code = str(raw["product_code"] or "").strip()
                    if source_scope_code and product_code != source_scope_code:
                        continue
                    month = period_to_month.get(int(raw["period_id"] or 0))
                    if not month:
                        continue
                    current_month = 13 if spec.mode == "actual" else int(spec.dto.current_month)
                    _add_month_value(
                        dependency_values_by_code[data_acct_code][version_key],
                        month=month,
                        budget_actual=int(raw["budget_actual"] or 0),
                        value=float(raw["value"] or 0.0),
                        current_month=current_month,
                    )

    async def build_formula_dependency_rows(rows: list[BudgetOutputReportRowDto]) -> list[BudgetOutputReportRowDto]:
        dependency_codes = await resolve_dependency_codes(rows)
        await ensure_dependency_values(dependency_codes)
        dependency_rows: list[BudgetOutputReportRowDto] = []
        for code in dependency_codes:
            meta = dependency_meta_by_code.get(code)
            if not meta:
                continue
            source_scope_code = meta.get("scope_code")
            dependency_rows.append(
                BudgetOutputReportRowDto(
                    row_key=f"FORMULA_REF.{code}",
                    display_name=str(meta.get("data_acct_name") or code),
                    data_acct_code=code,
                    data_acct_name=meta.get("data_acct_name"),
                    metric_node_code=meta.get("metric_node_code"),
                    metric_node_name=meta.get("metric_node_name"),
                    source_scope_type=meta.get("scope_type"),
                    source_scope_code=source_scope_code,
                    source_scope_name=meta.get("scope_name") or ("全行" if source_scope_code == "CORP" else None),
                    budget_formula=meta.get("budget_formula"),
                    actual_formula=meta.get("actual_formula"),
                    formula_calc_mode=int(meta.get("formula_calc_mode") or 0),
                    allow_manual_entry=int(meta.get("allow_manual_entry") if meta.get("allow_manual_entry") is not None else 1),
                    value_type=meta.get("value_type"),
                    row_type="METRIC",
                    level=8,
                    parent_row_key=None,
                    is_summary=False,
                    is_minus=str(meta.get("value_type") or "") == "支出" or str(meta.get("data_acct_name") or "").startswith(("减：", "减:")),
                    values_by_version={
                        version_key: _metric_to_dto(dependency_values_by_code.get(code, {}).get(version_key, _empty_metric()))
                        for version_key in selected_version_meta
                    },
                )
            )
        return dependency_rows

    report_tree = make_tree("TOTAL")
    product_overview_tree = make_tree("OVERVIEW") or report_tree
    first_detail_scope = detail_scope_codes[0] if detail_scope_codes else None
    product_detail_tree = make_tree(f"PRODUCT.{first_detail_scope}") if first_detail_scope else report_tree
    product_detail_tree = product_detail_tree or report_tree
    tree_keys = flatten_tree_keys(report_tree)
    overview_tree_keys = flatten_tree_keys(product_overview_tree)
    total_rows = [make_row(items_by_key[key], total_values.get(key, {})) for key in tree_keys if key in items_by_key]
    total_formula_dependency_rows = await build_formula_dependency_rows(total_rows)
    product_overview_blocks = [
        (
            lambda block_rows, scope_code=code: BudgetOutputProductBlockDto(
                product_code=product_nodes[scope_code].product_code,
                product_name=product_nodes[scope_code].product_name,
                descendant_product_codes=_collect_descendant_product_codes(scope_code, product_nodes),
                rows=block_rows,
                formula_dependency_rows=[],
            )
        )(
            [
                make_row(items_by_key[key], overview_values.get(code, {}).get(key, {}))
                for key in overview_tree_keys
                if key in items_by_key
            ]
        )
        for code in overview_scope_codes
    ]
    for block in product_overview_blocks:
        block.formula_dependency_rows = await build_formula_dependency_rows(block.rows)
    product_detail_blocks = []
    for code in detail_scope_codes:
        scope_tree = make_tree(f"PRODUCT.{code}") or product_detail_tree
        scope_keys = flatten_tree_keys(scope_tree)
        block_rows = [
            make_row(items_by_key[key], detail_values.get(code, {}).get(key, {}))
            for key in scope_keys
            if key in items_by_key
        ]
        product_detail_blocks.append(
            BudgetOutputProductBlockDto(
                product_code=product_nodes[code].product_code,
                product_name=product_nodes[code].product_name,
                descendant_product_codes=_collect_descendant_product_codes(code, product_nodes),
                rows=block_rows,
                formula_dependency_rows=await build_formula_dependency_rows(block_rows),
            )
        )

    return BudgetOutputDisplayReportResponse(
        title=f"{selected_year}年度预算展示报表",
        unit_label="元",
        available_years=available_years,
        selected_year=selected_year,
        budget_version_id=selected_budget_version_id,
        forecast_version_ids=selected_forecast_version_ids,
        versions=versions,
        selected_show_levels=[version.show_level for version in versions if version.show_level],
        product_tree=product_tree,
        report_tree=report_tree,
        product_overview_tree=product_overview_tree,
        product_detail_tree=product_detail_tree,
        selected_products=selected_products,
        total_rows=total_rows,
        total_formula_dependency_rows=total_formula_dependency_rows,
        product_blocks=product_detail_blocks,
        product_overview_blocks=product_overview_blocks,
        product_detail_blocks=product_detail_blocks,
        note=(
            "报表口径：按数据库中的预算展示布局配置展示；展示配置只维护顺序、层级和展示名称；绑定机构及产品指标编码的展示行按同一指标体系精确取数。"
            if config_items
            else "尚未配置预算展示科目；请先在展示科目配置中从已确认机构产品指标选择需要展示的科目。"
        ),
    )


async def _build_metric_display_report(
    *,
    year: int | None,
    budget_version_id: int | None,
    forecast_version_ids: list[int] | None,
    product_codes: list[str] | None,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    data_dir: Path,
) -> BudgetOutputDisplayReportResponse:
    _editable_budget_path, editable_year, _editable_version_id = await editable_context_provider()
    database_rows = await _fetch_budget_database_rows()
    available_years = sorted({int(row["year"]) for row in database_rows}, reverse=True)
    selected_year = int(year or editable_year)
    if selected_year not in available_years and database_rows:
        selected_year = int(database_rows[0]["year"])

    versions, version_specs, selected_budget_version_id, selected_forecast_version_ids = await _build_display_version_specs(
        selected_year=selected_year,
        database_rows=database_rows,
        data_dir=data_dir,
        budget_version_id=budget_version_id,
        forecast_version_ids=forecast_version_ids,
    )

    async with _connect_db(common_db_path()) as cdb:
        await cdb.execute("PRAGMA foreign_keys = ON")
        cur = await cdb.execute(
            f"""
            {org_product_runtime_products_cte_for_db(cdb)}
            SELECT product_code, product_name, parent_code, level
            FROM org_product_runtime_products
            WHERE product_code <> '' AND product_name <> ''
            ORDER BY product_code
            """
        )
        product_rows = await cur.fetchall()
        cur = await cdb.execute("SELECT period_id, month FROM period")
        period_rows = await cur.fetchall()
        config_items = await _fetch_display_config_items(cdb, active_only=True)

    product_tree, product_nodes = _build_product_tree(
        [(str(r["product_code"]), str(r["product_name"]), r["parent_code"], int(r["level"] or 1)) for r in product_rows]
    )
    period_to_month = {int(row["period_id"]): _parse_month(str(row["month"])) for row in period_rows}
    return await _build_configured_display_report(
        selected_year=selected_year,
        available_years=available_years,
        versions=versions,
        version_specs=version_specs,
        selected_budget_version_id=selected_budget_version_id,
        selected_forecast_version_ids=selected_forecast_version_ids,
        product_tree=product_tree,
        product_nodes=product_nodes,
        period_to_month=period_to_month,
        config_items=config_items,
        product_codes=product_codes,
    )


async def fetch_budget_display_config_items(
    db: Any,
    *,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    return await _fetch_display_config_items(db, active_only=active_only)


async def fetch_budget_display_config_candidates(db: Any) -> list[dict[str, Any]]:
    return await _fetch_display_config_candidates(db)


def budget_display_config_item_to_dto(row: dict[str, Any]) -> BudgetOutputDisplayConfigItemDto:
    return _display_config_item_to_dto(row)


def budget_display_candidate_to_dto(row: dict[str, Any]) -> BudgetOutputDisplayCandidateDto:
    return _display_candidate_to_dto(row)


async def build_budget_output_display_report(
    *,
    year: int | None,
    budget_version_id: int | None,
    forecast_version_ids: list[int] | None,
    product_codes: list[str] | None,
    editable_context_provider: Callable[[], Awaitable[tuple[Path, int, int]]],
    data_dir: Path,
) -> BudgetOutputDisplayReportResponse:
    return await _build_metric_display_report(
        year=year,
        budget_version_id=budget_version_id,
        forecast_version_ids=forecast_version_ids,
        product_codes=product_codes,
        editable_context_provider=editable_context_provider,
        data_dir=data_dir,
    )
