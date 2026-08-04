"""Tests for eurika.reasoning.planner.models (ROADMAP v3.0 Stage 2)."""

from __future__ import annotations

import pytest

from eurika.reasoning.planner.models import (
    ArchitectureModel,
    RefactorAction,
    RiskProfile,
    RiskReport,
    SimulationResult,
    SmellReport,
)


def test_smell_report_from_arch_smell() -> None:
    class FakeSmell:
        type = "god_module"
        nodes = ["foo.py", "bar.py"]
        severity = 5.0
        description = "High degree"
    s = SmellReport.from_arch_smell(FakeSmell(), hint="Split module")
    assert s.type == "god_module"
    assert s.nodes == ["foo.py", "bar.py"]
    assert s.severity == 5.0
    assert s.remediation_hint == "Split module"
    assert s.level == "high"


def test_refactor_action_from_action() -> None:
    class FakeAction:
        type = "split_module"
        target = "big.py"
        description = "Extract submodule"
        risk = 0.3
        expected_benefit = 0.7
    a = RefactorAction.from_action(FakeAction())
    assert a.type == "split_module"
    assert a.risk_profile.score == 0.3
    assert a.risk_profile.level == "medium"
    assert a.expected_benefit == 0.7


def test_risk_report() -> None:
    r = RiskReport(total_risk=0.5, level="medium", factors=["cycles"], recommendations=[])
    d = r.to_dict()
    assert d["total_risk"] == 0.5
    assert d["level"] == "medium"


def test_architecture_model_to_dict() -> None:
    m = ArchitectureModel(
        project_root="/proj",
        smells=[],
        cohesion=0.8,
        coupling=0.2,
        complexity=0.3,
        modularity=0.7,
    )
    d = m.to_dict()
    assert d["cohesion"] == 0.8
    assert d["coupling"] == 0.2


def test_architecture_model_from_graph_and_smells() -> None:
    from eurika.analysis.graph import ProjectGraph

    class FakeSmell:
        type = "cyclic_dependency"
        nodes = ["a.py", "b.py"]
        severity = 3.0
        description = "Cycle"

    g = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"], "b.py": ["a.py"]})
    smells = [FakeSmell()]
    health = {"score": 65, "level": "medium", "factors": ["1 cycle"]}
    m = ArchitectureModel.from_graph_and_smells("/proj", g, smells, health=health)
    assert m.project_root == "/proj"
    assert m.health_score == 65
    assert len(m.smells) == 1
    assert m.smells[0].type == "cyclic_dependency"
    assert 0 <= m.cohesion <= 1
    assert 0 <= m.coupling <= 1


def test_simulation_result_from_dict() -> None:
    d = {
        "would_modify": ["a.py", "b.py"],
        "would_skip": ["c.py"],
        "skipped_reasons": {"c.py": "path not found"},
        "errors": [],
        "operations_count": 3,
    }
    r = SimulationResult.from_simulate_dict(d)
    assert r.would_modify == ["a.py", "b.py"]
    assert r.would_skip == ["c.py"]
    assert r.skipped_reasons == {"c.py": "path not found"}
    assert r.operations_count == 3
