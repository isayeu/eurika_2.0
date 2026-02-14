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
v0.4: extract_class — when op.kind is extract_class and params has target_class
and methods_to_extract, uses AST to extract methods (that don't use self) into
a new class in a new file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from eurika.refactor.remove_import import remove_import_from_file
from eurika.refactor.split_module import split_module_by_import
from eurika.refactor.extract_class import extract_class

BACKUP_DIR = ".eurika_backups"


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
        if not target_file:
            errors.append("operation missing target_file")
            continue

        path = root / target_file
        if not path.exists():
            skipped.append(target_file)
            continue
        if not path.is_file():
            skipped.append(target_file)
            continue

        if dry_run:
            modified.append(target_file)
            continue

        # remove_cyclic_import: AST-based removal
        if kind == "remove_cyclic_import" and params.get("target_module"):
            try:
                new_content = remove_import_from_file(path, params["target_module"])
                if new_content is None:
                    skipped.append(target_file)
                    continue
                if do_backup:
                    backup_root = root / BACKUP_DIR / run_id
                    backup_path = backup_root / target_file
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                    if backup_dir is None:
                        backup_dir = str(backup_root)
                path.write_text(new_content, encoding="utf-8")
                modified.append(target_file)
            except Exception as e:
                errors.append(f"{target_file}: {e}")
            continue

        # split_module: AST-based extraction (or fallback to TODO when no extractable defs)
        if kind == "split_module" and params.get("imports_from"):
            try:
                result = split_module_by_import(
                    path,
                    params["imports_from"],
                    extracted_module_stem="_extracted",
                    target_file=target_file,
                )
                if result is not None:
                    new_rel_path, new_content, modified_original = result
                    new_path = root / new_rel_path
                    if new_path.exists():
                        skipped.append(target_file)
                        continue
                    if do_backup:
                        backup_root = root / BACKUP_DIR / run_id
                        backup_path = backup_root / target_file
                        backup_path.parent.mkdir(parents=True, exist_ok=True)
                        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                        if backup_dir is None:
                            backup_dir = str(backup_root)
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
                    skipped.append(target_file)
                    continue
                new_rel_path, new_content, modified_original = result
                new_path = root / new_rel_path
                if new_path.exists():
                    skipped.append(target_file)
                    continue
                if do_backup:
                    backup_root = root / BACKUP_DIR / run_id
                    backup_path = backup_root / target_file
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                    if backup_dir is None:
                        backup_dir = str(backup_root)
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
            skipped.append(target_file)
            continue
        # Skip if eurika TODO for this target already exists (prevents duplicates when diff varies)
        marker = f"# TODO: Refactor {target_file}"
        if marker in content:
            skipped.append(target_file)
            continue

        try:
            if do_backup:
                backup_root = root / BACKUP_DIR / run_id
                backup_path = backup_root / target_file
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                if backup_dir is None:
                    backup_dir = str(backup_root)

            suffix = "\n" + diff
            if not content.endswith("\n"):
                suffix = "\n" + suffix
            path.write_text(content + suffix, encoding="utf-8")
            modified.append(target_file)
        except Exception as e:
            errors.append(f"{target_file}: {e}")

    return {
        "dry_run": dry_run,
        "modified": modified,
        "skipped": skipped,
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

# TODO: Refactor patch_apply.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: eurika/reasoning/planner.py, cli/agent_handlers.py, patch_engine.py.
# - Introduce facade for callers: patch_engine.py, cli/agent_handlers.py, eurika/reasoning/planner.py....

# TODO: Refactor patch_apply.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: patch_engine.py, eurika/reasoning/planner.py, cli/agent_handlers.py.
# - Introduce facade for callers: patch_engine.py, cli/agent_handlers.py, eurika/reasoning/planner.py....

# TODO: Refactor patch_apply.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: eurika/reasoning/planner.py, tests/test_patch_apply_remove_import.py, cli/agent_handlers.py.
# - Introduce facade for callers: patch_engine.py, cli/agent_handlers.py, eurika/reasoning/planner.py....

# TODO: Refactor patch_apply.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: patch_engine.py, cli/agent_handlers.py, tests/test_patch_apply.py.
# - Introduce facade for callers: patch_engine.py, cli/agent_handlers.py, eurika/reasoning/planner.py....

# TODO: Refactor patch_apply.py (god_module -> refactor_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Consider grouping callers: tests/test_patch_apply.py, patch_engine.py, eurika/reasoning/planner.py.
# - Introduce facade for callers: patch_engine.py, cli/agent_handlers.py, eurika/reasoning/planner.py....
