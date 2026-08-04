"""Architecture smell detection (diagnostics layer).

Implementation moved from architecture_diagnostics.py (v0.9 migration).
Exposes ArchSmell, detect_architecture_smells, severity_to_level, remediation hints.
"""

from __future__ import annotations

from typing import Dict, List

from eurika.analysis.graph import ProjectGraph
from eurika.smells.models import ArchSmell, detect_smells

__all__ = [
    "ArchSmell",
    "detect_architecture_smells",
    "severity_to_level",
    "get_remediation_hint",
    "REMEDIATION_HINTS",
]


def detect_architecture_smells(graph: ProjectGraph) -> List[ArchSmell]:
    """High-level smell detection API."""
    return detect_smells(graph)


def severity_to_level(severity: float) -> str:
    """Map numeric severity to qualitative level (v0.8)."""
    if severity < 5:
        return "low"
    if severity < 12:
        return "medium"
    if severity < 20:
        return "high"
    return "critical"


REMEDIATION_HINTS: Dict[str, str] = {
    "god_class": "Extract methods that don't use self into a new class (extract_class).",
    "god_module": "Consider splitting into smaller modules; extract coherent sub-responsibilities.",
    "bottleneck": "Introduce facade or adapter to distribute dependents; avoid single point of failure.",
    "hub": "Extract coherent sub-graphs; consider splitting by domain or layer.",
    "cyclic_dependency": "Break the cycle: invert dependency, introduce abstraction layer, or extract shared code.",
    "long_function": "Extract nested def to module level, or extract if/for/while body to helper; max 3 params.",
    "deep_nesting": "Extract innermost block to helper; pass closure vars as args; flatten step-by-step.",
}


def get_remediation_hint(smell_type: str) -> str:
    """Return remediation hint for smell type (v0.8)."""
    return REMEDIATION_HINTS.get(smell_type, "Review module structure and dependencies.")
