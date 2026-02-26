"""Patch-operation builders for API/orchestration use."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


_EXTRACT_NESTED_INTERNAL_SKIP: dict[str, set[str]] = {
    "eurika/refactor/extract_function.py": {
        "_has_nonlocal_or_global",
        "add_extra_args_to_calls",
        "collect_blocks",
    },
}

_EXTRACT_BLOCK_SKIP_PATTERNS: frozenset[str] = frozenset({
    "eurika/refactor/", "eurika/reasoning/planner_patch_ops.py",
    "eurika/reasoning/planner_llm.py", "report/", "cli/orchestration/",
})


def _should_skip_extract_block_target(rel_path: str) -> bool:
    """Skip extract_block_to_helper for paths where extraction often breaks verify."""
    r = rel_path.replace("\\", "/")
    return any(r.startswith(p) or p in r for p in _EXTRACT_BLOCK_SKIP_PATTERNS)


def _should_skip_extract_nested_candidate(
    rel_path: str,
    nested_name: str,
) -> bool:
    """Skip known internal helper extractions that are high-noise for operability."""
    skip_names = _EXTRACT_NESTED_INTERNAL_SKIP.get(rel_path.replace("\\", "/"))
    return bool(skip_names and nested_name in skip_names)


def _should_try_extract_nested(stats: Optional[Dict[str, Dict[str, Any]]]) -> bool:
    """Allow extract_nested_function unless modern stats show repeated verify failures."""
    if not stats:
        return True
    rec = stats.get("long_function|extract_nested_function", {})
    total = int(rec.get("total", 0) or 0)
    success = int(rec.get("success", 0) or 0)
    verify_fail = int(rec.get("verify_fail", 0) or 0)
    not_applied = int(rec.get("not_applied", 0) or 0)
    has_detailed_outcomes = any(
        key in rec for key in ("verify_success", "verify_fail", "not_applied")
    )

    if total <= 0:
        return True
    # Legacy stats (pre outcome split) may overcount "fail" with skipped/no-op results.
    # Do not block retries based on those ambiguous aggregates.
    if not has_detailed_outcomes:
        return True
    if total >= 1 and success == 0 and verify_fail >= 1 and not_applied == 0:
        return False
    if total >= 3 and (success / total) < 0.25 and verify_fail > not_applied:
        return False
    return True


def _load_smell_action_learning_stats(root: Path) -> Optional[Dict[str, Dict[str, Any]]]:
    """Return smell-action aggregates (local + global merged, ROADMAP 3.0.2); None on error."""
    from eurika.storage.global_memory import get_merged_learning_stats

    try:
        return get_merged_learning_stats(root)
    except Exception:
        return None


def _deep_nesting_mode() -> str:
    """heuristic|llm|hybrid|skip. Default: hybrid (heuristic first, fallback to TODO/LLM)."""
    import os

    return os.environ.get("EURIKA_DEEP_NESTING_MODE", "hybrid").strip().lower() or "hybrid"


def _build_extract_block_op(
    rel_path: str,
    location: str,
    helper_name: str,
    block_start_line: int,
    line_count: int,
    extra_params: Optional[List[str]] = None,
    *,
    smell_type: str = "deep_nesting",
) -> Dict[str, Any]:
    """Build extract_block_to_helper operation payload."""
    params: Dict[str, Any] = {
        "location": location,
        "block_start_line": block_start_line,
        "helper_name": helper_name,
    }
    if extra_params:
        params["extra_params"] = extra_params
    return {
        "target_file": rel_path,
        "kind": "extract_block_to_helper",
        "description": (
            f"Extract nested block from {rel_path}:{location} "
            f"(line {block_start_line}, {line_count} lines)"
        ),
        "diff": f"# Extracted block to {helper_name}",
        "smell_type": smell_type,
        "params": params,
    }


def _build_extract_nested_op(
    rel_path: str,
    location: str,
    nested_name: str,
    line_count: int,
    extra_params: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build extract_nested_function operation payload."""
    params: Dict[str, Any] = {"location": location, "nested_function_name": nested_name}
    if extra_params:
        params["extra_params"] = extra_params
    return {
        "target_file": rel_path,
        "kind": "extract_nested_function",
        "description": (
            f"Extract nested function {nested_name} "
            f"from {rel_path}:{location} ({line_count} lines)"
        ),
        "diff": f"# Extracted {nested_name} to module level",
        "smell_type": "long_function",
        "params": params,
    }


def _build_refactor_smell_op(
    rel_path: str,
    smell: Any,
    root: Path,
) -> Dict[str, Any]:
    """Build fallback TODO operation payload for a code smell."""
    hint = (
        "consider extracting helper"
        if smell.kind == "long_function"
        else "consider extracting nested block"
    )
    diff_lines: List[str] = [f"\n# TODO (eurika): refactor {smell.kind} '{smell.location}' — {hint}\n"]
    if smell.kind == "long_function":
        try:
            from eurika.reasoning.planner_llm import ask_llm_extract_method_hints

            file_path = root / rel_path.replace("\\", "/")
            llm_hints = ask_llm_extract_method_hints(file_path, smell.location)
            if llm_hints:
                diff_lines.append("# LLM suggestions:\n")
                for h in llm_hints[:3]:
                    diff_lines.append(f"# - {h}\n")
        except Exception:
            pass
    diff = "".join(diff_lines)
    return {
        "target_file": rel_path,
        "kind": "refactor_code_smell",
        "description": f"Refactor {smell.kind} in {rel_path}:{smell.location}",
        "diff": diff,
        "smell_type": smell.kind,
        "params": {"location": smell.location, "metric": smell.metric},
    }


