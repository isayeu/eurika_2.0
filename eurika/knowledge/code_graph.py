"""
Code Graph — фасад над ProjectGraph (R10, KNOWLEDGE_GRAPH_DESIGN).

Предоставляет единую точку входа для code-level графа: modules, import edges.
Дальнейшее расширение: functions, calls — по мере необходимости.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set


@dataclass
class CodeGraph:
    """
    Code-level граф: nodes = file paths, edges = import dependencies.

    Схема (KNOWLEDGE_GRAPH_DESIGN §2.3):
      nodes: file_path
      edges: import(file_a → file_b)
    """

    nodes: Set[str]
    """Нормализованные пути файлов (POSIX)."""

    edges: Dict[str, List[str]]
    """src_file → [dst_file, ...] — import dependencies."""

    def import_edges(self) -> List[tuple[str, str]]:
        """Список пар (src, dst) для import edges."""
        result: List[tuple[str, str]] = []
        for src, dsts in self.edges.items():
            for dst in dsts:
                result.append((src, dst))
        return result


def build_code_graph(self_map: Dict[str, Any]) -> CodeGraph:
    """
    Построить CodeGraph из self_map.json.

    Использует ProjectGraph.from_self_map. Модули + import edges.
    Functions, calls — следующий этап (KNOWLEDGE_GRAPH_DESIGN §2.2).
    """
    from project_graph_api import ProjectGraph

    pg = ProjectGraph.from_self_map(self_map)
    return CodeGraph(nodes=set(pg.nodes), edges=dict(pg.edges))
