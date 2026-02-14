import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_graph_api import ProjectGraph
from eurika.smells.detector import ArchSmell
from eurika.smells.advisor import build_recommendations


def test_build_recommendations_for_hub_and_bottleneck():
    # Build a small graph where center.py fans out to many nodes (hub),
    # and core.py has many incoming edges (bottleneck).
    nodes = ["center.py", "core.py", "a.py", "b.py", "c.py"]
    edges = {
        "center.py": ["a.py", "b.py", "c.py"],
        "a.py": ["core.py"],
        "b.py": ["core.py"],
        "c.py": ["core.py"],
    }
    graph = ProjectGraph(nodes, edges)

    smells = [
        ArchSmell(type="hub", nodes=["center.py"], severity=1.0, description="test"),
        ArchSmell(type="bottleneck", nodes=["core.py"], severity=1.0, description="test"),
    ]

    recs = build_recommendations(graph, smells)

    # We expect at least one recommendation mentioning center.py as high fan-out hub.
    hub_rec = next((r for r in recs if "center.py" in r and "High fan-out" in r), None)
    assert hub_rec is not None

    # And at least one recommendation mentioning core.py as bottleneck.
    bottleneck_rec = next((r for r in recs if "core.py" in r and "Bottleneck risk" in r), None)
    assert bottleneck_rec is not None

