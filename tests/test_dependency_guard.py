"""
Dependency Guard (ROADMAP 2.8.2).

Checks forbidden imports per Architecture.md §0 Layer Map.
CI should run this test; failures indicate layer violations.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (path_pattern, forbidden_imports)
# path_pattern: regex or prefix match for file path relative to project root
# forbidden_imports: module names that must not appear in import/from statements
FORBIDDEN_RULES: list[tuple[str, list[str]]] = [
    # CLI must use patch_engine facade, not patch_apply directly
    ("cli/", ["patch_apply"]),
    # Main planner must not call apply; planning and execution are separate
    ("architecture_planner.py", ["patch_apply"]),
    ("architecture_planner_", ["patch_apply"]),
    # Analysis layer must not depend on Execution
    ("eurika/smells/", ["patch_apply", "patch_engine"]),
    ("eurika/analysis/", ["patch_apply", "patch_engine"]),
    ("code_awareness", ["patch_apply", "patch_engine"]),
    ("graph_analysis", ["patch_apply", "patch_engine"]),
    ("semantic_architecture", ["patch_apply", "patch_engine"]),
    ("system_topology", ["patch_apply", "patch_engine"]),
]


def _path_matches(path: Path, pattern: str) -> bool:
    rel = path.as_posix()
    if pattern.endswith("/"):
        return rel.startswith(pattern) or (pattern.rstrip("/") + "/") in rel
    if pattern.endswith(".py"):
        return pattern in rel or rel.endswith(pattern)
    return pattern in rel


def _extract_imports(content: str) -> set[str]:
    """Extract top-level imported module names from Python source."""
    mods: set[str] = set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return mods
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]  # first segment only
                mods.add(name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                name = node.module.split(".")[0]
                mods.add(name)
    return mods


def _collect_project_py_files() -> list[Path]:
    skip_dirs = {"__pycache__", ".git", ".venv", "venv", ".eurika_backups", "node_modules"}
    skip_containing = ["_shelved", ".eurika_backups"]
    files: list[Path] = []
    for p in ROOT.rglob("*.py"):
        if any(s in p.parts for s in skip_dirs):
            continue
        if any(s in str(p) for s in skip_containing):
            continue
        # Include tests to guard their mocks too; exclude from "cli" rule would need tweaks
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("tests/"):
            continue  # tests can import anything for testing
        files.append(p)
    return files


def test_no_forbidden_imports() -> None:
    """No project module may import from forbidden modules per layer rules."""
    violations: list[tuple[str, str]] = []
    for path in _collect_project_py_files():
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        imports = _extract_imports(content)
        rel = path.relative_to(ROOT).as_posix()
        for pattern, forbidden in FORBIDDEN_RULES:
            if not _path_matches(path, pattern):
                continue
            for mod in forbidden:
                if mod in imports:
                    violations.append((rel, mod))
    assert not violations, (
        "Forbidden imports (Architecture.md §0.4). Fix or add exception: "
        + "; ".join(f"{p} -> {m}" for p, m in violations)
    )
