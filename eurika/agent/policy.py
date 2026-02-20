"""Policy evaluation and explainability helpers for agent operations."""

from __future__ import annotations

from dataclasses import dataclass
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
    if kind in {"split_module", "extract_class", "refactor_module"}:
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
    if kind == "refactor_code_smell":
        return "Code smell marker is applied as a refactoring TODO."
    return "Operation is applied and verified in the patch cycle."


def _weak_pair_policy(
    op: dict[str, Any],
    *,
    mode: str,
) -> tuple[PolicyDecision | None, str | None]:
    """Return policy override for historically weak smell|action pairs."""
    kind = (op.get("kind") or "").strip()
    smell = (op.get("smell_type") or "").strip()
    weak_pairs = {
        ("hub", "split_module"),
        ("bottleneck", "introduce_facade"),
        ("long_function", "extract_nested_function"),
    }
    if (smell, kind) not in weak_pairs:
        return None, None
    if mode == "hybrid":
        return "review", f"historically weak pair requires manual approval: {smell}|{kind}"
    return "deny", f"historically weak pair blocked in auto mode: {smell}|{kind}"


def _apply_core_rules(
    op: dict[str, Any],
    *,
    config: PolicyConfig,
    index: int,
    seen_files: set[str],
    risk: RiskLevel,
) -> tuple[PolicyDecision, str]:
    """Apply core policy rules (test files, limits, risk). Returns (decision, reason)."""
    target_file = str(op.get("target_file") or "")
    if target_file.startswith("tests/") and not config.allow_test_files:
        return "deny", "test files are blocked by policy"
    if index > config.max_ops:
        return "deny", f"operation limit exceeded (max_ops={config.max_ops})"
    if target_file and target_file not in seen_files and len(seen_files) >= config.max_files:
        return "deny", f"file scope limit exceeded (max_files={config.max_files})"
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
) -> OperationPolicyResult:
    """Evaluate one patch operation against configured policy and produce explainability metadata."""
    risk = _estimate_risk(op)
    decision, reason = _apply_core_rules(
        op, config=config, index=index, seen_files=seen_files, risk=risk
    )

    if decision in {"allow", "review"}:
        weak_decision, weak_reason = _weak_pair_policy(op, mode=config.mode)
        if weak_decision is not None and weak_reason is not None:
            decision = weak_decision
            reason = weak_reason

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