def _should_emit_refactor_smell_op(
    root: Path,
    rel_path: str,
    diff: str,
    location: str,
    smell_type: str,
) -> bool:
    """Skip noisy refactor_code_smell ops that are likely no-op."""
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("tests/"):
        return False
    path = root / rel_path
    if not (path.exists() and path.is_file()):
        return True
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return True
    if diff.strip() and diff.strip() in content:
        return False
    if f"# TODO: Refactor {rel_path}" in content:
        return False
    if location and f"'{location}'" in content and "# TODO (eurika): refactor " in content:
        return False
    if smell_type and f"# TODO (eurika): refactor {smell_type} " in content:
        return False
    return True


def _emit_code_smell_todo() -> bool:
    """When True, emit refactor_code_smell (TODO) when no real fix."""
    import os

    return os.environ.get("EURIKA_EMIT_CODE_SMELL_TODO", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def get_code_smell_operations(project_root: Path) -> List[Dict[str, Any]]:
    """
    Build patch operations for code-level smells (long_function, deep_nesting).

    Uses CodeAwareness.find_smells. For long_function: tries extract_nested_function first;
    if no nested def, tries suggest_extract_block (if/for/while body); else TODO if emit_todo.
    For deep_nesting: suggest_extract_block when EURIKA_DEEP_NESTING_MODE in (heuristic, hybrid).
    """
    from code_awareness import CodeAwareness
    from eurika.refactor.extract_function import (
        suggest_extract_block,
        suggest_extract_nested_function,
    )

    root = Path(project_root).resolve()
    analyzer = CodeAwareness(root)
    allow_extract_nested = _should_try_extract_nested(_load_smell_action_learning_stats(root))
    emit_todo = _emit_code_smell_todo()
    ops: List[Dict[str, Any]] = []
    deep_mode = _deep_nesting_mode()
    fixed_locations: set[tuple[str, str]] = set()
    for file_path in analyzer.scan_python_files():
        rel = str(file_path.relative_to(root)).replace("\\", "/")
        for smell in analyzer.find_smells(file_path):
            loc_key = (rel, smell.location)
            if smell.kind == "long_function":
                if allow_extract_nested:
                    suggestion = suggest_extract_nested_function(file_path, smell.location)
                    if suggestion:
                        nested_name, line_count, extra_params = (
                            suggestion[0],
                            suggestion[1],
                            (suggestion[2] if len(suggestion) > 2 else []),
                        )
                        if _should_skip_extract_nested_candidate(rel, nested_name):
                            continue
                        ops.append(
                            _build_extract_nested_op(
                                rel, smell.location, nested_name, line_count, extra_params or None
                            )
                        )
                        fixed_locations.add(loc_key)
                        continue
                block_suggestion = suggest_extract_block(file_path, smell.location, min_lines=5)
                if block_suggestion and not _should_skip_extract_block_target(rel):
                    helper_name, block_line, line_count, extra = block_suggestion
                    ops.append(
                        _build_extract_block_op(
                            rel,
                            smell.location,
                            helper_name,
                            block_line,
                            line_count,
                            extra or None,
                            smell_type="long_function",
                        )
                    )
                    fixed_locations.add(loc_key)
                    continue
            if smell.kind == "deep_nesting":
                if deep_mode == "skip" or loc_key in fixed_locations:
                    continue
                if deep_mode in ("heuristic", "hybrid"):
                    block_suggestion = suggest_extract_block(file_path, smell.location)
                    if block_suggestion and not _should_skip_extract_block_target(rel):
                        helper_name, block_line, line_count, extra = block_suggestion
                        ops.append(
                            _build_extract_block_op(
                                rel, smell.location, helper_name, block_line, line_count, extra or None
                            )
                        )
                        fixed_locations.add(loc_key)
                        continue
            if not emit_todo:
                continue
            op = _build_refactor_smell_op(rel, smell, root)
            if _should_emit_refactor_smell_op(root, rel, op["diff"], smell.location, smell.kind):
                ops.append(op)
    return ops


_REMOVE_UNUSED_IMPORT_SKIP: frozenset[str] = frozenset({
    "eurika/agent/tool_contract.py",  # re-export layer; detector misses re-exports
})


def get_clean_imports_operations(project_root: Path) -> List[Dict[str, Any]]:
    """
    Build patch operations to remove unused imports (ROADMAP 2.4.2).

    Scans Python files (excludes __init__.py, *_api.py, venv, .git).
    Returns list of op dicts for patch_apply (kind="remove_unused_import").
    """
    from eurika.refactor.remove_unused_import import remove_unused_imports

    root = Path(project_root).resolve()
    skip_dirs = {"venv", ".venv", "node_modules", ".git", "__pycache__", ".eurika_backups"}
    facade_modules = {"patch_engine.py", "patch_apply.py"}
    ops: List[Dict[str, Any]] = []
    for p in sorted(root.rglob("*.py")):
        if any(skip in p.parts for skip in skip_dirs):
            continue
        if p.name == "__init__.py" or p.name.endswith("_api.py"):
            continue
        if p.name in facade_modules:
            continue
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if rel in _REMOVE_UNUSED_IMPORT_SKIP:
            continue
        if rel.startswith("tests/"):
            continue
        if remove_unused_imports(p) is None:
            continue
        ops.append(
            {
                "target_file": rel,
                "kind": "remove_unused_import",
                "description": f"Remove unused imports from {rel}",
                "diff": "# Removed unused imports.",
                "smell_type": None,
            }
        )
    return ops
