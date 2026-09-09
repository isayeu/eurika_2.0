"""Planning coupling v0 (VISION Stage 5).

Soft signals from Formal A/B + verify_by_kind into bug-hunt ranking.
Never autoapplies; never hard-denies — mirrors hypothesis caution.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Soft score deltas (same scale as bug_hunt._score_op).
AB_BASELINE_PENALTY = -25
AB_SANDBOX_BONUS = 15
VERIFY_LOW_PENALTY = -20
VERIFY_LOW_RATE = 0.5
VERIFY_MIN_N = 3
AB_MIN_DECISIVE = 2  # ignore noise from single trial
AB_RECENT_LIMIT = 20


def _ab_kind_bias(trials: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Aggregate recent decisive A/B trials by action kind."""
    by_kind: Dict[str, Dict[str, int]] = {}
    for trial in trials[-AB_RECENT_LIMIT:]:
        if not isinstance(trial, dict):
            continue
        kind = str(trial.get("kind") or "").strip()
        if not kind:
            continue
        winner = str(trial.get("winner") or "")
        # Skip noise: insufficient / graph_unchanged ties do not inform ranking.
        if winner in {"insufficient", ""}:
            continue
        if winner == "tie" and trial.get("graph_unchanged"):
            continue
        if not trial.get("smoke_ok") and winner != "baseline":
            winner = "baseline"
        bucket = by_kind.setdefault(kind, {"sandbox": 0, "baseline": 0, "tie": 0})
        if winner == "sandbox":
            bucket["sandbox"] += 1
        elif winner == "baseline":
            bucket["baseline"] += 1
        elif winner == "tie":
            bucket["tie"] += 1

    out: Dict[str, Dict[str, Any]] = {}
    for kind, counts in by_kind.items():
        decisive = int(counts["sandbox"]) + int(counts["baseline"])
        if decisive < AB_MIN_DECISIVE:
            continue
        if counts["baseline"] > counts["sandbox"]:
            bias = "baseline"
            delta = AB_BASELINE_PENALTY
        elif counts["sandbox"] > counts["baseline"]:
            bias = "sandbox"
            delta = AB_SANDBOX_BONUS
        else:
            continue
        out[kind] = {
            "bias": bias,
            "delta": delta,
            "sandbox_n": counts["sandbox"],
            "baseline_n": counts["baseline"],
            "tie_n": counts["tie"],
            "decisive_n": decisive,
        }
    return out


def _verify_kind_bias(by_kind: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(by_kind, dict):
        return out
    for kind, stats in by_kind.items():
        if not isinstance(stats, dict):
            continue
        vs = int(stats.get("verify_success") or 0)
        vf = int(stats.get("verify_fail") or 0)
        n = vs + vf
        if n < VERIFY_MIN_N:
            continue
        rate = stats.get("rate")
        try:
            rate_f = float(rate) if rate is not None else (vs / n if n else 0.0)
        except (TypeError, ValueError):
            rate_f = vs / n if n else 0.0
        if rate_f < VERIFY_LOW_RATE:
            out[str(kind)[:80]] = {
                "delta": VERIFY_LOW_PENALTY,
                "rate": round(rate_f, 3),
                "n": n,
            }
    return out


def load_planning_signals(project_root: str | Path) -> Dict[str, Any]:
    """Load soft ranking signals (facts only)."""
    root = Path(project_root).resolve()
    ab_bias: Dict[str, Dict[str, Any]] = {}
    verify_bias: Dict[str, Dict[str, Any]] = {}
    try:
        from eurika.evaluation.ab_compare import load_ab_trials

        ab_bias = _ab_kind_bias(load_ab_trials(root))
    except Exception:
        ab_bias = {}
    try:
        from eurika.api.experiment_memory import compute_self_improvement_metrics

        metrics = compute_self_improvement_metrics(root)
        vbk = metrics.get("verify_by_kind") if isinstance(metrics, dict) else None
        by_kind = vbk.get("by_kind") if isinstance(vbk, dict) else {}
        verify_bias = _verify_kind_bias(by_kind if isinstance(by_kind, dict) else {})
    except Exception:
        verify_bias = {}
    return {
        "version": 1,
        "ab_by_kind": ab_bias,
        "verify_low_by_kind": verify_bias,
        "note": "soft ranking only — not an apply gate",
    }


def score_delta_for_kind(
    kind: str,
    signals: Optional[Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """Return (score_delta, stamp fields) for an action kind."""
    k = str(kind or "").strip()
    stamp: Dict[str, Any] = {}
    if not k or not isinstance(signals, dict):
        return 0, stamp
    delta = 0
    ab = (signals.get("ab_by_kind") or {}).get(k)
    if isinstance(ab, dict):
        try:
            d = int(ab.get("delta") or 0)
        except (TypeError, ValueError):
            d = 0
        delta += d
        stamp["planning_ab_bias"] = ab.get("bias")
        stamp["planning_ab_delta"] = d
    ver = (signals.get("verify_low_by_kind") or {}).get(k)
    if isinstance(ver, dict):
        try:
            d = int(ver.get("delta") or 0)
        except (TypeError, ValueError):
            d = 0
        delta += d
        stamp["planning_verify_rate"] = ver.get("rate")
        stamp["planning_verify_delta"] = d
    if stamp:
        stamp["planning_coupling_v0"] = True
        stamp["planning_score_delta"] = delta
    return delta, stamp


def stamp_planning_on_ops(
    ops: List[Dict[str, Any]],
    signals: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Copy ops and attach planning_* fields when a signal applies."""
    if not signals:
        return ops
    out: List[Dict[str, Any]] = []
    for op in ops:
        if not isinstance(op, dict):
            out.append(op)
            continue
        kind = str(op.get("kind") or "")
        _delta, stamp = score_delta_for_kind(kind, signals)
        if not stamp:
            out.append(op)
            continue
        row = dict(op)
        row.update(stamp)
        out.append(row)
    return out
