from __future__ import annotations

import random
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.db_paths import budget_db_path, common_db_path
from app.init_db import ensure_databases


ASSET_SCALE = 1000.0
LIABILITY_SCALE = 900.0
LOAN_ASSET_RATIO = 0.60
INTERBANK_ASSET_RATIO = 0.25
DEPOSIT_LIABILITY_RATIO = 0.80
LOAN_RATE_MIN = 0.07
LOAN_RATE_MAX = 0.10
INTERBANK_RATE_MIN = 0.01
INTERBANK_RATE_MAX = 0.02
FTP_SPREAD_MIN = 0.001
FTP_SPREAD_MAX = 0.002
DEPOSIT_RATE_MIN = 0.01
DEPOSIT_RATE_MAX = 0.02
SMALL_DEPOSIT_SCALE = 10.0
RANDOM_SEED = 20260416


@dataclass
class LoanProductContext:
    product_code: str
    product_name: str
    domain: str  # personal | enterprise
    a_codes: list[str]
    c_code: str
    k_code: str
    budget_rate: float
    actual_rate: float


@dataclass
class DepositProductContext:
    product_code: str
    product_name: str
    domain: str  # personal | enterprise
    a_codes: list[str]
    c_code: str
    l_code: str
    budget_rate: float
    actual_rate: float


@dataclass
class InterbankAssetContext:
    a_code: str
    a_name: str
    product_code: str
    c_code: str
    k_code: str
    budget_rate: float
    actual_rate: float


@dataclass
class AssetFtpContext:
    key: str
    a_codes: list[str]
    c_code: str
    k_code: str
    budget_rate: float
    actual_rate: float


@dataclass
class SmallDepositContext:
    a_code: str
    c_code: str
    l_code: str
    budget_rate: float
    actual_rate: float


@dataclass
class LiabilityFtpContext:
    key: str
    a_code: str
    c_code: str
    l_code: str
    report_rate_code: str
    budget_rate: float
    actual_rate: float


def _fetch_all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    return list(cur.fetchall())


def _fmt_ref(code: str, name: str) -> str:
    return f"<{code} {name}>"


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _next_code_factory(conn: sqlite3.Connection):
    counters: dict[str, int] = {}
    for prefix in ("A", "C", "K", "L"):
        row = conn.execute(
            "SELECT MAX(CAST(SUBSTR(data_acct_code, 2) AS INTEGER)) FROM data_account WHERE data_acct_code LIKE ?",
            (f"{prefix}____",),
        ).fetchone()
        counters[prefix] = int(row[0] or 0)

    def _next(prefix: str) -> str:
        counters[prefix] += 1
        return f"{prefix}{counters[prefix]:04d}"

    return _next


def _load_mappings_by_data(conn: sqlite3.Connection) -> dict[str, set[str]]:
    rows = _fetch_all(conn, "SELECT data_acct_code, report_acct_code FROM report_data_mapping")
    mapping: dict[str, set[str]] = {}
    for r in rows:
        mapping.setdefault(r["data_acct_code"], set()).add(r["report_acct_code"])
    return mapping


