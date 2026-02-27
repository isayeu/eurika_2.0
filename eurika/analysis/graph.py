"""Project graph model exported from package namespace.

This module intentionally keeps a local copy of the graph model so package
imports work both from source checkout and installed distributions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple


@dataclass
class NodeMetrics:
    name: str
    fan_in: int
    fan_out: int
    layer: int


class ProjectGraph:
    """Dependency graph over project files."""

    def __init__(self, nodes: List[str], edges: Dict[str, List[str]]):
        norm_nodes = {Path(n).as_posix() for n in nodes}
        self.nodes: Set[str] = set(norm_nodes)
        self.edges: Dict[str, List[str]] = {n: [] for n in self.nodes}
        for src, dsts in edges.items():
            src_norm = Path(src).as_posix()
            if src_norm not in self.edges:
                self.edges[src_norm] = []
            for dst in dsts:
                dst_norm = Path(dst).as_posix()
                self.edges[src_norm].append(dst_norm)
                self.nodes.add(dst_norm)
        for node in list(self.nodes):
            self.edges.setdefault(node, [])

    @classmethod
    def from_self_map(cls, self_map: Dict) -> "ProjectGraph":
        modules = self_map.get("modules", [])
        deps = self_map.get("dependencies", {})
        file_nodes = [Path(module["path"]).as_posix() for module in modules]
        module_to_file: Dict[str, str] = {}
        for module in modules:
            p = Path(module["path"])
            module_to_file[p.stem] = p.as_posix()
        proj_edges: Dict[str, List[str]] = {}
        for src_key, dst_mods in deps.items():
            src_file = Path(src_key).as_posix()
            for mod_name in dst_mods:
                dst_file = module_to_file.get(mod_name.split(".")[0])
                if not dst_file:
                    continue
                proj_edges.setdefault(src_file, []).append(dst_file)
        return cls(file_nodes, proj_edges)

    def fan_in_out(self) -> Dict[str, Tuple[int, int]]:
        fan_out: Dict[str, int] = {node: len(self.edges.get(node, [])) for node in self.nodes}
        fan_in: Dict[str, int] = {node: 0 for node in self.nodes}
        for _src, dsts in self.edges.items():
            for dst in dsts:
                if dst not in fan_in:
                    fan_in[dst] = 0
                fan_in[dst] += 1
        return {node: (fan_in.get(node, 0), fan_out.get(node, 0)) for node in self.nodes}

    def _dfs_cycles(
        self,
        node: str,
        visited: Set[str],
        stack: List[str],
        on_stack: Set[str],
        cycles: List[List[str]],
    ) -> None:
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
        for node in self.nodes:
            if node not in visited:
                self._dfs_cycles(node, visited, stack, on_stack, cycles)
        return cycles

    def layers(self) -> Dict[str, int]:
        layer: Dict[str, int] = {}
        for _ in range(len(self.nodes) * 2):
            changed = False
            for node in self.nodes:
                outs = self.edges.get(node, [])
                if not outs:
                    if layer.get(node) is None:
                        layer[node] = 0
                        changed = True
                    continue
                if all((out in layer for out in outs)):
                    new_l = 1 + max((layer[out] for out in outs))
                    if layer.get(node) != new_l:
                        layer[node] = new_l
                        changed = True
            if not changed:
                break
        default_layer = max(layer.values()) if layer else 0
        for node in self.nodes:
            layer.setdefault(node, default_layer)
        return layer

    def metrics(self) -> Dict[str, NodeMetrics]:
        fan = self.fan_in_out()
        layers = self.layers()
        return {
            node: NodeMetrics(
                name=node,
                fan_in=fan[node][0],
                fan_out=fan[node][1],
                layer=layers[node],
            )
            for node in self.nodes
        }


__all__ = ["ProjectGraph", "NodeMetrics"]
