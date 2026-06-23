#!/usr/bin/env python3
"""Create the configured MySQL database and initialize runtime tables."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import settings  # noqa: E402
from app.init_db import ensure_databases  # noqa: E402

SCRIPTS_ROOT = API_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from prepare_deploy_generated_paths import prepare_generated_paths  # noqa: E402


def _quote_identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name or ""):
        raise ValueError(f"Unsafe MySQL database name: {name!r}")
    return f"`{name}`"


def main() -> int:
    db_name = settings.MYSQL_DATABASE
    conn = pymysql.connect(
        host=settings.MYSQL_HOST,
        port=int(settings.MYSQL_PORT),
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD or "",
        charset="utf8mb4",
        autocommit=True,
        init_command="SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS {_quote_identifier(db_name)} "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()

    prepare_generated_paths(settings.data_dir)
    ensure_databases()
    print(f"OK mysql_database={db_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
