from __future__ import annotations

import shutil
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from app.db_paths import common_db_path


def norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return text.replace(" ", "").replace("　", "")


def candidate_code(row_key: str) -> str | None:
    if row_key.startswith("OVERVIEW."):
        return "AA." + row_key[len("OVERVIEW.") :]
    if row_key.startswith("PRODUCT."):
        return row_key[len("PRODUCT.") :]
    return None


def scope_code(display_view: str) -> str | None:
    if display_view == "OVERVIEW":
        return "AA"
    if display_view.startswith("PRODUCT."):
        return display_view[len("PRODUCT.") :]
    return None


def write_report(rows: list[dict[str, str]], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "budget_display_rebind"
    columns = ["status", "row_key", "display_view", "display_name", "candidate_code", "data_acct_name", "reason"]
    ws.append(columns)
    for row in rows:
        ws.append([row.get(col, "") for col in columns])
    wb.save(path)


def main() -> None:
    db = common_db_path()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = db.parents[1] / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"common_before_budget_display_rebind_{timestamp}.db"
    shutil.copy2(db, backup_path)
    output_dir = db.parents[1] / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"budget_display_rebind_{timestamp}.xlsx"

    report_rows: list[dict[str, str]] = []
    bound = 0
    skipped = 0
    with sqlite3.connect(db) as conn:
        account_names = {
            code: name
            for code, name in conn.execute("SELECT data_acct_code, data_acct_name FROM data_account")
        }
        names_by_scope: dict[str, dict[str, list[tuple[str, str]]]] = {}
        for code, name in account_names.items():
            scope = code.split(".", 1)[0]
            names_by_scope.setdefault(scope, {}).setdefault(norm(name), []).append((code, name))
        display_rows = conn.execute(
            """
            SELECT row_key, display_view, display_name
            FROM budget_output_display_item
            WHERE data_acct_code IS NULL
            ORDER BY display_view, sort_order, row_key
            """
        ).fetchall()
        for row_key, display_view, display_name in display_rows:
            candidate = candidate_code(row_key)
            data_name = account_names.get(candidate or "")
            status = "SKIP"
            reason = ""
            if not candidate:
                reason = "row_key无法推导数据科目编码"
            elif not data_name:
                reason = "候选编码不存在于新数据科目体系"
            elif norm(display_name) != norm(data_name):
                reason = "候选编码存在但名称不一致"
            else:
                conn.execute(
                    """
                    UPDATE budget_output_display_item
                    SET data_acct_code = ?,
                        org_product_ref = NULL,
                        org_product_entity_code = NULL,
                        org_product_table_name = NULL,
                        org_product_metric_code = NULL,
                        org_product_metric_name = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE row_key = ?
                    """,
                    (candidate, row_key),
                )
                bound += 1
                status = "BOUND"
                reason = "编码和名称一致"
            if status != "BOUND" and candidate:
                scope = scope_code(display_view)
                scoped_matches = names_by_scope.get(scope or "", {}).get(norm(display_name), [])
                if len(scoped_matches) == 1:
                    matched_code, matched_name = scoped_matches[0]
                    conn.execute(
                        """
                        UPDATE budget_output_display_item
                        SET data_acct_code = ?,
                            org_product_ref = NULL,
                            org_product_entity_code = NULL,
                            org_product_table_name = NULL,
                            org_product_metric_code = NULL,
                            org_product_metric_name = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE row_key = ?
                        """,
                        (matched_code, row_key),
                    )
                    bound += 1
                    status = "BOUND"
                    reason = "同产品范围内名称唯一"
                    candidate = matched_code
                    data_name = matched_name
            if status != "BOUND":
                skipped += 1
            report_rows.append(
                {
                    "status": status,
                    "row_key": row_key,
                    "display_view": display_view,
                    "display_name": display_name,
                    "candidate_code": candidate or "",
                    "data_acct_name": data_name or "",
                    "reason": reason,
                }
            )
        conn.commit()
    write_report(report_rows, report_path)
    print(f"backup={backup_path}")
    print(f"report={report_path}")
    print(f"bound={bound}")
    print(f"skipped={skipped}")


if __name__ == "__main__":
    main()
