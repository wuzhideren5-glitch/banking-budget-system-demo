"""Compare-version helpers for Agent budget routing."""
from __future__ import annotations

from pathlib import Path
import re
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from typing import Any

CompareVersionOption = tuple[int, int, int, str]


def is_explicit_year_comparison(query: str) -> bool:
    q = str(query or "")
    if not q:
        return False
    if re.search(r"(预算.?实际|预实|差异)", q):
        return False
    if re.search(r"(?:比较|对比|相比)\s*20\d{2}\s*年?", q):
        return True
    if re.search(r"(?:和|与|跟)\s*20\d{2}\s*年?", q) and re.search(r"(比较|对比|相比|比)", q):
        return True
    years = set(re.findall(r"20\d{2}", q))
    return len(years) >= 2 and bool(re.search(r"(比较|对比|相比|比)", q))


def extract_compare_target_year(query: str) -> int | None:
    q = str(query or "")
    if not q or not is_explicit_year_comparison(q):
        return None
    m = re.search(r"(?:和|与|跟)\s*(20\d{2})\s*年?", q)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:比较|对比|相比)\s*(20\d{2})\s*年?", q)
    if m:
        return int(m.group(1))
    years = [int(y) for y in re.findall(r"20\d{2}", q)]
    if not years:
        return None
    return min(years) if len(set(years)) >= 2 else None


def extract_compare_show_level(text: str) -> int | None:
    t = str(text or "").strip()
    if not t:
        return None
    m = re.search(r"\b[Ll]\s*([1-5])\b", t)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(?:show[_\s-]?level|level)\s*([1-5])\b", t, flags=re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"层级\s*([1-5])", t)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"[1-5]", t)
    if m:
        return int(m.group(0))
    return None


def load_compare_version_options(
    *,
    compare_db: Path,
    common_db: Path,
) -> list[CompareVersionOption]:
    """
    Return [(show_level, source_year, source_version_id, source_version_name)].
    Prefer compare.db snapshots; fall back to common.db edit_show_version.
    """
    options: list[CompareVersionOption] = []
    if compare_db.exists():
        try:
            with sqlite3.connect(compare_db) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT show_level, source_year, source_version_id, source_version_name
                    FROM compare_budget_summary
                    WHERE show_level BETWEEN 1 AND 5
                    GROUP BY show_level, source_year, source_version_id, source_version_name
                    ORDER BY show_level ASC
                    """
                ).fetchall()
            for row in rows:
                show_level = int(row["show_level"] or 0)
                if show_level < 1 or show_level > 5:
                    continue
                source_year = int(row["source_year"] or 0)
                source_version_id = int(row["source_version_id"] or 0)
                source_version_name = str(row["source_version_name"] or f"V{source_version_id}")
                if source_version_id <= 0:
                    continue
                options.append((show_level, source_year, source_version_id, source_version_name))
        except Exception:
            options = []

    if options:
        dedup: dict[int, CompareVersionOption] = {}
        for row in options:
            dedup[row[0]] = row
        return [dedup[key] for key in sorted(dedup.keys())]

    if not common_db.exists():
        return []
    try:
        with sqlite3.connect(common_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT e.edit_show_sign AS show_level, d.year AS source_year, e.version_id AS source_version_id, d.data_file_name
                FROM edit_show_version e
                JOIN databases d ON d.id = e.data_file_id
                WHERE e.edit_show_sign BETWEEN 1 AND 5
                ORDER BY e.edit_show_sign ASC
                """
            ).fetchall()
        for row in rows:
            show_level = int(row["show_level"] or 0)
            source_year = int(row["source_year"] or 0)
            source_version_id = int(row["source_version_id"] or 0)
            source_version_name = f"{str(row['data_file_name'] or '').strip()} / V{source_version_id}"
            if show_level < 1 or show_level > 5 or source_version_id <= 0:
                continue
            options.append((show_level, source_year, source_version_id, source_version_name))
    except Exception:
        return []
    return options


def format_compare_version_options(options: list[CompareVersionOption]) -> list[str]:
    return [f"L{sl}（{sy}年 / V{sv} {sn}）" for sl, sy, sv, sn in options]


def filter_compare_options_by_target_year(
    options: list[CompareVersionOption],
    target_year: int | None,
) -> list[CompareVersionOption]:
    if target_year is None:
        return options
    filtered = [option for option in options if int(option[1]) == int(target_year)]
    return filtered or options


def current_compare_show_level_version(
    *,
    common_db: Path,
    show_level: int = 1,
) -> int:
    if not common_db.exists():
        return 0
    try:
        with sqlite3.connect(common_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT version_id
                FROM edit_show_version
                WHERE edit_show_sign = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(show_level),),
            ).fetchone()
            if not row:
                return 0
            return int(row["version_id"] or 0)
    except Exception:
        return 0


def compare_level_meta(
    *,
    compare_db: Path,
    common_db: Path,
    show_level: int,
) -> dict[str, Any]:
    level = int(show_level or 0)
    if not (1 <= level <= 5):
        return {}

    selected_version = current_compare_show_level_version(
        common_db=common_db,
        show_level=level,
    )
    if selected_version > 0:
        if compare_db.exists():
            try:
                with sqlite3.connect(compare_db) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        """
                        SELECT source_year, source_version_id, source_version_name
                        FROM compare_budget_summary
                        WHERE show_level = ? AND source_version_id = ?
                        ORDER BY source_year DESC
                        LIMIT 1
                        """,
                        (level, selected_version),
                    ).fetchone()
                if row:
                    return {
                        "show_level": level,
                        "source_year": int(row["source_year"] or 0),
                        "source_version_id": int(row["source_version_id"] or 0),
                        "source_version_name": str(row["source_version_name"] or "").strip(),
                    }
            except Exception:
                pass
        return {
            "show_level": level,
            "source_year": 0,
            "source_version_id": int(selected_version),
            "source_version_name": "",
        }

    for option_level, source_year, source_version_id, source_version_name in load_compare_version_options(
        compare_db=compare_db,
        common_db=common_db,
    ):
        if int(option_level) == level:
            return {
                "show_level": level,
                "source_year": int(source_year or 0),
                "source_version_id": int(source_version_id or 0),
                "source_version_name": str(source_version_name or "").strip(),
            }
    return {}


def is_yoy_requested(query: str, clarified: dict[str, Any] | None) -> bool:
    comparison_type = str((clarified or {}).get("comparison_type") or "").strip().lower()
    return (
        comparison_type == "yoy"
        or bool(re.search(r"(同比|去年同期|对比去年|yoy)", query, flags=re.IGNORECASE))
        or is_explicit_year_comparison(query)
    )


def compare_version_choice_hint(
    *,
    compare_db: Path,
    common_db: Path,
    show_level: int,
) -> str:
    level = int(show_level or 0)
    if level < 1 or level > 5:
        return ""
    meta = compare_level_meta(
        compare_db=compare_db,
        common_db=common_db,
        show_level=level,
    )
    if meta:
        source_year = int(meta.get("source_year") or 0)
        source_version_id = int(meta.get("source_version_id") or 0)
        source_version_name = str(meta.get("source_version_name") or "").strip()
        if source_version_id > 0:
            return f"已选择同比版本：L{level}（{source_year}年 / V{source_version_id} {source_version_name}）。"
    return f"已选择同比版本：L{level}。"
