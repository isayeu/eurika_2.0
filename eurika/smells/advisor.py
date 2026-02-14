"""
Architecture Advisor v0.1.

Implementation moved from architecture_advisor.py (v0.9 migration).
Converts smells + graph metrics into refactoring recommendations.
"""

from __future__ import annotations

from typing import List

from eurika.analysis.graph import ProjectGraph
from eurika.smells.models import ArchSmell


def _fmt_nodes(nodes: List[str], max_n: int = 3) -> str:
    if not nodes:
        return ""
    if len(nodes) <= max_n:
        return ", ".join(nodes)
    return ", ".join(nodes[:max_n]) + f" (and {len(nodes) - max_n} more)"


def _recommend_for_hub(fan, nodes: List[str]) -> List[str]:
    recs: List[str] = []
    for n in nodes:
        fi, fo = fan.get(n, (0, 0))
        recs.append(
            f"{n}: High fan-out ({fo}) with low fan-in ({fi}). "
            "Recommendation: split this module into smaller responsibilities "
            "(e.g. separate CLI wiring, core orchestration and reporting)."
        )
    return recs


def _recommend_for_bottleneck(fan, nodes: List[str]) -> List[str]:
    recs: List[str] = []
    for n in nodes:
        fi, fo = fan.get(n, (0, 0))
        recs.append(
            f"{n}: Bottleneck risk with fan-in {fi} and fan-out {fo}. "
            "Recommendation: introduce a facade or boundary so that other "
            "modules depend on a stable interface instead of this concrete implementation."
        )
    return recs


def _recommend_for_god_module(fan, nodes: List[str]) -> List[str]:
    recs: List[str] = []
    for n in nodes:
        fi, fo = fan.get(n, (0, 0))
        recs.append(
            f"{n}: God-module candidate (fan-in {fi}, fan-out {fo}). "
            "Recommendation: identify coherent sub-responsibilities and extract them "
            "into dedicated modules (e.g. core, analysis, reporting, CLI)."
        )
    return recs


def _recommend_for_cycle(nodes: List[str]) -> List[str]:
    nodes_str = _fmt_nodes(nodes)
    return [
        f"{nodes_str}: Cyclic dependency. "
        "Recommendation: break the cycle via dependency inversion or by introducing "
        "an abstraction layer that both sides depend on."
    ]


def build_recommendations(graph: ProjectGraph, smells: List[ArchSmell]) -> List[str]:
    """
    Turn smells into short, actionable architectural recommendations.

    Principles (v0.1):
    - hub → декомпозиция, разделение ответственности
    - bottleneck → снижение fan-in, введение фасадов
    - god_module → выделение подмодулей / слоёв
    - cyclic_dependency → инверсия зависимостей / введение интерфейсов
    """
    recs: List[str] = []
    fan = graph.fan_in_out()

    handlers = {
        "hub": lambda s: _recommend_for_hub(fan, s.nodes),
        "bottleneck": lambda s: _recommend_for_bottleneck(fan, s.nodes),
        "god_module": lambda s: _recommend_for_god_module(fan, s.nodes),
        "cyclic_dependency": lambda s: _recommend_for_cycle(s.nodes),
    }

    for smell in smells:
        handler = handlers.get(smell.type)
        if not handler:
            continue
        recs.extend(handler(smell))

    seen = set()
    deduped: List[str] = []
    for r in recs:
        if r in seen:
            continue
        seen.add(r)
        deduped.append(r)
    return deduped
