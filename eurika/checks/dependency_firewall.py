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


@dataclass(frozen=True)
class LayerPathRule:
    path_pattern: str
    layer: int


@dataclass(frozen=True)
class LayerImportRule:
    import_prefix: str
    layer: int


@dataclass(frozen=True)
class LayerException:
    path_pattern: str
    allowed_import_prefixes: tuple[str, ...]
    reason: str = ""


@dataclass(frozen=True)
class LayerViolation:
    path: str
    imported_module: str
    source_layer: int
    target_layer: int


@dataclass(frozen=True)
class SubsystemBypassRule:
    """R4: External clients must use package facade, not internal submodules."""

    path_pattern: str
    forbidden_import_prefix: str


@dataclass(frozen=True)
class SubsystemBypassViolation:
    path: str
    imported_module: str


@dataclass(frozen=True)
class SubsystemBypassException:
    path_pattern: str
    allowed_import_prefix: str
    reason: str = ""


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


DEFAULT_LAYER_PATH_RULES: tuple[LayerPathRule, ...] = (
    LayerPathRule(path_pattern="cli/", layer=6),
    LayerPathRule(path_pattern="report/", layer=5),
    LayerPathRule(path_pattern="eurika/reporting/", layer=5),
    LayerPathRule(path_pattern="architecture_summary.py", layer=5),
    LayerPathRule(path_pattern="architecture_history.py", layer=5),
    LayerPathRule(path_pattern="architecture_diff.py", layer=5),
    LayerPathRule(path_pattern="architecture_feedback.py", layer=5),
    LayerPathRule(path_pattern="architecture_advisor.py", layer=5),
    LayerPathRule(path_pattern="patch_apply.py", layer=4),
    LayerPathRule(path_pattern="patch_apply_", layer=4),
    LayerPathRule(path_pattern="patch_engine.py", layer=4),
    LayerPathRule(path_pattern="patch_engine_", layer=4),
    LayerPathRule(path_pattern="eurika/refactor/", layer=4),
    LayerPathRule(path_pattern="executor_sandbox.py", layer=4),
    LayerPathRule(path_pattern="architecture_planner.py", layer=3),
    LayerPathRule(path_pattern="architecture_planner_", layer=3),
    LayerPathRule(path_pattern="action_plan.py", layer=3),
    LayerPathRule(path_pattern="action_plan_", layer=3),
    LayerPathRule(path_pattern="patch_plan.py", layer=3),
    LayerPathRule(path_pattern="eurika/reasoning/planner", layer=3),
    LayerPathRule(path_pattern="eurika/analysis/", layer=2),
    LayerPathRule(path_pattern="eurika/smells/", layer=2),
    LayerPathRule(path_pattern="code_awareness", layer=2),
    LayerPathRule(path_pattern="graph_analysis", layer=2),
    LayerPathRule(path_pattern="semantic_architecture", layer=2),
    LayerPathRule(path_pattern="system_topology", layer=2),
    LayerPathRule(path_pattern="core/", layer=1),
    LayerPathRule(path_pattern="project_graph.py", layer=1),
    LayerPathRule(path_pattern="project_graph_api.py", layer=1),
    LayerPathRule(path_pattern="self_map_io.py", layer=1),
    LayerPathRule(path_pattern="patch_apply_backup.py", layer=0),
    LayerPathRule(path_pattern="eurika/storage/paths.py", layer=0),
    LayerPathRule(path_pattern="eurika/utils/fs", layer=0),
)


DEFAULT_LAYER_IMPORT_RULES: tuple[LayerImportRule, ...] = (
    LayerImportRule(import_prefix="cli", layer=6),
    LayerImportRule(import_prefix="report", layer=5),
    LayerImportRule(import_prefix="eurika.reporting", layer=5),
    LayerImportRule(import_prefix="architecture_summary", layer=5),
    LayerImportRule(import_prefix="architecture_history", layer=5),
    LayerImportRule(import_prefix="architecture_diff", layer=5),
    LayerImportRule(import_prefix="architecture_feedback", layer=5),
    LayerImportRule(import_prefix="architecture_advisor", layer=5),
    LayerImportRule(import_prefix="patch_apply", layer=4),
    LayerImportRule(import_prefix="patch_engine", layer=4),
    LayerImportRule(import_prefix="eurika.refactor", layer=4),
    LayerImportRule(import_prefix="executor_sandbox", layer=4),
    LayerImportRule(import_prefix="architecture_planner", layer=3),
    LayerImportRule(import_prefix="action_plan", layer=3),
    LayerImportRule(import_prefix="patch_plan", layer=3),
    LayerImportRule(import_prefix="eurika.reasoning.planner", layer=3),
    LayerImportRule(import_prefix="eurika.analysis", layer=2),
    LayerImportRule(import_prefix="eurika.smells", layer=2),
    LayerImportRule(import_prefix="code_awareness", layer=2),
    LayerImportRule(import_prefix="graph_analysis", layer=2),
    LayerImportRule(import_prefix="semantic_architecture", layer=2),
    LayerImportRule(import_prefix="system_topology", layer=2),
    LayerImportRule(import_prefix="core", layer=1),
    LayerImportRule(import_prefix="project_graph", layer=1),
    LayerImportRule(import_prefix="project_graph_api", layer=1),
    LayerImportRule(import_prefix="self_map_io", layer=1),
    LayerImportRule(import_prefix="patch_apply_backup", layer=0),
    LayerImportRule(import_prefix="eurika.storage.paths", layer=0),
    LayerImportRule(import_prefix="eurika.utils.fs", layer=0),
)


