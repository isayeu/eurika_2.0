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
    kind = str(op.get("kind") or op.get("operation_kind") or op.get("action_kind") or "").strip()
    params = op.get("params") or {}
    if not target_file or not kind:
        return {"error": "target_file and kind required"}
    path = root / target_file
    if kind == "agent_edit":
        edited = params.get("new_content")
        if not isinstance(edited, str):
            return {"error": "agent_edit: new_content required"}
        old_content = ""
        if path.exists() and path.is_file():
            try:
                old_content = path.read_text(encoding="utf-8")
            except OSError as e:
                return {"error": f"read failed: {e}"}
        unified_lines = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                edited.splitlines(keepends=True),
                fromfile=f"a/{target_file}",
                tofile=f"b/{target_file}",
                lineterm="",
            )
        )
        return {
            "target_file": target_file,
            "kind": kind,
            "old_content": old_content,
            "new_content": edited,
            "unified_diff": "".join(unified_lines) if unified_lines else "",
        }
    if not path.exists() or not path.is_file():
        return {"error": f"file not found: {target_file}"}
    supported = {"remove_unused_import", "remove_cyclic_import", "extract_block_to_helper", "extract_nested_function", "fix_import", "llm_extract_block", "extract_class"}
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
    elif kind == "llm_extract_block":
        new_content = params.get("new_content") or op.get("diff")
        if not new_content or not isinstance(new_content, str):
            return {"target_file": target_file, "kind": kind, "old_content": old_content, "error": "llm_extract_block: no new_content or diff"}
    elif kind == "extract_class":
        from eurika.refactor.extract_class import extract_class
        target_class = params.get("target_class")
        methods = params.get("methods_to_extract")
        if not target_class or not methods or not isinstance(methods, list):
            return {"target_file": target_file, "kind": kind, "old_content": old_content, "error": "extract_class: target_class and methods_to_extract required"}
        result = extract_class(path, target_class, methods, target_file=target_file)
        if result is None:
            return {"target_file": target_file, "kind": kind, "old_content": old_content, "error": "extract_class: extraction failed"}
        _extracted_rel, _extracted_content, modified_original = result
        new_content = modified_original
    if new_content is None or (kind == "fix_import" and not new_content):
        return {"target_file": target_file, "kind": kind, "old_content": old_content, "error": "operation would produce no change or extraction failed"}
    unified_lines = list(difflib.unified_diff(old_content.splitlines(keepends=True), new_content.splitlines(keepends=True), fromfile=f"a/{target_file}", tofile=f"b/{target_file}", lineterm=""))
    out: Dict[str, Any] = {"target_file": target_file, "kind": kind, "old_content": old_content, "new_content": new_content, "unified_diff": "".join(unified_lines) if unified_lines else ""}
    if op.get("oss_examples"):
        out["oss_examples"] = op["oss_examples"]
    return out


def _unified_file_diff(target_file: str, old_content: str, new_content: str) -> str:
    lines = list(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}",
            lineterm="",
        )
    )
    return "".join(lines)


def _preview_code_edit_ops(
    root: Path, ops: list[Dict[str, Any]]
) -> tuple[list[Dict[str, Any]], str]:
    """Build per-file previews for chat code_edit_patch ops. Returns (files, combined_diff)."""
    from .task_executor_helpers import within_root

    files: list[Dict[str, Any]] = []
    chunks: list[str] = []
    for op in ops:
        target = str(op.get("target") or "").strip()
        old_text = str(op.get("old_text") or "")
        new_text = str(op.get("new_text") or "")
        entry: Dict[str, Any] = {"target_file": target}
        if not target or not old_text:
            entry["error"] = "target and old_text required"
            files.append(entry)
            continue
        path = (root / target).resolve()
        if not within_root(root, path):
            entry["error"] = "path outside project"
            files.append(entry)
            continue
        if not path.exists() or not path.is_file():
            entry["error"] = f"file not found: {target}"
            files.append(entry)
            continue
        try:
            old_content = path.read_text(encoding="utf-8")
        except OSError as exc:
            entry["error"] = f"read failed: {exc}"
            files.append(entry)
            continue
        occurrences = old_content.count(old_text)
        if occurrences != 1:
            entry["error"] = f"old_text occurrences must be exactly 1, got {occurrences}"
            entry["old_content"] = old_content
            files.append(entry)
            continue
        new_content = old_content.replace(old_text, new_text, 1)
        unified = _unified_file_diff(target, old_content, new_content)
        entry.update(
            {
                "old_content": old_content,
                "new_content": new_content,
                "unified_diff": unified,
            }
        )
        files.append(entry)
        if unified:
            chunks.append(unified)
    return files, "\n".join(chunks)


