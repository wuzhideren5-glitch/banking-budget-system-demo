from __future__ import annotations

import argparse
from pathlib import Path
import sys


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db_bootstrap.retired_deletion import delete_retired_tables  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete retired tables with a database backup.")
    parser.add_argument(
        "--db",
        type=Path,
        default=REPO_ROOT / "var" / "data" / "common.db",
        help="SQLite database path. Defaults to var/data/common.db.",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=REPO_ROOT / "var" / "data" / "backups",
        help="Directory where the pre-delete database backup is written.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would be deleted.")
    args = parser.parse_args()

    result = delete_retired_tables(
        args.db,
        backup_root=args.backup_root,
        dry_run=args.dry_run,
    )
    action = "would_delete" if args.dry_run else "deleted"
    print(f"db={result.db_path}")
    print(f"{action}={','.join(result.deleted_tables) or '-'}")
    print(f"missing={','.join(result.missing_tables) or '-'}")
    print(f"backup={result.backup_path or '-'}")


if __name__ == "__main__":
    main()
