"""R1 Domain vs Presentation: format ArchitectResult for doctor/CLI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_SMELL_HOW_MAP: Dict[str, str] = {
    "god_module": "Split into focused modules by responsibility (e.g. core, analysis, reporting, CLI).",
    "bottleneck": "Introduce a facade so dependents use a stable interface instead of the concrete implementation.",
    "hub": "Decompose and split responsibilities; extract sub-modules.",
    "cyclic_dependency": "Break the cycle via dependency inversion or an abstraction layer that both sides depend on.",
}
_SMELL_REF_SUFFIX: str = " See Reference block for documentation."


def _parse_smell_from_risk(risk: str) -> Optional[str]:
    if not risk or not isinstance(risk, str):
        return None
    parts = risk.strip().split()
    if not parts:
        return None
    first = parts[0].lower()
    return first if first in _SMELL_HOW_MAP else None


def format_architect_template(data: Dict[str, Any]) -> str:
    """
    Presentation: format structured architect data to text (R1).
    data: from get_architect_data().
    """
    structure = data.get("structure") or {}
    modules = structure.get("modules", 0)
    deps = structure.get("dependencies", 0)
    cycles = structure.get("cycles", 0)
    maturity = data.get("maturity", "unknown")
    risks = data.get("risks") or []
    central = data.get("central_modules") or []
    trends = data.get("trends") or {}
    patch_plan = data.get("patch_plan")
    knowledge_snippet = data.get("knowledge_snippet", "")
    recent_snippet = data.get("recent_events_snippet", "")

    parts: List[str] = []
    if cycles == 0:
        parts.append(f"The codebase has {modules} modules and {deps} dependencies with no cycles.")
    else:
        parts.append(f"The codebase has {modules} modules, {deps} dependencies and {cycles} cycles.")
    parts.append(f"Syntactic maturity is {maturity}.")

    if risks:
        top = risks[:3]
        risk_str = "; ".join(top) if len(top) <= 2 else top[0] + " and " + str(len(risks) - 1) + " more"
        parts.append(f"Main risks: {risk_str}.")
    elif central:
        names = [c.get("name", "") for c in central[:3] if isinstance(c, dict)]
        parts.append(f"Central modules: {', '.join(names)}.")

    trend_complexity = trends.get("complexity", "unknown")
    trend_smells = trends.get("smells", "unknown")
    if trend_complexity != "unknown" or trend_smells != "unknown":
        parts.append(f"Trends: complexity {trend_complexity}, smells {trend_smells}.")
    regressions = data.get("regressions") or []
    if regressions:
        parts.append(f"Potential regressions: {'; '.join(regressions[:2])}.")

    if patch_plan and patch_plan.get("operations"):
        ops = patch_plan["operations"]
        total = len(ops)
        kind_counts: Dict[str, int] = {}
        for o in ops:
            k = o.get("kind", "refactor")
            kind_counts[k] = kind_counts.get(k, 0) + 1
        targets = list({o.get("target_file", "") for o in ops if o.get("target_file")})[:5]
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(kind_counts.items()))
        parts.append(f"Planned refactorings: {total} ops ({kinds}); top targets: {', '.join(targets[:3])}.")
    if recent_snippet:
        parts.append(f"Recent actions: {recent_snippet}.")

    out = " ".join(parts)

    # Recommendation block
    seen: set[str] = set()
    rec_lines: List[str] = []
    for r in risks[:5]:
        smell = _parse_smell_from_risk(r)
        if not smell or smell in seen:
            continue
        seen.add(smell)
        how = _SMELL_HOW_MAP.get(smell)
        if how:
            rec_lines.append(f"- {smell}: {how}")
    if rec_lines:
        ref_note = _SMELL_REF_SUFFIX if knowledge_snippet else ""
        out += "\n\nRecommendation (how to fix):\n" + "\n".join(rec_lines) + ref_note

    # Reference block
    if knowledge_snippet and knowledge_snippet.strip():
        snip = knowledge_snippet.strip()[:800]
        if len(knowledge_snippet.strip()) > 800:
            snip += "..."
        out += "\n\nReference (from documentation):\n" + snip

    return out
