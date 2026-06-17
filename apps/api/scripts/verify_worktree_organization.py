from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_ROOT_ENTRIES = (
    "README.md",
    "AGENTS.md",
    "CONTEXT.md",
    "apps",
    "docs",
    "resources",
    "archive",
    "var",
)

ALLOWED_ROOT_ENTRIES = {
    ".agents",
    ".git",
    ".gitignore",
    ".ignore",
    ".qoder",
    ".scratch",
    ".superpowers",
    ".vscode",
    "AGENTS.md",
    "CHANGELOG.md",
    "CONTEXT.md",
    "README.md",
    "apps",
    "archive",
    "docs",
    "node_modules",
    "package-lock.json",
    "package.json",
    "resources",
    "skills-lock.json",
    "start.sh",
    "stop.sh",
    "var",
}
LOCAL_ONLY_ROOT_ENTRIES = {
    ".git",
    ".qoder",
    ".superpowers",
    ".venv",
    ".vscode",
    "node_modules",
}
ROOT_ENTRY_LIST_PREFIX = "当前仓库根目录持久入口精确清单"

REQUIRED_GUIDE_FILES = (
    ".agents/README.md",
    ".agents/skills/README.md",
    ".scratch/README.md",
    "archive/README.md",
    "archive/frontend_retired/README.md",
    "archive/handover/README.md",
    "archive/releases/README.md",
    "archive/runtime_snapshots/README.md",
    "archive/team_packages/README.md",
    "var/README.md",
    "resources/README.md",
    "resources/business_inputs/README.md",
    "resources/download_template/README.md",
    "resources/knowledge_base/README.md",
    "docs/development/README.md",
    "docs/development/active-worktree-manifest.md",
    "docs/development/department-expense-module-map.md",
    "docs/development/current-worktree-status.md",
    "docs/development/worktree-organization-20260603.md",
    "docs/development/repo-layout.md",
    "docs/development/current-system-map.md",
    "docs/agents/README.md",
    "docs/product/Banking_Budget_Files.md",
)

REQUIRED_PACKAGE_SCRIPTS = {
    Path("package.json"): {
        "test:view-model": "npm --workspace apps/web run test:view-model",
    },
    Path("apps/web/package.json"): {
        "test:view-model": "playwright test --config=playwright.view-model.config.ts --reporter=list",
    },
}
RUNTIME_SCRIPT_REQUIRED_MARKERS = {
    Path("start.sh"): (
        'BACKEND_SCREEN_SESSION="banking-budget-api"',
        'FRONTEND_SCREEN_SESSION="banking-budget-web"',
        "screen_running()",
        "start_screen()",
        "port_listening()",
        "screen -dmS",
    ),
    Path("stop.sh"): (
        'BACKEND_SCREEN_SESSION="banking-budget-api"',
        'FRONTEND_SCREEN_SESSION="banking-budget-web"',
        "screen_running()",
        "stop_screen()",
        "stop_port_listener()",
        "lsof -tiTCP",
        "screen -S",
    ),
}

RETIRED_ROOT_ENTRIES = (
    ".hermes",
    ".venv312",
    "backend",
    "data",
    "download_template",
    "exports",
    "knowledge_base",
    "outputs",
    "releases",
    "src",
    "src_from_Figma",
)

ALLOWED_VAR_ENTRIES = {
    ".gitkeep",
    "README.md",
    "data",
    "logs",
    "output",
    "pids",
    "run",
    "scripts",
    "test-runs",
}

RETIRED_VAR_ENTRIES = (
    "backups",
    "exports",
    "log",
)
VAR_INDEX = Path("var/README.md")
VAR_DIR_LIST_PREFIX = "当前 `var/` 顶层运行目录精确清单"

ACTIVE_TEXT_ROOTS = (
    "README.md",
    "CONTEXT.md",
    "docs/product",
    "docs/development",
    "resources/knowledge_base",
    "apps/web/src",
    "apps/api/app",
)

ACTIVE_CODE_ROOTS = (
    "apps/api/app",
    "apps/api/scripts",
    "apps/web/src",
)
ACTIVE_PYTHON_BYTECODE_ROOTS = (
    Path("apps/api"),
    Path("apps/api/app"),
    Path("apps/api/scripts"),
)

FORBIDDEN_ACTIVE_MARKERS = (
    "预算基础数据维护",
    "预算基础数据录入",
    "基础数据维护四界面",
    "Figma `NavigationTree`",
)

RETIRED_CODE_MARKERS = (
    "report_accounts",
    "report_account",
    "report_data_mapping",
    "controlItemMapping",
    "ControlItemMapping",
    "control_item_subject_mapping",
    "DRIVER_EXPR",
    "driver_source_priority",
    "driver_module",
    "product_rollup_method",
    "forecast_workbench_layout",
    "assumption_parameter",
    "pivot_aggregate_rule",
    "control_item_code",
    "control_item_name",
    "control_dept_code",
)

RETIRED_CODE_MARKER_ALLOWED_FILES = {
    Path("apps/api/app/db_bootstrap/expense.py"),
    Path("apps/api/app/db_bootstrap/retired_deletion.py"),
    Path("apps/api/app/knowledge_base.py"),
    Path("apps/api/scripts/verify_worktree_organization.py"),
    Path("apps/api/scripts/full_user_journey.py"),
}

