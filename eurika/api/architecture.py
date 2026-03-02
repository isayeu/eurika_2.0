"""Architecture API routes: graph, summary, smells, self-guard (R1 public API facade)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def get_graph(project_root: Path) -> Dict[str, Any]:
    """
    Build dependency graph for UI (ROADMAP 3.5.7).
    Returns { nodes, edges } for vis-network format.
    nodes: [{ id, label, title, fan_in, fan_out }]
    edges: [{ from, to }]
    """
    from eurika.analysis.self_map import build_graph_from_self_map

    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return {"error": "self_map.json not found", "path": str(self_map_path)}
    graph = build_graph_from_self_map(self_map_path)
    fan = graph.fan_in_out()
    nodes = []
    for n in sorted(graph.nodes):
        fi, fo = fan.get(n, (0, 0))
        short = Path(n).name if "/" in n else n
        nodes.append(
            {"id": n, "label": short, "title": n + f" (fan-in: {fi}, fan-out: {fo})", "fan_in": fi, "fan_out": fo}
        )
    edges = []
    for src, dsts in graph.edges.items():
        for dst in dsts:
            edges.append({"from": src, "to": dst})
    return {"nodes": nodes, "edges": edges}


def get_summary(
    project_root: Path,
    *,
    include_plugins: bool = False,
) -> Dict[str, Any]:
    """
    Build architecture summary from project_root/self_map.json.
    Returns dict with keys: system, central_modules, risks, maturity.
    If self_map.json is missing, returns {"error": "...", "path": "..."}.
    R5: include_plugins=True merges plugin smells into summary.
    """
    from eurika.analysis.self_map import build_graph_from_self_map
    from eurika.smells.rules import build_summary

    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return {"error": "self_map.json not found", "path": str(self_map_path)}
    graph = build_graph_from_self_map(self_map_path)
    if include_plugins:
        from eurika.plugins import detect_smells_with_plugins, merge_smells_for_report

        eurika_smells, plugin_results = detect_smells_with_plugins(root, include_plugins=True)
        smells = merge_smells_for_report(eurika_smells, plugin_results)
        summary = build_summary(graph, smells)
        summary["_plugin_counts"] = [{"plugin": pid, "count": len(s)} for pid, s in plugin_results]
    else:
        from eurika.smells.detector import detect_architecture_smells

        smells = detect_architecture_smells(graph)
        summary = build_summary(graph, smells)
    return summary


def get_risk_prediction(project_root: Path, top_n: int = 10) -> Dict[str, Any]:
    """R5 2.1: Top modules by regression risk (smells + centrality + trends)."""
    from eurika.reasoning.risk_prediction import predict_module_regression_risk

    root = Path(project_root).resolve()
    predictions = predict_module_regression_risk(root, top_n=top_n)
    return {"predictions": predictions}


def get_smells_with_plugins(
    project_root: Path,
    *,
    include_plugins: bool = True,
) -> Dict[str, Any]:
    """R5 3.3: Eurika smells + plugin smells for unified report."""
    from eurika.plugins import detect_smells_with_plugins, merge_smells_for_report

    root = Path(project_root).resolve()
    eurika, plugin_results = detect_smells_with_plugins(root, include_plugins=include_plugins)
    merged = merge_smells_for_report(eurika, plugin_results)
    return {
        "eurika_smells": [
            {"type": s.type, "nodes": s.nodes, "severity": s.severity, "description": s.description}
            for s in eurika
        ],
        "plugin_smells": [{"plugin": pid, "count": len(smells)} for pid, smells in plugin_results],
        "merged": [
            {"type": s.type, "nodes": s.nodes, "severity": s.severity, "description": s.description}
            for s in merged
        ],
    }


def get_self_guard(project_root: Path) -> Dict[str, Any]:
    """R5: SELF-GUARD aggregated health gate for GUI/API."""
    from eurika.checks.self_guard import collect_self_guard

    root = Path(project_root).resolve()
    result = collect_self_guard(root)
    return {
        "forbidden_count": result.forbidden_count,
        "layer_viol_count": result.layer_viol_count,
        "subsystem_bypass_count": result.subsystem_bypass_count,
        "must_split_count": result.must_split_count,
        "candidates_count": result.candidates_count,
        "trend_alarms": result.trend_alarms,
        "complexity_budget_alarms": result.complexity_budget_alarms,
        "pass": (
            result.forbidden_count == 0
            and result.layer_viol_count == 0
            and result.subsystem_bypass_count == 0
            and result.must_split_count == 0
        ),
    }


def get_firewall_violations_detail(project_root: Path) -> Dict[str, Any]:
    """CR-A3: Dependency firewall violations for GUI (forbidden, layer, subsystem bypass)."""
    from eurika.checks.dependency_firewall import (
        collect_dependency_violations,
        collect_layer_violations,
        collect_subsystem_bypass_violations,
    )

    root = Path(project_root).resolve()
    forbidden = collect_dependency_violations(root)
    layer = collect_layer_violations(root)
    bypass = collect_subsystem_bypass_violations(root)
    return {
        "forbidden": [{"path": v.path, "forbidden_module": v.forbidden_module} for v in forbidden],
        "layer_violations": [
            {"path": v.path, "imported_module": v.imported_module, "source_layer": v.source_layer, "target_layer": v.target_layer}
            for v in layer
        ],
        "subsystem_bypass": [{"path": v.path, "imported_module": v.imported_module} for v in bypass],
    }
