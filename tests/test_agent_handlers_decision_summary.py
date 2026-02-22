"""Tests for decision summary CLI helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.agent_handlers import _decision_summary_from_report, _print_decision_summary


def test_decision_summary_prefers_report_field() -> None:
    report = {
        "decision_summary": {
            "blocked_by_policy": 2,
            "blocked_by_critic": 1,
            "blocked_by_human": 3,
        }
    }
    got = _decision_summary_from_report(report)
    assert got == {
        "blocked_by_policy": 2,
        "blocked_by_critic": 1,
        "blocked_by_human": 3,
    }


def test_decision_summary_fallback_from_policy_critic_and_skipped() -> None:
    report = {
        "policy_decisions": [
            {"decision": "deny"},
            {"decision": "allow"},
        ],
        "critic_decisions": [
            {"verdict": "deny"},
            {"verdict": "review"},
        ],
        "skipped_reasons": {
            "a.py": "rejected_in_hybrid",
            "b.py": "approval_state=pending",
        },
    }
    got = _decision_summary_from_report(report)
    assert got["blocked_by_policy"] == 1
    assert got["blocked_by_critic"] == 1
    assert got["blocked_by_human"] == 1


def test_print_decision_summary_writes_line(capsys) -> None:
    report = {
        "decision_summary": {
            "blocked_by_policy": 1,
            "blocked_by_critic": 0,
            "blocked_by_human": 2,
        }
    }
    _print_decision_summary(report, quiet=False)
    err = capsys.readouterr().err
    assert "Decision summary:" in err
    assert "policy=1" in err
    assert "critic=0" in err
    assert "human=2" in err
