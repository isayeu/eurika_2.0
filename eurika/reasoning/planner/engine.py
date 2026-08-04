"""
PlannerEngine: collect_facts → generate_candidates → rank → output_plan (review §2).

Planner decomposition: planner orchestrates four explicit steps.
LLM, risk, mutation — separate services called from generate_candidates/rank.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from eurika.reasoning.planner.analysis import index_smells_by_node

if TYPE_CHECKING:
    from patch_plan import PatchPlan
from eurika.reasoning.planner.patch_ops import build_patch_operations
from eurika.smells.detector import ArchSmell


def collect_facts(
    project_root: str,
    summary: Dict[str, Any],
    smells: List[Any],
    history_info: Dict[str, Any],
    priorities: List[Dict[str, Any]],
    *,
    graph: Optional[Any] = None,
    self_map: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Step 1: Gather inputs for planning (review §2).

    Returns dict with: project_root, summary, smells, history_info, priorities,
    smells_by_node, graph, self_map, oss_patterns.
    """
    smells_by_node = index_smells_by_node(smells)
    oss_patterns: Dict[str, Any] = {}
    try:
        lib_path = Path(project_root) / ".eurika" / "pattern_library.json"
        if lib_path.exists():
            from eurika.learning.pattern_library import load_pattern_library

            oss_patterns = load_pattern_library(lib_path)
    except Exception:
        pass
    return {
        "project_root": project_root,
        "summary": summary,
        "smells": smells,
        "history_info": history_info,
        "priorities": priorities,
        "smells_by_node": smells_by_node,
        "graph": graph,
        "self_map": self_map,
        "oss_patterns": oss_patterns,
    }


def generate_candidates(
    facts: Dict[str, Any],
    *,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Any]:
    """
    Step 2: Build patch operations from facts (review §2).

    Delegates to planner.patch_ops.build_patch_operations.
    """
    return build_patch_operations(
        project_root=facts["project_root"],
        summary=facts["summary"],
        smells=facts["smells"],
        priorities=facts["priorities"],
        smells_by_node=facts["smells_by_node"],
        learning_stats=learning_stats,
        graph=facts.get("graph"),
        self_map=facts.get("self_map"),
        oss_patterns=facts.get("oss_patterns"),
    )


def rank_candidates(
    candidates: List[Any],
    facts: Dict[str, Any],
) -> List[Any]:
    """
    Step 3: Rank candidates by energy/risk (review §2).

    When graph is present, uses energy_ranking.rank_operations_by_energy.
    RV8: weights_snapshot from facts — frozen weights for deterministic cycle.
    """
    graph = facts.get("graph")
    if graph is None:
        return candidates
    from eurika.reasoning.planner.energy_ranking import rank_operations_by_energy

    return rank_operations_by_energy(
        candidates,
        graph,
        facts["smells"],
        project_root=Path(facts["project_root"]),
        weights_snapshot=facts.get("weights_snapshot"),
    )


def output_plan(ranked: List[Any], project_root: str) -> PatchPlan:
    """
    Step 4: Wrap ranked operations in PatchPlan (review §2).
    """
    from patch_plan import PatchPlan

    return PatchPlan(project_root=project_root, operations=ranked)


def run_patch_plan(
    project_root: str,
    summary: Dict[str, Any],
    smells: List[ArchSmell],
    history_info: Dict[str, Any],
    priorities: List[Dict[str, Any]],
    *,
    learning_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    graph: Optional[Any] = None,
    self_map: Optional[Dict[str, Any]] = None,
    weights_snapshot: Optional[Dict[tuple[str, str], float]] = None,
) -> PatchPlan:
    """
    Full PlannerEngine pipeline: collect_facts → generate_candidates → rank → output_plan.
    RV8: weights_snapshot freezes weights for deterministic cycle.
    """
    facts = collect_facts(
        project_root, summary, smells, history_info, priorities,
        graph=graph, self_map=self_map,
    )
    if weights_snapshot is not None:
        facts["weights_snapshot"] = weights_snapshot
    candidates = generate_candidates(facts, learning_stats=learning_stats)
    ranked = rank_candidates(candidates, facts)
    return output_plan(ranked, project_root)
