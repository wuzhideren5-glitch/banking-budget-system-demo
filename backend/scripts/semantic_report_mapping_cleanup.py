from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[2]
COMMON_DB = ROOT / "data" / "common.db"


def _tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / f"common_before_semantic_report_mapping_cleanup_{_tag()}.db"
    shutil.copy2(db_path, out)
    return out


def _fetch_maps(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT m.report_acct_code, r.report_acct_name, r.parent_code,
                   m.data_acct_code, d.data_acct_name, d.value_type
            FROM report_data_mapping m
            JOIN report_account r ON r.report_acct_code = m.report_acct_code
            JOIN data_account d ON d.data_acct_code = m.data_acct_code
            ORDER BY m.report_acct_code, m.data_acct_code
            """
        )
    ]


def _descendants_by_code(conn: sqlite3.Connection) -> dict[str, set[str]]:
    rows = list(conn.execute("SELECT report_acct_code, parent_code FROM report_account"))
    children: dict[str, list[str]] = defaultdict(list)
    for code, parent in rows:
        if parent:
            children[str(parent)].append(str(code))

    def walk(code: str) -> set[str]:
        result: set[str] = set()
        for child in children.get(code, []):
            result.add(child)
            result.update(walk(child))
        return result

    return {str(code): walk(str(code)) for code, _ in rows}


def _has_account(conn: sqlite3.Connection, code: str) -> bool:
    return conn.execute("SELECT 1 FROM report_account WHERE report_acct_code = ?", (code,)).fetchone() is not None


def _ensure_report_account(
    conn: sqlite3.Connection,
    changes: list[dict[str, Any]],
    *,
    code: str,
    name: str,
    parent_code: str,
    level: int,
    is_summary: int = 1,
    is_minus: int = 1,
) -> None:
    row = conn.execute(
        "SELECT report_acct_name, parent_code, level, is_summary, is_minus FROM report_account WHERE report_acct_code = ?",
        (code,),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO report_account (
              report_acct_code, report_acct_name, parent_code, is_summary, is_minus, level, is_leaf, remark
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (code, name, parent_code, is_summary, is_minus, level, "语义清洗新增"),
        )
        changes.append({"action": "insert_report", "report_acct_code": code, "after": name, "reason": "补充缺失报告科目"})
        return
    old_name, old_parent, old_level, old_summary, old_minus = row
    if (old_name, old_parent, int(old_level), int(old_summary), int(old_minus)) != (
        name,
        parent_code,
        level,
        is_summary,
        is_minus,
    ):
        conn.execute(
            """
            UPDATE report_account
            SET report_acct_name = ?, parent_code = ?, level = ?, is_summary = ?, is_minus = ?
            WHERE report_acct_code = ?
            """,
            (name, parent_code, level, is_summary, is_minus, code),
        )
        changes.append(
            {
                "action": "update_report",
                "report_acct_code": code,
                "before": old_name,
                "after": name,
                "reason": "报告科目名称或属性与语义不一致",
            }
        )


def _insert_mapping(conn: sqlite3.Connection, changes: list[dict[str, Any]], report: str, data: str, reason: str) -> None:
    if not _has_account(conn, report):
        changes.append({"action": "skip_insert", "report_acct_code": report, "data_acct_code": data, "reason": "报告科目不存在"})
        return
    if conn.execute("SELECT 1 FROM data_account WHERE data_acct_code = ?", (data,)).fetchone() is None:
        changes.append({"action": "skip_insert", "report_acct_code": report, "data_acct_code": data, "reason": "数据科目不存在"})
        return
    exists = conn.execute(
        "SELECT 1 FROM report_data_mapping WHERE report_acct_code = ? AND data_acct_code = ?",
        (report, data),
    ).fetchone()
    if exists:
        return
    conn.execute("INSERT INTO report_data_mapping(report_acct_code, data_acct_code) VALUES (?, ?)", (report, data))
    changes.append({"action": "insert_mapping", "report_acct_code": report, "data_acct_code": data, "reason": reason})


def _delete_mapping(conn: sqlite3.Connection, changes: list[dict[str, Any]], report: str, data: str, reason: str) -> None:
    cur = conn.execute(
        "DELETE FROM report_data_mapping WHERE report_acct_code = ? AND data_acct_code = ?",
        (report, data),
    )
    if cur.rowcount:
        changes.append({"action": "delete_mapping", "report_acct_code": report, "data_acct_code": data, "reason": reason})


def _refresh_leaf_flags(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE report_account
        SET is_leaf = CASE
            WHEN EXISTS (
                SELECT 1 FROM report_account child
                WHERE child.parent_code = report_account.report_acct_code
            )
            THEN 0 ELSE 1
        END
        """
    )


