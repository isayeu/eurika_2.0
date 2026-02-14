import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_graph_api import ProjectGraph
from eurika.analysis.metrics import summarize_graph


def test_summarize_graph_metrics_and_cycles():
    # Simple graph with a single cycle: a -> b -> a
    nodes = ["a.py", "b.py", "c.py"]
    edges = {
        "a.py": ["b.py"],
        "b.py": ["a.py"],
        "c.py": [],
    }
    graph = ProjectGraph(nodes, edges)

    summary = summarize_graph(graph)

    assert summary["nodes"] == 3
    assert summary["edges"] == 2
    assert summary["cycles_count"] >= 1

    metrics = summary["metrics"]
    # a.py and b.py should both have non-zero fan_in and fan_out
    assert metrics["a.py"]["fan_out"] == 1
    assert metrics["a.py"]["fan_in"] == 1
    assert metrics["b.py"]["fan_out"] == 1
    assert metrics["b.py"]["fan_in"] == 1

