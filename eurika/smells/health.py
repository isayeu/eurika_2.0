"""
Architecture Health v0.3 (draft).

Implementation moved from architecture_health.py (v0.9 migration).
Computes health score from summary, smells, and trends.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from eurika.smells.detector import ArchSmell


def compute_health(
    summary: Dict[str, Any],
    smells: List[ArchSmell],
    trends: Dict[str, str],
) -> Dict[str, Any]:
    """
    Compute a simple health score in [0, 100] with a few qualitative levels.

    Heuristic:
    - start from 80;
    - subtract for smells and bad trends;
    - map final score to {high, medium, low}.
    """
    score = _initial_score()
    factors: List[str] = []

    score, smell_factors = _apply_smell_penalties(score, smells)
    factors.extend(smell_factors)

    score, trend_factors = _apply_trend_adjustments(score, trends)
    factors.extend(trend_factors)

    score = _clamp_score(score)
    level = _score_to_level(score)

    return {
        "score": score,
        "level": level,
        "factors": factors,
    }


def _initial_score() -> int:
    """Base starting score before penalties/bonuses."""
    return 80


def _apply_smell_penalties(
    score: int,
    smells: List[ArchSmell],
) -> Tuple[int, List[str]]:
    """Apply penalties based on architectural smells."""
    factors: List[str] = []

    smell_count = len(smells)
    if smell_count:
        penalty = min(20, smell_count * 3)
        score -= penalty
        factors.append(f"{smell_count} architectural smells (penalty {penalty})")

    types = {s.type for s in smells}
    if "god_module" in types:
        score -= 8
        factors.append("presence of god_module (penalty 8)")
    if "bottleneck" in types:
        score -= 6
        factors.append("presence of bottleneck (penalty 6)")
    if "cyclic_dependency" in types:
        score -= 6
        factors.append("presence of cyclic_dependency (penalty 6)")

    return score, factors


def _apply_trend_adjustments(
    score: int,
    trends: Dict[str, str],
) -> Tuple[int, List[str]]:
    """Apply penalties/bonuses based on architecture trends."""
    factors: List[str] = []

    comp = trends.get("complexity", "stable")
    smells_trend = trends.get("smells", "stable")
    central = trends.get("centralization", "stable")

    if comp == "increasing":
        score -= 3
        factors.append("complexity increasing (penalty 3)")
    if smells_trend == "increasing":
        score -= 10
        factors.append("smell count increasing (penalty 10)")
    elif smells_trend == "decreasing":
        score += 5
        factors.append("smell count decreasing (bonus 5)")

    if central == "increasing":
        score -= 5
        factors.append("centralization increasing (penalty 5)")

    return score, factors


def _clamp_score(score: int) -> int:
    """Clamp score into [0, 100] interval."""
    return max(0, min(100, score))


def _score_to_level(score: int) -> str:
    """Map numeric score to qualitative level."""
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def health_summary(health: Dict[str, Any]) -> str:
    """Render a small text summary for CLI output."""
    lines: List[str] = []
    lines.append("ARCHITECTURE HEALTH")
    lines.append("")
    lines.append(f"Health score: {health['score']} ({health['level']})")
    lines.append("")
    lines.append("Factors:")
    factors = health.get("factors") or []
    if not factors:
        lines.append("- no significant structural risks detected by current heuristic")
    else:
        for f in factors:
            lines.append(f"- {f}")
    return "\n".join(lines)
