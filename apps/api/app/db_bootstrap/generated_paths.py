"""Current generated-file path contract checks for Smart Report and Smart PPT."""
from __future__ import annotations

import sqlite3
from pathlib import Path


GENERATED_PATH_TABLES = (
    ("smart_report_template", "template_id", "file_path", "smart_report_templates"),
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


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_generated_file_paths(conn: sqlite3.Connection, data_dir: Path) -> None:
    """Reject generated-file rows that still point outside the current DATA_DIR."""
    invalid_paths: list[str] = []
    for table_name, id_column, path_column, folder_name in GENERATED_PATH_TABLES:
        if not _table_exists(conn, table_name):
            continue
        cur = conn.execute(
            f"""
            SELECT {id_column}, {path_column}
            FROM {table_name}
            WHERE {path_column} IS NOT NULL AND TRIM({path_column}) != ''
            """
        )
        folder_root = data_dir / folder_name
        for row_id, raw_path in cur.fetchall():
            text = str(raw_path or "").strip()
            path = Path(text)
            if (
                not path.is_absolute()
                or not path.exists()
                or not _is_under(path, folder_root)
            ):
                invalid_paths.append(f"{table_name}.{row_id}:{text}")

    if invalid_paths:
        raise RuntimeError(
            "Smart Report/PPT 生成文件路径不是当前 DATA_DIR 合同，系统不再自动迁移："
            + ", ".join(invalid_paths[:10])
        )
