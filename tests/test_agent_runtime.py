"""Tests for native agent runtime primitives."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.agent.runtime import run_agent_cycle


class _FakeTools:
    def observe(self, _):
        return {"seen": True}

    def reason(self, _):
        return {"reasoned": True}

    def propose(self, _):
        return {"decision": "apply"}

    def apply(self, _):
        return {"result": "applied"}

    def verify(self, _):
        return {"ok": True}

    def learn(self, _):
        return {"saved": True}


def test_run_agent_cycle_executes_all_stages() -> None:
    out = run_agent_cycle(mode="assist", tools=_FakeTools())
    assert out.mode == "assist"
    assert out.stages == ["observe", "reason", "propose", "apply", "verify", "learn"]
    assert out.payload == {"result": "applied"}
    assert out.stage_outputs["verify"]["payload"] == {"ok": True}


def test_run_agent_cycle_stops_on_error() -> None:
    """Runtime breaks on ToolResult(status='error') and records failed stage."""
    from eurika.agent.models import ToolResult

    class _ToolsFailAtPropose:
        def observe(self, _):
            return {"seen": True}

        def reason(self, _):
            return {"reasoned": True}

        def propose(self, _):
            return ToolResult(status="error", message="no plan", payload=None)

    out = run_agent_cycle(mode="hybrid", tools=_ToolsFailAtPropose())
    assert out.mode == "hybrid"
    assert out.stages == ["observe", "reason", "propose"]
    assert out.stage_outputs["propose"]["status"] == "error"
    assert out.stage_outputs["propose"]["message"] == "no plan"
    assert out.payload is None


def test_run_agent_cycle_handles_exception_as_error() -> None:
    """Runtime catches tool exceptions and records error, then breaks."""
    class _ToolsRaiseAtApply:
        def observe(self, _):
            return {"seen": True}

        def reason(self, _):
            return {"reasoned": True}

        def propose(self, _):
            return {"decision": "apply"}

        def apply(self, _):
            raise RuntimeError("apply failed")

    out = run_agent_cycle(mode="auto", tools=_ToolsRaiseAtApply())
    assert out.stages == ["observe", "reason", "propose", "apply"]
    assert out.stage_outputs["apply"]["status"] == "error"
    assert "apply failed" in (out.stage_outputs["apply"].get("message") or "")


def test_run_agent_cycle_skips_missing_stages() -> None:
    """Runtime skips stages not implemented on tools object."""
    class _PartialTools:
        def observe(self, _):
            return {"seen": True}

        def apply(self, _):
            return {"result": "applied"}

    out = run_agent_cycle(mode="assist", tools=_PartialTools())
    assert out.stages == ["observe", "apply"]
    assert out.payload == {"result": "applied"}
