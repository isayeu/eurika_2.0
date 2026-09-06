"""C.14 propose sandbox: apply+smoke-verify in an isolated worktree/copy.

Architecture Freeze path (ROADMAP §4.6): experiment off the live tree →
propose to Approvals → apply on main only after HITL.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

SANDBOX_DIR_REL = ".eurika/sandbox"


def sandbox_parent(project_root: Path) -> Path:
    return Path(project_root).resolve() / SANDBOX_DIR_REL


def is_git_checkout(project_root: Path) -> bool:
    root = Path(project_root).resolve()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and (proc.stdout or "").strip() == "true"


def list_propose_sandboxes(project_root: Path) -> list[Path]:
    """Existing ``propose_*`` dirs under ``.eurika/sandbox`` (sorted by name)."""
    parent = sandbox_parent(project_root)
    if not parent.is_dir():
        return []
    return sorted(
        path
        for path in parent.iterdir()
        if path.is_dir() and path.name.startswith("propose_")
    )


def git_worktree_prune(project_root: Path) -> dict[str, Any]:
    """Drop stale git worktree registrations (``git worktree prune``)."""
    root = Path(project_root).resolve()
    if not is_git_checkout(root):
        return {"ok": True, "skipped": "not_git", "pruned": False}
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "worktree", "prune", "--verbose"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc), "pruned": False}
    return {
        "ok": proc.returncode == 0,
        "pruned": True,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip()[:500],
        "stderr": (proc.stderr or "").strip()[:300],
    }


def prune_propose_sandboxes(
    project_root: Path,
    *,
    keep_latest: int = 0,
) -> dict[str, Any]:
    """Remove old propose sandboxes and prune git worktree metadata.

    Keeps the ``keep_latest`` newest dirs (by name stamp). Safe outside sandbox
    parent is refused by ``remove_propose_sandbox``.
    """
    root = Path(project_root).resolve()
    existing = list_propose_sandboxes(root)
    keep = max(0, int(keep_latest))
    to_remove = existing if keep <= 0 else existing[:-keep] if len(existing) > keep else []
    removed: list[str] = []
    errors: list[str] = []
    for path in to_remove:
        try:
            mode = "worktree" if (path / ".git").exists() else "copy"
            remove_propose_sandbox(root, path, mode=mode)
            removed.append(path.name)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    prune_meta = git_worktree_prune(root)
    return {
        "ok": not errors,
        "removed": removed,
        "kept": [p.name for p in existing if p.name not in removed],
        "errors": errors,
        "git_prune": prune_meta,
    }


def create_propose_sandbox(
    project_root: Path,
    *,
    drill_id: str,
    prune_stale: bool = True,
) -> dict[str, Any]:
    """Create an isolated root for propose apply+verify.

    Prefers ``git worktree add --detach``; falls back to an empty directory
    (seed writes polygon files). Returns ``{path, mode, name}``.
    """
    root = Path(project_root).resolve()
    parent = sandbox_parent(root)
    parent.mkdir(parents=True, exist_ok=True)
    prune_info: dict[str, Any] | None = None
    if prune_stale:
        # Drop leftovers before add — stale worktrees slow/break git worktree add.
        prune_info = prune_propose_sandboxes(root, keep_latest=0)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    name = f"propose_{drill_id}_{stamp}"
    dest = parent / name
    if dest.exists():
        raise RuntimeError(f"sandbox path already exists: {dest}")

    worktree_err: str | None = None
    if is_git_checkout(root):
        try:
            proc = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "worktree",
                    "add",
                    "--detach",
                    str(dest),
                    "HEAD",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            worktree_err = "git worktree add timed out"
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            proc = None
        if proc is not None and proc.returncode == 0 and dest.is_dir():
            out_ok: dict[str, Any] = {"path": dest, "mode": "worktree", "name": name}
            if prune_info is not None:
                out_ok["pruned"] = prune_info
            return out_ok
        if proc is not None:
            worktree_err = (proc.stderr or proc.stdout or "").strip()[:300] or worktree_err
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)

    dest.mkdir(parents=True, exist_ok=False)
    out: dict[str, Any] = {"path": dest, "mode": "copy", "name": name}
    if worktree_err:
        out["worktree_error"] = worktree_err
    if prune_info is not None:
        out["pruned"] = prune_info
    return out


def remove_propose_sandbox(
    project_root: Path,
    sandbox_path: Path,
    *,
    mode: str | None = None,
) -> None:
    """Remove sandbox worktree or directory (best-effort)."""
    root = Path(project_root).resolve()
    path = Path(sandbox_path).resolve()
    parent = sandbox_parent(root).resolve()
    try:
        path.relative_to(parent)
    except ValueError:
        raise RuntimeError(f"refusing to remove path outside sandbox parent: {path}") from None
    if mode == "worktree" or (path / ".git").exists() or is_git_checkout(root):
        subprocess.run(
            ["git", "-C", str(root), "worktree", "remove", "--force", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def smoke_verify_after_apply(
    sandbox_root: Path,
    *,
    drill_id: str,
    target_rel: str,
) -> dict[str, Any]:
    """Cheap post-apply checks on the polygon target (no full pytest)."""
    path = Path(sandbox_root).resolve() / target_rel
    if not path.is_file():
        return {"ok": False, "error": f"missing target after apply: {target_rel}"}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"read failed: {exc}"}
    try:
        compile(text, str(path), "exec")
    except SyntaxError as exc:
        return {"ok": False, "error": f"syntax: {exc}"}

    if drill_id == "imports":
        if "import os" in text:
            return {"ok": False, "error": "unused import `os` still present"}
        if "from pathlib import Path" not in text:
            return {"ok": False, "error": "expected Path import missing"}
        return {"ok": True}

    if drill_id == "extractable_block":
        if "def _extracted_block_" not in text:
            return {"ok": False, "error": "helper `_extracted_block_*` not found"}
        return {"ok": True}

    if drill_id == "deep_nesting":
        if "def _extracted_block_" not in text:
            return {"ok": False, "error": "helper `_extracted_block_*` not found"}
        if "def polygon_deep_nesting_extractable" not in text:
            return {"ok": False, "error": "main deep_nesting extractable missing"}
        return {"ok": True}

    if drill_id == "long_function":
        # Nested def should be extracted to module level (before parent).
        if "def _compute_first_half" not in text:
            return {"ok": False, "error": "missing `_compute_first_half`"}
        if text.find("def _compute_first_half") > text.find("def polygon_long_function"):
            return {"ok": False, "error": "nested def not extracted to module level"}
        return {"ok": True}

    if drill_id == "llm_extract":
        if "def _sum_intermediates" not in text and "def polygon_refactor_code_smell_drill" not in text:
            return {"ok": False, "error": "llm_extract result missing expected symbols"}
        # Live LLM may use another helper name; require parseable + main def.
        if "def polygon_refactor_code_smell_drill" not in text:
            return {"ok": False, "error": "main drill function missing after llm_extract"}
        return {"ok": True}

    if drill_id == "bug_hunt":
        # Kind-aware change checks run in apply_and_smoke_verify (needs before/after).
        return {"ok": True}

    return {"ok": False, "error": f"unknown drill_id for smoke verify: {drill_id}"}


def apply_and_smoke_verify(
    sandbox_root: Path,
    operation: dict[str, Any],
    *,
    drill_id: str,
) -> dict[str, Any]:
    """Apply one op inside the sandbox and smoke-verify the target."""
    import sys

    # Root-level ``patch_apply`` is not always on sys.path (eurika-qt entrypoint
    # unlike eurika_cli). Ensure the live checkout that owns this module is.
    repo_root = Path(__file__).resolve().parents[2]
    repo_s = str(repo_root)
    if repo_s not in sys.path:
        sys.path.insert(0, repo_s)

    target_rel = str(operation.get("target_file") or "")
    target_path = Path(sandbox_root).resolve() / target_rel
    before = ""
    if target_path.is_file():
        try:
            before = target_path.read_text(encoding="utf-8")
        except OSError:
            before = ""
    try:
        from patch_apply import apply_patch_plan

        report = apply_patch_plan(
            Path(sandbox_root).resolve(),
            {"operations": [operation]},
            dry_run=False,
            backup=False,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"sandbox apply failed: {exc}",
            "modified": [],
            "target_file": target_rel,
        }
    modified = list(report.get("modified") or []) if isinstance(report, dict) else []
    smoke = smoke_verify_after_apply(
        sandbox_root, drill_id=drill_id, target_rel=target_rel
    )
    if smoke.get("ok") and drill_id == "bug_hunt":
        after = ""
        if target_path.is_file():
            try:
                after = target_path.read_text(encoding="utf-8")
            except OSError as exc:
                return {
                    "ok": False,
                    "error": f"bug_hunt: read after apply failed: {exc}",
                    "modified": modified,
                    "target_file": target_rel,
                }
        from eurika.orchestration.bug_hunt import smoke_bug_hunt_change

        smoke = smoke_bug_hunt_change(
            before=before,
            after=after,
            operation=operation if isinstance(operation, dict) else {},
            modified=modified,
        )
    return {
        "ok": bool(smoke.get("ok")),
        "error": smoke.get("error"),
        "modified": modified,
        "target_file": target_rel,
        "apply_report_ok": True,
    }
