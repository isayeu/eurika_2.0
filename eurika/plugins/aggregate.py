"""R5 3.3: Aggregate Eurika smells + plugin smells into unified report."""

from __future__ import annotations

from pathlib import Path
from typing import List

from eurika.analysis.self_map import build_graph_from_self_map
from eurika.smells.detector import ArchSmell, detect_architecture_smells
from eurika.plugins.registry import run_plugins


def detect_smells_with_plugins(
    project_root: Path,
    *,
    include_plugins: bool = True,
) -> tuple[List[ArchSmell], List[tuple[str, List[ArchSmell]]]]:
    """
    Run Eurika smell detection + all registered plugins, return combined result.

    R5 3.3: Eurika + plugins → unified smells. Plugins can add custom smell types.
    Returns (eurika_smells, [(plugin_id, plugin_smells), ...]).
    """
    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    eurika_smells: List[ArchSmell] = []
    if self_map_path.exists():
        try:
            graph = build_graph_from_self_map(self_map_path)
            eurika_smells = detect_architecture_smells(graph)
        except Exception:
            pass

    plugin_results: List[tuple[str, List[ArchSmell]]] = []
    if include_plugins:
        plugin_results = run_plugins(root)

    return (eurika_smells, plugin_results)


def merge_smells_for_report(
    eurika_smells: List[ArchSmell],
    plugin_results: List[tuple[str, List[ArchSmell]]],
) -> List[ArchSmell]:
    """
    Merge Eurika + plugin smells into single list for summary/report.

    Eurika smells first, then plugin smells (with source in description for custom types).
    """
    result: List[ArchSmell] = list(eurika_smells)
    for plugin_id, smells in plugin_results:
        for s in smells:
            desc = s.description or ""
            if plugin_id and "(plugin:" not in desc:
                desc = f"{desc} [plugin: {plugin_id}]".strip()
            result.append(
                ArchSmell(
                    type=s.type,
                    nodes=list(s.nodes),
                    severity=float(getattr(s, "severity", 0) or 0),
                    description=desc or "custom",
                )
            )
    return result
