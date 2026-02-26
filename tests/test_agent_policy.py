"""Tests for agent policy evaluation (ROADMAP 2.7.3)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.agent.config import PolicyConfig, load_policy_config, suggest_policy_from_telemetry
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


def test_policy_denies_max_ops_exceeded() -> None:
    cfg = PolicyConfig(mode="auto", max_ops=2, max_files=100, allow_test_files=False, auto_apply_max_risk="high")
    op = {"kind": "remove_unused_import", "target_file": "foo.py", "description": "op"}
    out = evaluate_operation(op, config=cfg, index=3, seen_files=set())
    assert out.decision == "deny"
    assert "operation limit" in out.reason or "max_ops" in out.reason


def test_policy_denies_max_files_exceeded() -> None:
    cfg = PolicyConfig(mode="auto", max_ops=100, max_files=2, allow_test_files=False, auto_apply_max_risk="high")
    seen = {"a.py", "b.py"}
    op = {"kind": "remove_unused_import", "target_file": "c.py", "description": "op"}
    out = evaluate_operation(op, config=cfg, index=3, seen_files=seen)
    assert out.decision == "deny"
    assert "file scope" in out.reason or "max_files" in out.reason


def test_policy_deny_patterns_blocks_file() -> None:
    cfg = PolicyConfig(
        mode="auto", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="high",
        deny_patterns=("*api*.py", "*_internal*"),
    )
    op = {"kind": "remove_unused_import", "target_file": "foo/api_bar.py", "description": "op"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "deny"
    assert "deny pattern" in out.reason


def test_policy_api_breaking_guard_denies_auto_on_api_surface() -> None:
    cfg = PolicyConfig(
        mode="auto", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="high",
        api_breaking_guard=True,
    )
    op = {"kind": "split_module", "target_file": "eurika/api/__init__.py", "description": "split"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "deny"
    assert "API surface" in out.reason or "api_breaking" in out.reason


def test_policy_api_breaking_guard_review_hybrid_on_api_surface() -> None:
    cfg = PolicyConfig(
        mode="hybrid", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="low",
        api_breaking_guard=True,
    )
    op = {"kind": "extract_class", "target_file": "pkg/__init__.py", "description": "extract"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "review"
    assert "API surface" in out.reason or "manual" in out.reason


def test_policy_weak_pair_deny_in_auto() -> None:
    cfg = PolicyConfig(
        mode="auto", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="high",
    )
    op = {"kind": "split_module", "target_file": "x.py", "smell_type": "hub", "description": "split"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "deny"
    assert "weak pair" in out.reason or "blocked" in out.reason


def test_policy_weak_pair_review_in_hybrid() -> None:
    cfg = load_policy_config("hybrid")
    op = {"kind": "split_module", "target_file": "x.py", "smell_type": "hub", "description": "split"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "review"
    assert "weak" in out.reason or "approval" in out.reason


def test_policy_extract_block_weak_pair_deny_in_auto() -> None:
    """extract_block_to_helper weak pair should be denied in auto mode."""
    cfg = PolicyConfig(
        mode="auto", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="high",
    )
    op = {
        "kind": "extract_block_to_helper",
        "target_file": "x.py",
        "smell_type": "deep_nesting",
        "description": "extract block",
    }
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "deny"
    assert "weak" in out.reason or "blocked" in out.reason


def test_policy_extract_block_weak_pair_review_in_hybrid() -> None:
    """extract_block_to_helper weak pair should require review in hybrid mode."""
    cfg = load_policy_config("hybrid")
    op = {
        "kind": "extract_block_to_helper",
        "target_file": "x.py",
        "smell_type": "long_function",
        "description": "extract block",
    }
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "review"
    assert "weak" in out.reason or "approval" in out.reason


def test_policy_god_class_extract_class_weak_pair_deny_in_auto() -> None:
    """god_class|extract_class in WEAK: deny in auto (CYCLE_REPORT #34 tool_contract)."""
    cfg = PolicyConfig(
        mode="auto", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="high",
    )
    op = {"kind": "extract_class", "target_file": "x.py", "smell_type": "god_class", "description": "extract"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "deny"
    assert "weak" in out.reason or "blocked" in out.reason


def test_policy_god_class_extract_class_weak_pair_review_in_hybrid() -> None:
    """god_class|extract_class in WEAK: review in hybrid."""
    cfg = load_policy_config("hybrid")
    op = {"kind": "extract_class", "target_file": "x.py", "smell_type": "god_class", "description": "extract"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "review"
    assert "weak" in out.reason or "approval" in out.reason


def test_policy_low_risk_allowed_in_auto() -> None:
    cfg = PolicyConfig(mode="auto", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="medium")
    op = {"kind": "remove_unused_import", "target_file": "src/foo.py", "description": "cleanup"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision == "allow"


def test_policy_assist_bypasses_risk_limits() -> None:
    cfg = load_policy_config("assist")
    op = {"kind": "split_module", "target_file": "tests/x.py", "description": "split"}
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set())
    assert out.decision in {"allow", "review", "deny"}


def test_suggest_policy_from_telemetry_low_apply_rate() -> None:
    """Low apply_rate suggests reduced max_ops (ROADMAP 2.7.8)."""
    out = suggest_policy_from_telemetry({"apply_rate": 0.2, "rollback_rate": 0.0})
    assert out.get("EURIKA_AGENT_MAX_OPS") == "40"


def test_suggest_policy_from_telemetry_high_rollback_rate() -> None:
    """High rollback_rate suggests reduced max_ops."""
    out = suggest_policy_from_telemetry({"apply_rate": 0.5, "rollback_rate": 0.6})
    assert out.get("EURIKA_AGENT_MAX_OPS") == "40"


def test_suggest_policy_from_telemetry_empty() -> None:
    """Empty telemetry returns no suggestions."""
    assert suggest_policy_from_telemetry({}) == {}


def test_policy_target_verify_fail_history_denies_auto(tmp_path: Path) -> None:
    """Repeated verify_fail for same target|kind should block auto apply."""
    from eurika.storage import SessionMemory

    cfg = PolicyConfig(
        mode="auto", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="high",
    )
    op = {
        "kind": "split_module",
        "target_file": "x.py",
        "smell_type": "god_module",
        "description": "split",
        "params": {"location": "foo"},
    }
    mem = SessionMemory(tmp_path)
    mem.record_verify_failure([op])
    mem.record_verify_failure([op])
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set(), project_root=tmp_path)
    assert out.decision == "deny"
    assert "repeated verify failures" in out.reason


def test_policy_whitelist_allows_auto_for_known_target(tmp_path: Path) -> None:
    """Whitelist can allow safe target in auto even after fail-history deny."""
    from eurika.storage import SessionMemory

    cfg = PolicyConfig(
        mode="auto", max_ops=100, max_files=100, allow_test_files=False, auto_apply_max_risk="high",
    )
    op = {
        "kind": "extract_block_to_helper",
        "target_file": "eurika/api/chat.py",
        "smell_type": "deep_nesting",
        "description": "extract",
        "params": {"location": "_build_chat_context"},
    }
    mem = SessionMemory(tmp_path)
    mem.record_verify_failure([op])
    mem.record_verify_failure([op])

    wl_path = tmp_path / ".eurika" / "operation_whitelist.json"
    wl_path.parent.mkdir(parents=True, exist_ok=True)
    wl_path.write_text(
        json.dumps(
            {
                "operations": [
                    {
                        "kind": "extract_block_to_helper",
                        "target_file": "eurika/api/chat.py",
                        "smell_type": "deep_nesting",
                        "allow_in_hybrid": True,
                        "allow_in_auto": True,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    out = evaluate_operation(op, config=cfg, index=1, seen_files=set(), project_root=tmp_path)
    assert out.decision == "allow"
    assert "whitelisted target" in out.reason
