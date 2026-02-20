"""Tests for runtime mode wiring in CLI and orchestrator."""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import eurika_cli
from cli.orchestrator import run_cycle
from eurika.agent.models import AgentCycleResult


def test_cli_fix_accepts_runtime_mode_flag() -> None:
    parser = eurika_cli._build_parser()
    args = parser.parse_args(["fix", "--runtime-mode", "hybrid", "."])
    assert args.runtime_mode == "hybrid"


def test_cli_fix_accepts_hybrid_session_flags() -> None:
    parser = eurika_cli._build_parser()
    args = parser.parse_args(["fix", "--runtime-mode", "hybrid", "--non-interactive", "--session-id", "sprint3", "."])
    assert args.runtime_mode == "hybrid"
    assert args.non_interactive is True
    assert args.session_id == "sprint3"


def test_run_cycle_uses_runtime_wrapper_for_non_assist() -> None:
    fake = AgentCycleResult(mode="hybrid", stages=["observe", "apply"], payload={"ok": True})
    with patch("eurika.agent.runtime.run_agent_cycle", return_value=fake):
        out = run_cycle(ROOT, mode="doctor", runtime_mode="hybrid", no_llm=True)
    assert out["ok"] is True
    assert out["agent_runtime"]["mode"] == "hybrid"


def test_run_cycle_rejects_unknown_runtime_mode() -> None:
    out = run_cycle(ROOT, mode="doctor", runtime_mode="wrong-mode", no_llm=True)
    assert "error" in out
    assert "Unknown runtime_mode" in out["error"]
