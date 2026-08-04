import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_graph_api import ProjectGraph
from eurika.smells.models import ArchSmell
from eurika.evolution.history import ArchitectureHistory


def make_linear_graph(n: int) -> ProjectGraph:
    """
    Build a simple linear graph: 0 -> 1 -> 2 -> ... -> n-1
    Used only to synthesize fan_in/fan_out; structure is not important.
    """
    nodes = [f"m{i}.py" for i in range(n)]
    edges = {}
    for i in range(n - 1):
        edges[f"m{i}.py"] = [f"m{i+1}.py"]
    return ProjectGraph(nodes, edges)


def test_history_trend_and_regressions(tmp_path):
    history_path = tmp_path / "arch_history.json"
    h = ArchitectureHistory(storage_path=history_path)

    # Synthetic snapshots: complexity grows, smells first stable then increase.
    for i in range(3):
        g = make_linear_graph(3 + i)
        # first two points: no smells, last point: one smell
        smells = []
        if i == 2:
            smells = [ArchSmell(type="god_module", nodes=["m0.py"], severity=1.0, description="test")]
        summary = {
            "system": {
                "modules": len(g.nodes),
                "dependencies": sum(len(v) for v in g.edges.values()),
                "cycles": 0,
            },
            "maturity": "synthetic",
        }
        h.append(g, smells, summary)

    trends = h.trend(window=3)
    assert trends["complexity"] == "increasing"
    assert trends["smells"] == "increasing"

    regressions = h.detect_regressions(window=3)
    # We expect at least one regression message about smells increase.
    assert any("Total smells increased" in r for r in regressions)
    # v0.6: god_module tracked separately
    assert any("god_module increased" in r for r in regressions)


def test_history_version_and_risk_score(tmp_path):
    """v0.6: history point includes version (from pyproject) and risk_score when available."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "1.2.3"\n',
        encoding="utf-8",
    )
    history_path = tmp_path / "arch_history.json"
    h = ArchitectureHistory(storage_path=history_path)

    g = make_linear_graph(3)
    summary = {
        "system": {"modules": 3, "dependencies": 2, "cycles": 0},
        "maturity": "low",
    }
    h.append(g, [], summary)

    pts = h._points
    assert len(pts) == 1
    assert pts[0].version == "1.2.3"
    assert pts[0].risk_score is not None
    assert 0 <= pts[0].risk_score <= 100


def test_evolution_report_from_eurika_evolution_history(tmp_path):
    """eurika.evolution.history: evolution_report returns string with expected sections."""
    history_path = tmp_path / "arch_history.json"
    h = ArchitectureHistory(storage_path=history_path)

    g = make_linear_graph(4)
    summary = {
        "system": {"modules": 4, "dependencies": 3, "cycles": 0},
        "maturity": "medium",
    }
    h.append(g, [], summary)
    h.append(g, [], summary)

    report = h.evolution_report(window=5)
    assert "ARCHITECTURE EVOLUTION ANALYSIS" in report
    assert "Trend:" in report
    assert "Potential regressions:" in report
    assert "Maturity" in report

