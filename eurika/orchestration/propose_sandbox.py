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


def create_propose_sandbox(
    project_root: Path,
    *,
    drill_id: str,
) -> dict[str, Any]:
    """Create an isolated root for propose apply+verify.

    Prefers ``git worktree add --detach``; falls back to an empty directory
    (seed writes polygon files). Returns ``{path, mode, name}``.
    """
    root = Path(project_root).resolve()
    parent = sandbox_parent(root)
    parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    name = f"propose_{drill_id}_{stamp}"
    dest = parent / name
    if dest.exists():
        raise RuntimeError(f"sandbox path already exists: {dest}")

    worktree_err: str | None = None
    if is_git_checkout(root):
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
        if proc.returncode == 0 and dest.is_dir():
            return {"path": dest, "mode": "worktree", "name": name}
        worktree_err = (proc.stderr or proc.stdout or "").strip()[:300]
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)

    dest.mkdir(parents=True, exist_ok=False)
    out: dict[str, Any] = {"path": dest, "mode": "copy", "name": name}
    if worktree_err:
        out["worktree_error"] = worktree_err
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

    return {"ok": False, "error": f"unknown drill_id for smoke verify: {drill_id}"}


def apply_and_smoke_verify(
    sandbox_root: Path,
    operation: dict[str, Any],
    *,
    drill_id: str,
) -> dict[str, Any]:
    """Apply one op inside the sandbox and smoke-verify the target."""
    from patch_apply import apply_patch_plan

    target_rel = str(operation.get("target_file") or "")
    try:
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
    return {
        "ok": bool(smoke.get("ok")),
        "error": smoke.get("error"),
        "modified": modified,
        "target_file": target_rel,
        "apply_report_ok": True,
    }
