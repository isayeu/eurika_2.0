"""Task executor: code_edit_patch (single and batch)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .task_executor_helpers import (
    build_preview_snippet,
    run_pytest,
    task_backup_before_write,
    within_root,
)
from .task_executor_types import ExecutionReport, MAX_PATCH_OPS, MAX_PATCH_TEXT, TaskSpec


def execute_code_edit_patch(root: Path, spec: TaskSpec) -> ExecutionReport:
    """Safely apply simple text replacement with mandatory verify + rollback."""
    operations_json = str(spec.entities.get("operations_json") or "").strip()
    if operations_json:
        return execute_code_edit_patch_batch(root, spec, operations_json)
    is_dry_run = str(spec.entities.get("dry_run") or "").strip().lower() in {"1", "true", "yes"}
    target = (spec.target or "").strip()
    old_text = str(spec.entities.get("old_text") or "")
    new_text = str(spec.entities.get("new_text") or "")
    verify_target = str(spec.entities.get("verify_target") or "").strip()
    if not target:
        return ExecutionReport(ok=False, summary="patch failed", error="target file is required")
    if not old_text:
        return ExecutionReport(ok=False, summary="patch failed", error="old_text is required")
    if len(old_text) > MAX_PATCH_TEXT or len(new_text) > MAX_PATCH_TEXT:
        return ExecutionReport(ok=False, summary="patch failed", error="text size exceeds limit")
    path = (root / target).resolve()
    if not within_root(root, path):
        return ExecutionReport(ok=False, summary="patch failed", error="path outside project")
    if not path.exists() or not path.is_file():
        return ExecutionReport(ok=False, summary="patch failed", error="target file not found")
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ExecutionReport(ok=False, summary="patch failed", error=str(exc))
    occurrences = original.count(old_text)
    if occurrences != 1:
        return ExecutionReport(
            ok=False,
            summary="patch failed",
            error=f"old_text occurrences must be exactly 1, got {occurrences}",
        )
    patched = original.replace(old_text, new_text, 1)
    verify_args = ["-q"]
    if verify_target:
        verify_args.append(verify_target)
    elif (root / "tests" / "test_qt_smoke.py").exists():
        verify_args.append("tests/test_qt_smoke.py")
    if is_dry_run:
        preview = build_preview_snippet(old_text, new_text)
        return ExecutionReport(
            ok=True,
            summary="patch dry-run preview",
            applied_steps=["compute replacement plan"],
            verification={
                "runner": "dry_run",
                "ok": True,
                "verify_args": verify_args,
                "output": f"{target}\n{preview}",
            },
            artifacts_changed=[target],
        )
    task_backup_before_write(root, target, path)
    try:
        path.write_text(patched, encoding="utf-8")
    except OSError as exc:
        return ExecutionReport(ok=False, summary="patch failed", error=str(exc))

    verification = run_pytest(root, verify_args, timeout=300)
    if verification.get("ok"):
        return ExecutionReport(
            ok=True,
            summary="patch applied and verified",
            applied_steps=["replace text", "run verify"],
            verification=verification,
            artifacts_changed=[target],
        )
    try:
        path.write_text(original, encoding="utf-8")
    except OSError as exc:
        return ExecutionReport(
            ok=False,
            summary="patch verify failed and rollback failed",
            applied_steps=["replace text", "run verify"],
            verification=verification,
            artifacts_changed=[target],
            error=f"rollback failed: {exc}",
        )
    verification["rollback"] = "done"
    return ExecutionReport(
        ok=False,
        summary="patch verify failed, rollback done",
        applied_steps=["replace text", "run verify"],
        verification=verification,
        artifacts_changed=[],
        error="verify failed",
    )


def execute_code_edit_patch_batch(root: Path, spec: TaskSpec, operations_json: str) -> ExecutionReport:
    """Apply multiple replacements atomically with single verify and rollback."""
    is_dry_run = str(spec.entities.get("dry_run") or "").strip().lower() in {"1", "true", "yes"}
    try:
        raw_ops = json.loads(operations_json)
    except json.JSONDecodeError as exc:
        return ExecutionReport(ok=False, summary="patch failed", error=f"invalid operations_json: {exc}")
    if not isinstance(raw_ops, list) or not raw_ops:
        return ExecutionReport(ok=False, summary="patch failed", error="operations_json must be non-empty list")
    if len(raw_ops) > MAX_PATCH_OPS:
        return ExecutionReport(ok=False, summary="patch failed", error=f"too many operations: max {MAX_PATCH_OPS}")

    ops: List[Dict[str, str]] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            return ExecutionReport(ok=False, summary="patch failed", error="batch operation must be object")
        target = str(item.get("target") or "").strip()
        old_text = str(item.get("old_text") or "")
        new_text = str(item.get("new_text") or "")
        if not target or not old_text:
            return ExecutionReport(ok=False, summary="patch failed", error="each operation requires target and old_text")
        if len(old_text) > MAX_PATCH_TEXT or len(new_text) > MAX_PATCH_TEXT:
            return ExecutionReport(ok=False, summary="patch failed", error="text size exceeds limit")
        ops.append(
            {
                "target": target,
                "old_text": old_text,
                "new_text": new_text,
                "verify_target": str(item.get("verify_target") or "").strip(),
            }
        )

    originals: Dict[Path, str] = {}
    staged: Dict[Path, str] = {}
    changed_targets: List[str] = []
    verify_target = str(spec.entities.get("verify_target") or "").strip()

    for op in ops:
        target = op["target"]
        old_text = op["old_text"]
        new_text = op["new_text"]
        path = (root / target).resolve()
        if not within_root(root, path):
            return ExecutionReport(ok=False, summary="patch failed", error="path outside project")
        if not path.exists() or not path.is_file():
            return ExecutionReport(ok=False, summary="patch failed", error=f"target file not found: {target}")
        if path not in originals:
            try:
                originals[path] = path.read_text(encoding="utf-8")
            except OSError as exc:
                return ExecutionReport(ok=False, summary="patch failed", error=str(exc))
        current = staged.get(path, originals[path])
        occurrences = current.count(old_text)
        if occurrences != 1:
            return ExecutionReport(
                ok=False,
                summary="patch failed",
                error=f"old_text occurrences must be exactly 1 in `{target}`, got {occurrences}",
            )
        staged[path] = current.replace(old_text, new_text, 1)
        rel = str(path.relative_to(root))
        if rel not in changed_targets:
            changed_targets.append(rel)
        if not verify_target and op.get("verify_target"):
            verify_target = str(op.get("verify_target") or "").strip()
    verify_args = ["-q"]
    if verify_target:
        verify_args.append(verify_target)
    elif (root / "tests" / "test_qt_smoke.py").exists():
        verify_args.append("tests/test_qt_smoke.py")
    if is_dry_run:
        preview_lines = []
        for op in ops[:10]:
            preview_lines.append(op["target"])
            preview_lines.append(build_preview_snippet(op["old_text"], op["new_text"], max_len=140))
        if len(ops) > 10:
            preview_lines.append(f"... (+{len(ops) - 10} operations)")
        return ExecutionReport(
            ok=True,
            summary=f"batch patch dry-run preview ({len(ops)} ops)",
            applied_steps=[f"build {len(ops)} replacement plans"],
            verification={
                "runner": "dry_run",
                "ok": True,
                "verify_args": verify_args,
                "output": "\n".join(preview_lines),
            },
            artifacts_changed=changed_targets,
        )

    written: List[Path] = []
    batch_run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    try:
        for path, patched in staged.items():
            rel = str(path.relative_to(root))
            task_backup_before_write(root, rel, path, run_id=batch_run_id)
            path.write_text(patched, encoding="utf-8")
            written.append(path)
    except OSError as exc:
        for path in written:
            try:
                path.write_text(originals[path], encoding="utf-8")
            except OSError:
                pass
        return ExecutionReport(ok=False, summary="patch failed", error=f"write failed: {exc}")

    verification = run_pytest(root, verify_args, timeout=300)
    if verification.get("ok"):
        return ExecutionReport(
            ok=True,
            summary=f"batch patch applied and verified ({len(ops)} ops)",
            applied_steps=[f"apply {len(ops)} replacements", "run verify"],
            verification=verification,
            artifacts_changed=changed_targets,
        )

    rollback_failed = False
    for path in originals:
        try:
            path.write_text(originals[path], encoding="utf-8")
        except OSError:
            rollback_failed = True
    if rollback_failed:
        return ExecutionReport(
            ok=False,
            summary="batch patch verify failed and rollback failed",
            applied_steps=[f"apply {len(ops)} replacements", "run verify"],
            verification=verification,
            artifacts_changed=changed_targets,
            error="verify failed and rollback failed",
        )
    verification["rollback"] = "done"
    return ExecutionReport(
        ok=False,
        summary="batch patch verify failed, rollback done",
        applied_steps=[f"apply {len(ops)} replacements", "run verify"],
        verification=verification,
        artifacts_changed=[],
        error="verify failed",
    )
