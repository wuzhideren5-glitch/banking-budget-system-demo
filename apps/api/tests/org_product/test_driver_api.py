from __future__ import annotations

import compileall
import sys
from pathlib import Path


PROJECT_API_ROOT = Path(__file__).resolve().parent
REQUIRED_FILES = [
    PROJECT_API_ROOT / "app" / "main.py",
    PROJECT_API_ROOT / "app" / "routers" / "expense_forecast.py",
    PROJECT_API_ROOT / "app" / "routers" / "expense_forecast_rules.py",
    PROJECT_API_ROOT / "app" / "services" / "expense_forecast_rule_calculation.py",
    PROJECT_API_ROOT / "app" / "services" / "expense_forecast_rule_import_workflow.py",
    PROJECT_API_ROOT / "app" / "db_bootstrap" / "expense.py",
]


def main() -> int:
    missing = [str(path.relative_to(PROJECT_API_ROOT)) for path in REQUIRED_FILES if not path.exists()]
    if missing:
        print("missing required backend files:")
        for item in missing:
            print(f"- {item}")
        return 1

    ok = compileall.compile_dir(
        str(PROJECT_API_ROOT / "app"),
        quiet=1,
        force=False,
    )
    if not ok:
        print("backend source compile check failed")
        return 1

    print("backend smoke check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
