"""
Patch Apply v0.1 (draft)

Applies a PatchPlan in a minimal way: appends the textual `diff` (e.g. TODO
comment block) to each target file. No unified-diff parsing; intended for
human-reviewable plan output only.

Supports dry_run: when True, only reports what would be done; when False,
appends content to files. When backup=True (default for apply), copies each
file to .eurika_backups/<run_id>/ before modifying, so you can restore.

v0.2: remove_cyclic_import — when op.kind is remove_cyclic_import and
params.target_module is set, uses AST to remove the import instead of appending.
v0.3: split_module — when op.kind is split_module and params has imports_from,
uses AST to extract definitions into a new submodule.
v0.4: extract_class — when op.kind is extract_class and params has target_class.
v0.5: introduce_facade — when op.kind is introduce_facade, creates {stem}_api.py re-exporting public symbols.
and methods_to_extract, uses AST to extract methods (that don't use self) into
a new class in a new file.
v0.6: refactor_code_smell — when op.kind is refactor_code_smell (long_function, deep_nesting),
appends TODO comment via default append-diff path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from patch_apply_backup import (
    BACKUP_DIR,
    list_backups as _list_backups_impl,
    restore_backup as _restore_backup_impl,
    write_single_file_change as _write_single_file_change,
)
from patch_apply_handlers import (
    handle_create_module_stub,
    handle_fix_import,
    handle_non_default_kind,
)


def apply_patch_plan(
    project_root: Path,
    plan: Dict[str, Any],
    dry_run: bool = True,
    backup: bool = True,
) -> Dict[str, Any]:
    """
    Apply a patch plan (dict from PatchPlan.to_dict() or JSON).

    Each operation: append op["diff"] to project_root / op["target_file"].
    If dry_run is True, no files are modified; only a report is returned.
    If dry_run is False and backup is True, each target file is copied to
    project_root / .eurika_backups / <run_id> / <target_file> before writing.

    Returns:
        {
            "dry_run": bool,
            "modified": [str],
            "skipped": [str],
            "errors": [str],
            "backup_dir": str | None,   # set when backup was performed
        }
    """
    root = Path(project_root).resolve()
    modified: List[str] = []
    skipped: List[str] = []
    skipped_reasons: Dict[str, str] = {}
    errors: List[str] = []
    backup_dir: str | None = None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    operations = plan.get("operations") or []
    do_backup = not dry_run and backup

    for op in operations:
        target_file = op.get("target_file") or ""
        diff = op.get("diff") or ""
        kind = op.get("kind") or ""
        params = op.get("params") or {}
        content = op.get("content") or ""
        if not target_file:
            errors.append("operation missing target_file")
            continue

        path = root / target_file

        def _skip(reason: str) -> None:
            skipped.append(target_file)
            skipped_reasons[target_file] = reason

        if handle_create_module_stub(
            kind, path, target_file, content, dry_run, modified, _skip, errors
        ):
            continue

        handled, backup_dir = handle_fix_import(
            kind=kind,
            root=root,
            path=path,
            target_file=target_file,
            diff=diff,
            dry_run=dry_run,
            run_id=run_id,
            backup_dir=backup_dir,
            do_backup=do_backup,
            modified=modified,
            skip_cb=_skip,
            errors=errors,
        )
        if handled:
            continue

        if not path.exists():
            _skip("path not found")
            continue
        if not path.is_file():
            _skip("path not a file")
            continue

        if dry_run:
            modified.append(target_file)
            continue

        handled, backup_dir = handle_non_default_kind(
            root=root,
            path=path,
            target_file=target_file,
            kind=kind,
            params=params,
            run_id=run_id,
            backup_dir=backup_dir,
            do_backup=do_backup,
            modified=modified,
            skip_cb=_skip,
            errors=errors,
        )
        if handled:
            continue

        # Default: append diff
        content = path.read_text(encoding="utf-8")
        # Skip if exact diff already present
        if diff.strip() and diff.strip() in content:
            _skip("diff already in content")
            continue
        # For architectural ops (refactor_module, split_module): skip if file already has
        # "TODO: Refactor {target}" — prevents duplicate god_module TODOs. refactor_code_smell
        # uses different format (# TODO (eurika): refactor long_function...) and may add multiple.
        if kind in ("refactor_module", "split_module"):
            marker = f"# TODO: Refactor {target_file}"
            if marker in content:
                _skip("architectural TODO already present")
                continue

        try:
            suffix = "\n" + diff
            if not content.endswith("\n"):
                suffix = "\n" + suffix
            backup_dir, changed = _write_single_file_change(
                root, path, target_file, content + suffix, run_id, backup_dir, do_backup
            )
            if changed:
                modified.append(target_file)
        except Exception as e:
            errors.append(f"{target_file}: {e}")

    # Deduplicate modified (same file can be touched by multiple ops, e.g. clean_imports + refactor)
    modified_unique = list(dict.fromkeys(modified))

    return {
        "dry_run": dry_run,
        "modified": modified_unique,
        "skipped": skipped,
        "skipped_reasons": skipped_reasons,
        "errors": errors,
        "backup_dir": backup_dir,
        "run_id": run_id if do_backup and backup_dir else None,
    }


def list_backups(project_root: Path) -> Dict[str, Any]:
    """
    List available backup run_ids in .eurika_backups/.

    Returns:
        {"run_ids": [str], "backup_dir": str}
    """
    return _list_backups_impl(project_root)


def restore_backup(
    project_root: Path,
    run_id: str | None = None,
) -> Dict[str, Any]:
    """
    Restore files from .eurika_backups/<run_id>/ to project root.
    If run_id is None, restores from the latest run (most recent by name).

    Returns:
        {"restored": [str], "errors": [str], "run_id": str | None}
    """
    return _restore_backup_impl(project_root, run_id)

# TODO (eurika): refactor god_module patch_apply — extract handlers, introduce facade.


# TODO (eurika): refactor long_function 'apply_patch_plan' — consider extracting helper


# TODO (eurika): refactor deep_nesting 'apply_patch_plan' — consider extracting nested block
