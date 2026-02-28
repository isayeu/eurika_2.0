"""
Architecture Smells v0.1 — data model and detection.

Implementation moved from architecture_smells.py (v0.9 migration).
Turns ProjectGraph into architectural diagnostics (syntactic architecture / imports).
"""

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Dict, List

from eurika.analysis.graph import ProjectGraph


@dataclass
class ArchSmell:
    type: str
    nodes: List[str]
    severity: float
    description: str


def _degree_stats(degrees: Dict[str, int]) -> tuple[float, float]:
    values = list(degrees.values())
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return float(values[0]), 0.0
    return float(mean(values)), float(pstdev(values))


def detect_cycle_smells(graph: ProjectGraph) -> List[ArchSmell]:
    fan = graph.fan_in_out()
    cycles = graph.find_cycles()
    smells: List[ArchSmell] = []
    for cycle in cycles:
        if not cycle:
            continue
        fan_ins = [fan.get(n, (0, 0))[0] for n in cycle]
        avg_fan_in = sum(fan_ins) / len(fan_ins) if fan_ins else 0.0
        severity = len(cycle) * (1.0 + avg_fan_in)
        smells.append(
            ArchSmell(
                type="cyclic_dependency",
                nodes=cycle,
                severity=severity,
                description=f"Cycle of length {len(cycle)} with avg fan-in {avg_fan_in:.2f}",
            )
        )
    return smells


def detect_god_modules(graph: ProjectGraph) -> List[ArchSmell]:
    fan = graph.fan_in_out()
    degree = {n: fan[n][0] + fan[n][1] for n in graph.nodes}
    mu, sigma = _degree_stats(degree)
    if sigma == 0:
        return []
    threshold = mu + 2 * sigma
    smells: List[ArchSmell] = []
    for n, d in degree.items():
        if n.endswith("_api.py"):
            continue
        if d > threshold:
            smells.append(
                ArchSmell(
                    type="god_module",
                    nodes=[n],
                    severity=float(d),
                    description=f"High total degree {d} (fan-in + fan-out), threshold {threshold:.2f}",
                )
            )
    return smells


def detect_bottlenecks(graph: ProjectGraph) -> List[ArchSmell]:
    fan = graph.fan_in_out()
    fan_in = {n: v[0] for n, v in fan.items()}
    mu_in, sigma_in = _degree_stats(fan_in)
    smells: List[ArchSmell] = []
    for n in graph.nodes:
        if n.endswith("_api.py"):
            continue
        fi, fo = fan[n]
        if fi >= max(3, mu_in + 2 * sigma_in) and fo <= 1:
            severity = float(fi)
            smells.append(
                ArchSmell(
                    type="bottleneck",
                    nodes=[n],
                    severity=severity,
                    description=f"High fan-in {fi} with low fan-out {fo}",
                )
            )
    return smells


def detect_hubs(graph: ProjectGraph) -> List[ArchSmell]:
    fan = graph.fan_in_out()
    fan_out = {n: v[1] for n, v in fan.items()}
    mu_out, sigma_out = _degree_stats(fan_out)
    smells: List[ArchSmell] = []
    for n in graph.nodes:
        fi, fo = fan[n]
        if fo >= max(3, mu_out + 2 * sigma_out) and fi <= 1:
            severity = float(fo)
            smells.append(
                ArchSmell(
                    type="hub",
                    nodes=[n],
                    severity=severity,
                    description=f"High fan-out {fo} with low fan-in {fi}",
                )
            )
    return smells


def detect_smells(graph: ProjectGraph) -> List[ArchSmell]:
    """
    High-level API.
    v0.1: syntactic architecture (imports), heuristic thresholds.
    """
    smells: List[ArchSmell] = []
    smells.extend(detect_cycle_smells(graph))
    smells.extend(detect_god_modules(graph))
    smells.extend(detect_bottlenecks(graph))
    smells.extend(detect_hubs(graph))
    smells.sort(key=lambda s: s.severity, reverse=True)
    return smells
