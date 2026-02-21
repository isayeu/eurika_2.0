"""
System Topology v0.3 (draft)

Clusters modules into simple subsystems based on the import graph.

Heuristic:
- start from the prioritized / central modules;
- assign each other module to the closest central node (shortest path);
- produce a mapping: subsystem -> [modules...].

This is a first approximation for "system topology discovery".
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set

from project_graph_api import NodeMetrics, ProjectGraph


def central_modules_for_topology(graph: ProjectGraph, top_n: int = 3) -> List[str]:
    """Choose central modules (by degree) to act as cluster centers. ROADMAP 3.1-arch.4."""
    metrics: Dict[str, NodeMetrics] = graph.metrics()
    scored = sorted(
        metrics.values(),
        key=lambda m: (m.fan_in + m.fan_out),
        reverse=True,
    )
    return [m.name for m in scored[:top_n]]


def cluster_by_centers(graph: ProjectGraph, centers: List[str]) -> Dict[str, List[str]]:
    """
    Cluster modules around given centers using undirected BFS distance.

    Returns:
        dict: center_name -> list of module names in its cluster (including center).
    """
    undirected = _build_undirected_view(graph)
    clusters: Dict[str, List[str]] = {c: [] for c in centers}

    for node in graph.nodes:
        best_center = None
        best_dist = None

        for center in centers:
            dist = _bfs_distance(undirected, center, node, best_dist)
            if dist is None:
                continue
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_center = center

        if best_center is not None:
            clusters[best_center].append(node)

    return clusters


def _build_undirected_view(graph: ProjectGraph) -> Dict[str, Set[str]]:
    """Build undirected adjacency for distance computation."""
    undirected: Dict[str, Set[str]] = {n: set() for n in graph.nodes}
    for src, dsts in graph.edges.items():
        for dst in dsts:
            undirected[src].add(dst)
            undirected.setdefault(dst, set()).add(src)
    return undirected


def _bfs_distance(
    undirected: Dict[str, Set[str]],
    start: str,
    target: str,
    best_so_far: int | None,
) -> int | None:
    """
    Compute BFS distance between start and target.

    Stops early if distance exceeds best_so_far (when provided).
    """
    if start not in undirected:
        return None

    q = deque([(start, 0)])
    visited = {start}
    found_dist: int | None = None
    max_depth = best_so_far if best_so_far is not None else 10

    while q:
        cur, d = q.popleft()
        if cur == target:
            found_dist = d
            break
        if best_so_far is not None and d >= max_depth:
            continue
        for nxt in undirected.get(cur, ()):
            if nxt in visited:
                continue
            visited.add(nxt)
            q.append((nxt, d + 1))

    return found_dist


def topology_summary(graph: ProjectGraph, centers: List[str]) -> str:
    """Render a small text summary of system topology based on clusters."""
    clusters = cluster_by_centers(graph, centers)
    lines: List[str] = []
    lines.append("SYSTEM TOPOLOGY (heuristic clusters)")
    lines.append("")
    for center in centers:
        members = sorted(clusters.get(center, []))
        if not members:
            continue
        lines.append(f"Subsystem around {center}:")
        for m in members[:10]:
            if m == center:
                lines.append(f"  * {m} (center)")
            else:
                lines.append(f"  - {m}")
        if len(members) > 10:
            lines.append(f"  ... and {len(members) - 10} more")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

