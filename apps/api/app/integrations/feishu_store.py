"""飞书用户与系统用户的绑定（common.db，同步 sqlite）。"""

from __future__ import annotations

import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from datetime import datetime, timezone
from pathlib import Path

from app.core.passwords import verify_daily_password


def get_user_id_for_open_id(common_db: Path, open_id: str) -> int | None:
    conn = sqlite3.connect(common_db)
    try:
        cur = conn.execute(
            "SELECT user_id FROM feishu_user_binding WHERE open_id = ?",
            (open_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def _upsert_binding_with_conn(conn: sqlite3.Connection, open_id: str, user_id: int, now: str) -> None:
    conn.execute(
        """
        INSERT INTO feishu_user_binding (open_id, user_id, create_time)
        VALUES (?, ?, ?)
        ON CONFLICT(open_id) DO UPDATE SET user_id = excluded.user_id, create_time = excluded.create_time
        """,
        (open_id, user_id, now),
    )


def upsert_binding(common_db: Path, open_id: str, user_id: int) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(common_db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _upsert_binding_with_conn(conn, open_id, user_id, now)
        conn.commit()
    finally:
        conn.close()


def delete_binding(common_db: Path, open_id: str) -> bool:
    conn = sqlite3.connect(common_db)
    try:
        cur = conn.execute("DELETE FROM feishu_user_binding WHERE open_id = ?", (open_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def try_bind_with_password(
    common_db: Path, open_id: str, user_name: str, password: str
) -> tuple[bool, str]:
    """使用系统登录名 + 日常登录密码完成绑定。"""
    conn = sqlite3.connect(common_db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.execute(
            """
            SELECT id, daily_login_password
            FROM users
            WHERE user_name = ?
            """,
            (user_name.strip(),),
        )
        row = cur.fetchone()
        if not row:
            return False, "未找到该用户名，请核对后重试。"
        user_id = int(row[0])
        daily_hash = row[1]
        if not verify_daily_password(str(daily_hash or ""), password):
            return False, "密码不正确，绑定失败。"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _upsert_binding_with_conn(conn, open_id, user_id, now)
        conn.commit()
        return True, f"已绑定为系统用户「{user_name.strip()}」，可以开始提问。"
    finally:
        conn.close()


def list_bindings(common_db: Path) -> list[dict[str, str | int]]:
    conn = sqlite3.connect(common_db)
    try:
        cur = conn.execute(
            """
            SELECT f.open_id, f.user_id, u.user_name, f.create_time
            FROM feishu_user_binding f
            JOIN users u ON u.id = f.user_id
            ORDER BY f.create_time DESC
            """
        )
        rows = []
        for r in cur.fetchall():
            rows.append(
                {
                    "open_id": str(r[0]),
                    "user_id": int(r[1]),
                    "user_name": str(r[2]),
                    "create_time": str(r[3]),
                }
            )
        return rows
    finally:
        conn.close()
