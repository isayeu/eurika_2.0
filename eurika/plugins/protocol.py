"""R5 3.1: AnalyzerPlugin protocol — единый контракт для внешних анализаторов."""

from __future__ import annotations

from pathlib import Path
from typing import List, Protocol, runtime_checkable

from eurika.smells.detector import ArchSmell


@runtime_checkable
class AnalyzerPlugin(Protocol):
    """
    Protocol for external architecture analyzers.

    R5 3.1: Plugins implement analyze(project_root) and return List[ArchSmell].
    Each smell must have: type, nodes, severity, description.
    """

    def analyze(self, project_root: Path) -> List[ArchSmell]:
        """
        Analyze project at project_root and return architectural smells.

        Returns:
            List of ArchSmell (type, nodes, severity, description).
            nodes: module paths (e.g. "eurika/api/chat.py").
        """
        ...