TEXT_SUFFIXES = {".md", ".py", ".ts", ".tsx"}
APPS_ROOT = Path("apps")
CURRENT_SCRIPT_DIR = "apps/api/scripts"
BACKEND_API_ROOT = Path("apps/api")
BACKEND_API_DOCS_DIR = Path("apps/api/docs")
CURRENT_APP_MODULE_DIR = "apps/api/app"
CURRENT_ROUTER_DIR = "apps/api/app/routers"
CURRENT_SERVICE_DIR = "apps/api/app/services"
CURRENT_DB_BOOTSTRAP_DIR = "apps/api/app/db_bootstrap"
MAIN_PATH = Path("apps/api/app/main.py")
FILE_MAP_PATH = Path("docs/product/Banking_Budget_Files.md")
PRODUCT_DOCS_DIR = Path("docs/product")
PRODUCT_DOCS_INDEX = PRODUCT_DOCS_DIR / "README.md"
PRODUCT_DOC_LIST_PREFIX = "当前 `docs/product/` 产品文档精确清单"
RESOURCES_DIR = Path("resources")
RESOURCES_INDEX = RESOURCES_DIR / "README.md"
RESOURCES_DIR_LIST_PREFIX = "当前 `resources/` 顶层目录精确清单"
BUSINESS_INPUTS_DIR = Path("resources/business_inputs")
BUSINESS_INPUTS_INDEX = BUSINESS_INPUTS_DIR / "README.md"
BUSINESS_INPUT_LIST_PREFIX = "当前 `resources/business_inputs/` 精确文件清单"
DOWNLOAD_TEMPLATES_DIR = Path("resources/download_template")
DOWNLOAD_TEMPLATES_INDEX = DOWNLOAD_TEMPLATES_DIR / "README.md"
DOWNLOAD_TEMPLATE_LIST_PREFIX = "当前 `resources/download_template/` 精确文件清单"
KNOWLEDGE_BASE_DIR = Path("resources/knowledge_base")
KNOWLEDGE_BASE_INDEX = KNOWLEDGE_BASE_DIR / "README.md"
KNOWLEDGE_BASE_LAYER_LIST_PREFIX = "当前 `resources/knowledge_base/` 一级目录精确清单"
SCRATCH_DIR = Path(".scratch")
SCRATCH_INDEX = SCRATCH_DIR / "README.md"
SCRATCH_WORK_AREA_LIST_PREFIX = "当前 `.scratch/` 工作区精确清单"
ARCHIVE_DIR = Path("archive")
ARCHIVE_INDEX = ARCHIVE_DIR / "README.md"
ARCHIVE_DIR_LIST_PREFIX = "当前 `archive/` 顶层目录精确清单"
ARCHIVE_FRONTEND_RETIRED_DIR = Path("archive/frontend_retired")
ARCHIVE_FRONTEND_RETIRED_INDEX = ARCHIVE_FRONTEND_RETIRED_DIR / "README.md"
ARCHIVE_FRONTEND_RETIRED_DIR_LIST_PREFIX = "当前 `archive/frontend_retired/` 退休前端目录精确清单"
ARCHIVE_HANDOVER_DIR = Path("archive/handover")
ARCHIVE_HANDOVER_INDEX = ARCHIVE_HANDOVER_DIR / "README.md"
ARCHIVE_HANDOVER_DIR_LIST_PREFIX = "当前 `archive/handover/` 历史交接目录精确清单"
ARCHIVE_RELEASES_DIR = Path("archive/releases")
ARCHIVE_RELEASES_INDEX = ARCHIVE_RELEASES_DIR / "README.md"
ARCHIVE_RELEASES_DIR_LIST_PREFIX = "当前 `archive/releases/` 历史发布目录精确清单"
ARCHIVE_RUNTIME_SNAPSHOTS_DIR = Path("archive/runtime_snapshots")
ARCHIVE_RUNTIME_SNAPSHOTS_INDEX = ARCHIVE_RUNTIME_SNAPSHOTS_DIR / "README.md"
ARCHIVE_RUNTIME_SNAPSHOTS_DIR_LIST_PREFIX = "当前 `archive/runtime_snapshots/` 运行快照目录精确清单"
ARCHIVE_TEAM_PACKAGES_DIR = Path("archive/team_packages")
ARCHIVE_TEAM_PACKAGES_INDEX = ARCHIVE_TEAM_PACKAGES_DIR / "README.md"
ARCHIVE_TEAM_PACKAGES_DIR_LIST_PREFIX = "当前 `archive/team_packages/` 团队包目录精确清单"
WORKSPACE_CATALOG_PATH = Path("apps/web/src/app/workspaceCatalog.tsx")
FRONTEND_APP_DIR = Path("apps/web")
FRONTEND_E2E_DIR = Path("apps/web/e2e")
WORKSPACE_COMPONENT_ROOT = Path("apps/web/src/app/components")
FRONTEND_SRC_ROOT = Path("apps/web/src")
FRONTEND_APP_ROOT = Path("apps/web/src/app")
FRONTEND_ENTRY_PATH = Path("apps/web/src/main.tsx")
FRONTEND_LIB_ROOT = Path("apps/web/src/lib")
FRONTEND_STYLE_ROOT = Path("apps/web/src/styles")
CURRENT_SYSTEM_MAP_PATH = Path("docs/development/current-system-map.md")
DEVELOPMENT_DOCS_DIR = Path("docs/development")
DEVELOPMENT_DOCS_INDEX = DEVELOPMENT_DOCS_DIR / "README.md"
DEVELOPMENT_DOC_LIST_PREFIX = "当前 `docs/development/` 开发文档精确清单"
AGENT_DOCS_DIR = Path("docs/agents")
AGENT_DOCS_INDEX = AGENT_DOCS_DIR / "README.md"
SCRIPT_LIST_PREFIX = "当前 `apps/api/scripts/` 精确文件清单"
AGENT_DOC_LIST_PREFIX = "当前 `docs/agents/` 协作文档精确清单"
APPS_DIR_LIST_PREFIX = "当前 `apps/` 应用目录精确清单"
BACKEND_API_CONFIG_LIST_PREFIX = "当前 `apps/api/` 顶层配置精确文件清单"
BACKEND_API_DOC_LIST_PREFIX = "当前 `apps/api/docs/` 后端局部文档精确文件清单"
APP_MODULE_LIST_PREFIX = "当前 `apps/api/app/` 顶层精确文件清单"
ROUTER_LIST_PREFIX = "当前 `apps/api/app/routers/` 精确文件清单"
SERVICE_LIST_PREFIX = "当前 `apps/api/app/services/` 精确文件清单"
DB_BOOTSTRAP_LIST_PREFIX = "当前 `apps/api/app/db_bootstrap/` 精确文件清单"
FRONTEND_APP_CONFIG_LIST_PREFIX = "当前 `apps/web/` 顶层配置精确文件清单"
FRONTEND_E2E_LIST_PREFIX = "当前 `apps/web/e2e/` 前端验收脚本精确文件清单"
FRONTEND_SRC_LIST_PREFIX = "当前 `apps/web/src/` 顶层精确文件清单"
FRONTEND_COMPONENT_LIST_PREFIX = "当前 `apps/web/src/app/components/` 顶层精确文件清单"
FRONTEND_APP_LIST_PREFIX = "当前 `apps/web/src/app/` 顶层精确文件清单"
FRONTEND_LIB_LIST_PREFIX = "当前 `apps/web/src/lib/` 前端 domain 精确文件清单"
FRONTEND_SHARED_LIB_LIST_PREFIX = "当前 `apps/web/src/lib/` 前端 shared helper 精确文件清单"
FRONTEND_STYLE_LIST_PREFIX = "当前 `apps/web/src/styles/` 精确文件清单"
SYSTEM_MAP_WORKSPACE_LABEL_LIST_PREFIX = "当前 `workspaceCatalog.tsx` 精确标签清单"
SYSTEM_MAP_ROUTER_LIST_PREFIX = ROUTER_LIST_PREFIX
ROUTER_MOUNT_EXCEPTIONS = {
    "expense_forecast_rules.py": "registered from expense_forecast.py through register_expense_forecast_rule_routes",
    "org_product_helpers.py": "helper module shared by split org-product routers, not a standalone router",
}
NAVIGATION_DOC_PATHS = (
    Path("docs/product/Banking_Budget_System_PDD.md"),
    Path("docs/product/Banking_Budget_UI_Unified_PDD.md"),
)
ROOT_MARKDOWN_DOCS = (
    Path("README.md"),
    Path("CONTEXT.md"),
    Path("AGENTS.md"),
)
AGENTS_LOCAL_DIR = Path(".agents")
AGENTS_LOCAL_INDEX = AGENTS_LOCAL_DIR / "README.md"
AGENTS_LOCAL_DIR_LIST_PREFIX = "当前 `.agents/` 顶层目录精确清单"
AGENTS_SKILLS_DIR = Path(".agents/skills")
AGENTS_SKILLS_INDEX = AGENTS_SKILLS_DIR / "README.md"
AGENTS_SKILL_LIST_PREFIX = "当前 `.agents/skills/` 本地技能精确清单"


@dataclass(frozen=True)
class Finding:
    kind: str
    path: Path
    detail: str


