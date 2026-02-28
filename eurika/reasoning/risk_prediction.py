"""R5 2.1: Module regression risk prediction (history + smells)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def predict_module_regression_risk(
    project_root: Path,
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """
    Predict modules most likely to regress based on current smells and structure.

    R5 2.1: Score combines severity, centrality, smell type weight, and trends.
    Returns list of {module, score 0-100, reasons} sorted by score descending.
    """
    from eurika.analysis.self_map import build_graph_from_self_map
    from eurika.smells.detector import detect_architecture_smells
    from eurika.smells.rules import build_summary

    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return []

    try:
        graph = build_graph_from_self_map(self_map_path)
        smells = detect_architecture_smells(graph)
        summary = build_summary(graph, smells)
    except Exception:
        return []

    fan = graph.fan_in_out()
    scores: Dict[str, float] = {}
    reasons: Dict[str, List[str]] = {}

    # Base: smell severity per module (0–15 typical, scale to ~40)
    for s in smells:
        for node in s.nodes:
            sev = float(getattr(s, "severity", 0) or 0)
            scores[node] = scores.get(node, 0.0) + sev * 2.5
            reasons.setdefault(node, []).append(s.type)

    # Centrality: high degree = more coupling = regression risk
    for node in list(scores.keys()):
        fi, fo = fan.get(node, (0, 0))
        degree = fi + fo
        scores[node] += degree * 0.5
        if degree >= 8:
            reasons.setdefault(node, []).append("high_centrality")

    # Smell type weight: god_module, bottleneck = higher risk
    for node, r in reasons.items():
        if "god_module" in r:
            scores[node] += 8
        if "bottleneck" in r:
            scores[node] += 6
        if "hub" in r:
            scores[node] += 4

    # Summary risks bonus
    for risk in summary.get("risks") or []:
        if "@ " not in risk:
            continue
        _, rest = risk.split("@ ", 1)
        target = rest.split(" ", 1)[0].strip()
        if target in scores:
            scores[target] += 5
            if "in_summary_risks" not in reasons.get(target, []):
                reasons.setdefault(target, []).append("in_summary_risks")

    # Trend penalty: if smells/centralization increasing, boost all slightly
    trends: Dict[str, str] = {}
    try:
        from eurika.storage import ProjectMemory

        memory = ProjectMemory(root)
        trends = memory.history.trend(window=5)
    except Exception:
        pass

    if trends.get("smells") == "increasing" or trends.get("centralization") == "increasing":
        for node in scores:
            scores[node] += 2

    # Normalize to 0–100 and cap
    ordered = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
    max_s = max((s for _, s in ordered), default=1.0) or 1.0
    result: List[Dict[str, Any]] = []
    for module, raw in ordered:
        score = min(100, int(raw * 100 / max_s)) if max_s else 0
        result.append({
            "module": module,
            "score": score,
            "reasons": list(dict.fromkeys(reasons.get(module, []))),
        })
    return result
