"""Operation-kind handlers for patch_apply.apply_patch_plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from eurika.refactor.extract_class import extract_class
from eurika.refactor.extract_function import extract_block_to_helper, extract_nested_function
from eurika.refactor.introduce_facade import introduce_facade
from eurika.refactor.remove_import import remove_import_from_file
from eurika.refactor.remove_unused_import import remove_unused_imports
from eurika.refactor.split_module import (
    split_module_by_class,
    split_module_by_function,
    split_module_by_import,
)
from patch_apply_backup import backup_file, write_extracted_and_original, write_single_file_change


def try_split_module_chain(
    path: Path,
    target_file: str,
    params: Dict[str, Any],
) -> Optional[Tuple[str, str, str]]:
    """Try split_module_by_import -> by_class -> by_function."""
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


def handle_create_module_stub(
    kind: str,
    path: Path,
    target_file: str,
    content: str,
    dry_run: bool,
    modified: List[str],
    skip_cb: Callable[[str], None],
    errors: List[str],
) -> bool:
    """Handle create_module_stub operation."""
    if kind != "create_module_stub":
        return False
    if not (content and path):
        return False
    if path.exists():
        skip_cb("create_module_stub: path exists")
        return True
    if dry_run:
        modified.append(target_file)
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        modified.append(target_file)
    except Exception as exc:
        errors.append(f"{target_file}: {exc}")
    return True


def handle_fix_import(
    *,
    kind: str,
    root: Path,
    path: Path,
    target_file: str,
    diff: str,
    dry_run: bool,
    run_id: str,
    backup_dir: str | None,
    do_backup: bool,
    modified: List[str],
    skip_cb: Callable[[str], None],
    errors: List[str],
) -> tuple[bool, str | None]:
    """Handle fix_import operation."""
    if kind != "fix_import":
        return False, backup_dir
    if not diff:
        return False, backup_dir
    if not path.exists() or not path.is_file():
        skip_cb("fix_import: path missing or not file")
        return True, backup_dir
    if dry_run:
        modified.append(target_file)
        return True, backup_dir
    try:
        backup_dir, changed = write_single_file_change(
            root, path, target_file, diff, run_id, backup_dir, do_backup
        )
        if changed:
            modified.append(target_file)
    except Exception as exc:
        errors.append(f"{target_file}: {exc}")
    return True, backup_dir


def _apply_content_replacement(
    *,
    root: Path,
    path: Path,
    target_file: str,
    new_content: str | None,
    run_id: str,
    backup_dir: str | None,
    do_backup: bool,
    modified: List[str],
    skip_cb: Callable[[str], None],
    errors: List[str],
    skip_reason: str,
) -> tuple[bool, str | None]:
    """Apply new content via write_single_file_change; skip if new_content is None."""
    try:
        if new_content is None:
            skip_cb(skip_reason)
            return True, backup_dir
        backup_dir, changed = write_single_file_change(
            root, path, target_file, new_content, run_id, backup_dir, do_backup
        )
        if changed:
            modified.append(target_file)
    except Exception as exc:
        errors.append(f"{target_file}: {exc}")
    return True, backup_dir


def handle_non_default_kind(
    *,
    root: Path,
    path: Path,
    target_file: str,
    kind: str,
    params: Dict[str, Any],
    run_id: str,
    backup_dir: str | None,
    do_backup: bool,
    modified: List[str],
    skip_cb: Callable[[str], None],
    errors: List[str],
) -> tuple[bool, str | None]:
    """Handle non-default operation kinds after path checks and dry_run gate."""
    if kind == "remove_unused_import":
        return _apply_content_replacement(
            root=root,
            path=path,
            target_file=target_file,
            new_content=remove_unused_imports(path),
            run_id=run_id,
            backup_dir=backup_dir,
            do_backup=do_backup,
            modified=modified,
            skip_cb=skip_cb,
            errors=errors,
            skip_reason="remove_unused_import: no unused imports",
        )

    if kind == "remove_cyclic_import" and params.get("target_module"):
        return _apply_content_replacement(
            root=root,
            path=path,
            target_file=target_file,
            new_content=remove_import_from_file(path, params["target_module"]),
            run_id=run_id,
            backup_dir=backup_dir,
            do_backup=do_backup,
            modified=modified,
            skip_cb=skip_cb,
            errors=errors,
            skip_reason="remove_cyclic_import: import not found",
        )

    if kind == "split_module":
        try:
            result = try_split_module_chain(path, target_file, params)
            if result is not None:
                new_rel_path, new_content, modified_original = result
                backup_dir, changed = write_extracted_and_original(
                    root,
                    path,
                    target_file,
                    new_rel_path,
                    new_content,
                    modified_original,
                    run_id,
                    backup_dir,
                    do_backup,
                    "split_module: extracted file exists",
                    skip_cb,
                )
                if changed:
                    modified.append(target_file)
                    modified.append(new_rel_path)
                    return True, backup_dir
        except Exception as exc:
            errors.append(f"{target_file}: {exc}")
            return True, backup_dir
        return False, backup_dir

    if kind == "introduce_facade":
        try:
            result = introduce_facade(
                path,
                target_file=target_file,
                callers=params.get("callers"),
            )
            if result is None:
                skip_cb("introduce_facade: no facade created")
                return True, backup_dir
            new_rel_path, new_content = result
            new_path = root / new_rel_path
            if new_path.exists():
                skip_cb("introduce_facade: facade file exists")
                return True, backup_dir
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_path.write_text(new_content, encoding="utf-8")
            modified.append(new_rel_path)
        except Exception as exc:
            errors.append(f"{target_file}: {exc}")
        return True, backup_dir

    if kind == "refactor_module":
        try:
            result = try_split_module_chain(path, target_file, params)
            if result is not None:
                new_rel_path, new_content, modified_original = result
                new_path = root / new_rel_path
                if new_path.exists():
                    skip_cb("refactor_module: extracted file exists")
                    return True, backup_dir
                backup_dir = backup_file(
                    root, path, target_file, run_id, backup_dir, do_backup
                )
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_path.write_text(new_content, encoding="utf-8")
                path.write_text(modified_original, encoding="utf-8")
                modified.append(target_file)
                modified.append(new_rel_path)
                return True, backup_dir
        except Exception as exc:
            errors.append(f"{target_file}: {exc}")
            return True, backup_dir
        return False, backup_dir

    if (
        kind == "extract_block_to_helper"
        and params.get("location")
        and params.get("block_start_line") is not None
        and params.get("helper_name")
    ):
        try:
            extra_params = params.get("extra_params")
            new_content = extract_block_to_helper(
                path,
                params["location"],
                params["block_start_line"],
                params["helper_name"],
                extra_params=extra_params if isinstance(extra_params, list) else None,
            )
            if new_content is None:
                skip_cb("extract_block_to_helper: extraction failed")
                return True, backup_dir
            backup_dir, changed = write_single_file_change(
                root, path, target_file, new_content, run_id, backup_dir, do_backup
            )
            if changed:
                modified.append(target_file)
        except Exception as exc:
            errors.append(f"{target_file}: {exc}")
        return True, backup_dir

    if (
        kind == "extract_nested_function"
        and params.get("location")
        and params.get("nested_function_name")
    ):
        try:
            extra_params = params.get("extra_params")
            new_content = extract_nested_function(
                path, params["location"], params["nested_function_name"],
                extra_params=extra_params if isinstance(extra_params, list) else None,
            )
            if new_content is None:
                skip_cb("extract_nested_function: extraction failed")
                return True, backup_dir
            backup_dir, changed = write_single_file_change(
                root, path, target_file, new_content, run_id, backup_dir, do_backup
            )
            if changed:
                modified.append(target_file)
        except Exception as exc:
            errors.append(f"{target_file}: {exc}")
        return True, backup_dir

    if kind == "extract_class" and params.get("target_class") and params.get("methods_to_extract"):
        try:
            result = extract_class(
                path,
                params["target_class"],
                params["methods_to_extract"],
                target_file=target_file,
            )
            if result is None:
                skip_cb("extract_class: extraction failed")
                return True, backup_dir
            new_rel_path, new_content, modified_original = result
            backup_dir, changed = write_extracted_and_original(
                root,
                path,
                target_file,
                new_rel_path,
                new_content,
                modified_original,
                run_id,
                backup_dir,
                do_backup,
                "extract_class: extracted file exists",
                skip_cb,
            )
            if changed:
                modified.append(target_file)
                modified.append(new_rel_path)
        except Exception as exc:
            errors.append(f"{target_file}: {exc}")
        return True, backup_dir

    return False, backup_dir


# TODO (eurika): refactor long_function 'handle_non_default_kind' — consider extracting helper