def _display(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _iter_text_files(root: Path, relative_roots: tuple[str, ...]) -> tuple[Path, ...]:
    files: list[Path] = []
    for relative in relative_roots:
        current = root / relative
        if not current.exists():
            continue
        if current.is_file():
            if current.suffix in TEXT_SUFFIXES:
                files.append(current)
            continue
        for path in current.rglob("*"):
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                files.append(path)
    return tuple(sorted(files))


def _is_retired_marker_allowed(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return relative in RETIRED_CODE_MARKER_ALLOWED_FILES


def _workspace_labels(catalog_path: Path) -> tuple[str, ...]:
    text = catalog_path.read_text(encoding="utf-8")
    labels = re.findall(r'label:\s*"([^"]+)"', text)
    return tuple(dict.fromkeys(labels))


def _workspace_component_imports(catalog_path: Path) -> tuple[str, ...]:
    text = catalog_path.read_text(encoding="utf-8")
    imports = re.findall(r'from\s+"\.\/components\/([^"]+)"', text)
    return tuple(dict.fromkeys(imports))


def _markdown_relative_links(markdown_path: Path) -> tuple[tuple[str, Path], ...]:
    text = markdown_path.read_text(encoding="utf-8")
    links: list[tuple[str, Path]] = []
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
        raw_target = match.group(1).strip()
        if not raw_target or raw_target.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw_target):
            continue
        target = raw_target.strip("<>")
        target = target.split("#", 1)[0]
        if not target:
            continue
        links.append((raw_target, (markdown_path.parent / target).resolve()))
    return tuple(links)


def _current_markdown_link_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for relative in ROOT_MARKDOWN_DOCS:
        path = root / relative
        if path.exists():
            files.append(path)
    docs_root = root / "docs"
    if docs_root.exists():
        files.extend(sorted(path for path in docs_root.rglob("*.md") if path.is_file()))
    return tuple(dict.fromkeys(files))


def _system_map_line(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line
    return ""


def _system_map_workspace_labels(text: str) -> tuple[str, ...]:
    line = _system_map_line(text, SYSTEM_MAP_WORKSPACE_LABEL_LIST_PREFIX)
    if not line or "：" not in line:
        return tuple()
    raw_items = line.split("：", 1)[1].strip().rstrip("。")
    return tuple(item.strip() for item in raw_items.split("、") if item.strip())


def _system_map_router_files(text: str) -> tuple[str, ...]:
    line = _system_map_line(text, SYSTEM_MAP_ROUTER_LIST_PREFIX)
    if not line:
        return tuple()
    return tuple(re.findall(r"`([^`]+\.py)`", line))


def _prefixed_python_file_list(text: str, prefix: str) -> tuple[str, ...]:
    line = _system_map_line(text, prefix)
    if not line:
        return tuple()
    return tuple(re.findall(r"`([^`]+\.py)`", line))


def _prefixed_typescript_file_list(text: str, prefix: str) -> tuple[str, ...]:
    line = _system_map_line(text, prefix)
    if not line:
        return tuple()
    return tuple(re.findall(r"`([^`]+\.ts)`", line))


def _prefixed_file_list(text: str, prefix: str) -> tuple[str, ...]:
    line = _system_map_line(text, prefix)
    if not line:
        return tuple()
    inventory_text = line.rsplit("：", maxsplit=1)[-1]
    return tuple(re.findall(r"`([^`]+)`", inventory_text))


def _prefixed_frontend_file_list(text: str, prefix: str) -> tuple[str, ...]:
    line = _system_map_line(text, prefix)
    if not line:
        return tuple()
    return tuple(re.findall(r"`([^`]+\.(?:ts|tsx))`", line))


def _prefixed_css_file_list(text: str, prefix: str) -> tuple[str, ...]:
    line = _system_map_line(text, prefix)
    if not line:
        return tuple()
    return tuple(re.findall(r"`([^`]+\.css)`", line))


def _current_python_module_names(directory: Path) -> tuple[str, ...]:
    if not directory.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(directory.glob("*.py"))
        if path.name != "__init__.py"
    )


def _backend_api_config_names(api_root: Path) -> tuple[str, ...]:
    if not api_root.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(api_root.iterdir())
        if path.is_file() and not path.name.startswith("test_")
    )


def _child_dir_names(directory: Path) -> tuple[str, ...]:
    if not directory.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(directory.iterdir())
        if path.is_dir()
    )


def _markdown_file_names(directory: Path) -> tuple[str, ...]:
    if not directory.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(directory.glob("*.md"))
    )


def _indexed_markdown_file_names(directory: Path) -> tuple[str, ...]:
    if not directory.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(directory.glob("*.md"))
        if path.name != "README.md"
    )


def _indexed_file_names(directory: Path) -> tuple[str, ...]:
    if not directory.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != "README.md" and not path.name.startswith(".")
    )


def _root_handoff_entry_names(root: Path) -> tuple[str, ...]:
    return tuple(
        path.name
        for path in sorted(root.iterdir())
        if path.name not in LOCAL_ONLY_ROOT_ENTRIES
    )


def _verify_exact_module_inventory(
    findings: list[Finding],
    *,
    current_names: tuple[str, ...],
    inventory_path: Path,
    inventory_text: str,
    inventory_prefix: str,
    missing_list_kind: str,
    missing_current_kind: str,
    stale_kind: str,
    directory_label: str,
) -> None:
    if not current_names:
        return
    inventory_names = _prefixed_python_file_list(inventory_text, inventory_prefix)
    if not inventory_names:
        findings.append(Finding(missing_list_kind, inventory_path, directory_label))
        return
    for module_name in current_names:
        if module_name not in inventory_names:
            findings.append(Finding(missing_current_kind, inventory_path, module_name))
    for module_name in inventory_names:
        if module_name not in current_names:
            findings.append(Finding(stale_kind, inventory_path, module_name))


def _verify_child_dirs_have_readme(
    findings: list[Finding],
    *,
    directory: Path,
    missing_kind: str,
) -> None:
    if not directory.exists():
        return
    for child_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
        readme_path = child_dir / "README.md"
        if not readme_path.exists():
            findings.append(Finding(missing_kind, readme_path, child_dir.name))


def _frontend_domain_lib_files(lib_root: Path) -> tuple[Path, ...]:
    if not lib_root.exists():
        return tuple()
    return tuple(
        sorted(
            path
            for path in lib_root.rglob("*.ts")
            if path.name.endswith("Api.ts") or path.name.endswith("ViewModel.ts")
        )
    )


def _frontend_domain_lib_names(lib_root: Path) -> tuple[str, ...]:
    return tuple(path.name for path in _frontend_domain_lib_files(lib_root))


def _frontend_shared_lib_names(lib_root: Path) -> tuple[str, ...]:
    if not lib_root.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(lib_root.rglob("*.ts"))
        if not path.name.endswith("Api.ts") and not path.name.endswith("ViewModel.ts")
    )


def _frontend_app_config_names(app_dir: Path) -> tuple[str, ...]:
    if not app_dir.exists():
        return tuple()
    allowed_suffixes = {".cjs", ".html", ".json", ".ts"}
    return tuple(
        path.name
        for path in sorted(app_dir.iterdir())
        if path.is_file() and path.suffix in allowed_suffixes
    )


def _frontend_top_level_component_names(component_root: Path) -> tuple[str, ...]:
    if not component_root.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(component_root.iterdir())
        if path.is_file() and path.suffix in {".ts", ".tsx"}
    )


def _frontend_top_level_css_names(style_root: Path) -> tuple[str, ...]:
    if not style_root.exists():
        return tuple()
    return tuple(
        path.name
        for path in sorted(style_root.iterdir())
        if path.is_file() and path.suffix == ".css"
    )


def _verify_exact_frontend_inventory(
    findings: list[Finding],
    *,
    current_names: tuple[str, ...],
    inventory_path: Path,
    inventory_text: str,
    inventory_prefix: str,
    missing_list_kind: str,
    missing_current_kind: str,
    stale_kind: str,
    directory_label: str,
) -> None:
    if not current_names:
        return
    inventory_names = _prefixed_frontend_file_list(inventory_text, inventory_prefix)
    if not inventory_names:
        findings.append(Finding(missing_list_kind, inventory_path, directory_label))
        return
    for file_name in current_names:
        if file_name not in inventory_names:
            findings.append(Finding(missing_current_kind, inventory_path, file_name))
    for file_name in inventory_names:
        if file_name not in current_names:
            findings.append(Finding(stale_kind, inventory_path, file_name))


def _verify_exact_css_inventory(
    findings: list[Finding],
    *,
    current_names: tuple[str, ...],
    inventory_path: Path,
    inventory_text: str,
    inventory_prefix: str,
    missing_list_kind: str,
    missing_current_kind: str,
    stale_kind: str,
    directory_label: str,
) -> None:
    if not current_names:
        return
    inventory_names = _prefixed_css_file_list(inventory_text, inventory_prefix)
    if not inventory_names:
        findings.append(Finding(missing_list_kind, inventory_path, directory_label))
        return
    for file_name in current_names:
        if file_name not in inventory_names:
            findings.append(Finding(missing_current_kind, inventory_path, file_name))
    for file_name in inventory_names:
        if file_name not in current_names:
            findings.append(Finding(stale_kind, inventory_path, file_name))


