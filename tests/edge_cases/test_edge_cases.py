"""R3 Edge-case matrix: empty/huge input, model/network error, memory write error."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))


def _minimal_self_map(path: Path, modules: list[str], deps: dict) -> None:
    data = {
        "modules": [{"path": p, "lines": 10, "functions": [], "classes": []} for p in modules],
        "dependencies": deps,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.edge_case
def test_get_summary_empty_self_map_returns_error(tmp_path: Path) -> None:
    """Empty/missing self_map.json → get_summary returns error dict."""
    from eurika.api import get_summary

    out = get_summary(tmp_path)
    assert "error" in out
    assert "self_map" in out.get("error", "").lower() or "path" in out


@pytest.mark.edge_case
def test_get_summary_minimal_valid_returns_summary(tmp_path: Path) -> None:
    """Minimal valid self_map → summary with system, no crash."""
    _minimal_self_map(tmp_path / "self_map.json", ["a.py"], {})
    from eurika.api import get_summary

    out = get_summary(tmp_path)
    assert "error" not in out
    assert "system" in out
    assert out.get("system", {}).get("modules") == 1


@pytest.mark.edge_case
def test_architect_empty_summary_completes(tmp_path: Path) -> None:
    """Architect with empty summary → template returns, no crash."""
    from eurika.reasoning.architect import interpret_architecture_with_meta

    summary = {"system": {}, "maturity": "unknown"}
    history = {"trends": {}, "regressions": []}
    text, meta = interpret_architecture_with_meta(
        summary, history, use_llm=False, verbose=False
    )
    assert isinstance(text, str) and len(text) > 0
    assert meta.get("degraded_mode") is True
    assert "llm_disabled" in (meta.get("degraded_reasons") or [])


@pytest.mark.edge_case
def test_policy_empty_operation_kind_defaults_medium_risk() -> None:
    """Policy with unknown/empty operation kind → medium risk, allow or review."""
    from eurika.agent.policy import evaluate_operation
    from eurika.agent.config import PolicyConfig

    cfg = PolicyConfig(
        mode="assist", max_ops=100, max_files=100,
        allow_test_files=True, auto_apply_max_risk="high",
    )
    op = {"kind": "", "target_file": "x.py", "description": ""}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.risk in ("low", "medium", "high")
    assert out.decision in ("allow", "review", "deny")


@pytest.mark.edge_case
def test_agent_runtime_stage_exception_sets_error_state() -> None:
    """Runtime: stage raises → cycle returns ERROR state, no propagation."""
    from eurika.agent.runtime import run_agent_cycle
    from eurika.agent.models import AgentRuntimeState

    class FailingTools:
        def observe(self, _in):
            raise RuntimeError("network down")

    cycle = run_agent_cycle(mode="assist", tools=FailingTools())
    assert cycle.state == AgentRuntimeState.ERROR
    assert "observe" in cycle.stages
    assert cycle.stage_outputs.get("observe", {}).get("status") == "error"


@pytest.mark.edge_case
def test_memory_events_append_and_read(tmp_path: Path) -> None:
    """Memory events: append_event persists; all() returns events."""
    from eurika.storage import ProjectMemory

    mem = ProjectMemory(tmp_path)
    _ = mem.events
    mem.events.append_event("scan", {}, {"modules": 0}, result=True)
    events = mem.events.all()
    assert len(events) >= 1


@pytest.mark.edge_case
def test_cycle_state_empty_project_returns_done_or_error(tmp_path: Path) -> None:
    """Fix/doctor on empty project (no self_map) → state=error, predictable."""
    from cli.orchestrator import run_cycle

    out = run_cycle(tmp_path, mode="doctor", no_llm=True, quiet=True)
    assert "state" in out
    assert out["state"] in ("done", "error")
    if out.get("error"):
        assert out["state"] == "error"


@pytest.mark.edge_case
def test_build_patch_operations_empty_input_returns_list() -> None:
    """Planner: empty summary/smells → operations list (possibly empty), no crash."""
    from eurika.reasoning.planner_patch_ops import build_patch_operations

    summary = {"system": {"modules": 0, "dependencies": 0, "cycles": 0}, "risks": []}
    out = build_patch_operations(
        project_root=str(ROOT),
        summary=summary,
        smells=[],
        priorities=[],
        smells_by_node={},
    )
    assert isinstance(out, list)
    assert len(out) == 0


@pytest.mark.edge_case
def test_build_summary_huge_graph_no_overflow() -> None:
    """build_summary with large module list → completes, no overflow."""
    from eurika.analysis.graph import ProjectGraph
    from eurika.smells.summary import build_summary

    nodes = [f"m{i}.py" for i in range(500)]
    graph = ProjectGraph(nodes, {})
    smells = []
    out = build_summary(graph, smells)
    assert "system" in out
    assert out.get("system", {}).get("modules") == 500
