"""Prepare-stage helpers for fix-cycle orchestration."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Literal, cast

from .contracts import FixReport, OperationRecord, PatchPlan
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


_CODE_SMELL_KINDS = frozenset((
    "extract_block_to_helper",
    "extract_nested_function",
    "refactor_code_smell",
))


def prepend_fix_operations(
    path: Path,
    patch_plan: PatchPlan,
    operations: list[OperationRecord],
    no_clean_imports: bool,
    no_code_smells: bool,
) -> tuple[PatchPlan, list[OperationRecord]]:
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
    else:
        # --no-code-smells: also drop architect-proposed code-smell ops
        operations = [op for op in operations if (op.get("kind") or "") not in _CODE_SMELL_KINDS]
        patch_plan = dict(patch_plan, operations=operations)

    return patch_plan, operations


def _drop_noop_append_ops(
    operations: list[OperationRecord],
    path: Path,
) -> list[OperationRecord]:
    """Drop ops whose diff is already in the target file (avoids skipped: diff already in content)."""
    append_kinds = ("refactor_code_smell", "refactor_module", "split_module")
    kept: list[OperationRecord] = []
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


def _is_weak_pair(op: OperationRecord) -> bool:
    """True if op is a historically low-success smell|action pair."""
    from eurika.agent import WEAK_SMELL_ACTION_PAIRS
    kind = (op.get("kind") or "").strip()
    smell = (op.get("smell_type") or "").strip()
    return (smell, kind) in WEAK_SMELL_ACTION_PAIRS


def _deprioritize_weak_pairs(
    operations: list[OperationRecord],
) -> list[OperationRecord]:
    """Move weak-pair ops to the end so they are cut first when hitting max_ops."""
    return sorted(operations, key=lambda op: (1 if _is_weak_pair(op) else 0))


def _apply_context_priority(
    operations: list[OperationRecord],
    context_sources: dict[str, Any],
) -> list[OperationRecord]:
    """Boost operations with stronger semantic context signals. KPI A.4: verify_success_rate in tiebreak."""
    rejected_targets = set(context_sources.get("campaign_rejected_targets") or [])
    fail_targets = set(context_sources.get("recent_verify_fail_targets") or [])
    by_target = context_sources.get("by_target") or {}
    scored: list[tuple[int, float, int, OperationRecord]] = []
    for idx, op in enumerate(operations):
        target = str(op.get("target_file") or "")
        ctx = by_target.get(target) or {}
        tests = ctx.get("related_tests") or []
        neighbors = ctx.get("neighbor_modules") or []
        rate = ctx.get("verify_success_rate")
        hits: list[str] = []
        score = 0
        if target in fail_targets:
            score += 3
            hits.append("recent_verify_fail")
        if target in rejected_targets:
            score += 2
            hits.append("campaign_rejected")
        if tests:
            score += 1
            hits.append("related_tests")
        if neighbors:
            score += 1
            hits.append("neighbor_modules")
        if rate is not None:
            if rate >= 0.5:
                score += 1
                hits.append("high_verify_rate")
            elif rate < 0.25:
                score -= 1
                hits.append("low_verify_rate")
        op2 = dict(op)
        op2["context_score"] = score
        op2["context_hits"] = hits
        rate_tiebreak = -(rate if rate is not None else 0.0)
        scored.append((-score, rate_tiebreak, idx, op2))
    scored.sort()
    return [item[3] for item in scored]


def _approval_state_from_policy(decision: str) -> str:
    """Map policy decision to default approval state."""
    if decision == "allow":
        return "approved"
    if decision == "review":
        return "pending"
    return "rejected"


def _run_critic_pass(
    operations: list[OperationRecord],
    *,
    runtime_mode: str,
    project_root: Path | None = None,
) -> tuple[list[OperationRecord], list[dict[str, Any]]]:
    """Attach critic verdict to each operation before apply."""
    from eurika.agent import is_whitelisted_for_auto

    updated: list[OperationRecord] = []
    decisions: list[dict[str, Any]] = []
    for idx, op in enumerate(operations, start=1):
        op2 = dict(op)
        kind = str(op2.get("kind") or "")
        target = str(op2.get("target_file") or "")
        expl = op2.get("explainability") or {}
        risk = str(expl.get("risk") or op2.get("risk") or "unknown")
        diff = str(op2.get("diff") or "")
        approval_state = str(op2.get("approval_state") or "pending")
        whitelisted_auto = is_whitelisted_for_auto(op2, project_root)

        verdict = "allow"
        reason = "passed critic checks"
        if approval_state == "rejected":
            verdict = "deny"
            reason = "rejected by policy/human"
        elif "_extracted_extracted" in target:
            verdict = "deny"
            reason = "blocked repeated extracted chain"
        elif kind == "refactor_code_smell" and "# TODO" in diff:
            verdict = "deny"
            reason = "blocked todo-only patch candidate"
        elif risk == "high" and runtime_mode in {"hybrid", "auto"}:
            if whitelisted_auto:
                pass  # whitelist bypass: keep verdict=allow (polygon drills)
            else:
                verdict = "review"
                reason = "high-risk operation requires explicit review"
        elif (
            kind in {"split_module", "refactor_module", "extract_class"}
            and risk in {"medium", "high"}
            and runtime_mode in {"hybrid", "auto"}
        ):
            if whitelisted_auto:
                pass
            else:
                verdict = "review"
                reason = "structural refactor requires review"

        op2["critic_verdict"] = verdict
        op2["critic_reason"] = reason
        op2["decision_source"] = op2.get("decision_source", "policy")
        if verdict == "deny":
            op2["approval_state"] = "rejected"
        elif verdict == "review" and op2.get("approval_state") == "approved":
            op2["approval_state"] = "pending"

        updated.append(op2)
        decisions.append(
            {
                "index": idx,
                "target_file": target,
                "kind": kind,
                "verdict": verdict,
                "reason": reason,
                "risk": risk,
            }
        )
    return updated, decisions


def apply_runtime_policy(
    patch_plan: PatchPlan,
    operations: list[OperationRecord],
    *,
    path: Path,
    runtime_mode: str,
) -> tuple[PatchPlan, list[OperationRecord], list[dict[str, Any]]]:
    """Evaluate operations via policy engine and attach explainability metadata."""
    from eurika.agent import evaluate_operation, load_policy_config

    runtime_mode_lit = cast(Literal["assist", "hybrid", "auto"], runtime_mode)
    cfg = load_policy_config(runtime_mode_lit)
    seen_files: set[str] = set()
    kept: list[OperationRecord] = []
    decisions: list[dict[str, Any]] = []
    for idx, op in enumerate(operations, start=1):
        target_file = str(op.get("target_file") or "")
        res = evaluate_operation(
            op,
            config=cfg,
            index=idx,
            seen_files=seen_files,
            project_root=path,
        )
        op_with_meta = dict(op)
        op_with_meta["explainability"] = res.explainability
        op_with_meta["policy_decision"] = res.decision
        op_with_meta["approval_state"] = _approval_state_from_policy(res.decision)
        op_with_meta["critic_verdict"] = "pending"
        op_with_meta["critic_reason"] = ""
        op_with_meta["decision_source"] = "policy"
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
    patch_plan: PatchPlan,
    operations: list[OperationRecord],
    *,
    session_id: str | None,
) -> tuple[PatchPlan, list[OperationRecord], list[OperationRecord]]:
    """Skip operations that were explicitly rejected in this session earlier."""
    if not session_id:
        return patch_plan, operations, []
    from eurika.storage import SessionMemory, operation_key

    mem = SessionMemory(path)
    rejected_keys = mem.rejected_keys(session_id)
    if not rejected_keys:
        return patch_plan, operations, []
    kept: list[OperationRecord] = []
    skipped: list[OperationRecord] = []
    for op in operations:
        if operation_key(op) in rejected_keys:
            skipped.append(op)
            continue
        kept.append(op)
    return dict(patch_plan, operations=kept), kept, skipped


_CAMPAIGN_BYPASS_LOW_RISK_KINDS = frozenset({"remove_unused_import"})


def _op_in_polygon_whitelist(op: dict[str, Any], path: Path) -> bool:
    """True if op matches operation_whitelist with allow_in_auto (e.g. polygon drills)."""
    from eurika.agent import is_whitelisted_for_auto

    return is_whitelisted_for_auto(op, path)


def _allow_low_risk_campaign_bypass() -> bool:
    """When True, low-risk ops (e.g. remove_unused_import) bypass campaign skip."""
    import os

    return os.environ.get("EURIKA_CAMPAIGN_ALLOW_LOW_RISK", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def apply_campaign_memory(
    path: Path,
    patch_plan: PatchPlan,
    operations: list[OperationRecord],
    *,
    allow_retry: bool = False,
    allow_low_risk: bool = False,
) -> tuple[PatchPlan, list[OperationRecord], list[OperationRecord]]:
    """Skip ops rejected in any session or that failed verify 2+ times (ROADMAP 2.7.5).
    Bypassed when EURIKA_IGNORE_CAMPAIGN=1 (e.g. --apply-suggested-policy).
    When allow_low_risk or EURIKA_CAMPAIGN_ALLOW_LOW_RISK=1, low-risk kinds (remove_unused_import) bypass skip."""
    import os

    if allow_retry or os.environ.get("EURIKA_IGNORE_CAMPAIGN", "").strip() in {"1", "true", "yes"}:
        return patch_plan, operations, []
    from eurika.storage import SessionMemory, operation_key

    mem = SessionMemory(path)
    skip_keys = mem.campaign_keys_to_skip()
    if not skip_keys:
        return patch_plan, operations, []
    allow_low_risk = allow_low_risk or _allow_low_risk_campaign_bypass()
    kept: list[OperationRecord] = []
    skipped: list[OperationRecord] = []
    for op in operations:
        if operation_key(op) in skip_keys:
            if allow_low_risk and (
                str(op.get("kind") or "") in _CAMPAIGN_BYPASS_LOW_RISK_KINDS
                or _op_in_polygon_whitelist(op, path)
            ):
                kept.append(op)
            else:
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
) -> tuple[PatchPlan, list[OperationRecord]] | tuple[None, None]:
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


def _attach_llm_hint_runtime(result: Any) -> None:
    """Attach planner LLM-hints runtime counters to diagnose result output."""
    out = getattr(result, "output", None)
    if not isinstance(out, dict):
        return
    try:
        from eurika.reasoning.planner_llm import llm_hint_runtime_stats

        out["llm_hint_runtime"] = llm_hint_runtime_stats()
    except Exception:
        pass


def _early_exit(
    return_code: int,
    report: FixReport,
    result: Any,
    patch_plan: PatchPlan | None,
    operations: list[OperationRecord],
) -> tuple[dict[str, Any], Any, PatchPlan | None, list[OperationRecord]]:
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
    allow_campaign_retry: bool = False,
    allow_low_risk_campaign: bool = False,
) -> tuple[dict[str, Any] | None, Any, PatchPlan | None, list[OperationRecord]]:
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
    _attach_llm_hint_runtime(result)

    extracted = extract_patch_plan_from_result(result)
    if extracted == (None, None):
        root_str = str(path.resolve())
        patch_plan = {"project_root": root_str, "operations": []}
        operations = []
    else:
        patch_plan, operations = cast(tuple[PatchPlan, list[OperationRecord]], extracted)
    patch_plan, operations = prepend_fix_operations(
        path, patch_plan, operations, no_clean_imports, no_code_smells
    )
    operations = _drop_noop_append_ops(operations, path)
    operations = _deprioritize_weak_pairs(operations)
    patch_plan = dict(patch_plan, operations=operations)
    patch_plan, operations, policy_decisions = apply_runtime_policy(
        patch_plan,
        operations,
        path=path,
        runtime_mode=runtime_mode,
    )
    patch_plan, operations, campaign_skipped = apply_campaign_memory(
        path,
        patch_plan,
        operations,
        allow_retry=allow_campaign_retry,
        allow_low_risk=allow_low_risk_campaign,
    )
    patch_plan, operations, session_skipped = apply_session_rejections(
        path, patch_plan, operations, session_id=session_id
    )
    context_sources: dict[str, Any] = {}
    try:
        from eurika.reasoning.architect import build_context_sources

        context_sources = build_context_sources(path, operations)
        operations = _apply_context_priority(operations, context_sources)
    except Exception:
        context_sources = {}
    operations, critic_decisions = _run_critic_pass(
        operations, runtime_mode=runtime_mode, project_root=path
    )
    patch_plan = dict(patch_plan, operations=operations)
    if context_sources:
        patch_plan["context_sources"] = context_sources
    if not operations:
        return {
            "return_code": 0,
            "report": {
                "message": "Patch plan has no operations. Cycle complete.",
                "policy_decisions": policy_decisions,
                "critic_decisions": critic_decisions,
                "context_sources": context_sources,
                "campaign_skipped": len(campaign_skipped),
                "session_skipped": len(session_skipped),
                "llm_hint_runtime": result.output.get("llm_hint_runtime"),
            },
            "operations": [],
            "modified": [],
            "verify_success": True,
            "agent_result": result,
        }, result, patch_plan, []
    if session_skipped:
        result.output["session_skipped"] = len(session_skipped)
    result.output["policy_decisions"] = policy_decisions
    result.output["critic_decisions"] = critic_decisions
    result.output["context_sources"] = context_sources
    return None, result, patch_plan, operations




# TODO (eurika): refactor long_function 'prepare_fix_cycle_operations' — consider extracting helper
