from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "scripts" / "verify_delivery_package.py"


class VerifyDeliveryPackageScriptTests(unittest.TestCase):
    def run_script(self, root: Path, *, profile: str = "internal-runtime") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--profile", profile],
            check=False,
            capture_output=True,
            text=True,
        )

    def make_common_project_root(self, root: Path) -> None:
        for relative in (
            "apps/api",
            "apps/web",
            "docs/development",
            "resources/business_inputs",
            "resources/download_template",
            "resources/knowledge_base",
            "var/data",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        for relative in (
            "README.md",
            "AGENTS.md",
            "CONTEXT.md",
            "CHANGELOG.md",
            "package.json",
            "package-lock.json",
            "skills-lock.json",
            "start.sh",
            "stop.sh",
            "apps/api/requirements.txt",
            "apps/api/run_server.py",
            "apps/web/package.json",
        ):
            (root / relative).write_text("current\n", encoding="utf-8")

    def make_internal_runtime_root(self, root: Path) -> None:
        self.make_common_project_root(root)
        (root / "apps/api/.env").write_text("DATABASE_DIR=var/data\n", encoding="utf-8")
        (root / "apps/web/dist").mkdir(parents=True, exist_ok=True)
        (root / "apps/web/dist/index.html").write_text("<div id=\"root\"></div>\n", encoding="utf-8")
        for db_name in ("common.db", "budget_2025.db", "budget_2026.db", "compare.db"):
            (root / "var/data" / db_name).write_bytes(b"sqlite placeholder")

    def test_internal_runtime_package_succeeds_with_runtime_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_internal_runtime_root(root)

            result = self.run_script(root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("delivery_package=ok", result.stdout)

    def test_internal_runtime_package_fails_when_duplicate_apps_data_dir_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_internal_runtime_root(root)
            (root / "apps/var/data").mkdir(parents=True)
            (root / "apps/var/data/common.db").write_bytes(b"duplicate")

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "duplicate-data-dir-present|apps/var/data|use var/data as the only live data directory",
            result.stdout,
        )

    def test_internal_runtime_package_fails_when_required_db_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_internal_runtime_root(root)
            (root / "var/data/compare.db").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("runtime-db-missing|var/data/compare.db|compare.db", result.stdout)

    def test_internal_runtime_package_fails_when_dependency_cache_is_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_internal_runtime_root(root)
            (root / "node_modules").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("forbidden-delivery-entry-present|node_modules|node_modules", result.stdout)

    def test_forbidden_directory_is_not_recursively_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_internal_runtime_root(root)
            (root / "node_modules/pkg/__pycache__").mkdir(parents=True)
            (root / "node_modules/pkg/__pycache__/cached.cpython-311.pyc").write_bytes(b"cache")

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("forbidden-delivery-entry-present|node_modules|node_modules", result.stdout)
        self.assertNotIn("forbidden-generated-file-present|node_modules", result.stdout)

    def test_active_python_cache_directory_is_reported_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_internal_runtime_root(root)
            (root / "apps/api/app/__pycache__").mkdir(parents=True)
            (root / "apps/api/app/__pycache__/main.cpython-311.pyc").write_bytes(b"cache")

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("forbidden-generated-dir-present|apps/api/app/__pycache__|__pycache__", result.stdout)
        self.assertNotIn("forbidden-generated-file-present|apps/api/app/__pycache__", result.stdout)

    def test_source_only_package_fails_when_runtime_assets_are_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_common_project_root(root)
            (root / "apps/api/.env").write_text("DATABASE_DIR=var/data\n", encoding="utf-8")
            (root / "var/data/common.db").write_bytes(b"sqlite placeholder")
            (root / "apps/web/dist").mkdir(parents=True)

            result = self.run_script(root, profile="source-only")

        self.assertEqual(result.returncode, 1)
        self.assertIn("source-only-runtime-asset-present|apps/api/.env|.env", result.stdout)
        self.assertIn("source-only-runtime-asset-present|var/data|var/data", result.stdout)
        self.assertIn("source-only-runtime-asset-present|apps/web/dist|dist", result.stdout)


if __name__ == "__main__":
    unittest.main()
