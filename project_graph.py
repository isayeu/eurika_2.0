"""
Project Graph v0.1

Builds a dependency graph for the Eurika project based on self_map.
No execution, no agents — pure static structure.

Goals:
- import graph (files → files)
- cycles detection
- basic fan-in / fan-out metrics
- rough layering (by dependency distance from leafs)

NOTE: Layering here is a heuristic based on dependency depth,
not an architectural “role” (UI / domain / infra). It is safe for
relative comparisons, but must NOT be treated as ground truth about
system layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple
import json


@dataclass
class NodeMetrics:
    name: str
    fan_in: int
    fan_out: int
    layer: int


class ProjectGraph:
    """
    Dependency graph over project files.

    Nodes are **project files** (normalized POSIX paths from self_map["modules"]).
    Edges are **project-only dependencies** (imports that resolve to project files).
    External / stdlib imports are intentionally ignored.
    """

    def __init__(self, nodes: List[str], edges: Dict[str, List[str]]):
        # normalize node names to POSIX paths
        norm_nodes = {Path(n).as_posix() for n in nodes}
        self.nodes: Set[str] = set(norm_nodes)
        # edges: src -> [dst,...] (already normalized)
        self.edges: Dict[str, List[str]] = {n: [] for n in self.nodes}
        for src, dsts in edges.items():
            src_norm = Path(src).as_posix()
            if src_norm not in self.edges:
                self.edges[src_norm] = []
            for dst in dsts:
                dst_norm = Path(dst).as_posix()
                self.edges[src_norm].append(dst_norm)
                self.nodes.add(dst_norm)
        # ensure all nodes exist as keys
        for n in list(self.nodes):
            self.edges.setdefault(n, [])

    @classmethod
    def from_self_map(cls, self_map: Dict) -> "ProjectGraph":
        modules = self_map.get("modules", [])
        deps = self_map.get("dependencies", {})

        # project files from modules section
        file_nodes = [Path(m["path"]).as_posix() for m in modules]

        # map module name (stem) -> file path, to resolve imports
        module_to_file: Dict[str, str] = {}
        for m in modules:
            p = Path(m["path"])
            module_to_file[p.stem] = p.as_posix()

        # build project-only edges: src_file -> [dst_file,...]
        proj_edges: Dict[str, List[str]] = {}
        for src_key, dst_mods in deps.items():
            src_file = Path(src_key).as_posix()
            for mod_name in dst_mods:
                # only keep dependencies that resolve to project files
                dst_file = module_to_file.get(mod_name.split(".")[0])
                if not dst_file:
                    continue
                proj_edges.setdefault(src_file, []).append(dst_file)

        return cls(file_nodes, proj_edges)

    def fan_in_out(self) -> Dict[str, Tuple[int, int]]:
        fan_out: Dict[str, int] = {n: len(self.edges.get(n, [])) for n in self.nodes}
        fan_in: Dict[str, int] = {n: 0 for n in self.nodes}
        for src, dsts in self.edges.items():
            for dst in dsts:
                if dst not in fan_in:
                    fan_in[dst] = 0
                fan_in[dst] += 1
        return {n: (fan_in.get(n, 0), fan_out.get(n, 0)) for n in self.nodes}

    def _dfs_cycles(self, node: str, visited: Set[str], stack: List[str], on_stack: Set[str], cycles: List[List[str]]):
        visited.add(node)
        stack.append(node)
        on_stack.add(node)

        for nxt in self.edges.get(node, []):
            if nxt not in visited:
                self._dfs_cycles(nxt, visited, stack, on_stack, cycles)
                continue
            if nxt in on_stack:
                self._record_cycle_from(stack, nxt, cycles)

        stack.pop()
        on_stack.remove(node)

    def _record_cycle_from(self, stack: List[str], target: str, cycles: List[List[str]]) -> None:
        """Record a cycle starting from first occurrence of target in stack, if new."""
        if target not in stack:
            return
        idx = stack.index(target)
        cycle = stack[idx:].copy()
        if cycle and cycle not in cycles:
            cycles.append(cycle)

    def find_cycles(self) -> List[List[str]]:
        visited: Set[str] = set()
        on_stack: Set[str] = set()
        stack: List[str] = []
        cycles: List[List[str]] = []

        for n in self.nodes:
            if n not in visited:
                self._dfs_cycles(n, visited, stack, on_stack, cycles)
        return cycles

    def layers(self) -> Dict[str, int]:
        """
        Rough layering:
        - Start from nodes with no outgoing edges (leafs) → layer 0
        - For other nodes: 1 + max(layer[succ]) over its successors
        Cycles: if node is in a cycle, all nodes in that cycle get the same layer
        based on successors outside the cycle.
        """
        # initial graph copy
        fan: Dict[str, Tuple[int, int]] = self.fan_in_out()
        # successors mapping
        succ = self.edges

        # start from leafs
        layer: Dict[str, int] = {}
        changed = True
        # limit iterations to avoid infinite loops on cycles
        for _ in range(len(self.nodes) * 2):
            changed = False
            for n in self.nodes:
                outs = succ.get(n, [])
                if not outs:
                    if layer.get(n, None) is None:
                        layer[n] = 0
                        changed = True
                    continue
                # if all successors have layer, assign 1 + max
                if all(s in layer for s in outs):
                    new_l = 1 + max(layer[s] for s in outs)
                    if layer.get(n) != new_l:
                        layer[n] = new_l
                        changed = True
            if not changed:
                break
        # unresolved (cycles with all internal edges) → max layer or 0
        default_layer = max(layer.values()) if layer else 0
        for n in self.nodes:
            layer.setdefault(n, default_layer)
        return layer

    def metrics(self) -> Dict[str, NodeMetrics]:
        fan = self.fan_in_out()
        layers = self.layers()
        return {
            n: NodeMetrics(name=n, fan_in=fan[n][0], fan_out=fan[n][1], layer=layers[n])
            for n in self.nodes
        }

