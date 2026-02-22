"""Prepare-stage helpers for fix-cycle orchestration."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from .logging import get_logger

_LOG = get_logger("orchestration.prepare")


def run_fix_scan_stage(path: Path, quiet: bool, run_scan: Any) -> bool:
    """Run scan stage for fix cycle. Returns True on success."""
    if not quiet:
        _LOG.info("--- Step 1/4: scan ---")
        _LOG.info("eurika fix: scan -> diagnose -> plan -> patch -> verify")
    if quiet:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return run_scan(path) == 0
    return run_scan(path) == 0


def prepend_fix_operations(
    path: Path,
    patch_plan: dict[str, Any],
    operations: list[dict[str, Any]],
    no_clean_imports: bool,
    no_code_smells: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Prepend clean-imports and code-smell operations to patch plan."""
    if not no_clean_imports:
        from eurika.api import get_clean_imports_operations

        clean_ops = get_clean_imports_operations(path)
        if clean_ops:
            operations = clean_ops + operations
            patch_plan = dict(patch_plan, operations=operations)

    if not no_code_smells:
        from eurika.api import get_code_smell_operations

        code_smell_ops = get_code_smell_operations(path)
        if code_smell_ops:
            operations = code_smell_ops + operations
            patch_plan = dict(patch_plan, operations=operations)

    return patch_plan, operations


def _drop_noop_append_ops(
    operations: list[dict[str, Any]],
    path: Path,
) -> list[dict[str, Any]]:
    """Drop ops whose diff is already in the target file (avoids skipped: diff already in content)."""
    append_kinds = ("refactor_code_smell", "refactor_module", "split_module")
    kept: list[dict[str, Any]] = []
    for op in operations:
        kind = op.get("kind") or ""
        if kind not in append_kinds:
            kept.append(op)
            continue
        target = str(op.get("target_file") or "").replace("\\", "/")
        diff = (op.get("diff") or "").strip()
        file_path = path / target
        if not (file_path.exists() and file_path.is_file()):
            kept.append(op)
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            kept.append(op)
            continue
        if diff and diff in content:
            continue
        if kind in ("refactor_module", "split_module"):
            marker = f"# TODO: Refactor {target}"
            if marker in content:
                continue
        kept.append(op)
    return kept


def _is_weak_pair(op: dict[str, Any]) -> bool:
    """True if op is a historically low-success smell|action pair."""
    from eurika.agent.policy import WEAK_SMELL_ACTION_PAIRS
    kind = (op.get("kind") or "").strip()
    smell = (op.get("smell_type") or "").strip()
    return (smell, kind) in WEAK_SMELL_ACTION_PAIRS


