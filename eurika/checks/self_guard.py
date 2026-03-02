"""R5 Self-guard: aggregated health gate for eurika self-check."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# R5 1.2.3: Complexity budget thresholds (alerts when exceeded)
GOD_MODULE_BUDGET = 8
BOTTLENECK_BUDGET = 5


@dataclass
class SelfGuardResult:
    """Aggregated result of architectural checks."""

    forbidden_count: int
    layer_viol_count: int
    subsystem_bypass_count: int
    must_split_count: int
    candidates_count: int
    trend_alarms: list[str]
    complexity_budget_alarms: list[str]


def _compute_trends_from_history(data: dict, window: int = 5) -> dict[str, str]:
    """Derive trends from history array (same logic as ArchitectureHistory.trend)."""

    def _dir(values: list[int]) -> str:
        if len(values) < 2:
            return "stable"
        if values[-1] > values[0]:
            return "increasing"
        if values[-1] < values[0]:
            return "decreasing"
        return "stable"

    history = data.get("history") or []
    pts = history[-window:] if len(history) >= window else history
    if len(pts) < 2:
        return {"complexity": "insufficient_data", "smells": "insufficient_data", "centralization": "insufficient_data"}
    complexity_series = [p.get("modules", 0) + p.get("dependencies", 0) for p in pts]
    smells_series = [p.get("total_smells", 0) for p in pts]
    central_series = [p.get("max_degree", 0) for p in pts]
    return {
        "complexity": _dir(complexity_series),
        "smells": _dir(smells_series),
        "centralization": _dir(central_series),
    }


def collect_self_guard(root: Path) -> SelfGuardResult:
    """
    Run all architectural checks and aggregate counts.

    R5: single health gate for self-check.
    """
    from eurika.checks.dependency_firewall import (
        collect_dependency_violations,
        collect_layer_violations,
        collect_subsystem_bypass_violations,
    )
    from eurika.checks.file_size import check_file_size_limits

    forbidden = collect_dependency_violations(root)
    layer_viol = collect_layer_violations(root)
    bypass = collect_subsystem_bypass_violations(root)
    candidates, must_split = check_file_size_limits(root, include_tests=True)

    trend_alarms: list[str] = []
    try:
        history_path = root / ".eurika" / "history.json"
        if history_path.exists():
            import json

            data = json.loads(history_path.read_text(encoding="utf-8"))
            trends = _compute_trends_from_history(data) if isinstance(data, dict) else {}
            if trends.get("centralization") == "increasing":
                trend_alarms.append("centralization increasing")
            if trends.get("complexity") == "increasing":
                trend_alarms.append("complexity increasing")
            if trends.get("smells") == "increasing":
                trend_alarms.append("smell count increasing")
    except Exception:
        pass

    complexity_budget_alarms: list[str] = []
    try:
        self_map_path = root / "self_map.json"
        if self_map_path.exists():
            from eurika.core.pipeline import build_snapshot_from_self_map

            snapshot = build_snapshot_from_self_map(self_map_path)
            god_count = sum(1 for s in snapshot.smells if s.type == "god_module")
            bottleneck_count = sum(1 for s in snapshot.smells if s.type == "bottleneck")
            if god_count > GOD_MODULE_BUDGET:
                complexity_budget_alarms.append(f"god_module {god_count}>{GOD_MODULE_BUDGET}")
            if bottleneck_count > BOTTLENECK_BUDGET:
                complexity_budget_alarms.append(f"bottleneck {bottleneck_count}>{BOTTLENECK_BUDGET}")
    except Exception:
        pass

    return SelfGuardResult(
        forbidden_count=len(forbidden),
        layer_viol_count=len(layer_viol),
        subsystem_bypass_count=len(bypass),
        must_split_count=len(must_split),
        candidates_count=len(candidates),
        trend_alarms=trend_alarms,
        complexity_budget_alarms=complexity_budget_alarms,
    )


def format_self_guard_block(result: SelfGuardResult) -> str:
    """Format SELF-GUARD summary block for self-check output."""
    file_size_violations = result.candidates_count + result.must_split_count  # P0.4: >400 hard
    total = (
        result.forbidden_count
        + result.layer_viol_count
        + result.subsystem_bypass_count
        + result.must_split_count
        + result.candidates_count
    )
    has_alarms = result.trend_alarms or result.complexity_budget_alarms
    if total == 0 and not has_alarms:
        return "\nSELF-GUARD: PASS (0 violations, 0 alarms)\n"

    lines = ["", "SELF-GUARD (R5):"]
    if total > 0:
        parts = []
        if result.forbidden_count:
            parts.append(f"{result.forbidden_count} forbidden")
        if result.layer_viol_count:
            parts.append(f"{result.layer_viol_count} layer")
        if result.subsystem_bypass_count:
            parts.append(f"{result.subsystem_bypass_count} subsystem bypass")
        if file_size_violations:
            parts.append(f"{file_size_violations} file-size (>400 LOC)")
        lines.append(f"  Violations: {', '.join(parts)}")
    if result.trend_alarms:
        lines.append(f"  Trend alarms: {'; '.join(result.trend_alarms)}")
    if result.complexity_budget_alarms:
        lines.append(f"  Complexity budget: {'; '.join(result.complexity_budget_alarms)}")
    lines.append("")
    return "\n".join(lines)


def self_guard_pass(result: SelfGuardResult) -> bool:
    """True if no blocking violations (trend alarms are informational).
    P0.4: >400 LOC = hard budget; candidates and must_split both fail --strict."""
    return (
        result.forbidden_count == 0
        and result.layer_viol_count == 0
        and result.subsystem_bypass_count == 0
        and result.must_split_count == 0
        and result.candidates_count == 0  # P0.4: >400 LOC hard limit
    )
