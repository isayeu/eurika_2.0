"""Tests for ExecutorSandbox (dry_run and execute)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from action_plan import Action, ActionPlan
from executor_sandbox import ExecutorSandbox


def test_executor_sandbox_dry_run(tmp_path: Path) -> None:
    plan = ActionPlan(
        actions=[
            Action(
                type="refactor_module",
                target="a.py",
                description="Split module",
                risk=0.3,
                expected_benefit=0.8,
            ),
        ],
        priority=[0],
        total_risk=0.3,
        expected_gain=0.8,
    )
    sandbox = ExecutorSandbox(project_root=tmp_path)
    out = sandbox.dry_run(plan)
    assert out["total_risk"] == 0.3
    assert out["expected_gain"] == 0.8
    assert len(out["actions"]) == 1
    assert out["actions"][0]["status"] == "planned"
    assert (tmp_path / "architecture_actions_log.jsonl").exists()


def test_executor_sandbox_execute(tmp_path: Path) -> None:
    (tmp_path / "b.py").write_text("x = 1\n", encoding="utf-8")
    plan = ActionPlan(
        actions=[
            Action(
                type="refactor_module",
                target="b.py",
                description="Refactor b",
                risk=0.3,
                expected_benefit=0.8,
            ),
        ],
        priority=[0],
        total_risk=0.3,
        expected_gain=0.8,
    )
    sandbox = ExecutorSandbox(project_root=tmp_path)
    report = sandbox.execute(plan, backup=True)
    assert report.get("errors") == []
    assert "b.py" in report.get("modified", [])
    assert report.get("run_id") is not None
    assert report["actions"][0]["status"] == "applied"
    content = (tmp_path / "b.py").read_text(encoding="utf-8")
    assert "TODO" in content
    assert "Refactor b" in content
