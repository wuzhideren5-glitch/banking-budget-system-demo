from __future__ import annotations

from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

runpy.run_path(str(ROOT / "scripts" / "verify_worktree_organization.py"), run_name="__main__")
