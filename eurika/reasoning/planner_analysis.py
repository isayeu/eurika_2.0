"""Analysis helpers for architecture planning."""

from __future__ import annotations

from typing import Any, Dict, List

from eurika.smells.detector import ArchSmell
from eurika.reasoning.planner_types import PlanStep


def index_smells_by_node(smells: List[ArchSmell]) -> Dict[str, List[ArchSmell]]:
    """Build mapping node -> list[ArchSmell]."""
    smells_by_node: Dict[str, List[ArchSmell]] = {}
    for smell in smells:
        for node in smell.nodes:
            smells_by_node.setdefault(node, []).append(smell)
    return smells_by_node


def build_steps_from_priorities(
    priorities: List[Dict[str, Any]],
    smells_by_node: Dict[str, List[ArchSmell]],
    top_n: int = 5,
) -> List[PlanStep]:
    """Generate plan steps from prioritized modules and smells index."""
    steps: List[PlanStep] = []
    counter = 1
    for idx, priority_item in enumerate(priorities[:top_n], start=1):
        name = priority_item.get("name") or priority_item.get("module") or ""
        if not name:
            continue
        node_smells = smells_by_node.get(name, [])
        if not node_smells:
            continue
        step = _build_step_for_module(name, node_smells, idx, counter)
        steps.append(step)
        counter += 1
    return steps


def _decide_step_kind(node_smells: List[ArchSmell]) -> str:
    """Choose plan step kind from smell types."""
    from eurika.reasoning.graph_ops import refactor_kind_for_smells

    types = [smell.type for smell in node_smells]
    return refactor_kind_for_smells(types)


def _build_step_for_module(
    name: str,
    node_smells: List[ArchSmell],
    priority_idx: int,
    counter: int,
) -> PlanStep:
    """Create a single PlanStep for a module."""
    kind = _decide_step_kind(node_smells)
    smell_descriptions = [f"{smell.type} (severity={smell.severity:.2f})" for smell in node_smells]
    rationale = f"Module {name} is prioritized due to: " + ", ".join(smell_descriptions)
    hints: List[str] = []
    if kind == "split_module":
        hints.append("Extract coherent sub-responsibilities into separate modules.")
    if kind == "introduce_facade":
        hints.append("Introduce a facade or boundary to reduce direct fan-in.")
    if kind == "split_responsibility":
        hints.append("Split outgoing dependencies across clearer layers or services.")
    if kind == "break_cycle":
        hints.append("Break import cycles via inversion of dependencies or adapters.")
    smell_type = max(node_smells, key=lambda smell: smell.severity).type if node_smells else None
    return PlanStep(
        id=f"STEP-{counter:03d}",
        target=name,
        kind=kind,
        priority=priority_idx,
        rationale=rationale,
        hints=hints,
        smell_type=smell_type,
    )
