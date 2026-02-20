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