def _deprioritize_weak_pairs(
    operations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Move weak-pair ops to the end so they are cut first when hitting max_ops."""
    return sorted(operations, key=lambda op: (1 if _is_weak_pair(op) else 0))


def apply_runtime_policy(
    patch_plan: dict[str, Any],
    operations: list[dict[str, Any]],
    *,
    runtime_mode: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Evaluate operations via policy engine and attach explainability metadata."""
    from eurika.agent import evaluate_operation, load_policy_config

    cfg = load_policy_config(runtime_mode)
    seen_files: set[str] = set()
    kept: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for idx, op in enumerate(operations, start=1):
        target_file = str(op.get("target_file") or "")
        res = evaluate_operation(op, config=cfg, index=idx, seen_files=seen_files)
        op_with_meta = dict(op)
        op_with_meta["explainability"] = res.explainability
        decisions.append(
            {
                "index": idx,
                "target_file": target_file,
                "kind": op.get("kind"),
                "decision": res.decision,
                "reason": res.reason,
                "risk": res.risk,
            }
        )
        keep = (
            runtime_mode == "assist"
            or res.decision == "allow"
            or (res.decision == "review" and runtime_mode == "hybrid")
        )
        if keep:
            kept.append(op_with_meta)
            if target_file:
                seen_files.add(target_file)
    patch_plan = dict(patch_plan, operations=kept)
    return patch_plan, kept, decisions


def apply_session_rejections(
    path: Path,
    patch_plan: dict[str, Any],
    operations: list[dict[str, Any]],
    *,
    session_id: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Skip operations that were explicitly rejected in this session earlier."""
    if not session_id:
        return patch_plan, operations, []
    from eurika.storage import SessionMemory, operation_key

    mem = SessionMemory(path)
    rejected_keys = mem.rejected_keys(session_id)
    if not rejected_keys:
        return patch_plan, operations, []
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for op in operations:
        if operation_key(op) in rejected_keys:
            skipped.append(op)
            continue
        kept.append(op)
    return dict(patch_plan, operations=kept), kept, skipped


def apply_campaign_memory(
    path: Path,
    patch_plan: dict[str, Any],
    operations: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Skip ops rejected in any session or that failed verify 2+ times (ROADMAP 2.7.5).
    Bypassed when EURIKA_IGNORE_CAMPAIGN=1 (e.g. --apply-suggested-policy)."""
    import os
    if os.environ.get("EURIKA_IGNORE_CAMPAIGN", "").strip() in {"1", "true", "yes"}:
        return patch_plan, operations, []
    from eurika.storage import SessionMemory, operation_key

    mem = SessionMemory(path)
    skip_keys = mem.campaign_keys_to_skip()
    if not skip_keys:
        return patch_plan, operations, []
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for op in operations:
        if operation_key(op) in skip_keys:
            skipped.append(op)
            continue
        kept.append(op)
    return dict(patch_plan, operations=kept), kept, skipped


def run_fix_diagnose_stage(path: Path, window: int, quiet: bool) -> Any:
    """Run diagnose stage via ArchReviewAgentCore."""
    from agent_core import InputEvent
    from agent_core_arch_review import ArchReviewAgentCore

    if not quiet:
        _LOG.info("--- Step 2/4: diagnose ---")
    agent = ArchReviewAgentCore(project_root=path)
    event = InputEvent(
        type="arch_review",
        payload={"path": str(path), "window": window},
        source="cli",
    )
    return agent.handle(event)


def extract_patch_plan_from_result(
    result: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | tuple[None, None]:
    """Extract patch_plan and operations from agent result."""
    proposals = result.output.get("proposals", [])
    patch_proposal = next(
        (p for p in proposals if p.get("action") == "suggest_patch_plan"),
        None,
    )
    if not patch_proposal:
        return None, None
    patch_plan = patch_proposal.get("arguments", {}).get("patch_plan", {})
    operations = patch_plan.get("operations", [])
    return patch_plan, operations


def _early_exit(
    return_code: int,
    report: dict[str, Any],
    result: Any,
    patch_plan: dict[str, Any] | None,
    operations: list[dict[str, Any]],
) -> tuple[dict[str, Any], Any, dict[str, Any] | None, list[dict[str, Any]]]:
    """Build early-exit tuple for prepare_fix_cycle_operations."""
    return (
        {
            "return_code": return_code,
            "report": report,
            "operations": report.get("operations", operations),
            "modified": report.get("modified", []),
            "verify_success": report.get("verify_success", return_code == 0),
            "agent_result": result,
        },
        result,
        patch_plan,
        operations,
    )


def prepare_fix_cycle_operations(
    path: Path,
    *,
    runtime_mode: str,
    session_id: str | None,
    window: int,
    quiet: bool,
    skip_scan: bool,
    no_clean_imports: bool,
    no_code_smells: bool,
    run_scan: Any,
) -> tuple[dict[str, Any] | None, Any, dict[str, Any] | None, list[dict[str, Any]]]:
    """Prepare diagnose result, patch plan and operations; return early payload on stop conditions."""
    if not skip_scan:
        if not run_fix_scan_stage(path, quiet, run_scan):
            return _early_exit(
                1, {"operations": [], "modified": [], "verify_success": False},
                None, None, [],
            )

    result = run_fix_diagnose_stage(path, window, quiet)
    if not result.success:
        return _early_exit(1, result.output, result, None, [])

    extracted = extract_patch_plan_from_result(result)
    if extracted == (None, None):
        return _early_exit(
            0,
            {
                "message": "No suggest_patch_plan proposal. Cycle complete (nothing to apply).",
                "operations": [], "modified": [], "verify_success": True,
            },
            result, None, [],
        )
    patch_plan, operations = extracted
    patch_plan, operations = prepend_fix_operations(
        path, patch_plan, operations, no_clean_imports, no_code_smells
    )
    operations = _drop_noop_append_ops(operations, path)
    operations = _deprioritize_weak_pairs(operations)
    patch_plan = dict(patch_plan, operations=operations)
    patch_plan, operations, policy_decisions = apply_runtime_policy(
        patch_plan,
        operations,
        runtime_mode=runtime_mode,
    )
    patch_plan, operations, _ = apply_campaign_memory(path, patch_plan, operations)
    patch_plan, operations, session_skipped = apply_session_rejections(
        path, patch_plan, operations, session_id=session_id
    )
    if not operations:
        return {
            "return_code": 0,
            "report": {
                "message": "Patch plan has no operations. Cycle complete.",
                "policy_decisions": policy_decisions,
                "session_skipped": len(session_skipped),
            },
            "operations": [],
            "modified": [],
            "verify_success": True,
            "agent_result": result,
        }, result, patch_plan, []
    if session_skipped:
        result.output["session_skipped"] = len(session_skipped)
    result.output["policy_decisions"] = policy_decisions
    return None, result, patch_plan, operations




# TODO (eurika): refactor long_function 'prepare_fix_cycle_operations' — consider extracting helper
