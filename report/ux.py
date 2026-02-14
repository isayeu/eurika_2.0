"""
Report UX v0.7 — colors, ASCII charts, markdown export.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional


# ANSI codes (no external deps)
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"


def _color(text: str, code: str, use_color: bool) -> str:
    return f"{code}{text}{_RESET}" if use_color else text


def should_use_color(force: Optional[bool] = None) -> bool:
    """Use color only when stdout is TTY, unless force is set."""
    if force is not None:
        return force
    return sys.stdout.isatty()


def ascii_bar(value: int, max_val: int = 100, width: int = 10) -> str:
    """Simple ASCII bar: [████░░░░░░] 40/100"""
    if max_val <= 0:
        return "[] 0"
    filled = max(0, min(width, int(width * value / max_val)))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {value}/{max_val}"


def format_observation(observation: Dict[str, Any], *, use_color: bool = False) -> str:
    """Format scan observation. use_color from should_use_color()."""
    summary = observation.get("summary", {})
    smells = observation.get("smells", [])
    structure = observation.get("structure", [])
    duplicates = observation.get("duplicates", [])

    c = lambda t, code: _color(t, code, use_color)

    lines = [
        c("--- Eurika Scan Report ---", _CYAN),
        f"Files: {summary.get('files', 0)}",
        f"Lines: {summary.get('total_lines', 0)}",
        f"Smells: {c(str(summary.get('smells_count', 0)), _YELLOW) if summary.get('smells_count') else '0'}",
        f"Duplicate blocks: {summary.get('duplicates_count', 0)}",
        "",
    ]

    if structure:
        lines.append(c("Modules:", _BOLD))
        for s in structure:
            lines.append(f"  {s['path']} ({s['lines']} lines, {len(s['functions'])} functions, {len(s['classes'])} classes)")
        lines.append("")

    if smells:
        lines.append(c("Findings:", _BOLD))
        for s in smells[:10]:
            lines.append(f"  [{c(s['kind'], _YELLOW)}] {s['file']}:{s['location']} — {s['message']}")
        if len(smells) > 10:
            lines.append(f"  {c('...', _DIM)} and {len(smells) - 10} more")
        lines.append("")

    if duplicates:
        lines.append(c("Duplicates:", _BOLD))
        for d in duplicates[:5]:
            locs = d.get("locations", [])
            places = ", ".join(f"{loc['file']}:{loc['function']}" for loc in locs[:3])
            lines.append(f"  {d['count']}x similar: {places}")
        if len(duplicates) > 5:
            lines.append(f"  {c('...', _DIM)} and {len(duplicates) - 5} more")
        lines.append("")

    lines.append(c("--- End Report ---", _DIM))
    return "\n".join(lines)


def format_observation_md(observation: Dict[str, Any]) -> str:
    """Format scan observation as Markdown."""
    summary = observation.get("summary", {})
    smells = observation.get("smells", [])
    structure = observation.get("structure", [])
    duplicates = observation.get("duplicates", [])

    lines = [
        "# Eurika Scan Report",
        "",
        f"- **Files:** {summary.get('files', 0)}",
        f"- **Lines:** {summary.get('total_lines', 0)}",
        f"- **Smells:** {summary.get('smells_count', 0)}",
        f"- **Duplicate blocks:** {summary.get('duplicates_count', 0)}",
        "",
    ]

    if structure:
        lines.append("## Modules")
        lines.append("")
        for s in structure:
            lines.append(f"- `{s['path']}` — {s['lines']} lines, {len(s['functions'])} functions, {len(s['classes'])} classes")
        lines.append("")

    if smells:
        lines.append("## Findings")
        lines.append("")
        for s in smells:
            lines.append(f"- **[{s['kind']}]** `{s['file']}`:{s['location']} — {s['message']}")
        lines.append("")

    if duplicates:
        lines.append("## Duplicates")
        lines.append("")
        for d in duplicates:
            locs = d.get("locations", [])
            places = ", ".join(f"`{loc['file']}`:{loc['function']}" for loc in locs[:3])
            lines.append(f"- {d['count']}x similar: {places}")
        lines.append("")

    return "\n".join(lines)


def health_summary_enhanced(
    health: Dict[str, Any],
    *,
    use_color: bool = False,
    ascii_chart: bool = True,
) -> str:
    """Health summary with optional ASCII bar and colors."""
    score = health.get("score", 0)
    level = health.get("level", "unknown")
    factors = health.get("factors") or []

    c = lambda t, code: _color(t, code, use_color)

    lines = ["ARCHITECTURE HEALTH", ""]

    if ascii_chart:
        bar = ascii_bar(score, 100, 10)
        level_col = _GREEN if level == "high" else _YELLOW if level == "medium" else _RED
        lines.append(f"Health score: {bar} {c(f'({level})', level_col)}")
    else:
        lines.append(f"Health score: {score} ({level})")

    lines.append("")
    lines.append("Factors:")
    if not factors:
        lines.append("- no significant structural risks detected by current heuristic")
    else:
        for f in factors:
            lines.append(f"- {f}")
    return "\n".join(lines)
