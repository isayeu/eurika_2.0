import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_graph_api import ProjectGraph
from eurika.analysis.topology import cluster_by_centers


def test_cluster_by_centers_basic():
    # Simple star: center.py -> a.py, b.py, c.py
    nodes = ["center.py", "a.py", "b.py", "c.py"]
    edges = {
        "center.py": ["a.py", "b.py", "c.py"],
    }
    graph = ProjectGraph(nodes, edges)

    clusters = cluster_by_centers(graph, centers=["center.py"])
    assert "center.py" in clusters
    # All nodes should end up in the single cluster.
    assert set(clusters["center.py"]) == set(nodes)