def _write_audit(path: Path, summary: list[tuple[str, Any]], changes: list[dict[str, Any]], residuals: list[dict[str, Any]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "汇总"
    ws.append(["指标", "内容"])
    for row in summary:
        ws.append(list(row))

    for title, rows in (("变更明细", changes), ("剩余待复核", residuals)):
        sheet = wb.create_sheet(title)
        headers = sorted({key for row in rows for key in row.keys()})
        if not headers:
            sheet.append(["无记录"])
            continue
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(h, "") for h in headers])
    wb.save(path)


def cleanup(db_path: Path = COMMON_DB, dry_run: bool = False) -> dict[str, Any]:
    backup_path = None if dry_run else _backup(db_path)
    conn = sqlite3.connect(db_path)
    changes: list[dict[str, Any]] = []
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN")

        _ensure_report_account(
            conn,
            changes,
            code="X0303",
            name="业务及管理费",
            parent_code="X03",
            level=2,
            is_summary=1,
            is_minus=1,
        )
        _ensure_report_account(
            conn,
            changes,
            code="X0306",
            name="税金及附加",
            parent_code="X03",
            level=2,
            is_summary=1,
            is_minus=1,
        )
        _ensure_report_account(
            conn,
            changes,
            code="X0502",
            name="管理贷款余额",
            parent_code="X05",
            level=2,
            is_summary=1,
            is_minus=0,
        )

        # 1. Structural rule: if the same data account is mapped to both an
        # ancestor and its descendant, keep the most detailed descendant.
        descendants = _descendants_by_code(conn)
        by_data: dict[str, set[str]] = defaultdict(set)
        for row in _fetch_maps(conn):
            by_data[str(row["data_acct_code"])].add(str(row["report_acct_code"]))
        for data_code, reports in by_data.items():
            for report in list(reports):
                if descendants.get(report, set()) & reports:
                    _delete_mapping(conn, changes, report, data_code, "同一数据科目同时挂父子报告科目，删除父级映射避免双算")

        # Refresh snapshot after structural cleanup.
        rows = _fetch_maps(conn)

        # 2. Interest income / expense semantics.
        for row in rows:
            data = str(row["data_acct_code"])
            dname = str(row["data_acct_name"] or "")
            report = str(row["report_acct_code"])
            if "利息收入" in dname and "FTP利息收入" not in dname and any(key in dname for key in ("贷款", "票据", "福费廷")):
                _insert_mapping(conn, changes, "X0301010103", data, "信贷/票据/福费廷利息收入应归入信贷业务外部利息收入")
                if report == "X0301010101":
                    _delete_mapping(conn, changes, report, data, "信贷类外部利息收入不再挂通用外部利息收入，避免兄弟节点双算")
            if "FTP利息收入" in dname and any(key in dname for key in ("存款", "储蓄", "单位活期", "单位定期")):
                _insert_mapping(conn, changes, "X0301010201", data, "负债业务FTP收入应归入负债业务利息净收入")
                if report == "X0301010107":
                    _delete_mapping(conn, changes, report, data, "存款FTP收入不应挂资产业务分支")
            if "外部利息支出" in dname:
                _insert_mapping(conn, changes, "X0301010202", data, "外部利息支出应归入负债业务外部利息支出")
                if report in {"X0301010106", "X0301010108"}:
                    _delete_mapping(conn, changes, report, data, "外部利息支出不应挂资产业务分支")

        # 3. Risk cost, tax, and other business income/expense.
        for row in _fetch_maps(conn):
            data = str(row["data_acct_code"])
            dname = str(row["data_acct_name"] or "")
            report = str(row["report_acct_code"])
            if "风险成本" in dname or "减值损失" in dname:
                if "同业" in dname:
                    target = "X030202"
                elif "其他" in dname:
                    target = "X030203"
                else:
                    target = "X030201"
                _insert_mapping(conn, changes, target, data, "风险成本/减值损失按风险成本报告科目归类")
                if report in {"X03010201", "X03010202"}:
                    _delete_mapping(conn, changes, report, data, "风险成本不应挂手续费净收入")
            if "税金及附加" in dname or "营业税金" in dname:
                _insert_mapping(conn, changes, "X0306", data, "税金及附加应归入独立税金及附加报告科目")
                if report in {"X0302", "X0303"}:
                    _delete_mapping(conn, changes, report, data, "税金及附加不应挂资产减值损失或业务及管理费")
            if "其他业务支出" in dname:
                _insert_mapping(conn, changes, "X030402", data, "其他业务支出应归入其他业务支出")
                if report == "X030401":
                    _delete_mapping(conn, changes, report, data, "其他业务支出不应挂其他业务收入")

        # 4. HR IT / non-IT split.
        hr_targets = {
            "C7001": "X0303010201",
            "C7002": "X0303010101",
            "C7011": "X0303010201",
            "C7012": "X0303010101",
            "C7021": "X0303010202",
            "C7022": "X0303010102",
            "C7031": "X0303010202",
            "C7032": "X0303010102",
        }
        wrong_hr_pairs = {
            ("X0303010101", "C7001"),
            ("X0303010102", "C7011"),
            ("X0303010102", "C7012"),
        }
        for data, target in hr_targets.items():
            _insert_mapping(conn, changes, target, data, "按IT/非IT与常规/特别奖金语义修正人力费用归属")
        for report, data in wrong_hr_pairs:
            _delete_mapping(conn, changes, report, data, "人力费用IT/非IT或常规/特别语义错挂")

        # 5. Management loan / asset time-grain mismatches.
        for row in _fetch_maps(conn):
            data = str(row["data_acct_code"])
            dname = str(row["data_acct_name"] or "")
            report = str(row["report_acct_code"])
            rname = str(row["report_acct_name"] or "")
            if report == "X0501" and "时点余额" in dname:
                _delete_mapping(conn, changes, report, data, "个人金融管理贷款日均不应挂时点余额")
            if report == "X0601" and "日均" in dname:
                _delete_mapping(conn, changes, report, data, "管理资产时点余额不应挂日均数据")
            if "日均" in rname and "时点余额" in dname and report not in {"X0502"}:
                _delete_mapping(conn, changes, report, data, "日均报告科目不应挂时点余额")

        # 6. Ensure daily management loan inputs are available in the daily node.
        for data in ("E1210", "E1211", "E1212", "E1213"):
            _insert_mapping(conn, changes, "X0501", data, "个人金融管理贷款日均应使用日均类管理贷款数据")

        _refresh_leaf_flags(conn)

        residuals = _semantic_residuals(conn)
        duplicate_pairs = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT report_acct_code, data_acct_code, COUNT(*) c
                FROM report_data_mapping
                GROUP BY report_acct_code, data_acct_code
                HAVING c > 1
            )
            """
        ).fetchone()[0]
        orphan_report = conn.execute(
            """
            SELECT COUNT(*)
            FROM report_data_mapping m
            LEFT JOIN report_account r ON r.report_acct_code = m.report_acct_code
            WHERE r.report_acct_code IS NULL
            """
        ).fetchone()[0]
        orphan_data = conn.execute(
            """
            SELECT COUNT(*)
            FROM report_data_mapping m
            LEFT JOIN data_account d ON d.data_acct_code = m.data_acct_code
            WHERE d.data_acct_code IS NULL
            """
        ).fetchone()[0]

        if dry_run:
            conn.rollback()
        else:
            conn.execute(
                """
                INSERT INTO operation_log(user_id, action_type, action_desc, target_table, affected_rows,
                                          before_data, after_data, ip_address, create_time)
                VALUES (?, 'FIX', ?, 'report_data_mapping', ?, ?, ?, 'local-script', datetime('now'))
                """,
                (
                    "codex",
                    f"按语义清洗报告-数据映射，变更{len(changes)}项，剩余复核{len(residuals)}项",
                    len(changes),
                    str({"backup": str(backup_path)}),
                    str({"changes": len(changes), "residuals": len(residuals)}),
                ),
            )
            conn.commit()

        audit_path = ROOT / "data" / f"semantic_report_mapping_cleanup_{_tag()}.xlsx"
        summary = [
            ("模式", "dry-run" if dry_run else "applied"),
            ("备份文件", str(backup_path) if backup_path else ""),
            ("变更数", len(changes)),
            ("剩余待复核", len(residuals)),
            ("重复映射", duplicate_pairs),
            ("孤儿报告映射", orphan_report),
            ("孤儿数据映射", orphan_data),
        ]
        _write_audit(audit_path, summary, changes, residuals)
        return {
            "backup_path": str(backup_path) if backup_path else None,
            "audit_path": str(audit_path),
            "changes": len(changes),
            "residuals": len(residuals),
            "duplicates": duplicate_pairs,
            "orphan_report": orphan_report,
            "orphan_data": orphan_data,
            "dry_run": dry_run,
        }
    finally:
        conn.close()


def _semantic_residuals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    for row in _fetch_maps(conn):
        report = str(row["report_acct_code"])
        rname = str(row["report_acct_name"] or "")
        data = str(row["data_acct_code"])
        dname = str(row["data_acct_name"] or "")
        value_type = str(row["value_type"] or "")
        reason = ""
        if "支出" in rname and "收入" in dname:
            reason = "支出报告科目挂收入数据"
        elif "收入" in rname and "支出" in dname:
            reason = "收入报告科目挂支出数据"
        elif ("收益率" in rname or "付息率" in rname) and value_type != "百分比":
            reason = "利率类报告科目挂非百分比数据"
        elif "时点" in rname and "日均" in dname:
            reason = "时点报告科目挂日均数据"
        elif "日均" in rname and "时点" in dname:
            reason = "日均报告科目挂时点数据"
        if reason:
            residuals.append(
                {
                    "report_acct_code": report,
                    "report_acct_name": rname,
                    "data_acct_code": data,
                    "data_acct_name": dname,
                    "value_type": value_type,
                    "reason": reason,
                }
            )
    return residuals


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="按金融语义清洗报告科目与数据科目映射")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = cleanup(dry_run=args.dry_run)
    for key, value in result.items():
        print(f"{key}: {value}")