def _verify_exact_named_file_inventory(
    findings: list[Finding],
    *,
    current_names: tuple[str, ...],
    inventory_path: Path,
    inventory_text: str,
    inventory_prefix: str,
    missing_list_kind: str,
    missing_current_kind: str,
    stale_kind: str,
    directory_label: str,
) -> None:
    if not current_names:
        return
    inventory_names = _prefixed_file_list(inventory_text, inventory_prefix)
    if not inventory_names:
        findings.append(Finding(missing_list_kind, inventory_path, directory_label))
        return
    for file_name in current_names:
        if file_name not in inventory_names:
            findings.append(Finding(missing_current_kind, inventory_path, file_name))
    for file_name in inventory_names:
        if file_name not in current_names:
            findings.append(Finding(stale_kind, inventory_path, file_name))


def _frontend_ui_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    app_root = root / FRONTEND_APP_ROOT
    if app_root.exists():
        files.extend(
            path
            for path in app_root.rglob("*")
            if path.is_file() and path.suffix in {".ts", ".tsx"}
        )
    entry_path = root / FRONTEND_ENTRY_PATH
    if entry_path.exists():
        files.append(entry_path)
    return tuple(sorted(files))


def _active_python_bytecode_dirs(root: Path) -> tuple[Path, ...]:
    cache_dirs: set[Path] = set()
    for relative_root in ACTIVE_PYTHON_BYTECODE_ROOTS:
        current_root = root / relative_root
        if not current_root.exists():
            continue
        for cache_dir in current_root.rglob("__pycache__"):
            if ".venv" in cache_dir.parts:
                continue
            cache_dirs.add(cache_dir)
    return tuple(sorted(cache_dirs))


