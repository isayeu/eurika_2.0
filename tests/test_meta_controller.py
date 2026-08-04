"""Tests for meta-controller (ROADMAP v4.0)."""

from pathlib import Path


def test_evaluate_policy_normal(tmp_path: Path) -> None:
    """When no degradation, returns normal policy."""
    import os
    os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"] = "1"
    try:
        from eurika.cognition import evaluate_policy

        dec = evaluate_policy(tmp_path)
        assert dec.skip_adaptation is False
        assert dec.learning_rate_scale == 1.0
    finally:
        os.environ.pop("EURIKA_DISABLE_GLOBAL_MEMORY", None)


def test_evaluate_policy_degraded_consecutive_fails(tmp_path: Path) -> None:
    """3+ consecutive verify failures → skip_adaptation."""
    import os
    os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"] = "1"
    try:
        from eurika.cognition import evaluate_policy
        from eurika.storage.memory import ProjectMemory

        memory = ProjectMemory(tmp_path)
        for _ in range(4):
            memory.events.append_event(
                type="patch",
                input={"ops": 1},
                output={"verify_success": False},
                result=False,
            )
        dec = evaluate_policy(tmp_path)
        assert dec.skip_adaptation is True
        assert dec.learning_rate_scale == 0.0
    finally:
        os.environ.pop("EURIKA_DISABLE_GLOBAL_MEMORY", None)


def test_evaluate_policy_reduced_lr(tmp_path: Path) -> None:
    """Low recent success rate (0.3–0.5) → learning_rate_scale 0.5, not full skip."""
    import os
    os.environ["EURIKA_DISABLE_GLOBAL_MEMORY"] = "1"
    try:
        from eurika.cognition import evaluate_policy
        from eurika.storage.memory import ProjectMemory

        # 5 patch events, 2 success → recent_rate 0.4 (not degraded, but reduced)
        memory = ProjectMemory(tmp_path)
        for i in range(5):
            memory.events.append_event(
                type="patch",
                input={"ops": 1},
                output={"verify_success": i < 2},
                result=(i < 2),
            )
        dec = evaluate_policy(tmp_path)
        assert dec.skip_adaptation is False
        assert dec.learning_rate_scale == 0.5
    finally:
        os.environ.pop("EURIKA_DISABLE_GLOBAL_MEMORY", None)
