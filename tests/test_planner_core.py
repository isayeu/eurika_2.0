"""Tests for eurika.reasoning.planner.core (ROADMAP v3.0 §5.6)."""

from __future__ import annotations

import pytest

from eurika.analysis.graph import ProjectGraph
from eurika.reasoning.planner import analyze, detect_smells, propose_actions


def test_detect_smells() -> None:
    g = ProjectGraph(["a.py", "b.py"], {"a.py": ["b.py"], "b.py": ["a.py"]})
    smells = detect_smells(g)
    assert len(smells) >= 1
    assert any(s.type == "cyclic_dependency" for s in smells)


def test_analyze() -> None:
    g = ProjectGraph(["a.py", "b.py", "c.py"], {"a.py": ["b.py"], "b.py": ["c.py"]})
    out = analyze(g, top_n=5)
    assert "smells" in out
    assert "priorities" in out
    assert "targets" in out


def test_propose_actions() -> None:
    class FakeSmell:
        type = "god_module"
        nodes = ["big.py"]
        severity = 5.0
        description = "High degree"

    plan = propose_actions(
        "/proj",
        summary={},
        smells=[FakeSmell()],
        history_info={"trends": {}, "regressions": []},
        priorities=[{"name": "big.py", "reasons": ["god_module"]}],
    )
    assert hasattr(plan, "actions")
    assert hasattr(plan, "to_dict")
