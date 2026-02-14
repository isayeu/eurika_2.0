"""
Semantic Architecture v0.3 (draft)

Assigns simple semantic roles to modules and detects basic layer violations.

Roles (heuristic, project-specific for Eurika v0.3):
- "orchestration"  — CLI / AgentCore wiring, high-level flows
- "analytics"      — analysis / metrics / smells / planners
- "infrastructure" — IO, storage, history, feedback
- "tests"          — test modules
- "other"          — everything else

This is intentionally minimal and heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from project_graph_api import ProjectGraph


SemanticRole = str


@dataclass
class SemanticModuleInfo:
    name: str
    role: SemanticRole


def classify_modules(graph: ProjectGraph) -> Dict[str, SemanticModuleInfo]:
    """Assign a semantic role to each module based on simple heuristics."""
    result: Dict[str, SemanticModuleInfo] = {}
    for name in graph.nodes:
        result[name] = SemanticModuleInfo(name=name, role=_infer_role(name))
    return result


def _infer_role(name: str) -> SemanticRole:
    """Infer semantic role from module name."""
    lower = name.lower()

    if lower.startswith("tests/") or lower.startswith("test_") or "/tests/" in lower:
        return "tests"

    if "cli" in lower or "agent_core" in lower or "agent" in lower:
        return "orchestration"

    if any(
        key in lower
        for key in ("architecture_", "project_graph", "graph_analysis", "code_awareness", "planner")
    ):
        return "analytics"

    if any(
        key in lower
        for key in ("memory", "history", "feedback", "self_map", "io", "observation")
    ):
        return "infrastructure"

    return "other"


def detect_layer_violations(
    graph: ProjectGraph, roles: Dict[str, SemanticModuleInfo]
) -> List[Tuple[str, str, str, str]]:
    """
    Detect simple semantic layer violations.

    Returns list of (src, src_role, dst, dst_role) for suspicious edges.

    Heuristic rules:
    - "tests" should not be depended on by non-tests.
    - "infrastructure" should not depend on "orchestration" or "analytics".
    - "analytics" should not depend on "orchestration".
    """
    violations: List[Tuple[str, str, str, str]] = []

    for src, dsts in graph.edges.items():
        src_role = roles.get(src, SemanticModuleInfo(src, "other")).role
        for dst in dsts:
            dst_role = roles.get(dst, SemanticModuleInfo(dst, "other")).role

            # tests should be leafs from non-test perspective
            if dst_role == "tests" and src_role != "tests":
                violations.append((src, src_role, dst, dst_role))

            # infra should not depend on higher-level orchestration/analytics
            if src_role == "infrastructure" and dst_role in {"orchestration", "analytics"}:
                violations.append((src, src_role, dst, dst_role))

            # analytics should not depend on orchestration
            if src_role == "analytics" and dst_role == "orchestration":
                violations.append((src, src_role, dst, dst_role))

    return violations


def semantic_summary(graph: ProjectGraph) -> str:
    """Produce a small human-readable summary of semantic roles and violations."""
    roles = classify_modules(graph)
    violations = detect_layer_violations(graph, roles)

    counts: Dict[SemanticRole, int] = {}
    for info in roles.values():
        counts[info.role] = counts.get(info.role, 0) + 1

    lines: List[str] = []
    lines.append("SEMANTIC ARCHITECTURE (heuristic)")
    lines.append("")
    lines.append("Roles distribution:")
    for role in sorted(counts.keys()):
        lines.append(f"- {role}: {counts[role]} modules")

    lines.append("")
    lines.append("Potential layer violations:")
    if not violations:
        lines.append("- none detected (under current heuristics)")
    else:
        for src, src_role, dst, dst_role in violations[:10]:
            lines.append(f"- {src} ({src_role}) -> {dst} ({dst_role})")
        if len(violations) > 10:
            lines.append(f"- ... and {len(violations) - 10} more")

    return "\n".join(lines)

