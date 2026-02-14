import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_graph_api import ProjectGraph
from eurika.smells.models import detect_god_modules, detect_smells


def make_star_graph() -> ProjectGraph:
    """
    Build a small graph:
      center.py -> many leaf modules
      leaves -> (no deps)
    Expect center.py to be a hub.
    """
    leaves = [f"m{i}.py" for i in range(10)]
    nodes = ["center.py", *leaves]
    edges = {"center.py": leaves}
    return ProjectGraph(nodes, edges)


def make_bottleneck_graph() -> ProjectGraph:
    """
    Build a graph where one node has many incoming edges:
      many modules -> core.py
    core.py is a bottleneck (high fan-in, low fan-out).
    """
    sources = [f"s{i}.py" for i in range(10)]
    nodes = ["core.py", *sources]
    edges = {s: ["core.py"] for s in sources}
    return ProjectGraph(nodes, edges)


def test_detect_hub_smell():
    graph = make_star_graph()
    smells = detect_smells(graph)
    types = {s.type for s in smells}
    assert "hub" in types
    hub_nodes = [s.nodes for s in smells if s.type == "hub"][0]
    assert "center.py" in hub_nodes


def test_detect_bottleneck_smell():
    graph = make_bottleneck_graph()
    smells = detect_smells(graph)
    types = {s.type for s in smells}
    assert "bottleneck" in types
    bottleneck_nodes = [s.nodes for s in smells if s.type == "bottleneck"][0]
    assert "core.py" in bottleneck_nodes


def test_bottleneck_exempts_facade_api():
    """*_api.py modules (facades) are exempt from bottleneck — high fan-in is expected."""
    many = [f"m{i}.py" for i in range(15)]
    nodes = ["my_api.py", *many]
    edges = {m: ["my_api.py"] for m in many}
    graph = ProjectGraph(nodes, edges)
    from eurika.smells.models import detect_bottlenecks

    smells = detect_bottlenecks(graph)
    bottleneck_nodes = [n for s in smells if s.type == "bottleneck" for n in s.nodes]
    assert "my_api.py" not in bottleneck_nodes


def test_god_module_exempts_facade_api():
    """*_api.py modules (facades) are exempt from god_module — high degree is expected."""
    many = [f"m{i}.py" for i in range(15)]
    nodes = ["my_project_api.py", *many]
    edges = {
        "my_project_api.py": ["project_graph.py"],
        **{m: ["my_project_api.py"] for m in many},
    }
    graph = ProjectGraph(nodes, edges)
    smells = detect_god_modules(graph)
    god_nodes = [n for s in smells if s.type == "god_module" for n in s.nodes]
    assert "my_project_api.py" not in god_nodes

