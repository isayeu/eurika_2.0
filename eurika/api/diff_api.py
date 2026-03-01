"""Diff/preview API routes (ROADMAP 3.6.7, R1 public API facade)."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any, Dict


def _to_json_safe(obj: Any) -> Any:
    """Convert objects to JSON-serializable form: tuple->list, Path->str."""
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(x) for x in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return obj


def get_diff(old_self_map_path: Path, new_self_map_path: Path) -> Dict[str, Any]:
    """Compare two self_map snapshots. Returns dict with structures, centrality_shifts, smells, etc."""
    from eurika.evolution.diff import build_snapshot, diff_snapshots

    old_path = Path(old_self_map_path).resolve()
    new_path = Path(new_self_map_path).resolve()
    if not old_path.exists():
        return {"error": "old self_map not found", "path": str(old_path)}
    if not new_path.exists():
        return {"error": "new self_map not found", "path": str(new_path)}
    old_snap = build_snapshot(old_path)
    new_snap = build_snapshot(new_path)
    diff = diff_snapshots(old_snap, new_snap)
    return _to_json_safe(diff)


def _truncate_on_word_boundary(raw: str, max_len: int = 200) -> str:
    """Truncate text by word boundary for readable output."""
    if len(raw) <= max_len:
        return raw
    truncated = raw[:max_len]
    cut = truncated.rfind(" ")
    return (truncated[:cut] if cut >= 0 else truncated) + "..."


def preview_operation(project_root: Path, op: Dict[str, Any]) -> Dict[str, Any]:
    """Preview single-file operation: old/new content and unified diff (ROADMAP 3.6.7)."""
    root = Path(project_root).resolve()
    target_file = str(op.get("target_file") or "").strip()
    kind = str(op.get("kind") or "").strip()
    params = op.get("params") or {}
    if not target_file or not kind:
        return {"error": "target_file and kind required"}
    path = root / target_file
    if not path.exists() or not path.is_file():
        return {"error": f"file not found: {target_file}"}
    supported = {"remove_unused_import", "remove_cyclic_import", "extract_block_to_helper", "extract_nested_function", "fix_import"}
    if kind not in supported:
        return {"error": f"preview not supported for kind={kind}"}
    try:
        old_content = path.read_text(encoding="utf-8")
    except OSError as e:
        return {"error": f"read failed: {e}"}
    new_content: str | None = None
    if kind == "remove_unused_import":
        from eurika.refactor.remove_unused_import import remove_unused_imports
        new_content = remove_unused_imports(path)
    elif kind == "remove_cyclic_import" and params.get("target_module"):
        from eurika.refactor.remove_import import remove_import_from_file
        new_content = remove_import_from_file(path, params["target_module"])
    elif kind == "extract_block_to_helper":
        from eurika.refactor.extract_function import extract_block_to_helper
        loc, line, helper, extra = params.get("location"), params.get("block_start_line"), params.get("helper_name"), params.get("extra_params")
        if loc is not None and helper:
            new_content = extract_block_to_helper(path, loc, int(line) if line is not None else 0, helper, extra_params=extra if isinstance(extra, list) else None)
    elif kind == "extract_nested_function":
        from eurika.refactor.extract_function import extract_nested_function
        loc, nested, extra = params.get("location"), params.get("nested_function_name"), params.get("extra_params")
        if loc and nested:
            new_content = extract_nested_function(path, loc, nested, extra_params=extra if isinstance(extra, list) else None)
    elif kind == "fix_import":
        new_content = op.get("diff") or ""
    if new_content is None or (kind == "fix_import" and not new_content):
        return {"target_file": target_file, "kind": kind, "old_content": old_content, "error": "operation would produce no change or extraction failed"}
    unified_lines = list(difflib.unified_diff(old_content.splitlines(keepends=True), new_content.splitlines(keepends=True), fromfile=f"a/{target_file}", tofile=f"b/{target_file}", lineterm=""))
    out: Dict[str, Any] = {"target_file": target_file, "kind": kind, "old_content": old_content, "new_content": new_content, "unified_diff": "".join(unified_lines) if unified_lines else ""}
    if op.get("oss_examples"):
        out["oss_examples"] = op["oss_examples"]
    return out