def _load_data_accounts_by_product(conn: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    rows = _fetch_all(
        conn,
        """
        SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
        FROM data_account
        ORDER BY data_acct_code
        """,
    )
    data: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        data.setdefault(r["product_code"] or "", []).append(r)
    return data


def _load_dept_tree(conn: sqlite3.Connection) -> dict[str, tuple[str, str | None]]:
    rows = _fetch_all(conn, "SELECT dept_code, dept_name, parent_code FROM dept_account")
    return {r["dept_code"]: (r["dept_name"], r["parent_code"]) for r in rows}


def _domain_from_product(
    product_code: str,
    product_name: str,
    dept_tree: dict[str, tuple[str, str | None]],
    product_dept: dict[str, str],
) -> str:
    dept_code = product_dept.get(product_code)
    cursor = dept_code
    visited: set[str] = set()
    while cursor and cursor not in visited:
        visited.add(cursor)
        node = dept_tree.get(cursor)
        if not node:
            break
        dept_name, parent_code = node
        if "企业" in dept_name:
            return "enterprise"
        if "个人" in dept_name:
            return "personal"
        cursor = parent_code
    if "企" in product_name:
        return "enterprise"
    return "personal"


def _ensure_data_account(
    conn: sqlite3.Connection,
    code: str,
    name: str,
    product_code: str,
    value_type: str,
) -> None:
    conn.execute(
        """
        INSERT INTO data_account (
            data_acct_code, data_acct_name, product_code, budget_formula, actual_formula, need_calc, value_type, remark
        ) VALUES (?, ?, ?, NULL, NULL, 0, ?, ?)
        """,
        (code, name, product_code, value_type, "脚本自动补齐"),
    )


def _ensure_mapping(conn: sqlite3.Connection, report_code: str, data_code: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO report_data_mapping (report_acct_code, data_acct_code)
        VALUES (?, ?)
        """,
        (report_code, data_code),
    )


def _pick_account(
    rows: list[sqlite3.Row],
    mappings: dict[str, set[str]],
    prefix: str,
    report_prefix: str | None = None,
    name_keywords: tuple[str, ...] = (),
) -> sqlite3.Row | None:
    candidates = [r for r in rows if r["data_acct_code"].startswith(prefix)]
    if report_prefix:
        mapped = [r for r in candidates if any(code.startswith(report_prefix) for code in mappings.get(r["data_acct_code"], set()))]
        if mapped:
            return sorted(mapped, key=lambda x: x["data_acct_code"])[0]
    if name_keywords:
        named = [r for r in candidates if all(k in (r["data_acct_name"] or "") for k in name_keywords)]
        if named:
            return sorted(named, key=lambda x: x["data_acct_code"])[0]
    if candidates:
        return sorted(candidates, key=lambda x: x["data_acct_code"])[0]
    return None


def _loan_a_accounts(rows: list[sqlite3.Row], mappings: dict[str, set[str]]) -> list[sqlite3.Row]:
    matched = [
        r
        for r in rows
        if r["data_acct_code"].startswith("A")
        and any(code.startswith("X010103") for code in mappings.get(r["data_acct_code"], set()))
    ]
    if matched:
        return sorted(matched, key=lambda x: x["data_acct_code"])
    fallback = [r for r in rows if r["data_acct_code"].startswith("A") and "贷" in (r["data_acct_name"] or "") and "日均" in (r["data_acct_name"] or "")]
    return sorted(fallback, key=lambda x: x["data_acct_code"])


def _deposit_a_accounts(rows: list[sqlite3.Row], mappings: dict[str, set[str]]) -> list[sqlite3.Row]:
    matched = [
        r
        for r in rows
        if r["data_acct_code"].startswith("A")
        and any(code.startswith("X010201") for code in mappings.get(r["data_acct_code"], set()))
    ]
    if matched:
        return sorted(matched, key=lambda x: x["data_acct_code"])
    fallback = [r for r in rows if r["data_acct_code"].startswith("A") and "存款" in (r["data_acct_name"] or "") and "日均" in (r["data_acct_name"] or "")]
    return sorted(fallback, key=lambda x: x["data_acct_code"])


def _interbank_a_accounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = _fetch_all(
        conn,
        """
        SELECT DISTINCT d.data_acct_code, d.data_acct_name, d.product_code, d.value_type, d.budget_formula, d.actual_formula
        FROM report_data_mapping m
        JOIN data_account d ON d.data_acct_code = m.data_acct_code
        WHERE m.report_acct_code LIKE 'X010102%'
          AND d.data_acct_code LIKE 'A____'
        ORDER BY d.data_acct_code
        """,
    )
    return rows


def _norm_weights(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        return [1.0 / len(values)] * len(values)
    return [v / total for v in values]


def _upsert_budget_data(
    conn: sqlite3.Connection,
    data_code: str,
    period_id: int,
    budget_actual: int,
    version_id: int,
    value: float,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO budget_data (
            data_acct_code, period_id, budget_actual, version_id, value, need_calc, create_time, update_time
        ) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT(data_acct_code, period_id, version_id, budget_actual)
        DO UPDATE SET
            value = excluded.value,
            need_calc = excluded.need_calc,
            update_time = excluded.update_time
        """,
        (data_code, period_id, budget_actual, version_id, round(float(value), 6), now, now),
    )


def main() -> None:
    ensure_databases()
    rng = random.Random(RANDOM_SEED)
    common_path = common_db_path()
    budget_path = budget_db_path()

    with sqlite3.connect(common_path) as common_conn, sqlite3.connect(budget_path) as budget_conn:
        common_conn.row_factory = sqlite3.Row
        budget_conn.row_factory = sqlite3.Row
        common_conn.execute("PRAGMA foreign_keys = ON")

        next_code = _next_code_factory(common_conn)
        mappings = _load_mappings_by_data(common_conn)
        data_by_product = _load_data_accounts_by_product(common_conn)
        dept_tree = _load_dept_tree(common_conn)

        product_dept_rows = _fetch_all(common_conn, "SELECT product_code, dept_code FROM dept_product_mapping")
        product_dept = {r["product_code"]: r["dept_code"] for r in product_dept_rows}

        products = _fetch_all(common_conn, "SELECT product_code, product_name FROM product_type ORDER BY product_code")
        loan_products = [p for p in products if "贷" in (p["product_name"] or "")]
        deposit_products = [p for p in products if "存款" in (p["product_name"] or "")]

        created_accounts = 0
        created_mappings = 0
        updated_formulas = 0
        touched_codes: set[str] = set()

        loan_contexts: list[LoanProductContext] = []
        for p in loan_products:
            product_code = p["product_code"]
            product_name = p["product_name"]
            domain = _domain_from_product(product_code, product_name, dept_tree, product_dept)
            report_loan_daily = "X01010302" if domain == "enterprise" else "X01010301"
            report_loan_rate = "X1004" if domain == "enterprise" else "X1003"

            rows = data_by_product.get(product_code, [])
            a_rows = _loan_a_accounts(rows, mappings)
            if not a_rows:
                a_code = next_code("A")
                a_name = f"{product_name}贷款资产_表内日均"
                _ensure_data_account(common_conn, a_code, a_name, product_code, "金额")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                a_rows = _loan_a_accounts(rows, mappings)

            c_row = _pick_account(rows, mappings, "C", "X0301010103", ("贷款", "利息"))
            if not c_row:
                c_code = next_code("C")
                c_name = f"{product_name}贷款利息收入"
                _ensure_data_account(common_conn, c_code, c_name, product_code, "金额")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                c_row = _pick_account(rows, mappings, "C", "X0301010103", ("贷款", "利息"))
            k_row = _pick_account(rows, mappings, "K", "X100", ("收益率",))
            if not k_row:
                k_code = next_code("K")
                k_name = f"{product_name}贷款收益率_年化"
                _ensure_data_account(common_conn, k_code, k_name, product_code, "百分比")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                k_row = _pick_account(rows, mappings, "K", "X100", ("收益率",))

            if not c_row or not k_row:
                raise RuntimeError(f"贷款产品 {product_code} 未能建立C/K科目")

            for a in a_rows:
                before = common_conn.total_changes
                _ensure_mapping(common_conn, report_loan_daily, a["data_acct_code"])
                if common_conn.total_changes > before:
                    created_mappings += 1
                    mappings.setdefault(a["data_acct_code"], set()).add(report_loan_daily)
                touched_codes.add(a["data_acct_code"])

            for report_code, data_code in (
                ("X0301010103", c_row["data_acct_code"]),
                (report_loan_rate, k_row["data_acct_code"]),
            ):
                before = common_conn.total_changes
                _ensure_mapping(common_conn, report_code, data_code)
                if common_conn.total_changes > before:
                    created_mappings += 1
                    mappings.setdefault(data_code, set()).add(report_code)

            a_refs = "+".join(_fmt_ref(a["data_acct_code"], a["data_acct_name"]) for a in a_rows)
            c_ref = _fmt_ref(c_row["data_acct_code"], c_row["data_acct_name"])
            k_ref = _fmt_ref(k_row["data_acct_code"], k_row["data_acct_name"])
            base_expr = f"({a_refs})"
            c_budget_formula = f"{base_expr}*{k_ref}/12/1.06"
            k_actual_formula = f"{c_ref}/{base_expr}*12*1.06"

            common_conn.execute(
                "UPDATE data_account SET budget_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (c_budget_formula, c_row["data_acct_code"]),
            )
            common_conn.execute(
                "UPDATE data_account SET actual_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (k_actual_formula, k_row["data_acct_code"]),
            )
            updated_formulas += 2
            touched_codes.update({c_row["data_acct_code"], k_row["data_acct_code"]})

            budget_rate = rng.uniform(LOAN_RATE_MIN, LOAN_RATE_MAX)
            actual_rate = _clip(budget_rate + rng.uniform(-0.008, 0.008), LOAN_RATE_MIN, LOAN_RATE_MAX)
            loan_contexts.append(
                LoanProductContext(
                    product_code=product_code,
                    product_name=product_name,
                    domain=domain,
                    a_codes=[a["data_acct_code"] for a in a_rows],
                    c_code=c_row["data_acct_code"],
                    k_code=k_row["data_acct_code"],
                    budget_rate=budget_rate,
                    actual_rate=actual_rate,
                )
            )

        deposit_contexts: list[DepositProductContext] = []
        for p in deposit_products:
            product_code = p["product_code"]
            product_name = p["product_name"]
            domain = _domain_from_product(product_code, product_name, dept_tree, product_dept)
            report_dep_daily = "X01020102" if domain == "enterprise" else "X01020101"
            report_dep_rate = "X1104" if domain == "enterprise" else "X1103"

            rows = data_by_product.get(product_code, [])
            a_rows = _deposit_a_accounts(rows, mappings)
            if not a_rows:
                a_code = next_code("A")
                a_name = f"{product_name}_日均"
                _ensure_data_account(common_conn, a_code, a_name, product_code, "金额")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                a_rows = _deposit_a_accounts(rows, mappings)

            c_row = _pick_account(rows, mappings, "C", "X0301010108", ("存款", "支出"))
            if not c_row:
                c_code = next_code("C")
                c_name = f"{product_name}_外部利息支出"
                _ensure_data_account(common_conn, c_code, c_name, product_code, "金额")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                c_row = _pick_account(rows, mappings, "C", "X0301010108", ("存款", "支出"))

            l_row = _pick_account(rows, mappings, "L", "X110", ("付息率",))
            if not l_row:
                l_code = next_code("L")
                l_name = f"{product_name}付息率_年化"
                _ensure_data_account(common_conn, l_code, l_name, product_code, "百分比")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                l_row = _pick_account(rows, mappings, "L", "X110", ("付息率",))

            if not c_row or not l_row:
                raise RuntimeError(f"存款产品 {product_code} 未能建立C/L科目")

            for a in a_rows:
                before = common_conn.total_changes
                _ensure_mapping(common_conn, report_dep_daily, a["data_acct_code"])
                if common_conn.total_changes > before:
                    created_mappings += 1
                    mappings.setdefault(a["data_acct_code"], set()).add(report_dep_daily)
                touched_codes.add(a["data_acct_code"])

            for report_code, data_code in (
                ("X0301010108", c_row["data_acct_code"]),
                (report_dep_rate, l_row["data_acct_code"]),
            ):
                before = common_conn.total_changes
                _ensure_mapping(common_conn, report_code, data_code)
                if common_conn.total_changes > before:
                    created_mappings += 1
                    mappings.setdefault(data_code, set()).add(report_code)

            a_refs = "+".join(_fmt_ref(a["data_acct_code"], a["data_acct_name"]) for a in a_rows)
            c_ref = _fmt_ref(c_row["data_acct_code"], c_row["data_acct_name"])
            l_ref = _fmt_ref(l_row["data_acct_code"], l_row["data_acct_name"])
            base_expr = f"({a_refs})"
            c_budget_formula = f"{base_expr}*{l_ref}/12"
            l_actual_formula = f"{c_ref}/{base_expr}*12"

            common_conn.execute(
                "UPDATE data_account SET budget_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (c_budget_formula, c_row["data_acct_code"]),
            )
            common_conn.execute(
                "UPDATE data_account SET actual_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (l_actual_formula, l_row["data_acct_code"]),
            )
            updated_formulas += 2
            touched_codes.update({c_row["data_acct_code"], l_row["data_acct_code"]})

            budget_rate = rng.uniform(DEPOSIT_RATE_MIN, DEPOSIT_RATE_MAX)
            actual_rate = _clip(budget_rate + rng.uniform(-0.003, 0.003), DEPOSIT_RATE_MIN, DEPOSIT_RATE_MAX)
            deposit_contexts.append(
                DepositProductContext(
                    product_code=product_code,
                    product_name=product_name,
                    domain=domain,
                    a_codes=[a["data_acct_code"] for a in a_rows],
                    c_code=c_row["data_acct_code"],
                    l_code=l_row["data_acct_code"],
                    budget_rate=budget_rate,
                    actual_rate=actual_rate,
                )
            )

        interbank_contexts: list[InterbankAssetContext] = []
        interbank_a_rows = _interbank_a_accounts(common_conn)
        for a_row in interbank_a_rows:
            a_code = a_row["data_acct_code"]
            a_name = a_row["data_acct_name"] or a_code
            product_code = a_row["product_code"] or "Z9999"
            rows = data_by_product.get(product_code, [])
            a_ref_token = f"<{a_code} "
            name_core = a_name.replace("_日均", "").replace("日均", "")

            c_candidates = [
                r
                for r in rows
                if r["data_acct_code"].startswith("C")
                and any(code.startswith("X0301010101") for code in mappings.get(r["data_acct_code"], set()))
            ]
            c_row = next(
                (
                    r
                    for r in c_candidates
                    if a_ref_token in (r["budget_formula"] or "") or name_core in (r["data_acct_name"] or "")
                ),
                None,
            )
            if not c_row:
                c_code = next_code("C")
                c_name = f"{name_core}利息收入"
                _ensure_data_account(common_conn, c_code, c_name, product_code, "金额")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                c_row = next((r for r in rows if r["data_acct_code"] == c_code), None)

            k_candidates = [
                r
                for r in rows
                if r["data_acct_code"].startswith("K")
                and any(code.startswith("X1002") for code in mappings.get(r["data_acct_code"], set()))
            ]
            k_row = next(
                (
                    r
                    for r in k_candidates
                    if a_ref_token in (r["actual_formula"] or "") or name_core in (r["data_acct_name"] or "")
                ),
                None,
            )
            if not k_row:
                k_code = next_code("K")
                k_name = f"{name_core}收益率_年化"
                _ensure_data_account(common_conn, k_code, k_name, product_code, "百分比")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                k_row = next((r for r in rows if r["data_acct_code"] == k_code), None)

            if not c_row or not k_row:
                raise RuntimeError(f"同业资产科目 {a_code} 未能建立C/K科目")

            for report_code, data_code in (
                ("X0301010101", c_row["data_acct_code"]),
                ("X1002", k_row["data_acct_code"]),
            ):
                before = common_conn.total_changes
                _ensure_mapping(common_conn, report_code, data_code)
                if common_conn.total_changes > before:
                    created_mappings += 1
                    mappings.setdefault(data_code, set()).add(report_code)

            a_ref = _fmt_ref(a_code, a_name)
            c_ref = _fmt_ref(c_row["data_acct_code"], c_row["data_acct_name"])
            k_ref = _fmt_ref(k_row["data_acct_code"], k_row["data_acct_name"])
            c_budget_formula = f"{a_ref}*{k_ref}/12"
            k_actual_formula = f"{c_ref}/{a_ref}*12"

            common_conn.execute(
                "UPDATE data_account SET budget_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (c_budget_formula, c_row["data_acct_code"]),
            )
            common_conn.execute(
                "UPDATE data_account SET actual_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (k_actual_formula, k_row["data_acct_code"]),
            )
            updated_formulas += 2
            touched_codes.update({a_code, c_row["data_acct_code"], k_row["data_acct_code"]})

            budget_rate = rng.uniform(INTERBANK_RATE_MIN, INTERBANK_RATE_MAX)
            actual_rate = _clip(
                budget_rate + rng.uniform(-0.002, 0.002),
                INTERBANK_RATE_MIN,
                INTERBANK_RATE_MAX,
            )
            interbank_contexts.append(
                InterbankAssetContext(
                    a_code=a_code,
                    a_name=a_name,
                    product_code=product_code,
                    c_code=c_row["data_acct_code"],
                    k_code=k_row["data_acct_code"],
                    budget_rate=budget_rate,
                    actual_rate=actual_rate,
                )
            )

        name_rows = _fetch_all(
            common_conn,
            "SELECT data_acct_code, data_acct_name FROM data_account ORDER BY data_acct_code",
        )
        account_name_by_code = {
            r["data_acct_code"]: (r["data_acct_name"] or r["data_acct_code"]) for r in name_rows
        }

        small_deposit_contexts: list[SmallDepositContext] = []
        small_deposit_targets = [("A3120", "C3120", "L3120"), ("A3160", "C3160", "L3160")]
        for a_code, c_code, l_code in small_deposit_targets:
            if a_code not in account_name_by_code:
                continue
            c_name = account_name_by_code.get(c_code, c_code)
            l_name = account_name_by_code.get(l_code, l_code)
            a_name = account_name_by_code[a_code]

            c_exists = c_code in account_name_by_code
            l_exists = l_code in account_name_by_code
            if not c_exists or not l_exists:
                row = common_conn.execute(
                    "SELECT product_code FROM data_account WHERE data_acct_code = ?",
                    (a_code,),
                ).fetchone()
                product_code = (row[0] if row else None) or "Z9999"
                if not c_exists:
                    c_name = f"{a_name.replace('_日均', '').replace('日均', '')}_外部利息支出"
                    _ensure_data_account(common_conn, c_code, c_name, product_code, "金额")
                    created_accounts += 1
                    account_name_by_code[c_code] = c_name
                if not l_exists:
                    l_name = f"{a_name.replace('_日均', '').replace('日均', '')}付息率_年化"
                    _ensure_data_account(common_conn, l_code, l_name, product_code, "百分比")
                    created_accounts += 1
                    account_name_by_code[l_code] = l_name

            report_rate_code = (
                "X1104"
                if any(code.startswith("X01020102") for code in mappings.get(a_code, set()))
                else "X1103"
            )
            for report_code, data_code in (("X0301010108", c_code), (report_rate_code, l_code)):
                before = common_conn.total_changes
                _ensure_mapping(common_conn, report_code, data_code)
                if common_conn.total_changes > before:
                    created_mappings += 1
                    mappings.setdefault(data_code, set()).add(report_code)

            a_ref = _fmt_ref(a_code, a_name)
            c_ref = _fmt_ref(c_code, c_name)
            l_ref = _fmt_ref(l_code, l_name)
            common_conn.execute(
                "UPDATE data_account SET budget_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (f"{a_ref}*{l_ref}/12", c_code),
            )
            common_conn.execute(
                "UPDATE data_account SET actual_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (f"{c_ref}/{a_ref}*12", l_code),
            )
            updated_formulas += 2
            touched_codes.update({a_code, c_code, l_code})

            base_rate = rng.uniform(DEPOSIT_RATE_MIN, DEPOSIT_RATE_MAX)
            small_deposit_contexts.append(
                SmallDepositContext(
                    a_code=a_code,
                    c_code=c_code,
                    l_code=l_code,
                    budget_rate=base_rate,
                    actual_rate=_clip(
                        base_rate + rng.uniform(-0.003, 0.003),
                        DEPOSIT_RATE_MIN,
                        DEPOSIT_RATE_MAX,
                    ),
                )
            )

        # A3160 单独建模后，从企小乐聚合逻辑中移除，避免重复计入。
        for ctx in deposit_contexts:
            if ctx.product_code == "Z0017" and "A3160" in ctx.a_codes and len(ctx.a_codes) > 1:
                ctx.a_codes = [code for code in ctx.a_codes if code != "A3160"]
                if ctx.a_codes:
                    a_refs = "+".join(
                        _fmt_ref(code, account_name_by_code.get(code, code)) for code in ctx.a_codes
                    )
                    base_expr = f"({a_refs})"
                    c_ref = _fmt_ref(ctx.c_code, account_name_by_code.get(ctx.c_code, ctx.c_code))
                    l_ref = _fmt_ref(ctx.l_code, account_name_by_code.get(ctx.l_code, ctx.l_code))
                    common_conn.execute(
                        "UPDATE data_account SET budget_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                        (f"{base_expr}*{l_ref}/12", ctx.c_code),
                    )
                    common_conn.execute(
                        "UPDATE data_account SET actual_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                        (f"{c_ref}/{base_expr}*12", ctx.l_code),
                    )
                    updated_formulas += 2
                    touched_codes.update({ctx.c_code, ctx.l_code})

        liability_external_rate_by_a: dict[str, tuple[float, float, str]] = {}
        for ctx in deposit_contexts:
            for a_code in ctx.a_codes:
                report_rate_code = (
                    "X1104"
                    if any(code.startswith("X01020102") for code in mappings.get(a_code, set()))
                    else "X1103"
                )
                liability_external_rate_by_a[a_code] = (
                    ctx.budget_rate,
                    ctx.actual_rate,
                    report_rate_code,
                )
        for ctx in small_deposit_contexts:
            report_rate_code = (
                "X1104"
                if any(code.startswith("X01020102") for code in mappings.get(ctx.a_code, set()))
                else "X1103"
            )
            liability_external_rate_by_a[ctx.a_code] = (
                ctx.budget_rate,
                ctx.actual_rate,
                report_rate_code,
            )

        liability_ftp_contexts: list[LiabilityFtpContext] = []
        for a_code, (ext_budget_rate, ext_actual_rate, report_rate_code) in liability_external_rate_by_a.items():
            a_name = account_name_by_code.get(a_code, a_code)
            row = common_conn.execute(
                "SELECT product_code FROM data_account WHERE data_acct_code = ?",
                (a_code,),
            ).fetchone()
            product_code = (row[0] if row else None) or "Z9999"
            rows = data_by_product.get(product_code, [])
            a_token = f"<{a_code} "
            name_core = a_name.replace("_日均", "").replace("日均", "")

            c_candidates = [
                r
                for r in rows
                if r["data_acct_code"].startswith("C")
                and any(code.startswith("X0301010107") for code in mappings.get(r["data_acct_code"], set()))
            ]
            c_row = next(
                (
                    r
                    for r in c_candidates
                    if a_token in (r["budget_formula"] or "")
                    or name_core in (r["data_acct_name"] or "")
                ),
                None,
            )
            if not c_row:
                c_code = next_code("C")
                c_name = f"{name_core}内部FTP利息收入"
                _ensure_data_account(common_conn, c_code, c_name, product_code, "金额")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                account_name_by_code[c_code] = c_name
                c_row = next((r for r in rows if r["data_acct_code"] == c_code), None)

            l_candidates = [
                r
                for r in rows
                if r["data_acct_code"].startswith("L")
                and "FTP" in (r["data_acct_name"] or "")
            ]
            l_row = next(
                (
                    r
                    for r in l_candidates
                    if a_token in (r["actual_formula"] or "")
                ),
                None,
            )
            if not l_row:
                l_code = next_code("L")
                l_name = f"{name_core}内部FTP利率_年化"
                _ensure_data_account(common_conn, l_code, l_name, product_code, "百分比")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                account_name_by_code[l_code] = l_name
                l_row = next((r for r in rows if r["data_acct_code"] == l_code), None)

            if not c_row or not l_row:
                raise RuntimeError(f"负债科目 {a_code} 未能建立FTP C/L科目")

            for map_code, data_code in (("X0301010107", c_row["data_acct_code"]), (report_rate_code, l_row["data_acct_code"])):
                before = common_conn.total_changes
                _ensure_mapping(common_conn, map_code, data_code)
                if common_conn.total_changes > before:
                    created_mappings += 1
                    mappings.setdefault(data_code, set()).add(map_code)

            a_ref = _fmt_ref(a_code, a_name)
            c_ref = _fmt_ref(c_row["data_acct_code"], c_row["data_acct_name"])
            l_ref = _fmt_ref(l_row["data_acct_code"], l_row["data_acct_name"])
            common_conn.execute(
                "UPDATE data_account SET budget_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (f"{a_ref}*{l_ref}/12", c_row["data_acct_code"]),
            )
            common_conn.execute(
                "UPDATE data_account SET actual_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (f"{c_ref}/{a_ref}*12", l_row["data_acct_code"]),
            )
            updated_formulas += 2
            touched_codes.update({a_code, c_row["data_acct_code"], l_row["data_acct_code"]})

            liability_ftp_contexts.append(
                LiabilityFtpContext(
                    key=a_code,
                    a_code=a_code,
                    c_code=c_row["data_acct_code"],
                    l_code=l_row["data_acct_code"],
                    report_rate_code=report_rate_code,
                    budget_rate=ext_budget_rate + rng.uniform(FTP_SPREAD_MIN, FTP_SPREAD_MAX),
                    actual_rate=ext_actual_rate + rng.uniform(FTP_SPREAD_MIN, FTP_SPREAD_MAX),
                )
            )

        desired_liability_rate_map: dict[str, str] = {}
        for ctx in deposit_contexts:
            report_rate_code = (
                "X1104"
                if any(code.startswith("X01020102") for code in mappings.get(ctx.a_codes[0], set()))
                else "X1103"
            )
            desired_liability_rate_map[ctx.l_code] = report_rate_code
        for ctx in small_deposit_contexts:
            report_rate_code = (
                "X1104"
                if any(code.startswith("X01020102") for code in mappings.get(ctx.a_code, set()))
                else "X1103"
            )
            desired_liability_rate_map[ctx.l_code] = report_rate_code
        for ctx in liability_ftp_contexts:
            desired_liability_rate_map[ctx.l_code] = ctx.report_rate_code

        for data_code, desired_report in desired_liability_rate_map.items():
            for report_code in ("X1103", "X1104"):
                if report_code != desired_report and report_code in mappings.get(data_code, set()):
                    common_conn.execute(
                        "DELETE FROM report_data_mapping WHERE report_acct_code = ? AND data_acct_code = ?",
                        (report_code, data_code),
                    )
                    mappings[data_code].discard(report_code)
            before = common_conn.total_changes
            _ensure_mapping(common_conn, desired_report, data_code)
            if common_conn.total_changes > before:
                created_mappings += 1
                mappings.setdefault(data_code, set()).add(desired_report)

        loan_ftp_contexts: list[AssetFtpContext] = []
        for loan_ctx in loan_contexts:
            product_code = loan_ctx.product_code
            product_name = loan_ctx.product_name
            rows = data_by_product.get(product_code, [])
            code_tokens = [f"<{code} " for code in loan_ctx.a_codes]

            c_candidates = [
                r
                for r in rows
                if r["data_acct_code"].startswith("C")
                and any(code.startswith("X0301010104") for code in mappings.get(r["data_acct_code"], set()))
            ]
            c_row = next(
                (
                    r
                    for r in c_candidates
                    if "FTP" in (r["data_acct_name"] or "")
                    or any(token in (r["budget_formula"] or "") for token in code_tokens)
                ),
                None,
            )
            if not c_row:
                c_code = next_code("C")
                c_name = f"{product_name}贷款内部FTP利息支出"
                _ensure_data_account(common_conn, c_code, c_name, product_code, "金额")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                c_row = next((r for r in rows if r["data_acct_code"] == c_code), None)

            k_candidates = [
                r
                for r in rows
                if r["data_acct_code"].startswith("K")
                and "FTP" in (r["data_acct_name"] or "")
            ]
            k_row = next(
                (
                    r
                    for r in k_candidates
                    if any(token in (r["actual_formula"] or "") for token in code_tokens)
                ),
                None,
            )
            if not k_row:
                k_code = next_code("K")
                k_name = f"{product_name}贷款内部FTP利率_年化"
                _ensure_data_account(common_conn, k_code, k_name, product_code, "百分比")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                k_row = next((r for r in rows if r["data_acct_code"] == k_code), None)

            if not c_row or not k_row:
                raise RuntimeError(f"贷款产品 {product_code} 未能建立FTP C/K科目")

            before = common_conn.total_changes
            _ensure_mapping(common_conn, "X0301010104", c_row["data_acct_code"])
            if common_conn.total_changes > before:
                created_mappings += 1
                mappings.setdefault(c_row["data_acct_code"], set()).add("X0301010104")

            a_refs = "+".join(
                _fmt_ref(code, account_name_by_code.get(code, code)) for code in loan_ctx.a_codes
            )
            a_base_expr = f"({a_refs})"
            c_ref = _fmt_ref(c_row["data_acct_code"], c_row["data_acct_name"])
            k_ref = _fmt_ref(k_row["data_acct_code"], k_row["data_acct_name"])
            ftp_budget_formula = f"{a_base_expr}*{k_ref}/12"
            ftp_actual_formula = f"{c_ref}/{a_base_expr}*12"
            common_conn.execute(
                "UPDATE data_account SET budget_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (ftp_budget_formula, c_row["data_acct_code"]),
            )
            common_conn.execute(
                "UPDATE data_account SET actual_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (ftp_actual_formula, k_row["data_acct_code"]),
            )
            updated_formulas += 2
            touched_codes.update({c_row["data_acct_code"], k_row["data_acct_code"]})

            loan_ftp_contexts.append(
                AssetFtpContext(
                    key=product_code,
                    a_codes=list(loan_ctx.a_codes),
                    c_code=c_row["data_acct_code"],
                    k_code=k_row["data_acct_code"],
                    budget_rate=max(
                        loan_ctx.budget_rate
                        - rng.uniform(FTP_SPREAD_MIN, FTP_SPREAD_MAX),
                        0.0001,
                    ),
                    actual_rate=max(
                        loan_ctx.actual_rate
                        - rng.uniform(FTP_SPREAD_MIN, FTP_SPREAD_MAX),
                        0.0001,
                    ),
                )
            )

        interbank_ftp_contexts: list[AssetFtpContext] = []
        for inter_ctx in interbank_contexts:
            product_code = inter_ctx.product_code
            rows = data_by_product.get(product_code, [])
            a_token = f"<{inter_ctx.a_code} "
            name_core = inter_ctx.a_name.replace("_日均", "").replace("日均", "")

            c_candidates = [
                r
                for r in rows
                if r["data_acct_code"].startswith("C")
                and any(code.startswith("X0301010102") for code in mappings.get(r["data_acct_code"], set()))
            ]
            c_row = next(
                (
                    r
                    for r in c_candidates
                    if a_token in (r["budget_formula"] or "")
                    or name_core in (r["data_acct_name"] or "")
                ),
                None,
            )
            if not c_row:
                c_code = next_code("C")
                c_name = f"{name_core}内部FTP利息支出"
                _ensure_data_account(common_conn, c_code, c_name, product_code, "金额")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                c_row = next((r for r in rows if r["data_acct_code"] == c_code), None)

            k_candidates = [
                r
                for r in rows
                if r["data_acct_code"].startswith("K")
                and "FTP" in (r["data_acct_name"] or "")
            ]
            k_row = next(
                (
                    r
                    for r in k_candidates
                    if a_token in (r["actual_formula"] or "")
                ),
                None,
            )
            if not k_row:
                k_code = next_code("K")
                k_name = f"{name_core}内部FTP利率_年化"
                _ensure_data_account(common_conn, k_code, k_name, product_code, "百分比")
                created_accounts += 1
                rows = _fetch_all(
                    common_conn,
                    """
                    SELECT data_acct_code, data_acct_name, product_code, value_type, budget_formula, actual_formula
                    FROM data_account WHERE product_code = ? ORDER BY data_acct_code
                    """,
                    (product_code,),
                )
                data_by_product[product_code] = rows
                k_row = next((r for r in rows if r["data_acct_code"] == k_code), None)

            if not c_row or not k_row:
                raise RuntimeError(f"同业资产科目 {inter_ctx.a_code} 未能建立FTP C/K科目")

            before = common_conn.total_changes
            _ensure_mapping(common_conn, "X0301010102", c_row["data_acct_code"])
            if common_conn.total_changes > before:
                created_mappings += 1
                mappings.setdefault(c_row["data_acct_code"], set()).add("X0301010102")

            a_ref = _fmt_ref(inter_ctx.a_code, inter_ctx.a_name)
            c_ref = _fmt_ref(c_row["data_acct_code"], c_row["data_acct_name"])
            k_ref = _fmt_ref(k_row["data_acct_code"], k_row["data_acct_name"])
            ftp_budget_formula = f"{a_ref}*{k_ref}/12"
            ftp_actual_formula = f"{c_ref}/{a_ref}*12"
            common_conn.execute(
                "UPDATE data_account SET budget_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (ftp_budget_formula, c_row["data_acct_code"]),
            )
            common_conn.execute(
                "UPDATE data_account SET actual_formula = ?, need_calc = 1 WHERE data_acct_code = ?",
                (ftp_actual_formula, k_row["data_acct_code"]),
            )
            updated_formulas += 2
            touched_codes.update({c_row["data_acct_code"], k_row["data_acct_code"]})

            interbank_ftp_contexts.append(
                AssetFtpContext(
                    key=inter_ctx.a_code,
                    a_codes=[inter_ctx.a_code],
                    c_code=c_row["data_acct_code"],
                    k_code=k_row["data_acct_code"],
                    budget_rate=max(
                        inter_ctx.budget_rate
                        - rng.uniform(FTP_SPREAD_MIN, FTP_SPREAD_MAX),
                        0.0001,
                    ),
                    actual_rate=max(
                        inter_ctx.actual_rate
                        - rng.uniform(FTP_SPREAD_MIN, FTP_SPREAD_MAX),
                        0.0001,
                    ),
                )
            )

        common_conn.commit()

        period_rows = _fetch_all(
            common_conn,
            "SELECT period_id FROM period WHERE year = ? ORDER BY period_id",
            (f"Y{settings.budget_year}",),
        )
        period_ids = [int(r["period_id"]) for r in period_rows]
        if not period_ids:
            raise RuntimeError("未找到预算年度期间数据")

        version_row = budget_conn.execute("SELECT MAX(version_id) FROM version").fetchone()
        version_id = int(version_row[0] or 1)

        target_codes: set[str] = set()
        for ctx in loan_contexts:
            target_codes.update(ctx.a_codes)
            target_codes.add(ctx.c_code)
            target_codes.add(ctx.k_code)
        for ctx in deposit_contexts:
            target_codes.update(ctx.a_codes)
            target_codes.add(ctx.c_code)
            target_codes.add(ctx.l_code)
        for ctx in interbank_contexts:
            target_codes.add(ctx.a_code)
            target_codes.add(ctx.c_code)
            target_codes.add(ctx.k_code)
        for ctx in loan_ftp_contexts:
            target_codes.update(ctx.a_codes)
            target_codes.add(ctx.c_code)
            target_codes.add(ctx.k_code)
        for ctx in interbank_ftp_contexts:
            target_codes.update(ctx.a_codes)
            target_codes.add(ctx.c_code)
            target_codes.add(ctx.k_code)
        for ctx in small_deposit_contexts:
            target_codes.add(ctx.a_code)
            target_codes.add(ctx.c_code)
            target_codes.add(ctx.l_code)
        for ctx in liability_ftp_contexts:
            target_codes.add(ctx.a_code)
            target_codes.add(ctx.c_code)
            target_codes.add(ctx.l_code)

        existing_keys = set(
            (r["data_acct_code"], int(r["period_id"]), int(r["budget_actual"]))
            for r in _fetch_all(
                budget_conn,
                f"""
                SELECT data_acct_code, period_id, budget_actual
                FROM budget_data
                WHERE version_id = ?
                  AND data_acct_code IN ({",".join("?" for _ in target_codes)})
                """,
                (version_id, *sorted(target_codes)),
            )
        ) if target_codes else set()

        budget_inserted = 0
        budget_updated = 0

        loan_product_weights = _norm_weights([rng.uniform(0.8, 1.4) for _ in loan_contexts]) if loan_contexts else []
        deposit_product_weights = _norm_weights([rng.uniform(0.8, 1.4) for _ in deposit_contexts]) if deposit_contexts else []
        interbank_weights = _norm_weights([rng.uniform(0.8, 1.4) for _ in interbank_contexts]) if interbank_contexts else []
        loan_ftp_by_key = {ctx.key: ctx for ctx in loan_ftp_contexts}
        interbank_ftp_by_key = {ctx.key: ctx for ctx in interbank_ftp_contexts}
        loan_a_weights = {
            ctx.product_code: _norm_weights([rng.uniform(0.8, 1.2) for _ in ctx.a_codes]) for ctx in loan_contexts
        }
        deposit_a_weights = {
            ctx.product_code: _norm_weights([rng.uniform(0.8, 1.2) for _ in ctx.a_codes]) for ctx in deposit_contexts
        }

        for period_id in period_ids:
            liability_a_values: dict[tuple[str, int], float] = {}
            asset_budget = ASSET_SCALE * (1 + rng.uniform(-0.02, 0.02))
            liability_budget = LIABILITY_SCALE * (1 + rng.uniform(-0.02, 0.02))
            asset_actual = ASSET_SCALE * (1 + rng.uniform(-0.02, 0.02))
            liability_actual = LIABILITY_SCALE * (1 + rng.uniform(-0.02, 0.02))

            loan_budget_total = asset_budget * LOAN_ASSET_RATIO
            loan_actual_total = asset_actual * LOAN_ASSET_RATIO
            interbank_budget_total = asset_budget * INTERBANK_ASSET_RATIO
            interbank_actual_total = asset_actual * INTERBANK_ASSET_RATIO
            deposit_budget_total = liability_budget * DEPOSIT_LIABILITY_RATIO
            deposit_actual_total = liability_actual * DEPOSIT_LIABILITY_RATIO

            if loan_contexts:
                raw_budget = [w * (1 + rng.uniform(-0.04, 0.04)) for w in loan_product_weights]
                raw_actual = [w * (1 + rng.uniform(-0.04, 0.04)) for w in loan_product_weights]
                budget_weights = _norm_weights(raw_budget)
                actual_weights = _norm_weights(raw_actual)
                for idx, ctx in enumerate(loan_contexts):
                    product_budget_avg = loan_budget_total * budget_weights[idx]
                    product_actual_avg = loan_actual_total * actual_weights[idx]
                    sub_weights = loan_a_weights[ctx.product_code]
                    budget_sum_a = 0.0
                    actual_sum_a = 0.0
                    for j, a_code in enumerate(ctx.a_codes):
                        a_budget = product_budget_avg * sub_weights[j]
                        a_actual = product_actual_avg * sub_weights[j]
                        for budget_actual, value in ((0, a_budget), (1, a_actual)):
                            liability_a_values[(a_code, budget_actual)] = value
                            key = (a_code, period_id, budget_actual)
                            if key in existing_keys:
                                budget_updated += 1
                            else:
                                existing_keys.add(key)
                                budget_inserted += 1
                            _upsert_budget_data(budget_conn, a_code, period_id, budget_actual, version_id, value)
                        budget_sum_a += a_budget
                        actual_sum_a += a_actual

                    c_budget = budget_sum_a * ctx.budget_rate / 12 / 1.06
                    c_actual = actual_sum_a * ctx.actual_rate / 12 / 1.06
                    k_budget = ctx.budget_rate
                    k_actual = ctx.actual_rate

                    for data_code, budget_val, actual_val in (
                        (ctx.c_code, c_budget, c_actual),
                        (ctx.k_code, k_budget, k_actual),
                    ):
                        for budget_actual, value in ((0, budget_val), (1, actual_val)):
                            key = (data_code, period_id, budget_actual)
                            if key in existing_keys:
                                budget_updated += 1
                            else:
                                existing_keys.add(key)
                                budget_inserted += 1
                            _upsert_budget_data(budget_conn, data_code, period_id, budget_actual, version_id, value)

                    ftp_ctx = loan_ftp_by_key.get(ctx.product_code)
                    if ftp_ctx:
                        ftp_budget = budget_sum_a * ftp_ctx.budget_rate / 12
                        ftp_actual = actual_sum_a * ftp_ctx.actual_rate / 12
                        for data_code, budget_val, actual_val in (
                            (ftp_ctx.c_code, ftp_budget, ftp_actual),
                            (ftp_ctx.k_code, ftp_ctx.budget_rate, ftp_ctx.actual_rate),
                        ):
                            for budget_actual, value in ((0, budget_val), (1, actual_val)):
                                key = (data_code, period_id, budget_actual)
                                if key in existing_keys:
                                    budget_updated += 1
                                else:
                                    existing_keys.add(key)
                                    budget_inserted += 1
                                _upsert_budget_data(
                                    budget_conn,
                                    data_code,
                                    period_id,
                                    budget_actual,
                                    version_id,
                                    value,
                                )

            if deposit_contexts:
                raw_budget = [w * (1 + rng.uniform(-0.04, 0.04)) for w in deposit_product_weights]
                raw_actual = [w * (1 + rng.uniform(-0.04, 0.04)) for w in deposit_product_weights]
                budget_weights = _norm_weights(raw_budget)
                actual_weights = _norm_weights(raw_actual)
                for idx, ctx in enumerate(deposit_contexts):
                    product_budget_avg = deposit_budget_total * budget_weights[idx]
                    product_actual_avg = deposit_actual_total * actual_weights[idx]
                    sub_weights = deposit_a_weights[ctx.product_code]
                    budget_sum_a = 0.0
                    actual_sum_a = 0.0
                    for j, a_code in enumerate(ctx.a_codes):
                        a_budget = product_budget_avg * sub_weights[j]
                        a_actual = product_actual_avg * sub_weights[j]
                        for budget_actual, value in ((0, a_budget), (1, a_actual)):
                            key = (a_code, period_id, budget_actual)
                            if key in existing_keys:
                                budget_updated += 1
                            else:
                                existing_keys.add(key)
                                budget_inserted += 1
                            _upsert_budget_data(budget_conn, a_code, period_id, budget_actual, version_id, value)
                        budget_sum_a += a_budget
                        actual_sum_a += a_actual

                    c_budget = budget_sum_a * ctx.budget_rate / 12
                    c_actual = actual_sum_a * ctx.actual_rate / 12
                    l_budget = ctx.budget_rate
                    l_actual = ctx.actual_rate

                    for data_code, budget_val, actual_val in (
                        (ctx.c_code, c_budget, c_actual),
                        (ctx.l_code, l_budget, l_actual),
                    ):
                        for budget_actual, value in ((0, budget_val), (1, actual_val)):
                            key = (data_code, period_id, budget_actual)
                            if key in existing_keys:
                                budget_updated += 1
                            else:
                                existing_keys.add(key)
                                budget_inserted += 1
                            _upsert_budget_data(budget_conn, data_code, period_id, budget_actual, version_id, value)

            if interbank_contexts:
                raw_budget = [w * (1 + rng.uniform(-0.04, 0.04)) for w in interbank_weights]
                raw_actual = [w * (1 + rng.uniform(-0.04, 0.04)) for w in interbank_weights]
                budget_weights = _norm_weights(raw_budget)
                actual_weights = _norm_weights(raw_actual)
                for idx, ctx in enumerate(interbank_contexts):
                    a_budget = interbank_budget_total * budget_weights[idx]
                    a_actual = interbank_actual_total * actual_weights[idx]
                    c_budget = a_budget * ctx.budget_rate / 12
                    c_actual = a_actual * ctx.actual_rate / 12
                    k_budget = ctx.budget_rate
                    k_actual = ctx.actual_rate
                    for data_code, budget_val, actual_val in (
                        (ctx.a_code, a_budget, a_actual),
                        (ctx.c_code, c_budget, c_actual),
                        (ctx.k_code, k_budget, k_actual),
                    ):
                        for budget_actual, value in ((0, budget_val), (1, actual_val)):
                            key = (data_code, period_id, budget_actual)
                            if key in existing_keys:
                                budget_updated += 1
                            else:
                                existing_keys.add(key)
                                budget_inserted += 1
                            _upsert_budget_data(budget_conn, data_code, period_id, budget_actual, version_id, value)

                    ftp_ctx = interbank_ftp_by_key.get(ctx.a_code)
                    if ftp_ctx:
                        ftp_budget = a_budget * ftp_ctx.budget_rate / 12
                        ftp_actual = a_actual * ftp_ctx.actual_rate / 12
                        for data_code, budget_val, actual_val in (
                            (ftp_ctx.c_code, ftp_budget, ftp_actual),
                            (ftp_ctx.k_code, ftp_ctx.budget_rate, ftp_ctx.actual_rate),
                        ):
                            for budget_actual, value in ((0, budget_val), (1, actual_val)):
                                key = (data_code, period_id, budget_actual)
                                if key in existing_keys:
                                    budget_updated += 1
                                else:
                                    existing_keys.add(key)
                                    budget_inserted += 1
                                _upsert_budget_data(
                                    budget_conn,
                                    data_code,
                                    period_id,
                                    budget_actual,
                                    version_id,
                                    value,
                                )

            for ctx in small_deposit_contexts:
                a_budget = SMALL_DEPOSIT_SCALE * (1 + rng.uniform(-0.15, 0.15))
                a_actual = SMALL_DEPOSIT_SCALE * (1 + rng.uniform(-0.15, 0.15))
                c_budget = a_budget * ctx.budget_rate / 12
                c_actual = a_actual * ctx.actual_rate / 12
                for data_code, budget_val, actual_val in (
                    (ctx.a_code, a_budget, a_actual),
                    (ctx.c_code, c_budget, c_actual),
                    (ctx.l_code, ctx.budget_rate, ctx.actual_rate),
                ):
                    for budget_actual, value in ((0, budget_val), (1, actual_val)):
                        if data_code == ctx.a_code:
                            liability_a_values[(ctx.a_code, budget_actual)] = value
                        key = (data_code, period_id, budget_actual)
                        if key in existing_keys:
                            budget_updated += 1
                        else:
                            existing_keys.add(key)
                            budget_inserted += 1
                        _upsert_budget_data(
                            budget_conn,
                            data_code,
                            period_id,
                            budget_actual,
                            version_id,
                            value,
                        )

            for ctx in liability_ftp_contexts:
                a_budget = liability_a_values.get((ctx.a_code, 0))
                a_actual = liability_a_values.get((ctx.a_code, 1))
                if a_budget is None or a_actual is None:
                    continue
                c_budget = a_budget * ctx.budget_rate / 12
                c_actual = a_actual * ctx.actual_rate / 12
                for data_code, budget_val, actual_val in (
                    (ctx.c_code, c_budget, c_actual),
                    (ctx.l_code, ctx.budget_rate, ctx.actual_rate),
                ):
                    for budget_actual, value in ((0, budget_val), (1, actual_val)):
                        key = (data_code, period_id, budget_actual)
                        if key in existing_keys:
                            budget_updated += 1
                        else:
                            existing_keys.add(key)
                            budget_inserted += 1
                        _upsert_budget_data(
                            budget_conn,
                            data_code,
                            period_id,
                            budget_actual,
                            version_id,
                            value,
                        )

        stale_ftp_rate_rows = _fetch_all(
            common_conn,
            """
            SELECT d.data_acct_code
            FROM data_account d
            WHERE d.product_code = 'Z9000'
              AND d.data_acct_name LIKE '%内部FTP利率_年化'
              AND NOT EXISTS (
                    SELECT 1
                    FROM data_account x
                    WHERE (x.budget_formula LIKE '%<' || d.data_acct_code || ' %')
                       OR (x.actual_formula LIKE '%<' || d.data_acct_code || ' %')
              )
            ORDER BY d.data_acct_code
            """,
        )
        stale_ftp_rate_codes = [r["data_acct_code"] for r in stale_ftp_rate_rows]
        if stale_ftp_rate_codes:
            placeholders = ",".join("?" for _ in stale_ftp_rate_codes)
            common_conn.execute(
                f"DELETE FROM report_data_mapping WHERE data_acct_code IN ({placeholders})",
                tuple(stale_ftp_rate_codes),
            )
            common_conn.execute(
                f"DELETE FROM data_account WHERE data_acct_code IN ({placeholders})",
                tuple(stale_ftp_rate_codes),
            )
            budget_conn.execute(
                f"DELETE FROM budget_data WHERE data_acct_code IN ({placeholders})",
                tuple(stale_ftp_rate_codes),
            )
            for code in stale_ftp_rate_codes:
                target_codes.discard(code)

        common_conn.commit()
        budget_conn.commit()

        loan_summary = ", ".join(f"{ctx.product_code}:{ctx.product_name}" for ctx in loan_contexts)
        deposit_summary = ", ".join(f"{ctx.product_code}:{ctx.product_name}" for ctx in deposit_contexts)
        print("=== 执行完成 ===")
        print(f"贷款产品数: {len(loan_contexts)}")
        print(f"存款产品数: {len(deposit_contexts)}")
        print(f"同业资产科目数: {len(interbank_contexts)}")
        print(f"贷款FTP科目数: {len(loan_ftp_contexts)}")
        print(f"同业FTP科目数: {len(interbank_ftp_contexts)}")
        print(f"小规模存款科目数: {len(small_deposit_contexts)}")
        print(f"负债FTP科目数: {len(liability_ftp_contexts)}")
        print(f"新增数据科目: {created_accounts}")
        print(f"新增映射关系: {created_mappings}")
        print(f"覆盖公式条数: {updated_formulas}")
        print(f"BudgetData upsert 插入: {budget_inserted}")
        print(f"BudgetData upsert 更新: {budget_updated}")
        print(f"清理历史FTP重复利率科目: {len(stale_ftp_rate_codes)}")
        print(f"目标版本: version_id={version_id}, 年度=Y{settings.budget_year}")
        print(f"贷款产品清单: {loan_summary}")
        print(f"存款产品清单: {deposit_summary}")
        print(f"触达数据科目数: {len(touched_codes)}")


if __name__ == "__main__":
    main()
