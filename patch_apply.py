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
from typing import Any, Dict, List, Optional, Tuple

from eurika.refactor.remove_import import remove_import_from_file
from eurika.refactor.remove_unused_import import remove_unused_imports
from eurika.refactor.split_module import (
    split_module_by_class,
    split_module_by_function,
    split_module_by_import,
)
from eurika.refactor.extract_class import extract_class
from eurika.refactor.extract_function import extract_nested_function
from eurika.refactor.introduce_facade import introduce_facade

BACKUP_DIR = ".eurika_backups"


def _try_split_module_chain(
    path: Path, target_file: str, params: Dict[str, Any]
) -> Optional[Tuple[str, str, str]]:
    """Try split_module_by_import → by_class → by_function. Returns (new_rel_path, new_content, modified_original) or None."""
    result = split_module_by_import(
        path,
        params.get("imports_from") or [],
        extracted_module_stem="_extracted",
        target_file=target_file,
    )
    if result is None:
        result = split_module_by_class(path, target_file=target_file, min_class_size=3)
    if result is None:
        result = split_module_by_function(path, target_file=target_file, min_statements=1)
    return result


def _backup_file(
    root: Path,
    path: Path,
    target_file: str,
    run_id: str,
    backup_dir: str | None,
    do_backup: bool,
) -> str | None:
    """Copy path to .eurika_backups/run_id/target_file if do_backup. Returns backup_dir."""
    if not do_backup:
        return backup_dir
    backup_root = root / BACKUP_DIR / run_id
    backup_path = backup_root / target_file
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(backup_root) if backup_dir is None else backup_dir


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

        # create_module_stub: create new file (path may not exist)
        if kind == "create_module_stub" and content:
            if path.exists():
                _skip("create_module_stub: path exists")
                continue
            if dry_run:
                modified.append(target_file)
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                modified.append(target_file)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
            continue

        # fix_import: replace line in existing file
        if kind == "fix_import" and diff:
            if not path.exists() or not path.is_file():
                _skip("fix_import: path missing or not file")
                continue
            if dry_run:
                modified.append(target_file)
                continue
            try:
                backup_dir = _backup_file(root, path, target_file, run_id, backup_dir, do_backup)
                path.write_text(diff, encoding="utf-8")
                modified.append(target_file)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
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

        # remove_unused_import: AST-based removal (ROADMAP 2.4.1)
        if kind == "remove_unused_import":
            try:
                new_content = remove_unused_imports(path)
                if new_content is None:
                    _skip("remove_unused_import: no unused imports")
                    continue
                backup_dir = _backup_file(root, path, target_file, run_id, backup_dir, do_backup)
                path.write_text(new_content, encoding="utf-8")
                modified.append(target_file)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
            continue

        # remove_cyclic_import: AST-based removal
        if kind == "remove_cyclic_import" and params.get("target_module"):
            try:
                new_content = remove_import_from_file(path, params["target_module"])
                if new_content is None:
                    _skip("remove_cyclic_import: import not found")
                    continue
                backup_dir = _backup_file(root, path, target_file, run_id, backup_dir, do_backup)
                path.write_text(new_content, encoding="utf-8")
                modified.append(target_file)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
            continue

        # split_module: AST-based extraction (import-based or class-based fallback)
        if kind == "split_module":
            try:
                result = _try_split_module_chain(path, target_file, params)
                if result is not None:
                    new_rel_path, new_content, modified_original = result
                    new_path = root / new_rel_path
                    if new_path.exists():
                        _skip("split_module: extracted file exists")
                        continue
                    backup_dir = _backup_file(root, path, target_file, run_id, backup_dir, do_backup)
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    new_path.write_text(new_content, encoding="utf-8")
                    path.write_text(modified_original, encoding="utf-8")
                    modified.append(target_file)
                    modified.append(new_rel_path)
                    continue
                # result is None: no extractable defs, fall through to append diff (TODO hint)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
                continue

        # introduce_facade: create {stem}_api.py re-exporting bottleneck (ROADMAP: real fix for bottleneck)
        if kind == "introduce_facade":
            try:
                result = introduce_facade(
                    path,
                    target_file=target_file,
                    callers=params.get("callers"),
                )
                if result is None:
                    _skip("introduce_facade: no facade created")
                    continue
                new_rel_path, new_content = result
                new_path = root / new_rel_path
                if new_path.exists():
                    _skip("introduce_facade: facade file exists")
                    continue
                # No backup: we only create new file, do not modify bottleneck
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_path.write_text(new_content, encoding="utf-8")
                modified.append(new_rel_path)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
            continue

        # refactor_module: try split_module chain (ROADMAP: real fix instead of TODO)
        if kind == "refactor_module":
            try:
                result = _try_split_module_chain(path, target_file, params)
                if result is not None:
                    new_rel_path, new_content, modified_original = result
                    new_path = root / new_rel_path
                    if new_path.exists():
                        _skip("refactor_module: extracted file exists")
                        continue
                    backup_dir = _backup_file(root, path, target_file, run_id, backup_dir, do_backup)
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    new_path.write_text(new_content, encoding="utf-8")
                    path.write_text(modified_original, encoding="utf-8")
                    modified.append(target_file)
                    modified.append(new_rel_path)
                    continue
            except Exception as e:
                errors.append(f"{target_file}: {e}")
                continue

        # extract_nested_function: move nested function to module level (long_function smell)
        if kind == "extract_nested_function" and params.get("location") and params.get("nested_function_name"):
            try:
                new_content = extract_nested_function(
                    path,
                    params["location"],
                    params["nested_function_name"],
                )
                if new_content is None:
                    _skip("extract_nested_function: extraction failed")
                    continue
                backup_dir = _backup_file(root, path, target_file, run_id, backup_dir, do_backup)
                path.write_text(new_content, encoding="utf-8")
                modified.append(target_file)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
            continue

        # extract_class: AST-based method extraction
        if kind == "extract_class" and params.get("target_class") and params.get("methods_to_extract"):
            try:
                result = extract_class(
                    path,
                    params["target_class"],
                    params["methods_to_extract"],
                    target_file=target_file,
                )
                if result is None:
                    _skip("extract_class: extraction failed")
                    continue
                new_rel_path, new_content, modified_original = result
                new_path = root / new_rel_path
                if new_path.exists():
                    _skip("extract_class: extracted file exists")
                    continue
                backup_dir = _backup_file(root, path, target_file, run_id, backup_dir, do_backup)
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_path.write_text(new_content, encoding="utf-8")
                path.write_text(modified_original, encoding="utf-8")
                modified.append(target_file)
                modified.append(new_rel_path)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
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
            backup_dir = _backup_file(root, path, target_file, run_id, backup_dir, do_backup)
            suffix = "\n" + diff
            if not content.endswith("\n"):
                suffix = "\n" + suffix
            path.write_text(content + suffix, encoding="utf-8")
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
    root = Path(project_root).resolve()
    backup_root = root / BACKUP_DIR
    if not backup_root.is_dir():
        return {"run_ids": [], "backup_dir": str(backup_root)}
    run_ids = sorted(p.name for p in backup_root.iterdir() if p.is_dir())
    return {"run_ids": run_ids, "backup_dir": str(backup_root)}


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
    root = Path(project_root).resolve()
    backup_root = root / BACKUP_DIR
    restored: List[str] = []
    errors: List[str] = []

    if not backup_root.is_dir():
        errors.append(f"Backup dir not found: {backup_root}")
        return {"restored": [], "errors": errors, "run_id": None}

    if run_id is None:
        run_ids = sorted(p.name for p in backup_root.iterdir() if p.is_dir())
        if not run_ids:
            errors.append("No backup runs found")
            return {"restored": [], "errors": errors, "run_id": None}
        run_id = run_ids[-1]

    run_path = backup_root / run_id
    if not run_path.is_dir():
        errors.append(f"Run not found: {run_id}")
        return {"restored": [], "errors": errors, "run_id": run_id}

    for backup_file in run_path.rglob("*"):
        if not backup_file.is_file():
            continue
        rel = backup_file.relative_to(run_path)
        target = root / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(backup_file.read_text(encoding="utf-8"), encoding="utf-8")
            restored.append(str(rel))
        except Exception as e:
            errors.append(f"{rel}: {e}")

    return {"restored": restored, "errors": errors, "run_id": run_id}

# TODO (eurika): refactor god_module patch_apply — extract handlers, introduce facade.


# TODO (eurika): refactor long_function 'apply_patch_plan' — consider extracting helper


# TODO (eurika): refactor deep_nesting 'apply_patch_plan' — consider extracting nested block
