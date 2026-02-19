"""
Architecture Diff v0.1

Compares two architecture snapshots (self_map + derived graph/smells)
and produces an evolution report.

Supports both legacy ArchSnapshot (from self_map path) and core.ArchitectureSnapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Tuple

from eurika.analysis.metrics import summarize_graph
from eurika.analysis.graph import ProjectGraph
from eurika.smells.detector import (
    ArchSmell,
    detect_architecture_smells,
    get_remediation_hint,
    severity_to_level,
)
from eurika.smells.rules import build_summary
from eurika.analysis.self_map import load_self_map

if TYPE_CHECKING:
    from core.snapshot import ArchitectureSnapshot


@dataclass
class ArchSnapshot:
    path: Path
    modules: List[str]
    graph_summary: Dict
    smells: List[ArchSmell]
    summary: Dict  # eurika.smells.summary.build_summary result


def build_snapshot(self_map_path: Path) -> ArchSnapshot:
    self_map = load_self_map(self_map_path)
    graph = ProjectGraph.from_self_map(self_map)
    smells = detect_architecture_smells(graph)
    graph_sum = summarize_graph(graph)
    summary = build_summary(graph, smells)
    modules = [m["path"] for m in self_map.get("modules", [])]
    return ArchSnapshot(
        path=self_map_path,
        modules=modules,
        graph_summary=graph_sum,
        smells=smells,
        summary=summary,
    )


def _smell_counts(smells: List[ArchSmell]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for s in smells:
        counts[s.type] = counts.get(s.type, 0) + 1
    return counts


def diff_snapshots(old: ArchSnapshot, new: ArchSnapshot) -> Dict:
    structures = _compute_structural_diff(old, new)
    centrality_shifts = _compute_centrality_shifts(old, new)
    smell_diff = _compute_smell_diff(old, new)
    recommended_actions = _build_recommended_actions(
        old.smells, new.smells, centrality_shifts
    )
    bottlenecks = _modules_became_bottlenecks(old.smells, new.smells)

    return {
        "structures": structures,
        "centrality_shifts": centrality_shifts,
        "smells": smell_diff,
        "maturity": {
            "old": old.summary.get("maturity", "unknown"),
            "new": new.summary.get("maturity", "unknown"),
        },
        "system": {
            "old": old.graph_summary,
            "new": new.graph_summary,
        },
        "recommended_actions": recommended_actions,
        "bottleneck_modules": bottlenecks,
    }


def diff_architecture_snapshots(
    old: "ArchitectureSnapshot", new: "ArchitectureSnapshot"
) -> Dict:
    """Diff two core.ArchitectureSnapshot instances. Same output shape as diff_snapshots."""
    old_modules = sorted(old.graph.nodes)
    new_modules = sorted(new.graph.nodes)
    structures = _compute_structural_diff_from_modules(old_modules, new_modules)

    old_fan = old.graph.fan_in_out()
    new_fan = new.graph.fan_in_out()
    centrality_shifts = _compute_centrality_shifts_from_fan(
        old_modules, new_modules, old_fan, new_fan
    )

    smell_diff = _compute_smell_diff_from_smells(old.smells, new.smells)
    recommended_actions = _build_recommended_actions(
        old.smells, new.smells, centrality_shifts
    )
    bottlenecks = _modules_became_bottlenecks(old.smells, new.smells)

    return {
        "structures": structures,
        "centrality_shifts": centrality_shifts,
        "smells": smell_diff,
        "maturity": {
            "old": old.summary.get("maturity", "unknown"),
            "new": new.summary.get("maturity", "unknown"),
        },
        "system": {
            "old": summarize_graph(old.graph),
            "new": summarize_graph(new.graph),
        },
        "recommended_actions": recommended_actions,
        "bottleneck_modules": bottlenecks,
    }


def _compute_structural_diff_from_modules(
    old_modules: List[str], new_modules: List[str]
) -> Dict[str, List[str]]:
    old_set = set(old_modules)
    new_set = set(new_modules)
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    common = sorted(old_set & new_set)
    return {
        "modules_added": added,
        "modules_removed": removed,
        "modules_common": common,
    }


def _compute_centrality_shifts_from_fan(
    old_modules: List[str],
    new_modules: List[str],
    old_fan: Dict[str, Tuple[int, int]],
    new_fan: Dict[str, Tuple[int, int]],
) -> List[Dict[str, object]]:
    common = set(old_modules) & set(new_modules)
    shifts: List[Dict[str, object]] = []
    for m in sorted(common):
        ofi, ofo = old_fan.get(m, (0, 0))
        nfi, nfo = new_fan.get(m, (0, 0))
        if (ofi, ofo) != (nfi, nfo):
            shifts.append(
                {"module": m, "fan_in": (ofi, nfi), "fan_out": (ofo, nfo)}
            )
    return shifts


def _compute_smell_diff_from_smells(
    old_smells: List[ArchSmell], new_smells: List[ArchSmell]
) -> List[Dict[str, object]]:
    old_sm = _smell_counts(old_smells)
    new_sm = _smell_counts(new_smells)
    smell_types = sorted(set(old_sm) | set(new_sm))
    return [
        {"type": t, "old": old_sm.get(t, 0), "new": new_sm.get(t, 0)}
        for t in smell_types
    ]


def _compute_structural_diff(old: ArchSnapshot, new: ArchSnapshot) -> Dict[str, List[str]]:
    return _compute_structural_diff_from_modules(old.modules, new.modules)


def _compute_centrality_shifts(old: ArchSnapshot, new: ArchSnapshot) -> List[Dict[str, object]]:
    old_fan = ProjectGraph.from_self_map(load_self_map(old.path)).fan_in_out()
    new_fan = ProjectGraph.from_self_map(load_self_map(new.path)).fan_in_out()
    return _compute_centrality_shifts_from_fan(
        old.modules, new.modules, old_fan, new_fan
    )


def _compute_smell_diff(old: ArchSnapshot, new: ArchSnapshot) -> List[Dict[str, object]]:
    return _compute_smell_diff_from_smells(old.smells, new.smells)


def _index_smells_by_module(smells: List[ArchSmell]) -> Dict[str, Dict[str, float]]:
    """
    Build mapping: module -> {smell_type: max_severity}.

    For multi-node smells (cycles) each node gets the smell type.
    """
    index: Dict[str, Dict[str, float]] = {}
    for s in smells:
        for node in s.nodes:
            by_type = index.setdefault(node, {})
            prev = by_type.get(s.type, 0.0)
            if s.severity > prev:
                by_type[s.type] = float(s.severity)
    return index


def _modules_became_bottlenecks(
    old_smells: List[ArchSmell], new_smells: List[ArchSmell]
) -> List[str]:
    """
    Modules that became bottlenecks between old and new snapshots (v0.8+).

    A module is considered "became bottleneck" if it has a bottleneck smell
    in new_smells and did not have one in old_smells.
    """
    if not new_smells:
        return []
    old_index = _index_smells_by_module(old_smells)
    new_index = _index_smells_by_module(new_smells)
    modules: List[str] = []
    for module, types in new_index.items():
        if "bottleneck" in types and "bottleneck" not in old_index.get(module, {}):
            modules.append(module)
    return sorted(modules)


def _build_recommended_actions(
    old_smells: List[ArchSmell],
    new_smells: List[ArchSmell],
    shifts: List[Dict[str, object]],
    max_actions: int = 5,
) -> List[str]:
    """
    Heuristic recommended actions for diff report (v0.8+).

    Combines:
    - modules whose smell severity increased or newly appeared;
    - fan-in / fan-out growth from centrality_shifts.
    """
    if not new_smells:
        return []

    old_index = _index_smells_by_module(old_smells)
    new_index = _index_smells_by_module(new_smells)
    shift_index: Dict[str, Tuple[int, int, int, int]] = {}
    for s in shifts:
        m = s["module"]
        ofi, nfi = s["fan_in"]
        ofo, nfo = s["fan_out"]
        shift_index[m] = (int(ofi), int(nfi), int(ofo), int(nfo))

    ACTION_LABELS: Dict[str, str] = {
        "god_module": "refactor/split module",
        "bottleneck": "reduce bottleneck (add facade or redistribute calls)",
        "hub": "split hub into smaller dispatchers",
        "cyclic_dependency": "break dependency cycle",
    }

    candidates: List[Tuple[float, str, str, float, Tuple[int, int, int, int]]] = []

    modules = set(new_index.keys()) | set(shift_index.keys())
    for m in modules:
        new_types = new_index.get(m, {})
        if not new_types:
            continue
        old_types = old_index.get(m, {})
        # Choose strongest smell type by new severity
        t_best = max(new_types.items(), key=lambda kv: kv[1])[0]
        new_sev = new_types[t_best]
        old_sev = old_types.get(t_best, 0.0)
        delta_sev = max(0.0, new_sev - old_sev)

        ofi, nfi, ofo, nfo = shift_index.get(m, (0, 0, 0, 0))
        delta_in = max(0, nfi - ofi)
        delta_out = max(0, nfo - ofo)
        central_boost = max(delta_in, delta_out)

        # Score: new severity + growth in severity + centrality growth
        score = new_sev + delta_sev + central_boost
        if score <= 0:
            continue

        candidates.append((score, m, t_best, new_sev, (ofi, nfi, ofo, nfo)))

    if not candidates:
        return []

    candidates.sort(reverse=True, key=lambda x: x[0])
    actions: List[str] = []
    for _, module, smell_type, severity, (ofi, nfi, ofo, nfo) in candidates[:max_actions]:
        label = ACTION_LABELS.get(smell_type, "address structural risk")
        level = severity_to_level(severity)
        hint = get_remediation_hint(smell_type)
        if (ofi, ofo) == (0, 0) and (nfi, nfo) == (0, 0):
            actions.append(
                f"- {module}: {label} ({smell_type}, {level}, severity={severity:.2f}). Hint: {hint}"
            )
        else:
            actions.append(
                f"- {module}: {label} ({smell_type}, {level}, severity={severity:.2f}; "
                f"fan-in {ofi} → {nfi}, fan-out {ofo} → {nfo}). Hint: {hint}"
            )
    return actions


def diff_to_text(diff: Dict) -> str:
    lines: List[str] = []
    structures = diff["structures"]
    shifts = diff["centrality_shifts"]
    smells = diff["smells"]
    maturity = diff["maturity"]
    recommended = diff.get("recommended_actions") or []
    bottlenecks = diff.get("bottleneck_modules") or []

    lines.append("ARCHITECTURE EVOLUTION REPORT")
    lines.append("")

    _append_structural_changes(lines, structures)
    _append_centrality_shifts(lines, shifts)
    _append_top_fan_in_growth(lines, shifts)
    _append_became_bottlenecks(lines, bottlenecks)
    _append_smell_dynamics(lines, smells)
    _append_maturity_trajectory(lines, maturity)
    _append_recommended_actions(lines, recommended)

    return "\n".join(lines)


def _append_structural_changes(lines: List[str], structures: Dict[str, List[str]]) -> None:
    lines.append("1. Structural changes")
    lines.append(f"+ modules added: {len(structures['modules_added'])}")
    for m in structures["modules_added"]:
        lines.append(f"  + {m}")
    lines.append(f"- modules removed: {len(structures['modules_removed'])}")
    for m in structures["modules_removed"]:
        lines.append(f"  - {m}")
    lines.append(f"~ modules unchanged: {len(structures['modules_common'])}")
    lines.append("")


def _append_centrality_shifts(lines: List[str], shifts: List[Dict[str, object]]) -> None:
    lines.append("2. Centrality shifts")
    if not shifts:
        lines.append("  (no significant centrality changes)")
    else:
        for s in shifts[:10]:
            m = s["module"]
            ofi, nfi = s["fan_in"]
            ofo, nfo = s["fan_out"]
            lines.append(
                f"- {m}: fan-in {ofi} → {nfi}, fan-out {ofo} → {nfo}"
            )
    lines.append("")


def _append_top_fan_in_growth(lines: List[str], shifts: List[Dict[str, object]], top_n: int = 3) -> None:
    """
    Highlight top modules by fan-in growth (v0.8+).
    Uses centrality_shifts as input.
    """
    lines.append("2.a Top modules by fan-in growth")
    if not shifts:
        lines.append("  (no fan-in growth detected)")
        lines.append("")
        return

    # Compute Δ fan-in for each module and take top N with positive growth.
    deltas: List[Tuple[int, str, Tuple[int, int]]] = []
    for s in shifts:
        m = s["module"]
        ofi, nfi = s["fan_in"]
        delta = int(nfi) - int(ofi)
        if delta > 0:
            deltas.append((delta, m, (ofi, nfi)))

    if not deltas:
        lines.append("  (no positive fan-in growth)")
        lines.append("")
        return

    deltas.sort(reverse=True, key=lambda x: x[0])
    for delta, module, (ofi, nfi) in deltas[:top_n]:
        lines.append(f"- {module}: fan-in {ofi} → {nfi} (Δ {delta})")
    lines.append("")


def _append_became_bottlenecks(lines: List[str], modules: List[str]) -> None:
    """
    Print modules that became bottlenecks between old and new snapshots.
    """
    lines.append("2.b Modules that became bottlenecks")
    if not modules:
        lines.append("  (no new bottlenecks detected)")
        lines.append("")
        return
    for m in modules:
        lines.append(f"- {m}")
    lines.append("")


def _append_smell_dynamics(lines: List[str], smells: List[Dict[str, object]]) -> None:
    lines.append("3. Smell dynamics")
    if not smells:
        lines.append("  (no smells in either snapshot)")
    else:
        for s in smells:
            lines.append(
                f"- {s['type']}: {s['old']} → {s['new']}"
            )
    lines.append("")


def _append_maturity_trajectory(lines: List[str], maturity: Dict[str, str]) -> None:
    lines.append("4. Maturity trajectory")
    old = maturity.get("old", "unknown")
    new = maturity.get("new", "unknown")
    lines.append(f"- maturity: {old} → {new}")

    order = {
        "insufficient_data": 0,
        "low": 1,
        "medium": 2,
        "medium-high": 3,
        "high": 4,
    }
    if order.get(new, 0) < order.get(old, 0):
        lines.append("  Warning: maturity degraded over the observed window.")


def _append_recommended_actions(lines: List[str], actions: List[str]) -> None:
    lines.append("")
    lines.append("5. Recommended actions")
    if not actions:
        lines.append("  (no specific recommended actions; review smells and centrality manually)")
    else:
        lines.extend(actions)


def main_cli(old_path: str, new_path: str) -> None:
    """
    CLI helper:
      python architecture_diff.py self_map_old.json self_map_new.json
    """
    old = build_snapshot(Path(old_path))
    new = build_snapshot(Path(new_path))
    diff = diff_snapshots(old, new)
    print(diff_to_text(diff))


# TODO (eurika): refactor long_function '_build_recommended_actions' — consider extracting helper
