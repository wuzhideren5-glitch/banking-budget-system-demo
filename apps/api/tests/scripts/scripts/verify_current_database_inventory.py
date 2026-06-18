from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
REAL_SCRIPT = ROOT / "scripts" / "verify_current_database_inventory.py"

spec = importlib.util.spec_from_file_location("_real_verify_current_database_inventory", REAL_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load {REAL_SCRIPT}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

for name, value in vars(module).items():
    if not name.startswith("__"):
        globals()[name] = value

if __name__ == "__main__":
    raise SystemExit(module.main())
else:
    sys.modules[__name__] = module
