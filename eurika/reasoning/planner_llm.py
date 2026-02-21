"""
LLM hints for patch planning (ROADMAP 2.9.2).

For god_module, hub, bottleneck: optional Ollama call to suggest split points.
Result merged into patch_plan hints; fallback to graph heuristics when unavailable.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List


def _use_llm_hints() -> bool:
    """Check env to enable/disable LLM hints. Default: enabled."""
    v = os.environ.get("EURIKA_USE_LLM_HINTS", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _ollama_model() -> str:
    return os.environ.get("OLLAMA_OPENAI_MODEL", "qwen2.5-coder:7b")


def _build_planner_prompt(
    smell_type: str,
    module_name: str,
    graph_context: Dict[str, Any],
) -> str:
    """Build a compact prompt for split/facade suggestions."""
    if smell_type == "god_module":
        imp_from = graph_context.get("imports_from", [])[:5]
        imp_by = graph_context.get("imported_by", [])[:5]
        return (
            f"Module {module_name} is a god module (too many responsibilities). "
            f"It imports from: {imp_from}. Imported by: {imp_by}. "
            "In 1-3 short bullet points, suggest concrete split points or extraction targets. "
            "Example: 'Extract validation logic into module_x'; 'Group reporting in module_y'. "
            "Reply with bullet points only, no preamble."
        )
    if smell_type == "hub":
        imp_from = graph_context.get("imports_from", [])[:5]
        imp_by = graph_context.get("imported_by", [])[:5]
        return (
            f"Module {module_name} is a hub (high fan-out). It imports from: {imp_from}. Imported by: {imp_by}. "
            "In 1-3 short bullet points, suggest how to reduce fan-out or introduce abstractions. "
            "Reply with bullet points only, no preamble."
        )
    if smell_type == "bottleneck":
        callers = graph_context.get("callers", [])[:5]
        return (
            f"Module {module_name} is a bottleneck (high fan-in). Callers: {callers}. "
            "In 1-3 short bullet points, suggest facade or API boundary. "
            "Example: 'Create api.py re-exporting public symbols'. Reply with bullet points only, no preamble."
        )
    return ""


def _parse_llm_hints(text: str) -> List[str]:
    """Extract hint-like lines from LLM response. Filters noise."""
    if not text or not isinstance(text, str):
        return []
    hints: List[str] = []
    for line in text.strip().split("\n"):
        line = line.strip()
        # Drop empty, too short, or meta lines
        if not line or len(line) < 10:
            continue
        # Drop common LLM boilerplate
        if re.match(r"^(here are|sure[,.!]|certainly[,.!]|i (would|suggest|recommend))", line, re.I):
            continue
        # Unwrap bullet/number prefixes
        m = re.match(r"^[\-\*\d\.\)]+\s*", line)
        if m:
            line = line[m.end() :].strip()
        if line and len(line) >= 10 and line not in hints:
            hints.append(line[:200])  # Cap length
    return hints[:5]  # At most 5 hints


def ask_ollama_split_hints(
    smell_type: str,
    module_name: str,
    graph_context: Dict[str, Any],
) -> List[str]:
    """
    Ask Ollama for split/facade suggestions (ROADMAP 2.9.2).

    Returns list of hint strings; empty on failure or when disabled.
    Uses _call_ollama_cli from architect (CLI fallback path).
    """
    if not _use_llm_hints():
        return []
    if smell_type not in ("god_module", "hub", "bottleneck"):
        return []
    prompt = _build_planner_prompt(smell_type, module_name, graph_context)
    if not prompt:
        return []
    try:
        from eurika.reasoning.architect import _call_ollama_cli

        text, reason = _call_ollama_cli(_ollama_model(), prompt)
        if text:
            return _parse_llm_hints(text)
    except Exception:
        pass
    return []
