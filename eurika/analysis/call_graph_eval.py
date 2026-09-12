"""Read-only accuracy/cost probe for the static call graph (RV11).

Labeled fixture scores recall and false resolutions. Project cost is elapsed
time and graph size. Results are diagnostics only — not a planner/policy input.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from eurika.analysis.call_graph import CallGraph, build_call_graph

_HELPERS = "def helper(value):\n    return value\n"
_DECOY = "def getcwd():\n    return 0\n"
_APP = """\
import os
from helpers import helper as imported

def local():
    return 1

def hidden():
    return 3

def run(value):
    local()
    imported(value)
    os.getcwd()
    name = hidden
    name()
    getattr(hidden, "__call__")()

class Service:
    def first(self):
        self.second()

    def second(self):
        return 2
"""
EXPECTED_EDGES = frozenset(
    {
        ("app.py:run", "app.py:local"),
        ("app.py:run", "helpers.py:helper"),
        ("app.py:Service.first", "app.py:Service.second"),
    }
)
FORBIDDEN_EDGES = frozenset(
    {
        ("app.py:run", "decoy.py:getcwd"),
        ("app.py:run", "app.py:hidden"),
    }
)
_ACCURACY_CACHE: dict[str, Any] | None = None


def score_call_edges(
    found: set[tuple[str, str]],
    *,
    expected: frozenset[tuple[str, str]] = EXPECTED_EDGES,
    forbidden: frozenset[tuple[str, str]] = FORBIDDEN_EDGES,
) -> dict[str, Any]:
    """Score only labeled edges. Extra unresolved calls are conservative, not errors."""
    tp = expected & found
    false_hits = forbidden & found
    missing = expected - found
    labeled = len(tp) + len(false_hits)
    recall = (len(tp) / len(expected)) if expected else 1.0
    precision = (len(tp) / labeled) if labeled else 1.0
    return {
        "expected_n": len(expected),
        "found_expected_n": len(tp),
        "recall": round(recall, 4),
        "false_resolutions": len(false_hits),
        "precision_labeled": round(precision, 4),
        "missing": sorted(f"{src}->{dst}" for src, dst in missing),
        "note": "labeled fixture only; unresolved dynamic/external is conservative OK",
    }


def measure_call_graph(project_root: str | Path) -> tuple[CallGraph, dict[str, Any]]:
    """Build the graph and time it. Does not change planner inputs."""
    t0 = time.perf_counter()
    graph = build_call_graph(project_root)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    files = {node.file for node in graph.nodes.values()}
    cost = {
        "elapsed_ms": elapsed_ms,
        "files": len(files),
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "data_flow_edges": len(graph.data_flow.edges),
        "parse_errors": len(graph.parse_errors),
    }
    return graph, cost


def evaluate_call_graph_accuracy(*, use_cache: bool = True) -> dict[str, Any]:
    """Accuracy against the bundled labeled tree (not the opened project)."""
    global _ACCURACY_CACHE
    if use_cache and _ACCURACY_CACHE is not None:
        return dict(_ACCURACY_CACHE)
    with tempfile.TemporaryDirectory(prefix="eurika-call-graph-eval-") as raw:
        root = Path(raw)
        (root / "helpers.py").write_text(_HELPERS, encoding="utf-8")
        (root / "decoy.py").write_text(_DECOY, encoding="utf-8")
        (root / "app.py").write_text(_APP, encoding="utf-8")
        graph, cost = measure_call_graph(root)
        accuracy = score_call_edges(graph.edges)
        accuracy["elapsed_ms"] = cost["elapsed_ms"]
    _ACCURACY_CACHE = accuracy
    return dict(accuracy)


def attach_call_graph_diagnostics(project_root: str | Path) -> dict[str, Any]:
    """Serialize call graph plus read-only accuracy/cost diagnostics."""
    graph, cost = measure_call_graph(project_root)
    payload = graph.to_dict()
    payload["diagnostics"] = {
        "read_only": True,
        "planner_attached": False,
        "cost": cost,
        "accuracy": evaluate_call_graph_accuracy(),
    }
    return payload
