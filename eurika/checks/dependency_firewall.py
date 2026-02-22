"""Dependency firewall checks for architectural layer boundaries."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ImportRule:
    path_pattern: str
    forbidden_imports: tuple[str, ...]


@dataclass(frozen=True)
class Violation:
    path: str
    forbidden_module: str


DEFAULT_RULES: tuple[ImportRule, ...] = (
    # CLI must use patch_engine facade, not patch_apply directly.
    ImportRule(path_pattern="cli/", forbidden_imports=("patch_apply",)),
    # Main planner must not call apply; planning and execution are separate.
    ImportRule(path_pattern="architecture_planner.py", forbidden_imports=("patch_apply",)),
    ImportRule(path_pattern="architecture_planner_", forbidden_imports=("patch_apply",)),
    # Planning layer must not depend on Execution (Architecture.md §0.5).
    ImportRule(path_pattern="eurika/reasoning/", forbidden_imports=("patch_apply", "patch_engine")),
    # Analysis layer must not depend on Execution.
    ImportRule(path_pattern="eurika/smells/", forbidden_imports=("patch_apply", "patch_engine")),
    ImportRule(path_pattern="eurika/analysis/", forbidden_imports=("patch_apply", "patch_engine")),
    ImportRule(path_pattern="code_awareness", forbidden_imports=("patch_apply", "patch_engine")),
    ImportRule(path_pattern="graph_analysis", forbidden_imports=("patch_apply", "patch_engine")),
    ImportRule(path_pattern="semantic_architecture", forbidden_imports=("patch_apply", "patch_engine")),
    ImportRule(path_pattern="system_topology", forbidden_imports=("patch_apply", "patch_engine")),
)


def _path_matches(rel_path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return rel_path.startswith(pattern)
    if pattern.endswith(".py"):
        return rel_path.endswith(pattern) or pattern in rel_path
    return pattern in rel_path


def _extract_import_roots(content: str) -> set[str]:
    roots: set[str] = set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return roots
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _collect_project_py_files(root: Path) -> list[Path]:
    skip_dirs = {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        ".eurika_backups",
        "node_modules",
        ".cursor",
    }
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in skip_dirs for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith("tests/"):
            continue
        files.append(path)
    return files


def collect_dependency_violations(
    root: Path,
    rules: Iterable[ImportRule] = DEFAULT_RULES,
) -> list[Violation]:
    violations: list[Violation] = []
    for path in _collect_project_py_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            imports = _extract_import_roots(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        for rule in rules:
            if not _path_matches(rel, rule.path_pattern):
                continue
            for forbidden in rule.forbidden_imports:
                if forbidden in imports:
                    violations.append(Violation(path=rel, forbidden_module=forbidden))
    return violations
