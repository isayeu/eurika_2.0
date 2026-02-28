"""Policy evaluation and explainability helpers for agent operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .config import PolicyConfig, RiskLevel

PolicyDecision = Literal["allow", "review", "deny"]


@dataclass(slots=True)
class OperationPolicyResult:
    decision: PolicyDecision
    risk: RiskLevel
    reason: str
    explainability: dict[str, Any]


def _estimate_risk(op: dict[str, Any]) -> RiskLevel:
    kind = (op.get("kind") or "").strip()
    if kind in {"remove_unused_import", "remove_cyclic_import", "fix_import", "create_module_stub"}:
        return "low"
    if kind in {"split_module", "extract_class", "extract_block_to_helper", "refactor_module"}:
        return "high"
    return "medium"


def _expected_outcome(op: dict[str, Any]) -> str:
    kind = (op.get("kind") or "").strip()
    if kind == "remove_unused_import":
        return "Unused imports are removed without changing behavior."
    if kind == "remove_cyclic_import":
        return "Cycle edge is removed and imports become acyclic."
    if kind == "split_module":
        return "Oversized module is decomposed into a focused extracted module."
    if kind == "extract_class":
        return "Class responsibilities are extracted into a dedicated module."
    if kind == "extract_block_to_helper":
        return "Deeply nested block is extracted into a helper function."
    if kind == "refactor_code_smell":
        return "Code smell marker is applied as a refactoring TODO."
    return "Operation is applied and verified in the patch cycle."


WEAK_SMELL_ACTION_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("hub", "split_module"),
    ("bottleneck", "introduce_facade"),
    ("god_class", "extract_class"),
    ("long_function", "extract_nested_function"),
    ("long_function", "extract_block_to_helper"),
    ("long_function", "refactor_code_smell"),
    ("deep_nesting", "extract_block_to_helper"),
    ("deep_nesting", "refactor_code_smell"),
})

HARD_BLOCK_OPERATION_TARGETS: frozenset[tuple[str, str]] = frozenset({
    # Safety rail: self-refactor here frequently produces invalid helper extraction.
    ("extract_block_to_helper", "eurika/refactor/extract_function.py"),
})


def _hard_block_policy(op: dict[str, Any]) -> tuple[PolicyDecision | None, str | None]:
    """Block known fragile operation targets regardless of runtime mode."""
    kind = (op.get("kind") or "").strip()
    target = (op.get("target_file") or "").strip()
    if (kind, target) in HARD_BLOCK_OPERATION_TARGETS:
        return "deny", f"hard blocked target for safety: {target}|{kind}"
    return None, None


def _weak_pair_policy(
    op: dict[str, Any],
    *,
    mode: str,
) -> tuple[PolicyDecision | None, str | None]:
    """Return policy override for historically weak smell|action pairs."""
    kind = (op.get("kind") or "").strip()
    smell = (op.get("smell_type") or "").strip()
    if (smell, kind) not in WEAK_SMELL_ACTION_PAIRS:
        return None, None
    if mode == "hybrid":
        return "review", f"historically weak pair requires manual approval: {smell}|{kind}"
    return "deny", f"historically weak pair blocked in auto mode: {smell}|{kind}"


def _target_verify_fail_count(project_root: Path | None, op: dict[str, Any]) -> int:
    """Return verify_fail count for operation key from campaign memory."""
    if project_root is None:
        return 0
    try:
        from collections import Counter
        from eurika.storage import SessionMemory, operation_key

        mem = SessionMemory(project_root)
        data = mem._load()  # best-effort read of existing campaign data
        fail_keys = ((data.get("campaign") or {}).get("verify_fail_keys") or [])
        counts = Counter(str(k) for k in fail_keys)
        return int(counts.get(operation_key(op), 0))
    except Exception:
        return 0


_deny_candidates_cache: dict[str, list[dict[str, Any]]] = {}


def _load_deny_candidates(project_root: Path | None) -> list[dict[str, Any]]:
    """Load policy deny candidates from learning insights (KPI: rate<0.25, total>=3). Cached per project_root."""
    if project_root is None:
        return []
    key = str(project_root.resolve())
    if key in _deny_candidates_cache:
        return _deny_candidates_cache[key]
    try:
        from eurika.api import get_learning_insights

        insights = get_learning_insights(project_root, top_n=20)
        recs = insights.get("recommendations") or {}
        deny = recs.get("policy_deny_candidates") or []
        _deny_candidates_cache[key] = deny
        return deny
    except Exception:
        return []


def _deny_candidates_policy(
    op: dict[str, Any],
    *,
    mode: str,
    project_root: Path | None,
) -> tuple[PolicyDecision | None, str | None]:
    """Return policy override when op matches learning-based deny candidate (smell|action|target, rate<0.25)."""
    deny = _load_deny_candidates(project_root)
    if not deny:
        return None, None
    kind = str(op.get("kind") or "")
    smell = str(op.get("smell_type") or "")
    target = str(op.get("target_file") or "").replace("\\", "/")
    for r in deny:
        r_kind = str(r.get("action_kind") or "")
        r_smell = str(r.get("smell_type") or "")
        if r_kind != kind or r_smell != smell:
            continue
        rt = str(r.get("target_file") or "").replace("\\", "/")
        if rt and rt != target:
            continue
        rate = float(r.get("verify_success_rate", 0) or 0)
        total = int(r.get("total", 0) or 0)
        if total >= 3 and rate < 0.25:
            if mode == "auto":
                return "deny", f"learning: {smell}|{kind}@{target} rate={rate:.0%} (total={total}) — deny in auto"
            if mode == "hybrid":
                return "review", f"learning: {smell}|{kind}@{target} rate={rate:.0%} (total={total}) — review recommended"
        break
    return None, None


def _load_operation_whitelist(project_root: Path | None) -> list[dict[str, Any]]:
    """Load optional operation whitelist from .eurika/operation_whitelist.json."""
    if project_root is None:
        return []
    candidates = [
        project_root / ".eurika" / "operation_whitelist.json",
        project_root / "operation_whitelist.controlled.json",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ops = data.get("operations")
        if isinstance(ops, list):
            return [x for x in ops if isinstance(x, dict)]
    return []


def _op_matches_whitelist_entry(op: dict[str, Any], entry: dict[str, Any]) -> bool:
    """Match by kind + optional target_file + optional smell_type/location."""
    if str(entry.get("kind") or "") != str(op.get("kind") or ""):
        return False
    entry_target = str(entry.get("target_file") or "")
    if entry_target and entry_target != str(op.get("target_file") or ""):
        return False
    entry_smell = str(entry.get("smell_type") or "")
    if entry_smell and entry_smell != str(op.get("smell_type") or ""):
        return False
    entry_location = str(entry.get("location") or "")
    op_location = str((op.get("params") or {}).get("location") or "")
    if entry_location and entry_location != op_location:
        return False
    return True


def _whitelist_policy_override(
    op: dict[str, Any],
    *,
    mode: str,
    project_root: Path | None,
) -> tuple[PolicyDecision | None, str | None]:
    """Return optional decision override when operation is explicitly whitelisted."""
    for entry in _load_operation_whitelist(project_root):
        if not _op_matches_whitelist_entry(op, entry):
            continue
        allow_hybrid = bool(entry.get("allow_in_hybrid", True))
        allow_auto = bool(entry.get("allow_in_auto", False))
        if mode == "hybrid" and allow_hybrid:
            return "review", "whitelisted target for controlled hybrid rollout"
        if mode == "auto" and allow_auto:
            return "allow", "whitelisted target allowed in auto mode"
    return None, None


def _apply_core_rules(
    op: dict[str, Any],
    *,
    config: PolicyConfig,
    index: int,
    seen_files: set[str],
    risk: RiskLevel,
) -> tuple[PolicyDecision, str]:
    """Apply core policy rules (file patterns, limits, risk, API-breaking guard)."""
    target_file = str(op.get("target_file") or "")
    if target_file.startswith("tests/") and not config.allow_test_files:
        return "deny", "test files are blocked by policy"
    if config.matches_deny_pattern(target_file):
        return "deny", f"file matches deny pattern: {target_file}"
    if index > config.max_ops:
        return "deny", f"operation limit exceeded (max_ops={config.max_ops})"
    if target_file and target_file not in seen_files and len(seen_files) >= config.max_files:
        return "deny", f"file scope limit exceeded (max_files={config.max_files})"
    if config.api_breaking_guard and config.is_api_surface_file(target_file):
        if risk in ("medium", "high"):
            if config.mode == "hybrid":
                return "review", "API surface file requires manual approval"
            return "deny", "API surface file blocked by api_breaking_guard"
    if not config.allows_risk(risk):
        if config.mode == "hybrid":
            return "review", f"risk={risk} requires manual approval in hybrid mode"
        return "deny", f"risk={risk} exceeds auto_apply_max_risk={config.auto_apply_max_risk}"
    return "allow", "allowed by policy"


def evaluate_operation(
    op: dict[str, Any],
    *,
    config: PolicyConfig,
    index: int,
    seen_files: set[str],
    project_root: Path | None = None,
) -> OperationPolicyResult:
    """Evaluate one patch operation against configured policy and produce explainability metadata."""
    risk = _estimate_risk(op)
    hard_decision, hard_reason = _hard_block_policy(op)
    if hard_decision is not None and hard_reason is not None:
        explainability = {
            "why": str(op.get("description") or "No description provided."),
            "risk": risk,
            "expected_outcome": _expected_outcome(op),
            "rollback_plan": "Automatic rollback is triggered on verify failure.",
            "policy_decision": hard_decision,
            "policy_reason": hard_reason,
        }
        return OperationPolicyResult(
            decision=hard_decision,
            risk=risk,
            reason=hard_reason,
            explainability=explainability,
        )

    decision, reason = _apply_core_rules(
        op, config=config, index=index, seen_files=seen_files, risk=risk
    )

    if decision in {"allow", "review"}:
        weak_decision, weak_reason = _weak_pair_policy(op, mode=config.mode)
        if weak_decision is not None and weak_reason is not None:
            decision = weak_decision
            reason = weak_reason

    fail_count = _target_verify_fail_count(project_root, op)
    if fail_count >= 2:
        if config.mode == "auto":
            decision = "deny"
            reason = f"target has repeated verify failures (count={fail_count})"
        elif config.mode == "hybrid" and decision != "deny":
            decision = "review"
            reason = f"target has repeated verify failures (count={fail_count})"

    dc_decision, dc_reason = _deny_candidates_policy(
        op, mode=config.mode, project_root=project_root
    )
    if dc_decision is not None and dc_reason is not None:
        if decision != "deny":
            decision = dc_decision
            reason = dc_reason

    wl_decision, wl_reason = _whitelist_policy_override(
        op, mode=config.mode, project_root=project_root
    )
    if wl_decision is not None and wl_reason is not None:
        # Whitelist only relaxes conservative denies/reviews, never escalates.
        if decision == "deny" and wl_decision in {"review", "allow"}:
            decision = wl_decision
            reason = wl_reason
        elif decision == "review" and wl_decision in {"review", "allow"}:
            if wl_decision == "allow":
                decision = wl_decision
            reason = wl_reason

    explainability = {
        "why": str(op.get("description") or "No description provided."),
        "risk": risk,
        "expected_outcome": _expected_outcome(op),
        "rollback_plan": "Automatic rollback is triggered on verify failure.",
        "policy_decision": decision,
        "policy_reason": reason,
    }
    return OperationPolicyResult(
        decision=decision,
        risk=risk,
        reason=reason,
        explainability=explainability,
    )
