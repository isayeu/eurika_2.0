"""Critic / decision coupling v0 + multi-role critic v0 (VISION Stage 3–5).

Named algorithmic roles (evidence / verify / hypothesis / self) vote
caution|support|silent. Not extra LLM agents — VISION forbids multi-agent
«ради агентов». Soft-escalate allow→review only; never hard-deny from
these votes; never autoapply. Hard deny stays in ``prepare_critic``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eurika.api.planning_coupling import load_planning_signals, score_delta_for_kind
from eurika.utils.json_io import as_dict, as_list

CRITIC_ROLES = ("evidence", "verify", "hypothesis", "self")


def _hypothesis_caution(project_root: Path) -> Dict[str, int]:
    try:
        from eurika.api.hypothesis_engine import hypothesis_ranking_signals

        raw = hypothesis_ranking_signals(project_root)
        weights = raw.get("caution_weights") if isinstance(raw, dict) else {}
        out: Dict[str, int] = {}
        if isinstance(weights, dict):
            for k, v in weights.items():
                try:
                    out[str(k)] = int(v)
                except (TypeError, ValueError):
                    continue
        return out
    except Exception:
        return {}


def _cheap_self_problems(project_root: Path) -> List[Dict[str, Any]]:
    """Facts for the ``self`` critic role — no full Self Model rebuild."""
    root = Path(project_root).resolve()
    problems: List[Dict[str, Any]] = []
    if not (root / "self_map.json").is_file():
        problems.append(
            {
                "id": "missing_self_map",
                "kind": "missing_artifact",
                "severity": "attention",
                "detail": "self_map.json missing — graph metrics unavailable",
            }
        )
    if (root / ".eurika" / "pending_plan.json").is_file():
        problems.append(
            {
                "id": "pending_approvals",
                "kind": "hitl_backlog",
                "severity": "info",
                "detail": "Approvals queue present (.eurika/pending_plan.json)",
            }
        )
    if (root / ".eurika" / "pending_host_admin.json").is_file():
        problems.append(
            {
                "id": "pending_host_admin",
                "kind": "host_admin_hitl",
                "severity": "info",
                "detail": "host admin mutate queued for HITL",
            }
        )
    try:
        from eurika.utils.json_io import load_json_safe

        hitl = load_json_safe(root / ".eurika" / "hitl_journal.json")
        agg = hitl.get("aggregates") if isinstance(hitl, dict) else {}
        if isinstance(agg, dict):
            ok = int(agg.get("apply_ok") or 0)
            fail = int(agg.get("apply_fail") or 0)
            n = ok + fail
            if n >= 3 and (ok / n) < 0.35:
                problems.append(
                    {
                        "id": "apply_ok_low",
                        "kind": "verify",
                        "severity": "attention",
                        "detail": f"apply_ok_rate={ok}/{n} < 0.35",
                    }
                )
    except Exception:
        pass
    return problems


def load_critic_coupling_signals(project_root: str | Path) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    planning = load_planning_signals(root)
    return {
        "version": 2,
        "roles": list(CRITIC_ROLES),
        "planning": planning,
        "caution_weights": _hypothesis_caution(root),
        "self_problems": _cheap_self_problems(root),
        "note": (
            "multi-role critic v0 (algorithmic votes) — "
            "soft escalate allow→review only; not hard-deny / not autoapply; "
            "not extra LLM agents"
        ),
    }


def collect_critic_role_votes(
    op: Dict[str, Any],
    signals: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """One vote per named role. Empty signals → all silent."""
    votes: List[Dict[str, Any]] = []
    if not isinstance(signals, dict):
        return [{"role": r, "vote": "silent", "reason": "no signals"} for r in CRITIC_ROLES]
    kind = str(op.get("kind") or "")
    planning = as_dict(signals.get("planning"))
    delta, plan_stamp = score_delta_for_kind(kind, planning) if kind else (0, {})
    caution = as_dict(signals.get("caution_weights"))
    caution_delta = 0
    if kind and kind in caution:
        try:
            caution_delta = int(caution[kind])
        except (TypeError, ValueError):
            caution_delta = -25

    if plan_stamp.get("planning_ab_bias") == "baseline" and delta < 0:
        votes.append({"role": "evidence", "vote": "caution", "reason": f"ab_baseline({delta})"})
    elif plan_stamp.get("planning_ab_bias") == "sandbox" and delta > 0:
        votes.append({"role": "evidence", "vote": "support", "reason": "ab_sandbox_support"})
    else:
        votes.append({"role": "evidence", "vote": "silent", "reason": "no ab bias"})

    if plan_stamp.get("planning_verify_delta") and int(plan_stamp.get("planning_verify_delta") or 0) < 0:
        votes.append(
            {
                "role": "verify",
                "vote": "caution",
                "reason": f"verify_low(rate={plan_stamp.get('planning_verify_rate')})",
            }
        )
    else:
        votes.append({"role": "verify", "vote": "silent", "reason": "verify ok or unknown"})

    if caution_delta < 0:
        votes.append(
            {"role": "hypothesis", "vote": "caution", "reason": f"hypothesis_caution({caution_delta})"}
        )
    else:
        votes.append({"role": "hypothesis", "vote": "silent", "reason": "no hypothesis caution"})

    problems = as_list(signals.get("self_problems"))
    self_hits = [
        p
        for p in problems
        if isinstance(p, dict)
        and str(p.get("kind") or "") in {"missing_artifact", "verify"}
        and str(p.get("severity") or "") == "attention"
    ]
    if self_hits:
        first = self_hits[0]
        votes.append(
            {
                "role": "self",
                "vote": "caution",
                "reason": str(first.get("id") or first.get("detail") or "self_problem"),
            }
        )
    else:
        votes.append({"role": "self", "vote": "silent", "reason": "no first-class problems"})
    return votes


def couple_critic_verdict(
    op: Dict[str, Any],
    *,
    verdict: str,
    reason: str,
    signals: Optional[Dict[str, Any]],
    whitelisted_auto: bool = False,
) -> Tuple[str, str, Dict[str, Any]]:
    """Maybe escalate ``allow`` → ``review`` from soft signals.

    Returns (verdict, reason, stamp). Does not escalate whitelist-auto ops.
    Does not turn anything into ``deny`` from coupling signals.
    """
    stamp: Dict[str, Any] = {}
    if not isinstance(signals, dict):
        return verdict, reason, stamp
    if verdict == "deny":
        return verdict, reason, stamp
    if whitelisted_auto:
        stamp["critic_coupling_skipped"] = "whitelisted_auto"
        return verdict, reason, stamp

    kind = str(op.get("kind") or "")
    if not kind:
        return verdict, reason, stamp

    planning = signals.get("planning") if isinstance(signals.get("planning"), dict) else {}
    delta, plan_stamp = score_delta_for_kind(kind, planning)
    votes = collect_critic_role_votes(op, signals)
    triggers = [str(v.get("reason")) for v in votes if v.get("vote") == "caution"]
    stamp["critic_roles"] = votes
    stamp["critic_roles_caution"] = len(triggers)

    if not triggers:
        if plan_stamp.get("planning_ab_bias") == "sandbox" and delta > 0:
            stamp.update(plan_stamp)
            stamp["critic_coupling_v0"] = True
            stamp["critic_coupling_note"] = "ab_sandbox_support"
        return verdict, reason, stamp

    stamp.update(plan_stamp)
    stamp["critic_coupling_v0"] = True
    stamp["critic_coupling_triggers"] = triggers
    stamp["critic_coupling_score_delta"] = int(delta)

    if verdict == "allow":
        return (
            "review",
            f"critic coupling: escalate to review — {', '.join(triggers)}",
            stamp,
        )
    return (
        verdict,
        f"{reason}; coupling: {', '.join(triggers)}",
        stamp,
    )
