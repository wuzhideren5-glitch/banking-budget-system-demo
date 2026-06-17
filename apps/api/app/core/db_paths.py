from pathlib import Path

from app.core.config import settings


def common_db_path() -> Path:
    return settings.data_dir / "common.db"


def budget_db_path(year: int | None = None) -> Path:
    y = year if year is not None else settings.budget_year
    return settings.data_dir / f"budget_{y}.db"


def compare_db_path() -> Path:
    return settings.data_dir / "compare.db"


def list_budget_database_files() -> list[Path]:
    """Active year budget DBs under data_dir (sorted by path name)."""
    data_dir = settings.data_dir
    if not data_dir.is_dir():
        return []
    return sorted(
        path
        for path in data_dir.glob("budget_*.db")
        if path.stem.removeprefix("budget_").isdigit()
    )
