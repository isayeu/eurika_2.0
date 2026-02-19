"""Core orchestration pipeline for Eurika (v0.5 skeleton).

The goal of this module is to provide a single entrypoint for
\"architecture analysis\" over a project root, returning an
ArchitectureSnapshot instead of printing directly.

Over time, CLI and higher layers should call this module instead of
wiring runtime_scan / architecture_* modules manually.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from eurika.smells.rules import build_recommendations
from eurika.smells.detector import ArchSmell, get_remediation_hint, severity_to_level
from eurika.smells.rules import compute_health
from eurika.reporting.text import health_summary_enhanced
from eurika.storage import ProjectMemory
from architecture_pipeline import (
    _build_graph_and_summary,
    _build_graph_and_summary_from_self_map,
    _central_modules_for_topology,
)
from eurika.smells.rules import summary_to_text
from eurika.analysis.scanner import CodeAwareness, semantic_summary
from eurika.analysis.topology import topology_summary

from eurika.core.snapshot import ArchitectureSnapshot


def run_full_analysis(
    path: Path,
    *,
    history_window: int = 5,
    update_artifacts: bool = True,
) -> ArchitectureSnapshot:
    """Run the full architecture-awareness pipeline and return a snapshot.

    v0.5 skeleton implementation:
    - when update_artifacts=True: ensures self_map.json is up to date, appends to history;
    - when update_artifacts=False: reads existing artifacts only (read-only mode);
    - builds graph, smells, summary using existing helpers;
    - attaches trend info and evolution report to snapshot.
    """
    root = Path(path).resolve()

    # Ensure self_map.json is present and current (or skip if read-only).
    if update_artifacts:
        analyzer = CodeAwareness(root)
        analyzer.write_self_map(root)

    # Build core diagnostics.
    graph, smells, summary = _build_graph_and_summary(root)

    # Update history (or just read) and attach a lightweight view.
    memory = ProjectMemory(root)
    history = memory.history
    if update_artifacts:
        history.append(graph, smells, summary)
    trends = history.trend(window=history_window)
    regressions = history.detect_regressions(window=history_window)
    evolution_report_text = history.evolution_report(window=history_window)
    history_info: Dict[str, Any] = {
        "trends": trends,
        "regressions": regressions,
        "evolution_report": evolution_report_text,
    }

    # Diff information is not yet wired into the snapshot; will be
    # attached in later iterations once a stable snapshot API exists.
    return ArchitectureSnapshot(
        root=root,
        graph=graph,
        smells=smells,
        summary=summary,
        history=history_info,
        diff=None,
    )


def build_snapshot_from_self_map(self_map_path: Path) -> ArchitectureSnapshot:
    """Build ArchitectureSnapshot from an existing self_map.json file (read-only).

    Used for arch-diff and rescan comparison. Does not update history or write artifacts.
    root is set to the parent directory of the self_map file.
    """
    path = Path(self_map_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"self_map not found: {path}")
    root = path.parent
    graph, smells, summary = _build_graph_and_summary_from_self_map(path)
    return ArchitectureSnapshot(
        root=root,
        graph=graph,
        smells=smells,
        summary=summary,
        history=None,
        diff=None,
    )


def _smells_to_text(smells: List[ArchSmell], top_n: int = 5) -> str:
    """Format architecture smells as plain text (v0.8: level + remediation)."""
    if not smells:
        return ""
    lines = ["Architecture Smells:"]
    for s in smells[:top_n]:
        where = ", ".join(s.nodes[:3])
        level = severity_to_level(s.severity)
        lines.append(
            f"  [{s.type}] ({level}) severity={s.severity:.2f} in {where} — {s.description}"
        )
        lines.append(f"  → {get_remediation_hint(s.type)}")
    if len(smells) > top_n:
        lines.append(f"  ... and {len(smells) - top_n} more")
    return "\n".join(lines)


def render_full_architecture_report(
    snapshot: ArchitectureSnapshot,
    *,
    top_smells: int = 5,
    top_recs: int = 10,
    format: str = "text",
    use_color: bool = False,
) -> str:
    """Render the full architecture report from a snapshot (same output as run_architecture_pipeline)."""
    if format == "markdown":
        return _render_architecture_report_md(snapshot, top_smells, top_recs)

    parts: List[str] = []

    smells_text = _smells_to_text(snapshot.smells, top_n=top_smells)
    if smells_text:
        parts.append("\n" + smells_text)

    parts.append("\n" + summary_to_text(snapshot.summary))
    parts.append("\n" + semantic_summary(snapshot.graph))

    centers = _central_modules_for_topology(snapshot.graph)
    if centers:
        parts.append("\n" + topology_summary(snapshot.graph, centers))

    recs = build_recommendations(snapshot.graph, snapshot.smells)
    if recs:
        parts.append("\nARCHITECTURE RECOMMENDATIONS\n")
        for i, r in enumerate(recs[:top_recs], start=1):
            parts.append(f"{i}. {r}")

    if snapshot.history and "evolution_report" in snapshot.history:
        parts.append("\n" + str(snapshot.history["evolution_report"]))

    trends = (snapshot.history or {}).get("trends") or {}
    health = compute_health(snapshot.summary, snapshot.smells, trends)
    health_text = health_summary_enhanced(
        health,
        use_color=use_color,
        ascii_chart=True,
    )
    parts.append("\n" + health_text)

    return "".join(parts)


def _render_architecture_report_md(
    snapshot: ArchitectureSnapshot,
    top_smells: int,
    top_recs: int,
) -> str:
    """Markdown version of architecture report."""
    parts: List[str] = ["# Architecture Report", ""]

    if snapshot.smells:
        parts.append("## Architecture Smells")
        parts.append("")
        for s in snapshot.smells[:top_smells]:
            where = ", ".join(s.nodes[:3])
            level = severity_to_level(s.severity)
            parts.append(f"- **[{s.type}]** ({level}) severity={s.severity:.2f} in `{where}` — {s.description}")
            parts.append(f"  - _→ {get_remediation_hint(s.type)}_")
        if len(snapshot.smells) > top_smells:
            parts.append(f"- ... and {len(snapshot.smells) - top_smells} more")
        parts.append("")

    parts.append("## Summary")
    parts.append("")
    parts.append(summary_to_text(snapshot.summary))
    parts.append("")
    parts.append("## Semantic View")
    parts.append("")
    parts.append(semantic_summary(snapshot.graph))
    parts.append("")

    centers = _central_modules_for_topology(snapshot.graph)
    if centers:
        parts.append("## Topology")
        parts.append("")
        parts.append(topology_summary(snapshot.graph, centers))
        parts.append("")

    recs = build_recommendations(snapshot.graph, snapshot.smells)
    if recs:
        parts.append("## Recommendations")
        parts.append("")
        for i, r in enumerate(recs[:top_recs], start=1):
            parts.append(f"{i}. {r}")
        parts.append("")

    if snapshot.history and "evolution_report" in snapshot.history:
        parts.append("## Evolution")
        parts.append("")
        parts.append(str(snapshot.history["evolution_report"]))
        parts.append("")

    trends = (snapshot.history or {}).get("trends") or {}
    health = compute_health(snapshot.summary, snapshot.smells, trends)
    parts.append("## Health")
    parts.append("")
    parts.append(f"**Score:** {health['score']}/100 ({health['level']})")
    parts.append("")
    factors = health.get("factors") or []
    if factors:
        for f in factors:
            parts.append(f"- {f}")
    else:
        parts.append("- no significant structural risks detected")
    parts.append("")

    return "\n".join(parts)


# TODO: Refactor core/pipeline.py (hub -> refactor_module)
# Suggested steps:
# - Split outgoing dependencies across clearer layers or services.
# - Introduce intermediate abstractions to decouple from concrete implementations.
# - Align with semantic roles and system topology.


# TODO (eurika): refactor long_function '_render_architecture_report_md' — consider extracting helper
