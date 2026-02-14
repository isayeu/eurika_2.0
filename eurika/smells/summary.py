"""
Architecture Summary v0.1

Turns graph metrics + smells into a high-level system portrait.
This is still based on **syntactic** architecture (imports), not intent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from eurika.analysis.graph import ProjectGraph
from eurika.smells.detector import ArchSmell
from eurika.analysis.metrics import summarize_graph


@dataclass
class SummarySection:
    title: str
    lines: List[str]


def _central_nodes(graph: ProjectGraph, top_n: int = 3) -> List[str]:
    fan = graph.fan_in_out()
    scored = sorted(
        fan.items(),
        key=lambda kv: kv[1][0] + kv[1][1],
        reverse=True,
    )
    return [name for name, _ in scored[:top_n]]


def build_summary(graph: ProjectGraph, smells: List[ArchSmell]) -> Dict:
    """
    Structured summary for downstream use (e.g. JSON or richer reports).
    """
    g_sum = summarize_graph(graph)
    fan = graph.fan_in_out()

    central = _central_nodes(graph, top_n=3)
    cycles = g_sum.get("cycles", [])

    risk_items: List[str] = []
    for s in smells[:5]:
        where = ", ".join(s.nodes[:3])
        risk_items.append(f"{s.type} @ {where} (severity={s.severity:.2f})")

    maturity = "low"
    if g_sum["nodes"] <= 10 and not cycles:
        maturity = "medium"
    if g_sum["nodes"] <= 10 and not cycles and not any(s.type == "cyclic_dependency" for s in smells):
        maturity = "medium-high"

    return {
        "system": {
            "modules": g_sum["nodes"],
            "dependencies": g_sum["edges"],
            "cycles": len(cycles),
        },
        "central_modules": [
            {
                "name": n,
                "fan_in": fan[n][0],
                "fan_out": fan[n][1],
            }
            for n in central
        ],
        "risks": risk_items,
        "maturity": maturity,
    }


def summary_to_text(summary: Dict) -> str:
    """
    Render human-readable architecture summary.
    """
    sys = summary["system"]
    central = summary["central_modules"]
    risks = summary["risks"]
    maturity = summary["maturity"]

    lines: List[str] = []
    lines.append("ARCHITECTURE SUMMARY")
    lines.append("")
    lines.append("System:")
    lines.append(f"- Modules: {sys['modules']}, Dependencies: {sys['dependencies']}, Cycles: {sys['cycles']}")

    if central:
        lines.append("- Central modules:")
        for c in central:
            lines.append(
                f"  - {c['name']}: fan-in {c['fan_in']}, fan-out {c['fan_out']}"
            )

    if risks:
        lines.append("")
        lines.append("Risks:")
        for r in risks:
            lines.append(f"- {r}")

    lines.append("")
    lines.append(f"Overall maturity (syntactic view): {maturity}")

    # High-level verbalization
    if sys["modules"] <= 10 and not sys["cycles"]:
        lines.append(
            "The system is small, acyclic and centered around a few core modules. "
            "Main risk is over-centralization of responsibilities."
        )
    else:
        lines.append(
            "The system shows emerging complexity in its dependency structure. "
            "Consider decomposing highly connected modules and breaking cycles."
        )

    return "\n".join(lines)
