import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.analysis.graph import ProjectGraph
from eurika.smells.models import ArchSmell
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


def test_build_recommendations_rv5_blast_radius_in_text():
    """RV5: when blast_radius >= 10, recommendation includes blast_radius=N."""
    # core has 12 dependents (a..l) -> blast_radius(core)=12
    deps = ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py", "g.py", "h.py", "i.py", "j.py", "k.py", "l.py"]
    nodes = ["core.py"] + deps
    edges = {d: ["core.py"] for d in deps}
    graph = ProjectGraph(nodes, edges)
    smells = [ArchSmell(type="god_module", nodes=["core.py"], severity=1.0, description="test")]
    recs = build_recommendations(graph, smells)
    god_rec = next((r for r in recs if "core.py" in r and "God-module" in r), None)
    assert god_rec is not None
    assert "blast_radius=12" in god_rec


def test_build_recommendations_rv5_blast_radius_in_output():
    """RV5: when blast_radius >= 10, it appears in the recommendation text."""
    # core.py has 12 dependents -> blast_radius(core.py) = 12
    nodes = ["core.py"] + [f"dep{i}.py" for i in range(12)]
    edges = {f"dep{i}.py": ["core.py"] for i in range(12)}
    edges["core.py"] = []
    graph = ProjectGraph(nodes, edges)
    assert graph.blast_radius("core.py") == 12

    smells = [
        ArchSmell(type="god_module", nodes=["core.py"], severity=1.0, description="test"),
    ]
    recs = build_recommendations(graph, smells)
    god_rec = next((r for r in recs if "core.py" in r and "God-module" in r), None)
    assert god_rec is not None
    assert "blast_radius=12" in god_rec


def test_build_recommendations_rv5_blast_radius_in_text():
    """RV5: when blast_radius >= 10, recommendation includes blast_radius=N."""
    # core has 12 dependents (a..l) -> blast_radius(core)=12
    nodes = ["core.py"] + [f"{c}.py" for c in "abcdefghijkl"]
    edges = {f"{c}.py": ["core.py"] for c in "abcdefghijkl"}
    graph = ProjectGraph(nodes, edges)

    smells = [
        ArchSmell(type="god_module", nodes=["core.py"], severity=1.0, description="test"),
    ]
    recs = build_recommendations(graph, smells)

    god_rec = next((r for r in recs if "core.py" in r and "God-module" in r), None)
    assert god_rec is not None
    assert "blast_radius=12" in god_rec


def test_build_recommendations_rv5_blast_radius_in_text():
    """RV5: when blast_radius >= 10, recommendation includes blast_radius=N."""
    # core has 12 dependents (a..l) -> blast_radius(core)=12
    nodes = ["core.py"] + [f"{c}.py" for c in "abcdefghijkl"]
    edges = {f"{c}.py": ["core.py"] for c in "abcdefghijkl"}
    edges["core.py"] = []
    graph = ProjectGraph(nodes, edges)

    smells = [
        ArchSmell(type="god_module", nodes=["core.py"], severity=1.0, description="test"),
    ]
    recs = build_recommendations(graph, smells)
    god_rec = next((r for r in recs if "core.py" in r and "God-module" in r), None)
    assert god_rec is not None
    assert "blast_radius=12" in god_rec


def test_build_recommendations_rv5_blast_radius_in_output():
    """RV5: modules with blast_radius>=10 show blast_radius in recommend text."""
    # core.py has 12 dependents (a..l) -> blast_radius(core.py)=12
    nodes = ["core.py"] + [f"{c}.py" for c in "abcdefghijkl"]
    edges = {f"{c}.py": ["core.py"] for c in "abcdefghijkl"}
    graph = ProjectGraph(nodes, edges)

    smells = [
        ArchSmell(type="god_module", nodes=["core.py"], severity=1.0, description="test"),
    ]
    recs = build_recommendations(graph, smells)

    god_rec = next((r for r in recs if "core.py" in r and "God-module" in r), None)
    assert god_rec is not None
    assert "blast_radius=12" in god_rec


def test_build_recommendations_rv5_blast_radius_in_output():
    """RV5: when blast_radius >= 10, it appears in recommendation text."""
    # core.py has 12 dependents -> blast_radius(core.py)=12
    nodes = ["core.py"] + [f"dep{i}.py" for i in range(12)]
    edges = {f"dep{i}.py": ["core.py"] for i in range(12)}
    graph = ProjectGraph(nodes, edges)

    smells = [
        ArchSmell(type="god_module", nodes=["core.py"], severity=1.0, description="test"),
    ]

    recs = build_recommendations(graph, smells)

    god_rec = next((r for r in recs if "core.py" in r and "God-module" in r), None)
    assert god_rec is not None
    assert "blast_radius=12" in god_rec


def test_build_recommendations_rv5_blast_radius_in_output():
    """RV5: when blast_radius >= 10, it appears in recommendation text."""
    # core.py has 12 dependents -> blast_radius(core.py)=12
    nodes = ["core.py"] + [f"dep{i}.py" for i in range(12)]
    edges = {f"dep{i}.py": ["core.py"] for i in range(12)}
    graph = ProjectGraph(nodes, edges)
    assert graph.blast_radius("core.py") == 12

    smells = [
        ArchSmell(type="god_module", nodes=["core.py"], severity=1.0, description="test"),
    ]
    recs = build_recommendations(graph, smells)
    god_rec = next((r for r in recs if "core.py" in r and "God-module" in r), None)
    assert god_rec is not None
    assert "blast_radius=12" in god_rec

