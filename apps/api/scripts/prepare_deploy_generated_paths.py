#!/usr/bin/env python3
"""Normalize packaged Smart Report/PPT file paths for the current DATA_DIR."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


TEMPLATE_TABLES = (
    ("smart_report_template", "template_id", "file_path", "smart_report_templates"),
)

OUTPUT_TABLES = (
    ("smart_report_instance", "instance_id", "output_file_path", "smart_report_outputs"),
    ("smart_report_blueprint", "blueprint_id", "output_file_path", "smart_report_outputs"),
    ("smart_ppt_instance", "instance_id", "output_file_path", "smart_report_outputs"),
)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    }


def _normalize_template_paths(
    conn: sqlite3.Connection,
    data_dir: Path,
    *,
    dry_run: bool,
) -> tuple[int, list[str]]:
    changed = 0
    missing: list[str] = []
    for table_name, id_column, path_column, folder_name in TEMPLATE_TABLES:
        if not _table_exists(conn, table_name):
            continue
        rows = conn.execute(
            f"""
            SELECT {id_column}, {path_column}
            FROM {table_name}
            WHERE {path_column} IS NOT NULL AND TRIM({path_column}) != ''
            """
        ).fetchall()
        table_columns = _columns(conn, table_name)
        for row_id, raw_path in rows:
            original = Path(str(raw_path).strip())
            target = data_dir / folder_name / original.name
            if not target.exists():
                missing.append(f"{table_name}.{row_id}:{target}")
                if "status" in table_columns and not dry_run:
                    conn.execute(
                        f"UPDATE {table_name} SET status = 'inactive', {path_column} = '' WHERE {id_column} = ?",
                        (row_id,),
                    )
                elif not dry_run:
                    conn.execute(
                        f"UPDATE {table_name} SET {path_column} = '' WHERE {id_column} = ?",
                        (row_id,),
                    )
                changed += 1
                continue
            target_text = str(target)
            if str(raw_path) != target_text:
                if not dry_run:
                    conn.execute(
                        f"UPDATE {table_name} SET {path_column} = ? WHERE {id_column} = ?",
                        (target_text, row_id),
                    )
                changed += 1
    return changed, missing


def _normalize_output_paths(
    conn: sqlite3.Connection,
    data_dir: Path,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    rewritten = 0
    cleared = 0
    for table_name, id_column, path_column, folder_name in OUTPUT_TABLES:
        if not _table_exists(conn, table_name):
            continue
        rows = conn.execute(
            f"""
            SELECT {id_column}, {path_column}
            FROM {table_name}
            WHERE {path_column} IS NOT NULL AND TRIM({path_column}) != ''
            """
        ).fetchall()
        for row_id, raw_path in rows:
            original = Path(str(raw_path).strip())
            target = data_dir / folder_name / original.name
            if target.exists():
                target_text = str(target)
                if str(raw_path) != target_text:
                    if not dry_run:
                        conn.execute(
                            f"UPDATE {table_name} SET {path_column} = ? WHERE {id_column} = ?",
                            (target_text, row_id),
                        )
                    rewritten += 1
                continue
            if not dry_run:
                conn.execute(
                    f"UPDATE {table_name} SET {path_column} = NULL WHERE {id_column} = ?",
                    (row_id,),
                )
            cleared += 1
    return rewritten, cleared


def prepare_generated_paths(data_dir: Path, *, dry_run: bool = False) -> dict[str, object]:
    data_dir = data_dir.resolve()
    common_db = data_dir / "common.db"
    if not common_db.exists():
        return {
            "common_db": str(common_db),
            "status": "skipped",
            "reason": "common.db not found",
        }

    (data_dir / "smart_report_templates").mkdir(parents=True, exist_ok=True)
    (data_dir / "smart_report_outputs").mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(common_db)
    try:
        template_changed, missing_templates = _normalize_template_paths(
            conn,
            data_dir,
            dry_run=dry_run,
        )
        output_rewritten, output_cleared = _normalize_output_paths(
            conn,
            data_dir,
            dry_run=dry_run,
        )
        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return {
        "common_db": str(common_db),
        "status": "ready",
        "template_changed": template_changed,
        "template_missing": len(missing_templates),
        "output_rewritten": output_rewritten,
        "output_cleared": output_cleared,
        "missing_template_samples": missing_templates[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize packaged Smart Report/PPT file paths for deployment.",
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = prepare_generated_paths(args.data_dir, dry_run=args.dry_run)
    print(
        "[deploy-paths] "
        + " ".join(f"{key}={value}" for key, value in result.items() if key != "missing_template_samples")
    )
    for sample in result.get("missing_template_samples", []):
        print(f"[deploy-paths] missing_template={sample}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