def preview_chat_pending_plan(
    project_root: Path, pending_plan: Dict[str, Any] | None
) -> Dict[str, Any]:
    """Preview chat HITL pending_plan as unified diff / summary (Agent Diff button).

    Chat pending lives in dialog_state (not team-mode pending_plan.json).
    Primary path: intent=code_edit_patch with old_text/new_text or operations_json.
    """
    import json

    from .task_executor import is_pending_plan_valid
    from .task_executor_helpers import within_root

    if not isinstance(pending_plan, dict) or not pending_plan:
        return {"error": "no pending plan"}
    expired = not is_pending_plan_valid(pending_plan)
    intent = str(pending_plan.get("intent") or "").strip()
    target = str(pending_plan.get("target") or "").strip()
    raw_entities = pending_plan.get("entities")
    entities: Dict[str, Any] = raw_entities if isinstance(raw_entities, dict) else {}
    raw_steps = pending_plan.get("steps")
    steps: list[Any] = raw_steps if isinstance(raw_steps, list) else []
    root = Path(project_root).resolve()
    base: Dict[str, Any] = {
        "intent": intent,
        "target": target,
        "token": str(pending_plan.get("token") or ""),
        "expired": expired,
        "risk_level": str(pending_plan.get("risk_level") or ""),
    }

    if intent == "code_edit_patch":
        ops: list[Dict[str, Any]] = []
        operations_json = str(entities.get("operations_json") or "").strip()
        if operations_json:
            try:
                raw_ops = json.loads(operations_json)
            except json.JSONDecodeError as exc:
                return {**base, "error": f"invalid operations_json: {exc}"}
            if not isinstance(raw_ops, list) or not raw_ops:
                return {**base, "error": "operations_json must be non-empty list"}
            for item in raw_ops:
                if not isinstance(item, dict):
                    continue
                ops.append(
                    {
                        "target": str(item.get("target") or "").strip(),
                        "old_text": str(item.get("old_text") or ""),
                        "new_text": str(item.get("new_text") or ""),
                    }
                )
        else:
            ops.append(
                {
                    "target": target,
                    "old_text": str(entities.get("old_text") or ""),
                    "new_text": str(entities.get("new_text") or ""),
                }
            )
        files, combined = _preview_code_edit_ops(root, ops)
        out = {**base, "files": files, "unified_diff": combined}
        if not combined:
            first_err = next((f.get("error") for f in files if f.get("error")), None)
            out["error"] = first_err or "no change"
        return out

    if intent == "delete" and target:
        path = (root / target).resolve()
        if not within_root(root, path):
            return {**base, "error": "path outside project"}
        if not path.exists() or not path.is_file():
            return {**base, "error": f"file not found: {target}"}
        try:
            old_content = path.read_text(encoding="utf-8")
        except OSError as exc:
            return {**base, "error": f"read failed: {exc}"}
        unified = _unified_file_diff(target, old_content, "")
        return {
            **base,
            "files": [{"target_file": target, "old_content": old_content, "new_content": "", "unified_diff": unified}],
            "unified_diff": unified,
        }

    if intent == "create" and target:
        content = str(entities.get("code") or entities.get("content") or "")
        path = (root / target).resolve()
        if path.exists():
            return {**base, "error": f"file already exists: {target}"}
        unified = _unified_file_diff(target, "", content)
        summary = f"create {target}" + (f" ({len(content)} chars)" if content else " (empty)")
        return {**base, "unified_diff": unified or summary, "summary": summary}

    if intent == "run_command":
        cmd = str(entities.get("command") or target or "").strip()
        summary = f"$ {cmd}" if cmd else "run_command (no command)"
        return {**base, "unified_diff": summary, "summary": summary}

    lines = [f"intent={intent or '-'}", f"target={target or '-'}", f"risk={base['risk_level'] or '-'}"]
    for step in steps[:8]:
        lines.append(f"- {step}")
    summary = "\n".join(lines)
    return {**base, "unified_diff": summary, "summary": summary}
