"""Extracted from parent module to reduce complexity."""

from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from eurika.analysis.graph import ProjectGraph


def detect_smells(graph: "ProjectGraph") -> List[Any]:
    """
    Detect architectural smells from project graph.

    Delegates to eurika.smells.models.detect_smells.
    """
    from eurika.smells.models import detect_smells as _detect
    return _detect(graph)
