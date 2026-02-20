"""Tests for agent policy evaluation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.agent.config import load_policy_config
from eurika.agent.policy import evaluate_operation


def test_policy_hybrid_marks_high_risk_as_review() -> None:
    cfg = load_policy_config("hybrid")
    op = {"kind": "split_module", "target_file": "core/pipeline.py", "description": "Split large module"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "review"
    assert out.risk == "high"
    assert "manual approval" in out.reason


def test_policy_denies_test_file_by_default() -> None:
    cfg = load_policy_config("auto")
    op = {"kind": "remove_unused_import", "target_file": "tests/test_x.py", "description": "cleanup"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "deny"
    assert "test files" in out.reason