DEFAULT_LAYER_EXCEPTIONS: tuple[LayerException, ...] = ()


DEFAULT_SUBSYSTEM_BYPASS_RULES: tuple[SubsystemBypassRule, ...] = (
    # R4: External clients use package facade, not internal submodules.
    SubsystemBypassRule(path_pattern="eurika/reasoning/", forbidden_import_prefix="eurika.knowledge.base"),
    SubsystemBypassRule(path_pattern="cli/", forbidden_import_prefix="eurika.agent.policy"),
    SubsystemBypassRule(path_pattern="cli/", forbidden_import_prefix="eurika.agent.runtime"),
    SubsystemBypassRule(path_pattern="cli/", forbidden_import_prefix="eurika.agent.tools"),
    SubsystemBypassRule(path_pattern="eurika/api/", forbidden_import_prefix="eurika.reasoning.context_sources"),
    SubsystemBypassRule(path_pattern="cli/", forbidden_import_prefix="eurika.reasoning.context_sources"),
    SubsystemBypassRule(path_pattern="architecture_planner", forbidden_import_prefix="eurika.reasoning.planner_patch_ops"),
)

DEFAULT_SUBSYSTEM_BYPASS_EXCEPTIONS: tuple[SubsystemBypassException, ...] = (
    # R4: Legacy planner scripts at project root; migrate to eurika.reasoning.planner in Phase B.2
    SubsystemBypassException(
        path_pattern="architecture_planner",
        allowed_import_prefix="eurika.reasoning.planner_patch_ops",
        reason="Legacy planner build_patch_plan; migrate to facade",
    ),
)


def _path_matches(rel_path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return rel_path.startswith(pattern)
    if pattern.endswith(".py"):
        return rel_path.endswith(pattern) or pattern in rel_path
    return pattern in rel_path


def _extract_import_modules(content: str) -> set[str]:
    modules: set[str] = set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return modules
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _extract_import_roots(content: str) -> set[str]:
    return {module.split(".")[0] for module in _extract_import_modules(content)}


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


def _resolve_layer_for_path(
    rel_path: str,
    path_rules: Iterable[LayerPathRule],
) -> int | None:
    for rule in path_rules:
        if _path_matches(rel_path, rule.path_pattern):
            return rule.layer
    return None


def _resolve_layer_for_import(
    imported_module: str,
    import_rules: Iterable[LayerImportRule],
) -> int | None:
    best_layer: int | None = None
    best_len = -1
    for rule in import_rules:
        prefix = rule.import_prefix
        if imported_module == prefix or imported_module.startswith(prefix + "."):
            if len(prefix) > best_len:
                best_len = len(prefix)
                best_layer = rule.layer
    return best_layer


def _is_exception(
    rel_path: str,
    imported_module: str,
    exceptions: Iterable[LayerException],
) -> bool:
    for ex in exceptions:
        if not _path_matches(rel_path, ex.path_pattern):
            continue
        for prefix in ex.allowed_import_prefixes:
            if imported_module == prefix or imported_module.startswith(prefix + "."):
                return True
    return False


def _is_subsystem_exception(
    rel_path: str,
    imported_module: str,
    exceptions: Iterable[SubsystemBypassException],
) -> bool:
    for ex in exceptions:
        if not _path_matches(rel_path, ex.path_pattern):
            continue
        prefix = ex.allowed_import_prefix
        if imported_module == prefix or imported_module.startswith(prefix + "."):
            return True
    return False


def collect_subsystem_bypass_violations(
    root: Path,
    *,
    rules: Iterable[SubsystemBypassRule] = DEFAULT_SUBSYSTEM_BYPASS_RULES,
    exceptions: Iterable[SubsystemBypassException] = DEFAULT_SUBSYSTEM_BYPASS_EXCEPTIONS,
) -> list[SubsystemBypassViolation]:
    """R4: Find imports that bypass package facades (use internal submodules directly)."""
    violations: list[SubsystemBypassViolation] = []
    for path in _collect_project_py_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            imported_modules = _extract_import_modules(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        for rule in rules:
            if not _path_matches(rel, rule.path_pattern):
                continue
            for module in imported_modules:
                if module == rule.forbidden_import_prefix or module.startswith(
                    rule.forbidden_import_prefix + "."
                ):
                    if not _is_subsystem_exception(rel, module, exceptions):
                        violations.append(
                            SubsystemBypassViolation(path=rel, imported_module=module)
                        )
    return violations


def collect_layer_violations(
    root: Path,
    *,
    path_rules: Iterable[LayerPathRule] = DEFAULT_LAYER_PATH_RULES,
    import_rules: Iterable[LayerImportRule] = DEFAULT_LAYER_IMPORT_RULES,
    exceptions: Iterable[LayerException] = DEFAULT_LAYER_EXCEPTIONS,
) -> list[LayerViolation]:
    violations: list[LayerViolation] = []
    for path in _collect_project_py_files(root):
        rel = path.relative_to(root).as_posix()
        source_layer = _resolve_layer_for_path(rel, path_rules)
        if source_layer is None:
            continue
        try:
            imported_modules = _extract_import_modules(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        for module in imported_modules:
            target_layer = _resolve_layer_for_import(module, import_rules)
            if target_layer is None:
                continue
            # Layer contract: only same or lower layers are allowed.
            if target_layer <= source_layer:
                continue
            if _is_exception(rel, module, exceptions):
                continue
            violations.append(
                LayerViolation(
                    path=rel,
                    imported_module=module,
                    source_layer=source_layer,
                    target_layer=target_layer,
                )
            )
    return violations