def _verify_package_scripts(findings: list[Finding], root: Path) -> None:
    for relative_path, required_scripts in REQUIRED_PACKAGE_SCRIPTS.items():
        package_path = root / relative_path
        if not package_path.exists():
            findings.append(Finding("package-json-missing", package_path, str(relative_path)))
            continue
        try:
            package_data = json.loads(package_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            findings.append(Finding("package-json-invalid", package_path, str(relative_path)))
            continue
        scripts = package_data.get("scripts")
        if not isinstance(scripts, dict):
            findings.append(Finding("package-scripts-missing", package_path, str(relative_path)))
            continue
        for script_name, expected_command in required_scripts.items():
            actual_command = scripts.get(script_name)
            if actual_command is None:
                findings.append(Finding("package-script-missing", package_path, script_name))
            elif actual_command != expected_command:
                findings.append(
                    Finding(
                        "package-script-mismatch",
                        package_path,
                        f"{script_name}|expected={expected_command}|actual={actual_command}",
                    )
                )


def _verify_runtime_scripts(findings: list[Finding], root: Path) -> None:
    for relative_path, required_markers in RUNTIME_SCRIPT_REQUIRED_MARKERS.items():
        script_path = root / relative_path
        if not script_path.exists():
            continue
        script_text = script_path.read_text(encoding="utf-8")
        for marker in required_markers:
            if marker not in script_text:
                findings.append(Finding("runtime-script-marker-missing", script_path, marker))


def _mounted_router_modules(main_path: Path) -> set[str]:
    if not main_path.exists():
        return set()

    text = main_path.read_text(encoding="utf-8")
    mounted_modules: set[str] = set()
    imports: dict[str, list[str]] = {}
    for match in re.finditer(r"from\s+app\.routers\.([A-Za-z0-9_]+)\s+import\s+([^\n]+)", text):
        module = match.group(1)
        raw_symbols = match.group(2)
        symbols: list[str] = []
        for raw_symbol in raw_symbols.split(","):
            symbol = raw_symbol.strip()
            if not symbol:
                continue
            symbol = symbol.split(" as ")[-1].strip()
            symbols.append(symbol)
        imports[module] = symbols

    for module, symbols in imports.items():
        for symbol in symbols:
            if re.search(rf"include_router\(\s*{re.escape(symbol)}(?:\b|\()", text):
                mounted_modules.add(module)
                break
    return mounted_modules


def verify(root: Path) -> tuple[Finding, ...]:
    root = root.resolve()
    findings: list[Finding] = []

    for relative in REQUIRED_ROOT_ENTRIES:
        path = root / relative
        if not path.exists():
            findings.append(Finding("missing-required-root-entry", path, relative))

    for path in sorted(root.iterdir()):
        if path.name not in ALLOWED_ROOT_ENTRIES:
            findings.append(Finding("unexpected-root-entry", path, path.name))

    root_readme = root / "README.md"
    if root_readme.exists():
        root_readme_text = root_readme.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_root_handoff_entry_names(root),
            inventory_path=root_readme,
            inventory_text=root_readme_text,
            inventory_prefix=ROOT_ENTRY_LIST_PREFIX,
            missing_list_kind="root-entry-list-missing-from-readme",
            missing_current_kind="root-entry-missing-from-readme",
            stale_kind="root-entry-list-stale",
            directory_label=".",
        )

    var_root = root / "var"
    if var_root.exists():
        for path in sorted(var_root.iterdir()):
            if path.name not in ALLOWED_VAR_ENTRIES:
                findings.append(Finding("unexpected-var-entry", path, path.name))
        for relative in RETIRED_VAR_ENTRIES:
            path = var_root / relative
            if path.exists():
                findings.append(Finding("retired-var-entry-present", path, relative))
        var_index = root / VAR_INDEX
        if var_index.exists():
            var_index_text = var_index.read_text(encoding="utf-8")
            _verify_exact_named_file_inventory(
                findings,
                current_names=_child_dir_names(var_root),
                inventory_path=var_index,
                inventory_text=var_index_text,
                inventory_prefix=VAR_DIR_LIST_PREFIX,
                missing_list_kind="var-dir-list-missing-from-index",
                missing_current_kind="var-dir-missing-from-index",
                stale_kind="var-dir-list-stale",
                directory_label="var",
            )

    for relative in REQUIRED_GUIDE_FILES:
        path = root / relative
        if not path.exists():
            findings.append(Finding("missing-guide-file", path, relative))

    _verify_package_scripts(findings, root)
    _verify_runtime_scripts(findings, root)

    for relative in RETIRED_ROOT_ENTRIES:
        path = root / relative
        if path.exists():
            findings.append(Finding("retired-root-entry-present", path, relative))

    for path in _iter_text_files(root, ACTIVE_TEXT_ROOTS):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in FORBIDDEN_ACTIVE_MARKERS:
            if marker in text:
                findings.append(Finding("forbidden-active-marker", path, marker))

    for path in _iter_text_files(root, ACTIVE_CODE_ROOTS):
        if _is_retired_marker_allowed(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in RETIRED_CODE_MARKERS:
            if marker in text:
                findings.append(Finding("retired-code-marker-outside-contract", path, marker))

    for markdown_path in _current_markdown_link_files(root):
        for raw_link, resolved_link in _markdown_relative_links(markdown_path):
            if not resolved_link.exists():
                findings.append(Finding("current-doc-missing-link", resolved_link, raw_link))

    for cache_dir in _active_python_bytecode_dirs(root):
        findings.append(Finding("active-python-bytecode-cache-present", cache_dir, "__pycache__"))

    archive_index = root / ARCHIVE_INDEX
    archive_dir = root / ARCHIVE_DIR
    if archive_index.exists() and archive_dir.exists():
        archive_text = archive_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(archive_dir),
            inventory_path=archive_index,
            inventory_text=archive_text,
            inventory_prefix=ARCHIVE_DIR_LIST_PREFIX,
            missing_list_kind="archive-dir-list-missing-from-index",
            missing_current_kind="archive-dir-missing-from-index",
            stale_kind="archive-dir-list-stale",
            directory_label=str(ARCHIVE_DIR),
        )

    archive_frontend_retired_index = root / ARCHIVE_FRONTEND_RETIRED_INDEX
    archive_frontend_retired_dir = root / ARCHIVE_FRONTEND_RETIRED_DIR
    if archive_frontend_retired_index.exists() and archive_frontend_retired_dir.exists():
        archive_frontend_retired_text = archive_frontend_retired_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(archive_frontend_retired_dir),
            inventory_path=archive_frontend_retired_index,
            inventory_text=archive_frontend_retired_text,
            inventory_prefix=ARCHIVE_FRONTEND_RETIRED_DIR_LIST_PREFIX,
            missing_list_kind="archive-frontend-retired-dir-list-missing-from-index",
            missing_current_kind="archive-frontend-retired-dir-missing-from-index",
            stale_kind="archive-frontend-retired-dir-list-stale",
            directory_label=str(ARCHIVE_FRONTEND_RETIRED_DIR),
        )
        _verify_child_dirs_have_readme(
            findings,
            directory=archive_frontend_retired_dir,
            missing_kind="archive-frontend-retired-dir-missing-readme",
        )

    archive_handover_index = root / ARCHIVE_HANDOVER_INDEX
    archive_handover_dir = root / ARCHIVE_HANDOVER_DIR
    if archive_handover_index.exists() and archive_handover_dir.exists():
        archive_handover_text = archive_handover_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(archive_handover_dir),
            inventory_path=archive_handover_index,
            inventory_text=archive_handover_text,
            inventory_prefix=ARCHIVE_HANDOVER_DIR_LIST_PREFIX,
            missing_list_kind="archive-handover-dir-list-missing-from-index",
            missing_current_kind="archive-handover-dir-missing-from-index",
            stale_kind="archive-handover-dir-list-stale",
            directory_label=str(ARCHIVE_HANDOVER_DIR),
        )

    archive_releases_index = root / ARCHIVE_RELEASES_INDEX
    archive_releases_dir = root / ARCHIVE_RELEASES_DIR
    if archive_releases_index.exists() and archive_releases_dir.exists():
        archive_releases_text = archive_releases_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(archive_releases_dir),
            inventory_path=archive_releases_index,
            inventory_text=archive_releases_text,
            inventory_prefix=ARCHIVE_RELEASES_DIR_LIST_PREFIX,
            missing_list_kind="archive-release-dir-list-missing-from-index",
            missing_current_kind="archive-release-dir-missing-from-index",
            stale_kind="archive-release-dir-list-stale",
            directory_label=str(ARCHIVE_RELEASES_DIR),
        )

    archive_runtime_snapshots_index = root / ARCHIVE_RUNTIME_SNAPSHOTS_INDEX
    archive_runtime_snapshots_dir = root / ARCHIVE_RUNTIME_SNAPSHOTS_DIR
    if archive_runtime_snapshots_index.exists() and archive_runtime_snapshots_dir.exists():
        archive_runtime_snapshots_text = archive_runtime_snapshots_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(archive_runtime_snapshots_dir),
            inventory_path=archive_runtime_snapshots_index,
            inventory_text=archive_runtime_snapshots_text,
            inventory_prefix=ARCHIVE_RUNTIME_SNAPSHOTS_DIR_LIST_PREFIX,
            missing_list_kind="archive-runtime-snapshot-dir-list-missing-from-index",
            missing_current_kind="archive-runtime-snapshot-dir-missing-from-index",
            stale_kind="archive-runtime-snapshot-dir-list-stale",
            directory_label=str(ARCHIVE_RUNTIME_SNAPSHOTS_DIR),
        )

    archive_team_packages_index = root / ARCHIVE_TEAM_PACKAGES_INDEX
    archive_team_packages_dir = root / ARCHIVE_TEAM_PACKAGES_DIR
    if archive_team_packages_index.exists() and archive_team_packages_dir.exists():
        archive_team_packages_text = archive_team_packages_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(archive_team_packages_dir),
            inventory_path=archive_team_packages_index,
            inventory_text=archive_team_packages_text,
            inventory_prefix=ARCHIVE_TEAM_PACKAGES_DIR_LIST_PREFIX,
            missing_list_kind="archive-team-package-dir-list-missing-from-index",
            missing_current_kind="archive-team-package-dir-missing-from-index",
            stale_kind="archive-team-package-dir-list-stale",
            directory_label=str(ARCHIVE_TEAM_PACKAGES_DIR),
        )

    resources_index = root / RESOURCES_INDEX
    resources_dir = root / RESOURCES_DIR
    if resources_index.exists() and resources_dir.exists():
        resources_text = resources_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(resources_dir),
            inventory_path=resources_index,
            inventory_text=resources_text,
            inventory_prefix=RESOURCES_DIR_LIST_PREFIX,
            missing_list_kind="resources-dir-list-missing-from-index",
            missing_current_kind="resources-dir-missing-from-index",
            stale_kind="resources-dir-list-stale",
            directory_label=str(RESOURCES_DIR),
        )

    file_map = root / FILE_MAP_PATH
    apps_root = root / APPS_ROOT
    if file_map.exists() and apps_root.exists():
        file_map_text = file_map.read_text(encoding="utf-8")
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_app_dir_names = _child_dir_names(apps_root)
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_app_dir_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=APPS_DIR_LIST_PREFIX,
            missing_list_kind="apps-dir-list-missing-from-file-map",
            missing_current_kind="apps-dir-list-missing-current-dir",
            stale_kind="apps-dir-list-stale",
            directory_label=str(APPS_ROOT),
        )
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_app_dir_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=APPS_DIR_LIST_PREFIX,
            missing_list_kind="system-map-apps-dir-list-missing",
            missing_current_kind="system-map-apps-dir-list-missing-current-dir",
            stale_kind="system-map-apps-dir-list-stale",
            directory_label=str(APPS_ROOT),
        )

    script_dir = root / CURRENT_SCRIPT_DIR
    if file_map.exists() and script_dir.exists():
        file_map_text = file_map.read_text(encoding="utf-8")
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_script_names = _current_python_module_names(script_dir)
        _verify_exact_module_inventory(
            findings,
            current_names=current_script_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=SCRIPT_LIST_PREFIX,
            missing_list_kind="script-list-missing-from-file-map",
            missing_current_kind="script-list-missing-current-script",
            stale_kind="script-list-stale",
            directory_label=CURRENT_SCRIPT_DIR,
        )
        _verify_exact_module_inventory(
            findings,
            current_names=current_script_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=SCRIPT_LIST_PREFIX,
            missing_list_kind="system-map-script-list-missing",
            missing_current_kind="system-map-script-list-missing-current-script",
            stale_kind="system-map-script-list-stale",
            directory_label=CURRENT_SCRIPT_DIR,
        )

    backend_api_root = root / BACKEND_API_ROOT
    if file_map.exists() and backend_api_root.exists():
        file_map_text = file_map.read_text(encoding="utf-8")
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_backend_config_names = _backend_api_config_names(backend_api_root)
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_backend_config_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=BACKEND_API_CONFIG_LIST_PREFIX,
            missing_list_kind="backend-api-config-list-missing-from-file-map",
            missing_current_kind="backend-api-config-list-missing-current-file",
            stale_kind="backend-api-config-list-stale",
            directory_label=str(BACKEND_API_ROOT),
        )
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_backend_config_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=BACKEND_API_CONFIG_LIST_PREFIX,
            missing_list_kind="system-map-backend-api-config-list-missing",
            missing_current_kind="system-map-backend-api-config-list-missing-current-file",
            stale_kind="system-map-backend-api-config-list-stale",
            directory_label=str(BACKEND_API_ROOT),
        )

    backend_api_docs_dir = root / BACKEND_API_DOCS_DIR
    if file_map.exists() and backend_api_docs_dir.exists():
        file_map_text = file_map.read_text(encoding="utf-8")
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_backend_doc_names = _markdown_file_names(backend_api_docs_dir)
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_backend_doc_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=BACKEND_API_DOC_LIST_PREFIX,
            missing_list_kind="backend-api-doc-list-missing-from-file-map",
            missing_current_kind="backend-api-doc-list-missing-current-file",
            stale_kind="backend-api-doc-list-stale",
            directory_label=str(BACKEND_API_DOCS_DIR),
        )
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_backend_doc_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=BACKEND_API_DOC_LIST_PREFIX,
            missing_list_kind="system-map-backend-api-doc-list-missing",
            missing_current_kind="system-map-backend-api-doc-list-missing-current-file",
            stale_kind="system-map-backend-api-doc-list-stale",
            directory_label=str(BACKEND_API_DOCS_DIR),
        )

    app_module_dir = root / CURRENT_APP_MODULE_DIR
    if file_map.exists() and app_module_dir.exists():
        file_map_text = file_map.read_text(encoding="utf-8")
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_app_module_names = _current_python_module_names(app_module_dir)
        _verify_exact_module_inventory(
            findings,
            current_names=current_app_module_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=APP_MODULE_LIST_PREFIX,
            missing_list_kind="app-module-list-missing-from-file-map",
            missing_current_kind="app-module-list-missing-current-module",
            stale_kind="app-module-list-stale",
            directory_label=CURRENT_APP_MODULE_DIR,
        )
        _verify_exact_module_inventory(
            findings,
            current_names=current_app_module_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=APP_MODULE_LIST_PREFIX,
            missing_list_kind="system-map-app-module-list-missing",
            missing_current_kind="system-map-app-module-list-missing-current-module",
            stale_kind="system-map-app-module-list-stale",
            directory_label=CURRENT_APP_MODULE_DIR,
        )

    router_dir = root / CURRENT_ROUTER_DIR
    if file_map.exists() and router_dir.exists():
        file_map_text = file_map.read_text(encoding="utf-8")
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_router_names = tuple(
            router_path.name
            for router_path in sorted(router_dir.glob("*.py"))
            if router_path.name != "__init__.py"
        )
        file_map_router_names = _system_map_router_files(file_map_text)
        if not file_map_router_names:
            findings.append(Finding("router-list-missing-from-file-map", file_map, CURRENT_ROUTER_DIR))
        else:
            for router_name in current_router_names:
                if router_name not in file_map_router_names:
                    findings.append(Finding("router-list-missing-current-router", file_map, router_name))
            for router_name in file_map_router_names:
                if router_name not in current_router_names:
                    findings.append(Finding("router-list-stale", file_map, router_name))
        system_map_router_names = _system_map_router_files(system_map_text)
        if not system_map_router_names:
            findings.append(Finding("system-map-router-list-missing", system_map, CURRENT_ROUTER_DIR))
        else:
            for router_name in current_router_names:
                if router_name not in system_map_router_names:
                    findings.append(Finding("system-map-router-list-missing-current-router", system_map, router_name))
            for router_name in system_map_router_names:
                if router_name not in current_router_names:
                    findings.append(Finding("system-map-router-list-stale", system_map, router_name))
        mounted_router_modules = _mounted_router_modules(root / MAIN_PATH)
        for router_path in sorted(router_dir.glob("*.py")):
            if router_path.name == "__init__.py":
                continue
            if router_path.name not in file_map_text:
                findings.append(Finding("router-missing-from-file-map", router_path, router_path.name))
            if router_path.name not in system_map_text:
                findings.append(Finding("router-missing-from-system-map", router_path, router_path.name))
            if (
                router_path.name not in ROUTER_MOUNT_EXCEPTIONS
                and router_path.stem not in mounted_router_modules
            ):
                findings.append(Finding("router-missing-from-main-mount", router_path, router_path.name))

    service_dir = root / CURRENT_SERVICE_DIR
    if file_map.exists() and service_dir.exists():
        file_map_text = file_map.read_text(encoding="utf-8")
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_service_names = _current_python_module_names(service_dir)
        _verify_exact_module_inventory(
            findings,
            current_names=current_service_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=SERVICE_LIST_PREFIX,
            missing_list_kind="service-list-missing-from-file-map",
            missing_current_kind="service-list-missing-current-service",
            stale_kind="service-list-stale",
            directory_label=CURRENT_SERVICE_DIR,
        )
        _verify_exact_module_inventory(
            findings,
            current_names=current_service_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=SERVICE_LIST_PREFIX,
            missing_list_kind="system-map-service-list-missing",
            missing_current_kind="system-map-service-list-missing-current-service",
            stale_kind="system-map-service-list-stale",
            directory_label=CURRENT_SERVICE_DIR,
        )

    db_bootstrap_dir = root / CURRENT_DB_BOOTSTRAP_DIR
    if file_map.exists() and db_bootstrap_dir.exists():
        file_map_text = file_map.read_text(encoding="utf-8")
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_bootstrap_names = _current_python_module_names(db_bootstrap_dir)
        _verify_exact_module_inventory(
            findings,
            current_names=current_bootstrap_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=DB_BOOTSTRAP_LIST_PREFIX,
            missing_list_kind="db-bootstrap-list-missing-from-file-map",
            missing_current_kind="db-bootstrap-list-missing-current-module",
            stale_kind="db-bootstrap-list-stale",
            directory_label=CURRENT_DB_BOOTSTRAP_DIR,
        )
        _verify_exact_module_inventory(
            findings,
            current_names=current_bootstrap_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=DB_BOOTSTRAP_LIST_PREFIX,
            missing_list_kind="system-map-db-bootstrap-list-missing",
            missing_current_kind="system-map-db-bootstrap-list-missing-current-module",
            stale_kind="system-map-db-bootstrap-list-stale",
            directory_label=CURRENT_DB_BOOTSTRAP_DIR,
        )

    product_docs_index = root / PRODUCT_DOCS_INDEX
    product_docs_dir = root / PRODUCT_DOCS_DIR
    if product_docs_index.exists() and product_docs_dir.exists():
        index_text = product_docs_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_indexed_markdown_file_names(product_docs_dir),
            inventory_path=product_docs_index,
            inventory_text=index_text,
            inventory_prefix=PRODUCT_DOC_LIST_PREFIX,
            missing_list_kind="product-doc-list-missing-from-index",
            missing_current_kind="product-doc-missing-from-index",
            stale_kind="product-doc-list-stale",
            directory_label=str(PRODUCT_DOCS_DIR),
        )
        for raw_link, resolved_link in _markdown_relative_links(product_docs_index):
            if not resolved_link.exists():
                findings.append(Finding("product-doc-index-missing-link", resolved_link, raw_link))

    development_docs_index = root / DEVELOPMENT_DOCS_INDEX
    development_docs_dir = root / DEVELOPMENT_DOCS_DIR
    if development_docs_index.exists() and development_docs_dir.exists():
        index_text = development_docs_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_indexed_markdown_file_names(development_docs_dir),
            inventory_path=development_docs_index,
            inventory_text=index_text,
            inventory_prefix=DEVELOPMENT_DOC_LIST_PREFIX,
            missing_list_kind="development-doc-list-missing-from-index",
            missing_current_kind="development-doc-missing-from-index",
            stale_kind="development-doc-list-stale",
            directory_label=str(DEVELOPMENT_DOCS_DIR),
        )

    agent_docs_index = root / AGENT_DOCS_INDEX
    agent_docs_dir = root / AGENT_DOCS_DIR
    if agent_docs_index.exists() and agent_docs_dir.exists():
        index_text = agent_docs_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_indexed_markdown_file_names(agent_docs_dir),
            inventory_path=agent_docs_index,
            inventory_text=index_text,
            inventory_prefix=AGENT_DOC_LIST_PREFIX,
            missing_list_kind="agent-doc-list-missing-from-index",
            missing_current_kind="agent-doc-missing-from-index",
            stale_kind="agent-doc-list-stale",
            directory_label=str(AGENT_DOCS_DIR),
        )

    agents_local_index = root / AGENTS_LOCAL_INDEX
    agents_local_dir = root / AGENTS_LOCAL_DIR
    if agents_local_index.exists() and agents_local_dir.exists():
        index_text = agents_local_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(agents_local_dir),
            inventory_path=agents_local_index,
            inventory_text=index_text,
            inventory_prefix=AGENTS_LOCAL_DIR_LIST_PREFIX,
            missing_list_kind="agents-local-dir-list-missing-from-index",
            missing_current_kind="agents-local-dir-missing-from-index",
            stale_kind="agents-local-dir-list-stale",
            directory_label=str(AGENTS_LOCAL_DIR),
        )

    agents_skills_index = root / AGENTS_SKILLS_INDEX
    agents_skills_dir = root / AGENTS_SKILLS_DIR
    if agents_skills_index.exists() and agents_skills_dir.exists():
        index_text = agents_skills_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(agents_skills_dir),
            inventory_path=agents_skills_index,
            inventory_text=index_text,
            inventory_prefix=AGENTS_SKILL_LIST_PREFIX,
            missing_list_kind="agents-skill-list-missing-from-index",
            missing_current_kind="agents-skill-missing-from-index",
            stale_kind="agents-skill-list-stale",
            directory_label=str(AGENTS_SKILLS_DIR),
        )

    scratch_index = root / SCRATCH_INDEX
    scratch_dir = root / SCRATCH_DIR
    if scratch_index.exists() and scratch_dir.exists():
        index_text = scratch_index.read_text(encoding="utf-8")
        current_work_area_names = _child_dir_names(scratch_dir)
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_work_area_names,
            inventory_path=scratch_index,
            inventory_text=index_text,
            inventory_prefix=SCRATCH_WORK_AREA_LIST_PREFIX,
            missing_list_kind="scratch-work-area-list-missing-from-index",
            missing_current_kind="scratch-work-area-missing-from-index",
            stale_kind="scratch-work-area-list-stale",
            directory_label=str(SCRATCH_DIR),
        )

    business_inputs_index = root / BUSINESS_INPUTS_INDEX
    business_inputs_dir = root / BUSINESS_INPUTS_DIR
    if business_inputs_index.exists() and business_inputs_dir.exists():
        business_inputs_text = business_inputs_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_indexed_file_names(business_inputs_dir),
            inventory_path=business_inputs_index,
            inventory_text=business_inputs_text,
            inventory_prefix=BUSINESS_INPUT_LIST_PREFIX,
            missing_list_kind="business-input-list-missing-from-index",
            missing_current_kind="business-input-missing-from-index",
            stale_kind="business-input-list-stale",
            directory_label=str(BUSINESS_INPUTS_DIR),
        )
    download_templates_index = root / DOWNLOAD_TEMPLATES_INDEX
    download_templates_dir = root / DOWNLOAD_TEMPLATES_DIR
    if download_templates_index.exists() and download_templates_dir.exists():
        download_templates_text = download_templates_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_indexed_file_names(download_templates_dir),
            inventory_path=download_templates_index,
            inventory_text=download_templates_text,
            inventory_prefix=DOWNLOAD_TEMPLATE_LIST_PREFIX,
            missing_list_kind="download-template-list-missing-from-index",
            missing_current_kind="download-template-missing-from-index",
            stale_kind="download-template-list-stale",
            directory_label=str(DOWNLOAD_TEMPLATES_DIR),
        )
    _verify_child_dirs_have_readme(
        findings,
        directory=root / KNOWLEDGE_BASE_DIR,
        missing_kind="knowledge-base-dir-missing-readme",
    )
    knowledge_base_index = root / KNOWLEDGE_BASE_INDEX
    knowledge_base_dir = root / KNOWLEDGE_BASE_DIR
    if knowledge_base_index.exists() and knowledge_base_dir.exists():
        knowledge_base_text = knowledge_base_index.read_text(encoding="utf-8")
        _verify_exact_named_file_inventory(
            findings,
            current_names=_child_dir_names(knowledge_base_dir),
            inventory_path=knowledge_base_index,
            inventory_text=knowledge_base_text,
            inventory_prefix=KNOWLEDGE_BASE_LAYER_LIST_PREFIX,
            missing_list_kind="knowledge-base-layer-list-missing-from-index",
            missing_current_kind="knowledge-base-layer-missing-from-index",
            stale_kind="knowledge-base-layer-list-stale",
            directory_label=str(KNOWLEDGE_BASE_DIR),
        )

    workspace_catalog = root / WORKSPACE_CATALOG_PATH
    if workspace_catalog.exists():
        labels = _workspace_labels(workspace_catalog)
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        system_map_labels = _system_map_workspace_labels(system_map_text)
        if not system_map_labels:
            findings.append(Finding("system-map-workspace-label-list-missing", system_map, str(WORKSPACE_CATALOG_PATH)))
        else:
            for label in labels:
                if label not in system_map_labels:
                    findings.append(Finding("system-map-workspace-label-list-missing-current-label", system_map, label))
            for label in system_map_labels:
                if label not in labels:
                    findings.append(Finding("system-map-workspace-label-list-stale", system_map, label))
        for label in labels:
            if label not in system_map_text:
                findings.append(Finding("workspace-label-missing-from-system-map", system_map, label))
        for relative in NAVIGATION_DOC_PATHS:
            doc_path = root / relative
            if not doc_path.exists():
                findings.append(Finding("missing-navigation-doc", doc_path, str(relative)))
                continue
            doc_text = doc_path.read_text(encoding="utf-8")
            for label in labels:
                if label not in doc_text:
                    findings.append(Finding("workspace-label-missing-from-doc", doc_path, label))

        if file_map.exists():
            file_map_text = file_map.read_text(encoding="utf-8")
            for import_path in _workspace_component_imports(workspace_catalog):
                component_path = root / WORKSPACE_COMPONENT_ROOT / f"{import_path}.tsx"
                component_name = f"{Path(import_path).name}.tsx"
                if not component_path.exists():
                    findings.append(Finding("workspace-component-import-missing-file", component_path, component_name))
                if component_name not in file_map_text:
                    findings.append(Finding("workspace-component-missing-from-file-map", component_path, component_name))

    frontend_app_dir = root / FRONTEND_APP_DIR
    if frontend_app_dir.exists():
        file_map_text = file_map.read_text(encoding="utf-8") if file_map.exists() else ""
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_app_config_names = _frontend_app_config_names(frontend_app_dir)
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_app_config_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=FRONTEND_APP_CONFIG_LIST_PREFIX,
            missing_list_kind="frontend-app-config-list-missing-from-file-map",
            missing_current_kind="frontend-app-config-list-missing-current-file",
            stale_kind="frontend-app-config-list-stale",
            directory_label=str(FRONTEND_APP_DIR),
        )
        _verify_exact_named_file_inventory(
            findings,
            current_names=current_app_config_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=FRONTEND_APP_CONFIG_LIST_PREFIX,
            missing_list_kind="system-map-frontend-app-config-list-missing",
            missing_current_kind="system-map-frontend-app-config-list-missing-current-file",
            stale_kind="system-map-frontend-app-config-list-stale",
            directory_label=str(FRONTEND_APP_DIR),
        )

    frontend_e2e_dir = root / FRONTEND_E2E_DIR
    if frontend_e2e_dir.exists():
        file_map_text = file_map.read_text(encoding="utf-8") if file_map.exists() else ""
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_e2e_names = _frontend_top_level_component_names(frontend_e2e_dir)
        _verify_exact_frontend_inventory(
            findings,
            current_names=current_e2e_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=FRONTEND_E2E_LIST_PREFIX,
            missing_list_kind="frontend-e2e-list-missing-from-file-map",
            missing_current_kind="frontend-e2e-list-missing-current-file",
            stale_kind="frontend-e2e-list-stale",
            directory_label=str(FRONTEND_E2E_DIR),
        )
        _verify_exact_frontend_inventory(
            findings,
            current_names=current_e2e_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=FRONTEND_E2E_LIST_PREFIX,
            missing_list_kind="system-map-frontend-e2e-list-missing",
            missing_current_kind="system-map-frontend-e2e-list-missing-current-file",
            stale_kind="system-map-frontend-e2e-list-stale",
            directory_label=str(FRONTEND_E2E_DIR),
        )

    frontend_src_root = root / FRONTEND_SRC_ROOT
    if frontend_src_root.exists():
        file_map_text = file_map.read_text(encoding="utf-8") if file_map.exists() else ""
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_src_names = _frontend_top_level_component_names(frontend_src_root)
        _verify_exact_frontend_inventory(
            findings,
            current_names=current_src_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=FRONTEND_SRC_LIST_PREFIX,
            missing_list_kind="frontend-src-list-missing-from-file-map",
            missing_current_kind="frontend-src-list-missing-current-file",
            stale_kind="frontend-src-list-stale",
            directory_label=str(FRONTEND_SRC_ROOT),
        )
        _verify_exact_frontend_inventory(
            findings,
            current_names=current_src_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=FRONTEND_SRC_LIST_PREFIX,
            missing_list_kind="system-map-frontend-src-list-missing",
            missing_current_kind="system-map-frontend-src-list-missing-current-file",
            stale_kind="system-map-frontend-src-list-stale",
            directory_label=str(FRONTEND_SRC_ROOT),
        )

    frontend_app_root = root / FRONTEND_APP_ROOT
    if frontend_app_root.exists():
        file_map_text = file_map.read_text(encoding="utf-8") if file_map.exists() else ""
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_app_names = _frontend_top_level_component_names(frontend_app_root)
        _verify_exact_frontend_inventory(
            findings,
            current_names=current_app_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=FRONTEND_APP_LIST_PREFIX,
            missing_list_kind="frontend-app-list-missing-from-file-map",
            missing_current_kind="frontend-app-list-missing-current-file",
            stale_kind="frontend-app-list-stale",
            directory_label=str(FRONTEND_APP_ROOT),
        )
        _verify_exact_frontend_inventory(
            findings,
            current_names=current_app_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=FRONTEND_APP_LIST_PREFIX,
            missing_list_kind="system-map-frontend-app-list-missing",
            missing_current_kind="system-map-frontend-app-list-missing-current-file",
            stale_kind="system-map-frontend-app-list-stale",
            directory_label=str(FRONTEND_APP_ROOT),
        )

    component_root = root / WORKSPACE_COMPONENT_ROOT
    if component_root.exists():
        file_map_text = file_map.read_text(encoding="utf-8") if file_map.exists() else ""
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_component_names = _frontend_top_level_component_names(component_root)
        _verify_exact_frontend_inventory(
            findings,
            current_names=current_component_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=FRONTEND_COMPONENT_LIST_PREFIX,
            missing_list_kind="frontend-component-list-missing-from-file-map",
            missing_current_kind="frontend-component-list-missing-current-component",
            stale_kind="frontend-component-list-stale",
            directory_label=str(WORKSPACE_COMPONENT_ROOT),
        )
        _verify_exact_frontend_inventory(
            findings,
            current_names=current_component_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=FRONTEND_COMPONENT_LIST_PREFIX,
            missing_list_kind="system-map-frontend-component-list-missing",
            missing_current_kind="system-map-frontend-component-list-missing-current-component",
            stale_kind="system-map-frontend-component-list-stale",
            directory_label=str(WORKSPACE_COMPONENT_ROOT),
        )

    frontend_style_root = root / FRONTEND_STYLE_ROOT
    if frontend_style_root.exists():
        file_map_text = file_map.read_text(encoding="utf-8") if file_map.exists() else ""
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_style_names = _frontend_top_level_css_names(frontend_style_root)
        _verify_exact_css_inventory(
            findings,
            current_names=current_style_names,
            inventory_path=file_map,
            inventory_text=file_map_text,
            inventory_prefix=FRONTEND_STYLE_LIST_PREFIX,
            missing_list_kind="frontend-style-list-missing-from-file-map",
            missing_current_kind="frontend-style-list-missing-current-file",
            stale_kind="frontend-style-list-stale",
            directory_label=str(FRONTEND_STYLE_ROOT),
        )
        _verify_exact_css_inventory(
            findings,
            current_names=current_style_names,
            inventory_path=system_map,
            inventory_text=system_map_text,
            inventory_prefix=FRONTEND_STYLE_LIST_PREFIX,
            missing_list_kind="system-map-frontend-style-list-missing",
            missing_current_kind="system-map-frontend-style-list-missing-current-file",
            stale_kind="system-map-frontend-style-list-stale",
            directory_label=str(FRONTEND_STYLE_ROOT),
        )

    frontend_lib_root = root / FRONTEND_LIB_ROOT
    if frontend_lib_root.exists():
        file_map_text = file_map.read_text(encoding="utf-8") if file_map.exists() else ""
        system_map = root / CURRENT_SYSTEM_MAP_PATH
        system_map_text = system_map.read_text(encoding="utf-8") if system_map.exists() else ""
        current_lib_names = _frontend_domain_lib_names(frontend_lib_root)
        current_shared_lib_names = _frontend_shared_lib_names(frontend_lib_root)
        file_map_lib_names = _prefixed_typescript_file_list(file_map_text, FRONTEND_LIB_LIST_PREFIX)
        system_map_lib_names = _prefixed_typescript_file_list(system_map_text, FRONTEND_LIB_LIST_PREFIX)
        file_map_shared_lib_names = _prefixed_typescript_file_list(file_map_text, FRONTEND_SHARED_LIB_LIST_PREFIX)
        system_map_shared_lib_names = _prefixed_typescript_file_list(system_map_text, FRONTEND_SHARED_LIB_LIST_PREFIX)
        if current_lib_names and not file_map_lib_names:
            findings.append(Finding("frontend-lib-list-missing-from-file-map", file_map, str(FRONTEND_LIB_ROOT)))
        else:
            for lib_name in current_lib_names:
                if lib_name not in file_map_lib_names:
                    findings.append(Finding("frontend-lib-list-missing-current-lib", file_map, lib_name))
            for lib_name in file_map_lib_names:
                if lib_name not in current_lib_names:
                    findings.append(Finding("frontend-lib-list-stale", file_map, lib_name))
        if current_lib_names and not system_map_lib_names:
            findings.append(Finding("system-map-frontend-lib-list-missing", system_map, str(FRONTEND_LIB_ROOT)))
        else:
            for lib_name in current_lib_names:
                if lib_name not in system_map_lib_names:
                    findings.append(Finding("system-map-frontend-lib-list-missing-current-lib", system_map, lib_name))
            for lib_name in system_map_lib_names:
                if lib_name not in current_lib_names:
                    findings.append(Finding("system-map-frontend-lib-list-stale", system_map, lib_name))
        if current_shared_lib_names and not file_map_shared_lib_names:
            findings.append(Finding("frontend-shared-lib-list-missing-from-file-map", file_map, str(FRONTEND_LIB_ROOT)))
        else:
            for lib_name in current_shared_lib_names:
                if lib_name not in file_map_shared_lib_names:
                    findings.append(Finding("frontend-shared-lib-list-missing-current-lib", file_map, lib_name))
            for lib_name in file_map_shared_lib_names:
                if lib_name not in current_shared_lib_names:
                    findings.append(Finding("frontend-shared-lib-list-stale", file_map, lib_name))
        if current_shared_lib_names and not system_map_shared_lib_names:
            findings.append(Finding("system-map-frontend-shared-lib-list-missing", system_map, str(FRONTEND_LIB_ROOT)))
        else:
            for lib_name in current_shared_lib_names:
                if lib_name not in system_map_shared_lib_names:
                    findings.append(Finding("system-map-frontend-shared-lib-list-missing-current-lib", system_map, lib_name))
            for lib_name in system_map_shared_lib_names:
                if lib_name not in current_shared_lib_names:
                    findings.append(Finding("system-map-frontend-shared-lib-list-stale", system_map, lib_name))
        for lib_path in _frontend_domain_lib_files(frontend_lib_root):
            if lib_path.name not in file_map_text:
                findings.append(Finding("frontend-lib-missing-from-file-map", lib_path, lib_path.name))
            if lib_path.name not in system_map_text:
                findings.append(Finding("frontend-lib-missing-from-system-map", lib_path, lib_path.name))

    for ui_path in _frontend_ui_files(root):
        try:
            ui_text = ui_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "/api/" in ui_text:
            findings.append(Finding("frontend-ui-raw-api-path", ui_path, "/api/"))

    return tuple(findings)


def render(findings: tuple[Finding, ...], root: Path) -> str:
    lines: list[str] = []
    if not findings:
        return "worktree_organization=ok\n"
    lines.append("worktree_organization=failed")
    for finding in findings:
        lines.append(f"{finding.kind}|{_display(finding.path, root)}|{finding.detail}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify active worktree boundaries and stale current-doc markers.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to inspect. Defaults to this checkout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    findings = verify(root)
    print(render(findings, root), end="")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
