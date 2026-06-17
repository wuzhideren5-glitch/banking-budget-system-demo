from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]

COMMON_REQUIRED_ENTRIES = (
    "README.md",
    "AGENTS.md",
    "CONTEXT.md",
    "apps/api",
    "apps/web",
    "docs",
    "resources",
    "package.json",
    "package-lock.json",
    "start.sh",
    "stop.sh",
)

INTERNAL_RUNTIME_REQUIRED_ENTRIES = (
    "apps/api/.env",
    "apps/web/dist",
    "resources/download_template",
    "resources/knowledge_base",
    "var/data/common.db",
    "var/data/budget_2025.db",
    "var/data/budget_2026.db",
    "var/data/compare.db",
)

SOURCE_ONLY_FORBIDDEN_RUNTIME_ASSETS = (
    ("apps/api/.env", ".env"),
    ("apps/web/dist", "dist"),
    ("var/data", "var/data"),
)

COMMON_FORBIDDEN_ENTRIES = (
    ".git",
    ".venv",
    ".venv312",
    "node_modules",
    "apps/api/.venv",
    "apps/web/node_modules",
    "apps/web/playwright-report",
    "apps/web/test-results",
    "archive",
    "releases",
    ".superpowers",
    "var/logs",
    "var/pids",
    "var/run",
    "var/output",
    "var/test-runs",
    "var/data/backups",
)

GENERATED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".vite",
}

FORBIDDEN_SUFFIXES = (
    ".log",
    ".pid",
    ".pyc",
)

PRUNED_SUFFIX_SCAN_DIRS = tuple(Path(relative) for relative in COMMON_FORBIDDEN_ENTRIES)


@dataclass(frozen=True)
class Finding:
    kind: str
    path: Path
    detail: str

    def format(self, root: Path) -> str:
        try:
            relative = self.path.resolve().relative_to(root)
        except ValueError:
            relative = self.path
        return f"{self.kind}|{relative.as_posix()}|{self.detail}"


def _is_under(relative: Path, parent: Path) -> bool:
    return relative == parent or parent in relative.parents


def _is_pruned_dir(relative: Path) -> bool:
    if any(part in GENERATED_DIR_NAMES for part in relative.parts):
        return True
    return any(_is_under(relative, pruned_dir) for pruned_dir in PRUNED_SUFFIX_SCAN_DIRS)


def _iter_forbidden_generated_dirs(root: Path) -> tuple[Path, ...]:
    dirs: list[Path] = []
    for current_root, dir_names, _file_names in os.walk(root):
        current_path = Path(current_root)
        kept_dir_names = []
        for dir_name in dir_names:
            child_path = current_path / dir_name
            child_relative = child_path.relative_to(root)
            if dir_name in GENERATED_DIR_NAMES:
                dirs.append(child_path)
                continue
            if _is_pruned_dir(child_relative):
                continue
            kept_dir_names.append(dir_name)
        dir_names[:] = kept_dir_names
    return tuple(sorted(dirs))


def _iter_forbidden_suffix_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        relative_current = current_path.relative_to(root)
        if relative_current != Path(".") and _is_pruned_dir(relative_current):
            dir_names[:] = []
            continue

        kept_dir_names = []
        for dir_name in dir_names:
            child_relative = (current_path / dir_name).relative_to(root)
            if _is_pruned_dir(child_relative):
                continue
            kept_dir_names.append(dir_name)
        dir_names[:] = kept_dir_names

        for file_name in file_names:
            if any(file_name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
                files.append(current_path / file_name)
    return tuple(sorted(files))


def _verify_common(findings: list[Finding], root: Path) -> None:
    for relative in COMMON_REQUIRED_ENTRIES:
        path = root / relative
        if not path.exists():
            findings.append(Finding("delivery-required-entry-missing", path, relative))

    for relative in COMMON_FORBIDDEN_ENTRIES:
        path = root / relative
        if path.exists():
            findings.append(Finding("forbidden-delivery-entry-present", path, relative))

    duplicate_data_dir = root / "apps" / "var" / "data"
    if duplicate_data_dir.exists():
        findings.append(
            Finding(
                "duplicate-data-dir-present",
                duplicate_data_dir,
                "use var/data as the only live data directory",
            )
        )

    for path in _iter_forbidden_generated_dirs(root):
        findings.append(Finding("forbidden-generated-dir-present", path, path.name))

    for path in _iter_forbidden_suffix_files(root):
        findings.append(Finding("forbidden-generated-file-present", path, path.name))


def _verify_internal_runtime(findings: list[Finding], root: Path) -> None:
    for relative in INTERNAL_RUNTIME_REQUIRED_ENTRIES:
        path = root / relative
        if not path.exists():
            kind = "runtime-db-missing" if relative.startswith("var/data/") else "runtime-entry-missing"
            findings.append(Finding(kind, path, Path(relative).name))


def _verify_source_only(findings: list[Finding], root: Path) -> None:
    for relative, label in SOURCE_ONLY_FORBIDDEN_RUNTIME_ASSETS:
        path = root / relative
        if path.exists():
            findings.append(Finding("source-only-runtime-asset-present", path, label))


def verify(root: Path, *, profile: str) -> tuple[Finding, ...]:
    root = root.resolve()
    findings: list[Finding] = []
    _verify_common(findings, root)

    if profile == "internal-runtime":
        _verify_internal_runtime(findings, root)
    elif profile == "source-only":
        _verify_source_only(findings, root)
    else:
        findings.append(Finding("unknown-delivery-profile", root, profile))

    return tuple(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify banking budget delivery package contents.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Package root or extracted package root.")
    parser.add_argument(
        "--profile",
        choices=("internal-runtime", "source-only"),
        default="internal-runtime",
        help="Delivery package profile to verify.",
    )
    args = parser.parse_args()

    findings = verify(args.root, profile=args.profile)
    if findings:
        for finding in findings:
            print(finding.format(args.root.resolve()))
        return 1

    print(f"delivery_package=ok profile={args.profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
