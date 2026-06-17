from __future__ import annotations

from pathlib import Path

from app.core.db_paths import list_budget_database_files


def active_budget_database_files() -> list[Path]:
    return [
        path
        for path in list_budget_database_files()
        if path.name.startswith("budget_") and path.stem.split("_", 1)[1].isdigit()
    ]
