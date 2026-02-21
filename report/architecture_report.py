"""Architecture report presentation (ROADMAP 3.1-arch.4).

Domain vs presentation: rendering only. Takes ArchitectureSnapshot, returns formatted string.
Domain logic (run_full_analysis, build_snapshot) stays in core/pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List

from eurika.smells.detector import ArchSmell, get_remediation_hint, severity_to_level
from eurika.smells.rules import build_recommendations, compute_health, summary_to_text
from eurika.reporting.text import health_summary_enhanced

from eurika.analysis.topology import central_modules_for_topology
from eurika.analysis.scanner import semantic_summary
from eurika.analysis.topology import topology_summary


def _smells_to_text(smells: List[ArchSmell], top_n: int = 5) -> str:
    """Format architecture smells as plain text."""
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


def _render_health_section_md(health: Dict[str, Any]) -> str:
    """Format Health section as markdown."""
    lines = [
        "## Health",
        "",
        f"**Score:** {health['score']}/100 ({health['level']})",
        "",
    ]
    factors = health.get("factors") or []
    if factors:
        for f in factors:
            lines.append(f"- {f}")
    else:
        lines.append("- no significant structural risks detected")
    lines.append("")
    return "\n".join(lines)


def render_full_architecture_report(
    snapshot: Any,
    *,
    top_smells: int = 5,
    top_recs: int = 10,
    format: str = "text",
    use_color: bool = False,
) -> str:
    """Render the full architecture report from a snapshot (presentation only)."""
    if format == "markdown":
        return _render_architecture_report_md(snapshot, top_smells, top_recs)

    parts: List[str] = []

    smells_text = _smells_to_text(snapshot.smells, top_n=top_smells)
    if smells_text:
        parts.append("\n" + smells_text)

    parts.append("\n" + summary_to_text(snapshot.summary))
    parts.append("\n" + semantic_summary(snapshot.graph))

    centers = central_modules_for_topology(snapshot.graph)
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
    snapshot: Any,
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
            parts.append(
                f"- **[{s.type}]** ({level}) severity={s.severity:.2f} in `{where}` — {s.description}"
            )
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

    centers = central_modules_for_topology(snapshot.graph)
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
    parts.append(_render_health_section_md(health))

    return "\n".join(parts)
