from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "scripts" / "verify_worktree_organization.py"


class VerifyWorktreeOrganizationScriptTests(unittest.TestCase):
    def run_script(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def make_minimal_root(self, root: Path) -> None:
        for relative in (
            "apps/api/app",
            "apps/api/app/db_bootstrap",
            "apps/api/app/routers",
            "apps/api/app/services",
            "apps/web/src",
            "apps/web/src/app/components",
            "apps/web/src/lib",
            "apps/web/e2e",
            "apps/api/scripts",
            ".agents/skills/current-skill",
            ".scratch/current-work-area",
            "archive",
            "archive/current-archive-area",
            "archive/frontend_retired/current-retired-frontend",
            "archive/handover/current-handover-area",
            "archive/releases/current-release-area",
            "archive/runtime_snapshots/current-runtime-snapshot-area",
            "archive/team_packages/current-team-package-area",
            "docs/agents",
            "docs/development",
            "docs/product",
            "apps/api/docs",
            "resources/business_inputs",
            "resources/download_template",
            "resources/knowledge_base",
            "resources/knowledge_base/current_layer",
            "var",
            "var/data",
            "var/logs",
            "var/output",
            "var/pids",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        for relative in ("README.md", "AGENTS.md", "CONTEXT.md"):
            (root / relative).write_text("# current\n", encoding="utf-8")
        (root / "README.md").write_text(
            "当前仓库根目录持久入口精确清单（工作树门禁读取）：`.agents`, `.scratch`, `AGENTS.md`, `CONTEXT.md`, `README.md`, `apps`, `archive`, `docs`, `package.json`, `resources`, `var`。\n",
            encoding="utf-8",
        )
        (root / "package.json").write_text(
            json.dumps(
                {
                    "scripts": {
                        "test:view-model": "npm --workspace apps/web run test:view-model",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        for relative in (
            ".agents/README.md",
            ".agents/skills/README.md",
            ".agents/skills/current-skill/SKILL.md",
            ".scratch/README.md",
            "archive/README.md",
            "archive/frontend_retired/README.md",
            "archive/frontend_retired/current-retired-frontend/README.md",
            "archive/handover/README.md",
            "archive/releases/README.md",
            "archive/runtime_snapshots/README.md",
            "archive/team_packages/README.md",
            "var/README.md",
            "resources/README.md",
            "resources/business_inputs/README.md",
            "resources/download_template/README.md",
            "resources/knowledge_base/README.md",
            "resources/knowledge_base/current_layer/README.md",
            "docs/agents/README.md",
            "docs/agents/domain.md",
            "docs/agents/issue-tracker.md",
            "docs/agents/triage-labels.md",
            "docs/development/README.md",
            "docs/development/active-worktree-manifest.md",
            "docs/development/department-expense-module-map.md",
            "docs/development/current-worktree-status.md",
            "docs/development/worktree-organization-20260603.md",
            "docs/development/repo-layout.md",
        ):
            (root / relative).write_text("# current\n", encoding="utf-8")
        (root / ".agents/README.md").write_text(
            "当前 `.agents/` 顶层目录精确清单（工作树门禁读取）：`skills`。\n"
            "skills\n",
            encoding="utf-8",
        )
        (root / ".agents/skills/README.md").write_text(
            "当前 `.agents/skills/` 本地技能精确清单（工作树门禁读取）：`current-skill`。\n"
            "current-skill\n",
            encoding="utf-8",
        )
        (root / ".scratch/README.md").write_text(
            "当前 `.scratch/` 工作区精确清单（工作树门禁读取）：`current-work-area`。\n"
            "current-work-area\n",
            encoding="utf-8",
        )
        (root / "archive/README.md").write_text(
            "当前 `archive/` 顶层目录精确清单（工作树门禁读取）：`current-archive-area`, `frontend_retired`, `handover`, `releases`, `runtime_snapshots`, `team_packages`。\n"
            "current-archive-area\nfrontend_retired\nhandover\nreleases\nruntime_snapshots\nteam_packages\n",
            encoding="utf-8",
        )
        (root / "archive/frontend_retired/README.md").write_text(
            "当前 `archive/frontend_retired/` 退休前端目录精确清单（工作树门禁读取）：`current-retired-frontend`。\n"
            "current-retired-frontend\n",
            encoding="utf-8",
        )
        (root / "archive/frontend_retired/current-retired-frontend/README.md").write_text(
            "# retired frontend bucket\n",
            encoding="utf-8",
        )
        (root / "archive/handover/README.md").write_text(
            "当前 `archive/handover/` 历史交接目录精确清单（工作树门禁读取）：`current-handover-area`。\n"
            "current-handover-area\n",
            encoding="utf-8",
        )
        (root / "archive/releases/README.md").write_text(
            "当前 `archive/releases/` 历史发布目录精确清单（工作树门禁读取）：`current-release-area`。\n"
            "current-release-area\n",
            encoding="utf-8",
        )
        (root / "archive/runtime_snapshots/README.md").write_text(
            "当前 `archive/runtime_snapshots/` 运行快照目录精确清单（工作树门禁读取）：`current-runtime-snapshot-area`。\n"
            "current-runtime-snapshot-area\n",
            encoding="utf-8",
        )
        (root / "archive/team_packages/README.md").write_text(
            "当前 `archive/team_packages/` 团队包目录精确清单（工作树门禁读取）：`current-team-package-area`。\n"
            "current-team-package-area\n",
            encoding="utf-8",
        )
        (root / "resources/README.md").write_text(
            "当前 `resources/` 顶层目录精确清单（工作树门禁读取）：`business_inputs`, `download_template`, `knowledge_base`。\n"
            "business_inputs\ndownload_template\nknowledge_base\n",
            encoding="utf-8",
        )
        (root / "docs/agents/README.md").write_text(
            "当前 `docs/agents/` 协作文档精确清单（工作树门禁读取）：`domain.md`, `issue-tracker.md`, `triage-labels.md`。\n"
            "domain.md\nissue-tracker.md\ntriage-labels.md\n",
            encoding="utf-8",
        )
        (root / "var/README.md").write_text(
            "当前 `var/` 顶层运行目录精确清单（工作树门禁读取）：`data`, `logs`, `output`, `pids`。\n",
            encoding="utf-8",
        )
        (root / "resources/business_inputs/current_business_input.xlsx").write_bytes(
            b"minimal workbook placeholder",
        )
        (root / "resources/business_inputs/README.md").write_text(
            "当前 `resources/business_inputs/` 精确文件清单（工作树门禁读取）：`current_business_input.xlsx`。\n"
            "current_business_input.xlsx\n",
            encoding="utf-8",
        )
        (root / "resources/download_template/current_template.xlsx").write_bytes(
            b"minimal template placeholder",
        )
        (root / "resources/download_template/README.md").write_text(
            "当前 `resources/download_template/` 精确文件清单（工作树门禁读取）：`current_template.xlsx`。\n"
            "current_template.xlsx\n",
            encoding="utf-8",
        )
        (root / "resources/knowledge_base/README.md").write_text(
            "当前 `resources/knowledge_base/` 一级目录精确清单（工作树门禁读取）：`current_layer`。\n"
            "current_layer\n",
            encoding="utf-8",
        )
        (root / "docs/development/current-system-map.md").write_text(
            "预算管理\n数据科目维护\ncurrent_router.py\ncurrentApi.ts\ncurrentViewModel.ts\n"
            "当前 `workspaceCatalog.tsx` 精确标签清单（工作树门禁读取）：预算管理、数据科目维护。\n"
            "当前 `apps/` 应用目录精确清单（工作树门禁读取）：`api`, `web`。\n"
            "当前 `apps/api/scripts/` 精确文件清单（工作树门禁读取）：`current_tool.py`。\n"
            "当前 `apps/api/` 顶层配置精确文件清单（工作树门禁读取）：`.env.example`, `requirements.txt`, `run_server.py`。\n"
            "当前 `apps/api/docs/` 后端局部文档精确文件清单（工作树门禁读取）：`current_backend_doc.md`。\n"
            "当前 `apps/api/app/` 顶层精确文件清单（工作树门禁读取）：`current_app_module.py`, `main.py`。\n"
            "当前 `apps/api/app/routers/` 精确文件清单（工作树门禁读取）：`current_router.py`。\n"
            "当前 `apps/api/app/services/` 精确文件清单（工作树门禁读取）：`current_service.py`。\n"
            "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`。\n"
            "当前 `apps/web/` 顶层配置精确文件清单（工作树门禁读取）：`index.html`, `package.json`, `vite.config.ts`。\n"
            "当前 `apps/web/e2e/` 前端验收脚本精确文件清单（工作树门禁读取）：`current-user-journey.spec.ts`。\n"
            "当前 `apps/web/src/` 顶层精确文件清单（工作树门禁读取）：`main.tsx`, `vite-env.d.ts`。\n"
            "当前 `apps/web/src/app/` 顶层精确文件清单（工作树门禁读取）：`workspaceCatalog.tsx`。\n"
            "当前 `apps/web/src/app/components/` 顶层精确文件清单（工作树门禁读取）：`DataAccountContent.tsx`。\n"
            "当前 `apps/web/src/lib/` 前端 domain 精确文件清单（工作树门禁读取）：`currentApi.ts`, `currentViewModel.ts`。\n"
            "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单（工作树门禁读取）：`api.ts`。\n"
            "当前 `apps/web/src/styles/` 精确文件清单（工作树门禁读取）：`index.css`。\n",
            encoding="utf-8",
        )
        (root / "docs/product/Banking_Budget_Files.md").write_text(
            (
                "current_tool.py\n"
                "current_router.py\n"
                "当前 `apps/` 应用目录精确清单（工作树门禁读取）：`api`, `web`。\n"
                "当前 `apps/api/scripts/` 精确文件清单（工作树门禁读取）：`current_tool.py`。\n"
                "当前 `apps/api/` 顶层配置精确文件清单（工作树门禁读取）：`.env.example`, `requirements.txt`, `run_server.py`。\n"
                "当前 `apps/api/docs/` 后端局部文档精确文件清单（工作树门禁读取）：`current_backend_doc.md`。\n"
                "当前 `apps/api/app/` 顶层精确文件清单（工作树门禁读取）：`current_app_module.py`, `main.py`。\n"
                "当前 `apps/api/app/routers/` 精确文件清单（工作树门禁读取）：`current_router.py`。\n"
                "当前 `apps/api/app/services/` 精确文件清单（工作树门禁读取）：`current_service.py`。\n"
                "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`。\n"
                "当前 `apps/web/` 顶层配置精确文件清单（工作树门禁读取）：`index.html`, `package.json`, `vite.config.ts`。\n"
                "当前 `apps/web/e2e/` 前端验收脚本精确文件清单（工作树门禁读取）：`current-user-journey.spec.ts`。\n"
                "当前 `apps/web/src/` 顶层精确文件清单（工作树门禁读取）：`main.tsx`, `vite-env.d.ts`。\n"
                "当前 `apps/web/src/app/` 顶层精确文件清单（工作树门禁读取）：`workspaceCatalog.tsx`。\n"
                "当前 `apps/web/src/app/components/` 顶层精确文件清单（工作树门禁读取）：`DataAccountContent.tsx`。\n"
                "当前 `apps/web/src/lib/` 前端 domain 精确文件清单（工作树门禁读取）：`currentApi.ts`, `currentViewModel.ts`。\n"
                "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单（工作树门禁读取）：`api.ts`。\n"
                "当前 `apps/web/src/styles/` 精确文件清单（工作树门禁读取）：`index.css`。\n"
                "DataAccountContent.tsx\n"
                "currentApi.ts\n"
                "currentViewModel.ts\n"
                "api.ts\n"
                ".env.example\n"
                "current_backend_doc.md\n"
                "requirements.txt\n"
                "run_server.py\n"
                "current-user-journey.spec.ts\n"
                "index.html\n"
                "package.json\n"
                "vite.config.ts\n"
                "Banking_Budget_Files.md\n"
                "Banking_Budget_System_PDD.md\n"
                "Banking_Budget_UI_Unified_PDD.md\n"
            ),
            encoding="utf-8",
        )
        (root / "docs/product/README.md").write_text(
            "当前 `docs/product/` 产品文档精确清单（工作树门禁读取）：`Banking_Budget_Files.md`, `Banking_Budget_System_PDD.md`, `Banking_Budget_UI_Unified_PDD.md`。\n"
            "Banking_Budget_Files.md\nBanking_Budget_System_PDD.md\nBanking_Budget_UI_Unified_PDD.md\n",
            encoding="utf-8",
        )
        (root / "docs/development/README.md").write_text(
            (
                "当前 `docs/development/` 开发文档精确清单（工作树门禁读取）：`active-worktree-manifest.md`, `current-system-map.md`, `current-worktree-status.md`, `department-expense-module-map.md`, `repo-layout.md`, `worktree-organization-20260603.md`。\n"
                "active-worktree-manifest.md\n"
                "current-system-map.md\n"
                "current-worktree-status.md\n"
                "department-expense-module-map.md\n"
                "repo-layout.md\n"
                "worktree-organization-20260603.md\n"
            ),
            encoding="utf-8",
        )
        (root / "apps/web/src/app").mkdir(parents=True, exist_ok=True)
        (root / "apps/web/src/main.tsx").write_text(
            "import './styles/index.css';\n",
            encoding="utf-8",
        )
        (root / "apps/web/index.html").write_text(
            "<div id=\"root\"></div>\n",
            encoding="utf-8",
        )
        (root / "apps/web/package.json").write_text(
            json.dumps(
                {
                    "name": "minimal-web",
                    "scripts": {
                        "test:view-model": "playwright test --config=playwright.view-model.config.ts --reporter=list",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "apps/web/vite.config.ts").write_text(
            "export default {};\n",
            encoding="utf-8",
        )
        (root / "apps/web/e2e/current-user-journey.spec.ts").write_text(
            "import { test } from '@playwright/test';\n",
            encoding="utf-8",
        )
        (root / "apps/web/src/vite-env.d.ts").write_text(
            "/// <reference types=\"vite/client\" />\n",
            encoding="utf-8",
        )
        (root / "apps/web/src/app/workspaceCatalog.tsx").write_text(
            'import { DataAccountContent } from "./components/DataAccountContent";\n'
            'export const workspaceTree = [{ label: "预算管理", children: [{ label: "数据科目维护" }] }];\n',
            encoding="utf-8",
        )
        (root / "apps/web/src/styles").mkdir(parents=True, exist_ok=True)
        (root / "apps/web/src/styles/index.css").write_text(
            ":root { color: black; }\n",
            encoding="utf-8",
        )
        (root / "apps/web/src/app/components/DataAccountContent.tsx").write_text(
            "export function DataAccountContent() { return null; }\n",
            encoding="utf-8",
        )
        (root / "apps/web/src/lib/currentApi.ts").write_text(
            "export const currentApi = {};\n",
            encoding="utf-8",
        )
        (root / "apps/web/src/lib/currentViewModel.ts").write_text(
            "export const currentViewModel = {};\n",
            encoding="utf-8",
        )
        (root / "apps/web/src/lib/api.ts").write_text(
            "export const requestJson = {};\n",
            encoding="utf-8",
        )
        for relative in (
            "docs/product/Banking_Budget_System_PDD.md",
            "docs/product/Banking_Budget_UI_Unified_PDD.md",
        ):
            (root / relative).write_text(
                "预算管理\n数据科目维护\n",
                encoding="utf-8",
            )
        (root / "apps/api/scripts/current_tool.py").write_text(
            "print('ok')\n",
            encoding="utf-8",
        )
        (root / "apps/api/.env.example").write_text(
            "DATABASE_DIR=var/data\n",
            encoding="utf-8",
        )
        (root / "apps/api/requirements.txt").write_text(
            "fastapi\n",
            encoding="utf-8",
        )
        (root / "apps/api/run_server.py").write_text(
            "print('server')\n",
            encoding="utf-8",
        )
        (root / "apps/api/docs/current_backend_doc.md").write_text(
            "Current backend doc.\n",
            encoding="utf-8",
        )
        (root / "apps/api/app/routers/current_router.py").write_text(
            "router = object()\n",
            encoding="utf-8",
        )
        (root / "apps/api/app/services/current_service.py").write_text(
            "VALUE = 'current'\n",
            encoding="utf-8",
        )
        (root / "apps/api/app/db_bootstrap/current_bootstrap.py").write_text(
            "VALUE = 'current'\n",
            encoding="utf-8",
        )
        (root / "apps/api/app/current_app_module.py").write_text(
            "VALUE = 'current'\n",
            encoding="utf-8",
        )
        (root / "apps/api/app/main.py").write_text(
            "from app.routers.current_router import router as current_router\n\n"
            "app.include_router(current_router)\n",
            encoding="utf-8",
        )

    def test_succeeds_for_current_minimal_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)

            result = self.run_script(root)

        self.assertEqual(result.returncode, 0)
        self.assertIn("worktree_organization=ok", result.stdout)

    def test_fails_when_retired_root_entry_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "src").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("retired-root-entry-present|src|src", result.stdout)

    def test_fails_when_unexpected_root_file_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "ad_hoc_import_review.xlsx").write_bytes(b"temporary workbook")

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "unexpected-root-entry|ad_hoc_import_review.xlsx|ad_hoc_import_review.xlsx",
            result.stdout,
        )

    def test_fails_when_allowed_root_entry_is_not_in_readme_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "root-entry-missing-from-readme|README.md|CHANGELOG.md",
            result.stdout,
        )

    def test_fails_when_root_readme_keeps_stale_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            readme = root / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "当前仓库根目录持久入口精确清单（工作树门禁读取）：`.agents`, `.scratch`, `AGENTS.md`, `CONTEXT.md`, `README.md`, `apps`, `archive`, `docs`, `package.json`, `resources`, `var`。",
                    "当前仓库根目录持久入口精确清单（工作树门禁读取）：`.agents`, `.scratch`, `AGENTS.md`, `CONTEXT.md`, `README.md`, `apps`, `archive`, `docs`, `old_src`, `package.json`, `resources`, `var`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("root-entry-list-stale|README.md|old_src", result.stdout)

    def test_fails_when_retired_var_entry_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "var/exports").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("retired-var-entry-present|var/exports|exports", result.stdout)

    def test_fails_when_python_bytecode_cache_returns_to_active_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/scripts/__pycache__").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "active-python-bytecode-cache-present|apps/api/scripts/__pycache__|__pycache__",
            result.stdout,
        )

    def test_fails_when_unexpected_var_entry_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "var/tmp-debug").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("unexpected-var-entry|var/tmp-debug|tmp-debug", result.stdout)
        self.assertIn("var-dir-missing-from-index|var/README.md|tmp-debug", result.stdout)

    def test_fails_when_allowed_transient_var_dir_is_not_in_exact_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "var/test-runs").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("var-dir-missing-from-index|var/README.md|test-runs", result.stdout)

    def test_fails_when_var_index_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            var_index = root / "var/README.md"
            var_index.write_text(
                var_index.read_text(encoding="utf-8").replace(
                    "当前 `var/` 顶层运行目录精确清单（工作树门禁读取）：`data`, `logs`, `output`, `pids`。",
                    "当前 `var/` 顶层运行目录精确清单（工作树门禁读取）：`data`, `logs`, `old-output`, `output`, `pids`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("var-dir-list-stale|var/README.md|old-output", result.stdout)

    def test_fails_when_current_doc_uses_retired_budget_input_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "docs/product/Banking_Budget_Rules_PDD.md").write_text(
                "预算基础数据维护",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("forbidden-active-marker|docs/product/Banking_Budget_Rules_PDD.md|预算基础数据维护", result.stdout)

    def test_allows_retired_marker_in_explicit_retired_deletion_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/app/db_bootstrap/retired_deletion.py").write_text(
                'RETIRED_TABLES = ("report_account", "report_data_mapping")\n',
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`。",
                    "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`, `retired_deletion.py`。",
                ),
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`。",
                    "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`, `retired_deletion.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 0)
        self.assertIn("worktree_organization=ok", result.stdout)

    def test_fails_when_retired_marker_returns_to_regular_active_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/app/services/new_feature.py").write_text(
                'LEGACY_TABLE = "report_account"\n',
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "retired-code-marker-outside-contract|apps/api/app/services/new_feature.py|report_account",
            result.stdout,
        )

    def test_fails_when_retired_control_item_mapping_name_returns_to_frontend_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/lib/newFeatureViewModel.ts").write_text(
                "export const legacyName = 'controlItemMappingViewModel';\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "retired-code-marker-outside-contract|apps/web/src/lib/newFeatureViewModel.ts|controlItemMapping",
            result.stdout,
        )

    def test_fails_when_root_view_model_test_script_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            package_path = root / "package.json"
            package_data = json.loads(package_path.read_text(encoding="utf-8"))
            package_data["scripts"].pop("test:view-model")
            package_path.write_text(
                json.dumps(package_data, ensure_ascii=False),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("package-script-missing|package.json|test:view-model", result.stdout)

    def test_fails_when_frontend_view_model_test_script_is_mismatched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            package_path = root / "apps/web/package.json"
            package_data = json.loads(package_path.read_text(encoding="utf-8"))
            package_data["scripts"]["test:view-model"] = "playwright test --reporter=list"
            package_path.write_text(
                json.dumps(package_data, ensure_ascii=False),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "package-script-mismatch|apps/web/package.json|test:view-model|expected=playwright test --config=playwright.view-model.config.ts --reporter=list|actual=playwright test --reporter=list",
            result.stdout,
        )

    def test_fails_when_archive_map_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing-guide-file|archive/README.md|archive/README.md", result.stdout)

    def test_fails_when_archive_dir_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/unlisted-legacy-area").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-dir-missing-from-index|archive/README.md|unlisted-legacy-area",
            result.stdout,
        )

    def test_fails_when_archive_index_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            archive_index = root / "archive/README.md"
            archive_index.write_text(
                archive_index.read_text(encoding="utf-8").replace(
                    "当前 `archive/` 顶层目录精确清单（工作树门禁读取）：`current-archive-area`, `frontend_retired`, `handover`, `releases`, `runtime_snapshots`, `team_packages`。",
                    "当前 `archive/` 顶层目录精确清单（工作树门禁读取）：`current-archive-area`, `frontend_retired`, `handover`, `releases`, `retired-legacy-area`, `runtime_snapshots`, `team_packages`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-dir-list-stale|archive/README.md|retired-legacy-area",
            result.stdout,
        )

    def test_fails_when_archive_frontend_retired_map_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/frontend_retired/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "missing-guide-file|archive/frontend_retired/README.md|archive/frontend_retired/README.md",
            result.stdout,
        )

    def test_fails_when_archive_frontend_retired_dir_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/frontend_retired/unlisted-retired-ui").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-frontend-retired-dir-missing-from-index|archive/frontend_retired/README.md|unlisted-retired-ui",
            result.stdout,
        )

    def test_fails_when_archive_frontend_retired_index_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            frontend_retired_index = root / "archive/frontend_retired/README.md"
            frontend_retired_index.write_text(
                frontend_retired_index.read_text(encoding="utf-8").replace(
                    "当前 `archive/frontend_retired/` 退休前端目录精确清单（工作树门禁读取）：`current-retired-frontend`。",
                    "当前 `archive/frontend_retired/` 退休前端目录精确清单（工作树门禁读取）：`current-retired-frontend`, `old-retired-ui`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-frontend-retired-dir-list-stale|archive/frontend_retired/README.md|old-retired-ui",
            result.stdout,
        )

    def test_fails_when_archive_frontend_retired_bucket_lacks_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/frontend_retired/current-retired-frontend/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-frontend-retired-dir-missing-readme|archive/frontend_retired/current-retired-frontend/README.md|current-retired-frontend",
            result.stdout,
        )

    def test_fails_when_archive_handover_map_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/handover/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "missing-guide-file|archive/handover/README.md|archive/handover/README.md",
            result.stdout,
        )

    def test_fails_when_archive_handover_dir_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/handover/unlisted-legacy-bucket").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-handover-dir-missing-from-index|archive/handover/README.md|unlisted-legacy-bucket",
            result.stdout,
        )

    def test_fails_when_archive_handover_index_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            handover_index = root / "archive/handover/README.md"
            handover_index.write_text(
                handover_index.read_text(encoding="utf-8").replace(
                    "当前 `archive/handover/` 历史交接目录精确清单（工作树门禁读取）：`current-handover-area`。",
                    "当前 `archive/handover/` 历史交接目录精确清单（工作树门禁读取）：`current-handover-area`, `retired-handover-area`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-handover-dir-list-stale|archive/handover/README.md|retired-handover-area",
            result.stdout,
        )

    def test_fails_when_archive_releases_map_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/releases/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "missing-guide-file|archive/releases/README.md|archive/releases/README.md",
            result.stdout,
        )

    def test_fails_when_archive_release_dir_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/releases/unlisted-release").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-release-dir-missing-from-index|archive/releases/README.md|unlisted-release",
            result.stdout,
        )

    def test_fails_when_archive_releases_index_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            release_index = root / "archive/releases/README.md"
            release_index.write_text(
                release_index.read_text(encoding="utf-8").replace(
                    "当前 `archive/releases/` 历史发布目录精确清单（工作树门禁读取）：`current-release-area`。",
                    "当前 `archive/releases/` 历史发布目录精确清单（工作树门禁读取）：`current-release-area`, `old-release`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-release-dir-list-stale|archive/releases/README.md|old-release",
            result.stdout,
        )

    def test_fails_when_archive_runtime_snapshots_map_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/runtime_snapshots/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "missing-guide-file|archive/runtime_snapshots/README.md|archive/runtime_snapshots/README.md",
            result.stdout,
        )

    def test_fails_when_archive_runtime_snapshot_dir_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/runtime_snapshots/unlisted-runtime-snapshot").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-runtime-snapshot-dir-missing-from-index|archive/runtime_snapshots/README.md|unlisted-runtime-snapshot",
            result.stdout,
        )

    def test_fails_when_archive_runtime_snapshots_index_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            runtime_index = root / "archive/runtime_snapshots/README.md"
            runtime_index.write_text(
                runtime_index.read_text(encoding="utf-8").replace(
                    "当前 `archive/runtime_snapshots/` 运行快照目录精确清单（工作树门禁读取）：`current-runtime-snapshot-area`。",
                    "当前 `archive/runtime_snapshots/` 运行快照目录精确清单（工作树门禁读取）：`current-runtime-snapshot-area`, `old-runtime-snapshot`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-runtime-snapshot-dir-list-stale|archive/runtime_snapshots/README.md|old-runtime-snapshot",
            result.stdout,
        )

    def test_fails_when_archive_team_packages_map_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/team_packages/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "missing-guide-file|archive/team_packages/README.md|archive/team_packages/README.md",
            result.stdout,
        )

    def test_fails_when_archive_team_package_dir_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "archive/team_packages/unlisted-team-package").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-team-package-dir-missing-from-index|archive/team_packages/README.md|unlisted-team-package",
            result.stdout,
        )

    def test_fails_when_archive_team_packages_index_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            team_package_index = root / "archive/team_packages/README.md"
            team_package_index.write_text(
                team_package_index.read_text(encoding="utf-8").replace(
                    "当前 `archive/team_packages/` 团队包目录精确清单（工作树门禁读取）：`current-team-package-area`。",
                    "当前 `archive/team_packages/` 团队包目录精确清单（工作树门禁读取）：`current-team-package-area`, `old-team-package`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "archive-team-package-dir-list-stale|archive/team_packages/README.md|old-team-package",
            result.stdout,
        )

    def test_fails_when_scratch_map_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / ".scratch/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing-guide-file|.scratch/README.md|.scratch/README.md", result.stdout)

    def test_fails_when_controlled_resources_map_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "resources/README.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing-guide-file|resources/README.md|resources/README.md", result.stdout)

    def test_fails_when_resources_dir_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "resources/legacy_samples").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "resources-dir-missing-from-index|resources/README.md|legacy_samples",
            result.stdout,
        )

    def test_fails_when_resources_index_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            resources_index = root / "resources/README.md"
            resources_index.write_text(
                resources_index.read_text(encoding="utf-8").replace(
                    "当前 `resources/` 顶层目录精确清单（工作树门禁读取）：`business_inputs`, `download_template`, `knowledge_base`。",
                    "当前 `resources/` 顶层目录精确清单（工作树门禁读取）：`business_inputs`, `download_template`, `knowledge_base`, `old_samples`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "resources-dir-list-stale|resources/README.md|old_samples",
            result.stdout,
        )

    def test_fails_when_current_worktree_status_doc_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "docs/development/current-worktree-status.md").unlink()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "missing-guide-file|docs/development/current-worktree-status.md|docs/development/current-worktree-status.md",
            result.stdout,
        )

    def test_fails_when_apps_dir_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/legacy_app").mkdir(parents=True, exist_ok=True)
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/` 应用目录精确清单（工作树门禁读取）：`api`, `web`。",
                    "当前 `apps/` 应用目录精确清单（工作树门禁读取）：`api`, `legacy_app`, `web`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "apps-dir-list-missing-current-dir|docs/product/Banking_Budget_Files.md|legacy_app",
            result.stdout,
        )

    def test_fails_when_apps_dir_exact_list_keeps_stale_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/` 应用目录精确清单（工作树门禁读取）：`api`, `web`。",
                    "当前 `apps/` 应用目录精确清单（工作树门禁读取）：`api`, `old_backend`, `web`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "apps-dir-list-stale|docs/product/Banking_Budget_Files.md|old_backend",
            result.stdout,
        )

    def test_fails_when_apps_dir_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/new_web").mkdir(parents=True, exist_ok=True)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/` 应用目录精确清单（工作树门禁读取）：`api`, `web`。",
                    "当前 `apps/` 应用目录精确清单（工作树门禁读取）：`api`, `new_web`, `web`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-apps-dir-list-missing-current-dir|docs/development/current-system-map.md|new_web",
            result.stdout,
        )

    def test_fails_when_current_script_is_not_in_file_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/scripts/unlisted_tool.py").write_text(
                "print('missing map entry')\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "script-list-missing-current-script|docs/product/Banking_Budget_Files.md|unlisted_tool.py",
            result.stdout,
        )

    def test_fails_when_script_file_map_list_keeps_stale_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/scripts/` 精确文件清单（工作树门禁读取）：`current_tool.py`。",
                    "当前 `apps/api/scripts/` 精确文件清单（工作树门禁读取）：`current_tool.py`, `stale_tool.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "script-list-stale|docs/product/Banking_Budget_Files.md|stale_tool.py",
            result.stdout,
        )

    def test_fails_when_current_script_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/scripts/unlisted_system_map_tool.py").write_text(
                "print('missing system map entry')\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/scripts/` 精确文件清单（工作树门禁读取）：`current_tool.py`。",
                    "当前 `apps/api/scripts/` 精确文件清单（工作树门禁读取）：`current_tool.py`, `unlisted_system_map_tool.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-script-list-missing-current-script|docs/development/current-system-map.md|unlisted_system_map_tool.py",
            result.stdout,
        )

    def test_fails_when_backend_api_config_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/uv.lock").write_text(
                "version = 1\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/` 顶层配置精确文件清单（工作树门禁读取）：`.env.example`, `requirements.txt`, `run_server.py`。",
                    "当前 `apps/api/` 顶层配置精确文件清单（工作树门禁读取）：`.env.example`, `requirements.txt`, `run_server.py`, `uv.lock`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "backend-api-config-list-missing-current-file|docs/product/Banking_Budget_Files.md|uv.lock",
            result.stdout,
        )

    def test_fails_when_backend_api_config_exact_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/` 顶层配置精确文件清单（工作树门禁读取）：`.env.example`, `requirements.txt`, `run_server.py`。",
                    "当前 `apps/api/` 顶层配置精确文件清单（工作树门禁读取）：`.env.example`, `legacy.ini`, `requirements.txt`, `run_server.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "backend-api-config-list-stale|docs/product/Banking_Budget_Files.md|legacy.ini",
            result.stdout,
        )

    def test_fails_when_backend_api_config_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/pyproject.toml").write_text(
                "[project]\nname = 'minimal-api'\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/` 顶层配置精确文件清单（工作树门禁读取）：`.env.example`, `requirements.txt`, `run_server.py`。",
                    "当前 `apps/api/` 顶层配置精确文件清单（工作树门禁读取）：`.env.example`, `pyproject.toml`, `requirements.txt`, `run_server.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-backend-api-config-list-missing-current-file|docs/development/current-system-map.md|pyproject.toml",
            result.stdout,
        )

    def test_fails_when_backend_api_doc_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/docs/new_backend_doc.md").write_text(
                "New backend doc.\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/docs/` 后端局部文档精确文件清单（工作树门禁读取）：`current_backend_doc.md`。",
                    "当前 `apps/api/docs/` 后端局部文档精确文件清单（工作树门禁读取）：`current_backend_doc.md`, `new_backend_doc.md`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "backend-api-doc-list-missing-current-file|docs/product/Banking_Budget_Files.md|new_backend_doc.md",
            result.stdout,
        )

    def test_fails_when_backend_api_doc_exact_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/docs/` 后端局部文档精确文件清单（工作树门禁读取）：`current_backend_doc.md`。",
                    "当前 `apps/api/docs/` 后端局部文档精确文件清单（工作树门禁读取）：`current_backend_doc.md`, `retired_backend_doc.md`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "backend-api-doc-list-stale|docs/product/Banking_Budget_Files.md|retired_backend_doc.md",
            result.stdout,
        )

    def test_fails_when_backend_api_doc_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/docs/new_system_backend_doc.md").write_text(
                "New system backend doc.\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/docs/` 后端局部文档精确文件清单（工作树门禁读取）：`current_backend_doc.md`。",
                    "当前 `apps/api/docs/` 后端局部文档精确文件清单（工作树门禁读取）：`current_backend_doc.md`, `new_system_backend_doc.md`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-backend-api-doc-list-missing-current-file|docs/development/current-system-map.md|new_system_backend_doc.md",
            result.stdout,
        )

    def test_fails_when_current_router_is_not_in_file_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/app/routers/unlisted_router.py").write_text(
                "router = object()\n",
                encoding="utf-8",
            )
            (root / "apps/api/app/main.py").write_text(
                "from app.routers.current_router import router as current_router\n"
                "from app.routers.unlisted_router import router as unlisted_router\n\n"
                "app.include_router(current_router)\n"
                "app.include_router(unlisted_router)\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("router-missing-from-file-map|apps/api/app/routers/unlisted_router.py|unlisted_router.py", result.stdout)

    def test_fails_when_current_app_module_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/app/new_app_module.py").write_text(
                "VALUE = 'new'\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/` 顶层精确文件清单（工作树门禁读取）：`current_app_module.py`, `main.py`。",
                    "当前 `apps/api/app/` 顶层精确文件清单（工作树门禁读取）：`current_app_module.py`, `main.py`, `new_app_module.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "app-module-list-missing-current-module|docs/product/Banking_Budget_Files.md|new_app_module.py",
            result.stdout,
        )

    def test_fails_when_app_module_list_keeps_stale_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/` 顶层精确文件清单（工作树门禁读取）：`current_app_module.py`, `main.py`。",
                    "当前 `apps/api/app/` 顶层精确文件清单（工作树门禁读取）：`current_app_module.py`, `main.py`, `stale_app_module.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "app-module-list-stale|docs/product/Banking_Budget_Files.md|stale_app_module.py",
            result.stdout,
        )

    def test_fails_when_current_router_is_not_in_system_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/app/routers/new_router.py").write_text(
                "router = object()\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8") + "new_router.py\n",
                encoding="utf-8",
            )
            (root / "apps/api/app/main.py").write_text(
                "from app.routers.current_router import router as current_router\n"
                "from app.routers.new_router import router as new_router\n\n"
                "app.include_router(current_router)\n"
                "app.include_router(new_router)\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("router-missing-from-system-map|apps/api/app/routers/new_router.py|new_router.py", result.stdout)

    def test_fails_when_system_map_router_list_keeps_stale_router(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/routers/` 精确文件清单（工作树门禁读取）：`current_router.py`。",
                    "当前 `apps/api/app/routers/` 精确文件清单（工作树门禁读取）：`current_router.py`, `stale_router.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-router-list-stale|docs/development/current-system-map.md|stale_router.py",
            result.stdout,
        )

    def test_fails_when_router_file_map_list_keeps_stale_router(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/routers/` 精确文件清单（工作树门禁读取）：`current_router.py`。",
                    "当前 `apps/api/app/routers/` 精确文件清单（工作树门禁读取）：`current_router.py`, `stale_router.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "router-list-stale|docs/product/Banking_Budget_Files.md|stale_router.py",
            result.stdout,
        )

    def test_fails_when_current_router_is_not_mounted_from_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/app/routers/unmounted_router.py").write_text(
                "router = object()\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8") + "unmounted_router.py\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("router-missing-from-main-mount|apps/api/app/routers/unmounted_router.py|unmounted_router.py", result.stdout)

    def test_fails_when_current_service_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/app/services/new_service.py").write_text(
                "VALUE = 'new'\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/services/` 精确文件清单（工作树门禁读取）：`current_service.py`。",
                    "当前 `apps/api/app/services/` 精确文件清单（工作树门禁读取）：`current_service.py`, `new_service.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "service-list-missing-current-service|docs/product/Banking_Budget_Files.md|new_service.py",
            result.stdout,
        )

    def test_fails_when_service_list_keeps_stale_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/services/` 精确文件清单（工作树门禁读取）：`current_service.py`。",
                    "当前 `apps/api/app/services/` 精确文件清单（工作树门禁读取）：`current_service.py`, `stale_service.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "service-list-stale|docs/product/Banking_Budget_Files.md|stale_service.py",
            result.stdout,
        )

    def test_fails_when_current_db_bootstrap_module_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/api/app/db_bootstrap/new_bootstrap.py").write_text(
                "VALUE = 'new'\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`。",
                    "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`, `new_bootstrap.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "db-bootstrap-list-missing-current-module|docs/product/Banking_Budget_Files.md|new_bootstrap.py",
            result.stdout,
        )

    def test_fails_when_db_bootstrap_list_keeps_stale_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`。",
                    "当前 `apps/api/app/db_bootstrap/` 精确文件清单（工作树门禁读取）：`current_bootstrap.py`, `stale_bootstrap.py`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "db-bootstrap-list-stale|docs/product/Banking_Budget_Files.md|stale_bootstrap.py",
            result.stdout,
        )

    def test_fails_when_product_doc_is_not_in_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "docs/product/Unlisted_Current_PDD.md").write_text(
                "# missing from index\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("product-doc-missing-from-index|docs/product/README.md|Unlisted_Current_PDD.md", result.stdout)

    def test_fails_when_product_doc_index_keeps_stale_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            product_index = root / "docs/product/README.md"
            product_index.write_text(
                product_index.read_text(encoding="utf-8").replace(
                    "当前 `docs/product/` 产品文档精确清单（工作树门禁读取）：`Banking_Budget_Files.md`, `Banking_Budget_System_PDD.md`, `Banking_Budget_UI_Unified_PDD.md`。",
                    "当前 `docs/product/` 产品文档精确清单（工作树门禁读取）：`Banking_Budget_Files.md`, `Banking_Budget_System_PDD.md`, `Banking_Budget_UI_Unified_PDD.md`, `Old_Product_PDD.md`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "product-doc-list-stale|docs/product/README.md|Old_Product_PDD.md",
            result.stdout,
        )

    def test_fails_when_development_doc_is_not_in_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "docs/development/unlisted-current-dev-doc.md").write_text(
                "# missing from index\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "development-doc-missing-from-index|docs/development/README.md|unlisted-current-dev-doc.md",
            result.stdout,
        )

    def test_fails_when_development_doc_index_keeps_stale_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            development_index = root / "docs/development/README.md"
            development_index.write_text(
                development_index.read_text(encoding="utf-8").replace(
                    "当前 `docs/development/` 开发文档精确清单（工作树门禁读取）：`active-worktree-manifest.md`, `current-system-map.md`, `current-worktree-status.md`, `department-expense-module-map.md`, `repo-layout.md`, `worktree-organization-20260603.md`。",
                    "当前 `docs/development/` 开发文档精确清单（工作树门禁读取）：`active-worktree-manifest.md`, `current-system-map.md`, `current-worktree-status.md`, `department-expense-module-map.md`, `old-dev-note.md`, `repo-layout.md`, `worktree-organization-20260603.md`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "development-doc-list-stale|docs/development/README.md|old-dev-note.md",
            result.stdout,
        )

    def test_fails_when_agent_doc_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "docs/agents/new-agent-doc.md").write_text(
                "# missing from agent docs index\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "agent-doc-missing-from-index|docs/agents/README.md|new-agent-doc.md",
            result.stdout,
        )

    def test_fails_when_agent_doc_index_keeps_stale_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            agent_index = root / "docs/agents/README.md"
            agent_index.write_text(
                agent_index.read_text(encoding="utf-8").replace(
                    "当前 `docs/agents/` 协作文档精确清单（工作树门禁读取）：`domain.md`, `issue-tracker.md`, `triage-labels.md`。",
                    "当前 `docs/agents/` 协作文档精确清单（工作树门禁读取）：`domain.md`, `issue-tracker.md`, `retired-agent-doc.md`, `triage-labels.md`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "agent-doc-list-stale|docs/agents/README.md|retired-agent-doc.md",
            result.stdout,
        )

    def test_fails_when_local_agent_skill_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / ".agents/skills/new-local-skill").mkdir()
            (root / ".agents/skills/new-local-skill/SKILL.md").write_text(
                "# new local skill\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "agents-skill-missing-from-index|.agents/skills/README.md|new-local-skill",
            result.stdout,
        )

    def test_fails_when_local_agent_skill_index_keeps_stale_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            skill_index = root / ".agents/skills/README.md"
            skill_index.write_text(
                skill_index.read_text(encoding="utf-8").replace(
                    "当前 `.agents/skills/` 本地技能精确清单（工作树门禁读取）：`current-skill`。",
                    "当前 `.agents/skills/` 本地技能精确清单（工作树门禁读取）：`current-skill`, `retired-skill`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "agents-skill-list-stale|.agents/skills/README.md|retired-skill",
            result.stdout,
        )

    def test_fails_when_scratch_work_area_is_not_in_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / ".scratch/unlisted-work-area").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "scratch-work-area-missing-from-index|.scratch/README.md|unlisted-work-area",
            result.stdout,
        )

    def test_fails_when_scratch_work_area_index_keeps_stale_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            scratch_index = root / ".scratch/README.md"
            scratch_index.write_text(
                scratch_index.read_text(encoding="utf-8").replace(
                    "当前 `.scratch/` 工作区精确清单（工作树门禁读取）：`current-work-area`。",
                    "当前 `.scratch/` 工作区精确清单（工作树门禁读取）：`current-work-area`, `retired-work-area`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "scratch-work-area-list-stale|.scratch/README.md|retired-work-area",
            result.stdout,
        )

    def test_fails_when_business_input_is_not_in_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "resources/business_inputs/unlisted_business_input.xlsx").write_bytes(
                b"missing business input registration",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "business-input-missing-from-index|resources/business_inputs/README.md|unlisted_business_input.xlsx",
            result.stdout,
        )

    def test_fails_when_business_input_index_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            business_input_index = root / "resources/business_inputs/README.md"
            business_input_index.write_text(
                business_input_index.read_text(encoding="utf-8").replace(
                    "当前 `resources/business_inputs/` 精确文件清单（工作树门禁读取）：`current_business_input.xlsx`。",
                    "当前 `resources/business_inputs/` 精确文件清单（工作树门禁读取）：`current_business_input.xlsx`, `old_business_input.xlsx`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "business-input-list-stale|resources/business_inputs/README.md|old_business_input.xlsx",
            result.stdout,
        )

    def test_fails_when_download_template_is_not_in_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "resources/download_template/unlisted_template.xlsx").write_bytes(
                b"missing template registration",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "download-template-missing-from-index|resources/download_template/README.md|unlisted_template.xlsx",
            result.stdout,
        )

    def test_fails_when_download_template_index_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            template_index = root / "resources/download_template/README.md"
            template_index.write_text(
                template_index.read_text(encoding="utf-8").replace(
                    "当前 `resources/download_template/` 精确文件清单（工作树门禁读取）：`current_template.xlsx`。",
                    "当前 `resources/download_template/` 精确文件清单（工作树门禁读取）：`current_template.xlsx`, `old_template.xlsx`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "download-template-list-stale|resources/download_template/README.md|old_template.xlsx",
            result.stdout,
        )

    def test_fails_when_knowledge_base_layer_has_no_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "resources/knowledge_base/unregistered_layer").mkdir()

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "knowledge-base-dir-missing-readme|resources/knowledge_base/unregistered_layer/README.md|unregistered_layer",
            result.stdout,
        )

    def test_fails_when_knowledge_base_layer_is_not_in_index_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "resources/knowledge_base/new_layer").mkdir()
            (root / "resources/knowledge_base/new_layer/README.md").write_text(
                "# new layer\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "knowledge-base-layer-missing-from-index|resources/knowledge_base/README.md|new_layer",
            result.stdout,
        )

    def test_fails_when_knowledge_base_index_keeps_stale_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            knowledge_index = root / "resources/knowledge_base/README.md"
            knowledge_index.write_text(
                knowledge_index.read_text(encoding="utf-8").replace(
                    "当前 `resources/knowledge_base/` 一级目录精确清单（工作树门禁读取）：`current_layer`。",
                    "当前 `resources/knowledge_base/` 一级目录精确清单（工作树门禁读取）：`current_layer`, `old_layer`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "knowledge-base-layer-list-stale|resources/knowledge_base/README.md|old_layer",
            result.stdout,
        )

    def test_fails_when_product_doc_index_link_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            index_path = root / "docs/product/README.md"
            index_path.write_text(
                index_path.read_text(encoding="utf-8")
                + "[Missing PDD](Missing_Current_PDD.md)\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "product-doc-index-missing-link|docs/product/Missing_Current_PDD.md|Missing_Current_PDD.md",
            result.stdout,
        )

    def test_fails_when_current_doc_relative_link_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "docs/development/repo-layout.md").write_text(
                "[Missing dev doc](missing-dev-doc.md)\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "current-doc-missing-link|docs/development/missing-dev-doc.md|missing-dev-doc.md",
            result.stdout,
        )

    def test_fails_when_workspace_label_is_missing_from_navigation_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/workspaceCatalog.tsx").write_text(
                'export const workspaceTree = [{ label: "预算管理", children: [{ label: "新增导航页" }] }];\n',
                encoding="utf-8",
            )
            (root / "docs/product/Banking_Budget_System_PDD.md").write_text(
                "预算管理\n新增导航页\n",
                encoding="utf-8",
            )
            (root / "docs/product/Banking_Budget_UI_Unified_PDD.md").write_text(
                "预算管理\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("workspace-label-missing-from-doc|docs/product/Banking_Budget_UI_Unified_PDD.md|新增导航页", result.stdout)

    def test_fails_when_workspace_label_is_missing_from_system_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/workspaceCatalog.tsx").write_text(
                'export const workspaceTree = [{ label: "预算管理", children: [{ label: "系统地图缺失页" }] }];\n',
                encoding="utf-8",
            )
            for relative in (
                "docs/product/Banking_Budget_System_PDD.md",
                "docs/product/Banking_Budget_UI_Unified_PDD.md",
            ):
                (root / relative).write_text(
                    "预算管理\n系统地图缺失页\n",
                    encoding="utf-8",
                )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "workspace-label-missing-from-system-map|docs/development/current-system-map.md|系统地图缺失页",
            result.stdout,
        )

    def test_fails_when_system_map_workspace_label_list_keeps_stale_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `workspaceCatalog.tsx` 精确标签清单（工作树门禁读取）：预算管理、数据科目维护。",
                    "当前 `workspaceCatalog.tsx` 精确标签清单（工作树门禁读取）：预算管理、数据科目维护、旧导航页。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-workspace-label-list-stale|docs/development/current-system-map.md|旧导航页",
            result.stdout,
        )

    def test_fails_when_workspace_component_is_not_in_file_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/workspaceCatalog.tsx").write_text(
                'import { NewPageContent } from "./components/NewPageContent";\n'
                'export const workspaceTree = [{ label: "预算管理" }];\n',
                encoding="utf-8",
            )
            (root / "apps/web/src/app/components/NewPageContent.tsx").write_text(
                "export function NewPageContent() { return null; }\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("workspace-component-missing-from-file-map|apps/web/src/app/components/NewPageContent.tsx|NewPageContent.tsx", result.stdout)

    def test_fails_when_frontend_component_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/components/NewSubView.tsx").write_text(
                "export function NewSubView() { return null; }\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/app/components/` 顶层精确文件清单（工作树门禁读取）：`DataAccountContent.tsx`。",
                    "当前 `apps/web/src/app/components/` 顶层精确文件清单（工作树门禁读取）：`DataAccountContent.tsx`, `NewSubView.tsx`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-component-list-missing-current-component|docs/product/Banking_Budget_Files.md|NewSubView.tsx",
            result.stdout,
        )

    def test_fails_when_frontend_component_list_keeps_stale_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/app/components/` 顶层精确文件清单（工作树门禁读取）：`DataAccountContent.tsx`。",
                    "当前 `apps/web/src/app/components/` 顶层精确文件清单（工作树门禁读取）：`DataAccountContent.tsx`, `StaleView.tsx`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-component-list-stale|docs/product/Banking_Budget_Files.md|StaleView.tsx",
            result.stdout,
        )

    def test_fails_when_frontend_component_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/components/NewSystemMapView.tsx").write_text(
                "export function NewSystemMapView() { return null; }\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/app/components/` 顶层精确文件清单（工作树门禁读取）：`DataAccountContent.tsx`。",
                    "当前 `apps/web/src/app/components/` 顶层精确文件清单（工作树门禁读取）：`DataAccountContent.tsx`, `NewSystemMapView.tsx`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-frontend-component-list-missing-current-component|docs/development/current-system-map.md|NewSystemMapView.tsx",
            result.stdout,
        )

    def test_fails_when_frontend_app_config_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/playwright.config.ts").write_text(
                "export default {};\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/` 顶层配置精确文件清单（工作树门禁读取）：`index.html`, `package.json`, `vite.config.ts`。",
                    "当前 `apps/web/` 顶层配置精确文件清单（工作树门禁读取）：`index.html`, `package.json`, `playwright.config.ts`, `vite.config.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-app-config-list-missing-current-file|docs/product/Banking_Budget_Files.md|playwright.config.ts",
            result.stdout,
        )

    def test_fails_when_frontend_app_config_exact_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/` 顶层配置精确文件清单（工作树门禁读取）：`index.html`, `package.json`, `vite.config.ts`。",
                    "当前 `apps/web/` 顶层配置精确文件清单（工作树门禁读取）：`legacy.config.ts`, `index.html`, `package.json`, `vite.config.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-app-config-list-stale|docs/product/Banking_Budget_Files.md|legacy.config.ts",
            result.stdout,
        )

    def test_fails_when_frontend_app_config_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/tailwind.config.cjs").write_text(
                "module.exports = {};\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/` 顶层配置精确文件清单（工作树门禁读取）：`index.html`, `package.json`, `vite.config.ts`。",
                    "当前 `apps/web/` 顶层配置精确文件清单（工作树门禁读取）：`index.html`, `package.json`, `tailwind.config.cjs`, `vite.config.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-frontend-app-config-list-missing-current-file|docs/development/current-system-map.md|tailwind.config.cjs",
            result.stdout,
        )

    def test_fails_when_frontend_e2e_file_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/e2e/new-user-journey.spec.ts").write_text(
                "import { test } from '@playwright/test';\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/e2e/` 前端验收脚本精确文件清单（工作树门禁读取）：`current-user-journey.spec.ts`。",
                    "当前 `apps/web/e2e/` 前端验收脚本精确文件清单（工作树门禁读取）：`current-user-journey.spec.ts`, `new-user-journey.spec.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-e2e-list-missing-current-file|docs/product/Banking_Budget_Files.md|new-user-journey.spec.ts",
            result.stdout,
        )

    def test_fails_when_frontend_e2e_exact_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/e2e/` 前端验收脚本精确文件清单（工作树门禁读取）：`current-user-journey.spec.ts`。",
                    "当前 `apps/web/e2e/` 前端验收脚本精确文件清单（工作树门禁读取）：`current-user-journey.spec.ts`, `retired-user-journey.spec.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-e2e-list-stale|docs/product/Banking_Budget_Files.md|retired-user-journey.spec.ts",
            result.stdout,
        )

    def test_fails_when_frontend_e2e_file_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/e2e/new-system-user-journey.spec.ts").write_text(
                "import { test } from '@playwright/test';\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/e2e/` 前端验收脚本精确文件清单（工作树门禁读取）：`current-user-journey.spec.ts`。",
                    "当前 `apps/web/e2e/` 前端验收脚本精确文件清单（工作树门禁读取）：`current-user-journey.spec.ts`, `new-system-user-journey.spec.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-frontend-e2e-list-missing-current-file|docs/development/current-system-map.md|new-system-user-journey.spec.ts",
            result.stdout,
        )

    def test_fails_when_frontend_src_file_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/legacyEntry.ts").write_text(
                "export const legacyEntry = true;\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/` 顶层精确文件清单（工作树门禁读取）：`main.tsx`, `vite-env.d.ts`。",
                    "当前 `apps/web/src/` 顶层精确文件清单（工作树门禁读取）：`legacyEntry.ts`, `main.tsx`, `vite-env.d.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-src-list-missing-current-file|docs/product/Banking_Budget_Files.md|legacyEntry.ts",
            result.stdout,
        )

    def test_fails_when_frontend_src_exact_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/` 顶层精确文件清单（工作树门禁读取）：`main.tsx`, `vite-env.d.ts`。",
                    "当前 `apps/web/src/` 顶层精确文件清单（工作树门禁读取）：`RetiredRoot.ts`, `main.tsx`, `vite-env.d.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-src-list-stale|docs/product/Banking_Budget_Files.md|RetiredRoot.ts",
            result.stdout,
        )

    def test_fails_when_frontend_src_file_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/newSystemEntry.ts").write_text(
                "export const newSystemEntry = true;\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/` 顶层精确文件清单（工作树门禁读取）：`main.tsx`, `vite-env.d.ts`。",
                    "当前 `apps/web/src/` 顶层精确文件清单（工作树门禁读取）：`main.tsx`, `newSystemEntry.ts`, `vite-env.d.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-frontend-src-list-missing-current-file|docs/development/current-system-map.md|newSystemEntry.ts",
            result.stdout,
        )

    def test_fails_when_frontend_style_file_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/styles/legacy.css").write_text(
                ".legacy { display: block; }\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/styles/` 精确文件清单（工作树门禁读取）：`index.css`。",
                    "当前 `apps/web/src/styles/` 精确文件清单（工作树门禁读取）：`index.css`, `legacy.css`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-style-list-missing-current-file|docs/product/Banking_Budget_Files.md|legacy.css",
            result.stdout,
        )

    def test_fails_when_frontend_style_exact_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/styles/` 精确文件清单（工作树门禁读取）：`index.css`。",
                    "当前 `apps/web/src/styles/` 精确文件清单（工作树门禁读取）：`index.css`, `retired.css`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-style-list-stale|docs/product/Banking_Budget_Files.md|retired.css",
            result.stdout,
        )

    def test_fails_when_frontend_style_file_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/styles/new-system.css").write_text(
                ".new-system { display: block; }\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/styles/` 精确文件清单（工作树门禁读取）：`index.css`。",
                    "当前 `apps/web/src/styles/` 精确文件清单（工作树门禁读取）：`index.css`, `new-system.css`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-frontend-style-list-missing-current-file|docs/development/current-system-map.md|new-system.css",
            result.stdout,
        )

    def test_fails_when_frontend_app_file_is_not_in_file_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/NewShell.tsx").write_text(
                "export function NewShell() { return null; }\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/app/` 顶层精确文件清单（工作树门禁读取）：`workspaceCatalog.tsx`。",
                    "当前 `apps/web/src/app/` 顶层精确文件清单（工作树门禁读取）：`NewShell.tsx`, `workspaceCatalog.tsx`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-app-list-missing-current-file|docs/product/Banking_Budget_Files.md|NewShell.tsx",
            result.stdout,
        )

    def test_fails_when_frontend_app_exact_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/app/` 顶层精确文件清单（工作树门禁读取）：`workspaceCatalog.tsx`。",
                    "当前 `apps/web/src/app/` 顶层精确文件清单（工作树门禁读取）：`RetiredShell.tsx`, `workspaceCatalog.tsx`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-app-list-stale|docs/product/Banking_Budget_Files.md|RetiredShell.tsx",
            result.stdout,
        )

    def test_fails_when_frontend_app_file_is_not_in_system_map_exact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/NewSystemShell.tsx").write_text(
                "export function NewSystemShell() { return null; }\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/app/` 顶层精确文件清单（工作树门禁读取）：`workspaceCatalog.tsx`。",
                    "当前 `apps/web/src/app/` 顶层精确文件清单（工作树门禁读取）：`NewSystemShell.tsx`, `workspaceCatalog.tsx`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-frontend-app-list-missing-current-file|docs/development/current-system-map.md|NewSystemShell.tsx",
            result.stdout,
        )

    def test_fails_when_workspace_component_import_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/workspaceCatalog.tsx").write_text(
                'import { MissingPageContent } from "./components/MissingPageContent";\n'
                'export const workspaceTree = [{ label: "预算管理" }];\n',
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("workspace-component-import-missing-file|apps/web/src/app/components/MissingPageContent.tsx|MissingPageContent.tsx", result.stdout)

    def test_fails_when_frontend_domain_lib_is_not_in_file_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/lib/newFeatureApi.ts").write_text(
                "export const newFeatureApi = {};\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/lib/` 前端 domain 精确文件清单（工作树门禁读取）：`currentApi.ts`, `currentViewModel.ts`。",
                    "当前 `apps/web/src/lib/` 前端 domain 精确文件清单（工作树门禁读取）：`currentApi.ts`, `currentViewModel.ts`, `newFeatureApi.ts`。",
                )
                + "newFeatureApi.ts\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-lib-list-missing-current-lib|docs/product/Banking_Budget_Files.md|newFeatureApi.ts",
            result.stdout,
        )

    def test_fails_when_frontend_domain_lib_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/lib/` 前端 domain 精确文件清单（工作树门禁读取）：`currentApi.ts`, `currentViewModel.ts`。",
                    "当前 `apps/web/src/lib/` 前端 domain 精确文件清单（工作树门禁读取）：`currentApi.ts`, `currentViewModel.ts`, `staleFeatureApi.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-lib-list-stale|docs/product/Banking_Budget_Files.md|staleFeatureApi.ts",
            result.stdout,
        )

    def test_fails_when_frontend_domain_lib_is_not_in_system_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/lib/newFeatureViewModel.ts").write_text(
                "export const newFeatureViewModel = {};\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/lib/` 前端 domain 精确文件清单（工作树门禁读取）：`currentApi.ts`, `currentViewModel.ts`。",
                    "当前 `apps/web/src/lib/` 前端 domain 精确文件清单（工作树门禁读取）：`currentApi.ts`, `currentViewModel.ts`, `newFeatureViewModel.ts`。",
                )
                + "newFeatureViewModel.ts\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-frontend-lib-list-missing-current-lib|docs/development/current-system-map.md|newFeatureViewModel.ts",
            result.stdout,
        )

    def test_fails_when_frontend_shared_lib_is_not_in_file_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/lib/newSharedHelper.ts").write_text(
                "export const newSharedHelper = {};\n",
                encoding="utf-8",
            )
            system_map = root / "docs/development/current-system-map.md"
            system_map.write_text(
                system_map.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单（工作树门禁读取）：`api.ts`。",
                    "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单（工作树门禁读取）：`api.ts`, `newSharedHelper.ts`。",
                )
                + "newSharedHelper.ts\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-shared-lib-list-missing-current-lib|docs/product/Banking_Budget_Files.md|newSharedHelper.ts",
            result.stdout,
        )

    def test_fails_when_frontend_shared_lib_list_keeps_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单（工作树门禁读取）：`api.ts`。",
                    "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单（工作树门禁读取）：`api.ts`, `retiredHelper.ts`。",
                ),
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "frontend-shared-lib-list-stale|docs/product/Banking_Budget_Files.md|retiredHelper.ts",
            result.stdout,
        )

    def test_fails_when_frontend_shared_lib_is_not_in_system_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/lib/newSystemSharedHelper.ts").write_text(
                "export const newSystemSharedHelper = {};\n",
                encoding="utf-8",
            )
            files_doc = root / "docs/product/Banking_Budget_Files.md"
            files_doc.write_text(
                files_doc.read_text(encoding="utf-8").replace(
                    "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单（工作树门禁读取）：`api.ts`。",
                    "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单（工作树门禁读取）：`api.ts`, `newSystemSharedHelper.ts`。",
                )
                + "newSystemSharedHelper.ts\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "system-map-frontend-shared-lib-list-missing-current-lib|docs/development/current-system-map.md|newSystemSharedHelper.ts",
            result.stdout,
        )

    def test_fails_when_frontend_ui_file_contains_raw_api_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            (root / "apps/web/src/app/components/DataAccountContent.tsx").write_text(
                'export function DataAccountContent() { return fetch("/api/data-accounts"); }\n',
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("frontend-ui-raw-api-path|apps/web/src/app/components/DataAccountContent.tsx|/api/", result.stdout)

    def _allow_root_runtime_scripts(self, root: Path) -> None:
        readme_path = root / "README.md"
        readme_path.write_text(
            readme_path.read_text(encoding="utf-8").replace(
                "`package.json`, `resources`, `var`",
                "`package.json`, `resources`, `start.sh`, `stop.sh`, `var`",
            ),
            encoding="utf-8",
        )

    def test_runtime_scripts_with_screen_contract_pass_worktree_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            self._allow_root_runtime_scripts(root)
            (root / "start.sh").write_text(
                """
BACKEND_SCREEN_SESSION="banking-budget-api"
FRONTEND_SCREEN_SESSION="banking-budget-web"
screen_running() { screen -ls 2>/dev/null || true; }
port_listening() { lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
start_screen() { screen -dmS "$1" bash -lc "$2"; }
""",
                encoding="utf-8",
            )
            (root / "stop.sh").write_text(
                """
BACKEND_SCREEN_SESSION="banking-budget-api"
FRONTEND_SCREEN_SESSION="banking-budget-web"
screen_running() { screen -ls 2>/dev/null || true; }
stop_screen() { screen -S "$2" -X quit; }
stop_port_listener() { lsof -tiTCP:"$2" -sTCP:LISTEN; }
""",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 0)

    def test_runtime_scripts_fail_when_screen_contract_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_minimal_root(root)
            self._allow_root_runtime_scripts(root)
            (root / "start.sh").write_text(
                "nohup python3 apps/api/run_server.py --port 8009 & echo $! > var/pids/backend.pid\n",
                encoding="utf-8",
            )
            (root / "stop.sh").write_text(
                "kill $(cat var/pids/backend.pid)\n",
                encoding="utf-8",
            )

            result = self.run_script(root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("runtime-script-marker-missing|start.sh|BACKEND_SCREEN_SESSION=\"banking-budget-api\"", result.stdout)
        self.assertIn("runtime-script-marker-missing|start.sh|port_listening()", result.stdout)
        self.assertIn("runtime-script-marker-missing|stop.sh|stop_port_listener()", result.stdout)


if __name__ == "__main__":
    unittest.main()
