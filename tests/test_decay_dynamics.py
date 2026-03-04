"""
Decay dynamics — калибровка (Review III шаги 1–4).

Шаг 1: полигон контролируемых провалов
Шаг 2: наблюдение динамики (падение priority, archive)
Шаг 3: восстановление после успеха
Шаг 4: forgetting (пока в design)
"""

from pathlib import Path

import pytest

from eurika.polygon.decay_polygon import (
    inject_failures,
    inject_success,
    run_decay_observation,
    scenario_controlled_failures,
)
from eurika.reasoning.priority_decay import apply_decay


def _kind_fn(node: str) -> str:
    return "split_module" if "god" in node else "refactor_module"


# --- Шаг 1: полигон ---


def test_inject_failures(tmp_path: Path) -> None:
    """Контролируемые провалы: inject создаёт learn events в EventLog."""
    from eurika.storage import get_recent_failures

    inject_failures(tmp_path, "stuck.py", "split_module", 2)
    failures = get_recent_failures(tmp_path, limit=5)
    assert len(failures) >= 1
    assert any((tf == "stuck.py" and k == "split_module") for tf, k, _ in failures)


def test_scenario_controlled_failures(tmp_path: Path) -> None:
    """Сценарий: несколько целей с разным числом провалов."""
    (tmp_path / ".eurika").mkdir(parents=True)
    scenario_controlled_failures(
        tmp_path,
        [
            ("a.py", "split_module", 0),  # нет провалов
            ("b.py", "split_module", 2),
            ("c.py", "extract_class", 5),
        ],
    )
    scores = {"a.py": 10.0, "b.py": 10.0, "c.py": 10.0}
    reasons = {"a.py": ["god_module"], "b.py": ["god_module"], "c.py": ["god_class"]}
    apply_decay(
        scores,
        reasons,
        lambda n: "split_module" if n != "c.py" else "extract_class",
        tmp_path,
    )
    # a без penalty, b с penalty, c archived
    assert scores["a.py"] == 10.0
    assert scores["b.py"] < 10.0
    assert scores["c.py"] < 2.0


# --- Шаг 2: динамика ---


def test_decay_priority_drops_monotonically(tmp_path: Path) -> None:
    """Прирост провалов → монотонное падение effective_priority."""
    from eurika.storage.paths import storage_path

    (tmp_path / ".eurika").mkdir(parents=True)
    base = 10.0
    scores_by_failures: dict[int, float] = {}
    for n in range(6):
        events_path = storage_path(tmp_path, "events")
        if events_path.exists():
            events_path.unlink()
        inject_failures(tmp_path, "x.py", "split_module", n)
        scores = {"x.py": base}
        reasons = {"x.py": ["god_module"]}
        apply_decay(scores, reasons, lambda _: "split_module", tmp_path)
        scores_by_failures[n] = scores["x.py"]
    # 0 → 1 → 2 → ... → 5: каждый шаг снижает score (или archive)
    assert scores_by_failures[0] == base
    assert scores_by_failures[1] < scores_by_failures[0]
    assert scores_by_failures[2] < scores_by_failures[1]
    assert scores_by_failures[5] < 2.0  # archived


def test_decay_archive_after_5(tmp_path: Path) -> None:
    """Ровно 5 провалов → archive (score *= 0.1)."""
    (tmp_path / ".eurika").mkdir(parents=True)
    inject_failures(tmp_path, "archived.py", "split_module", 5)
    scores = {"archived.py": 10.0, "fresh.py": 5.0}
    reasons = {"archived.py": ["god_module"], "fresh.py": ["hub"]}
    apply_decay(
        scores,
        reasons,
        lambda n: "split_module" if n == "archived.py" else "refactor_module",
        tmp_path,
    )
    assert scores["archived.py"] == 1.0  # 10 * 0.1
    assert scores["fresh.py"] == 5.0


# --- Шаг 3: восстановление после успеха ---


def test_decay_forgetting_old_failures(tmp_path: Path) -> None:
    """Step 4: старые провалы весят меньше. 4 old + 1 success vs 4 fresh — old выше."""
    import time

    from eurika.storage import ProjectMemory

    (tmp_path / ".eurika").mkdir(parents=True)
    mem = ProjectMemory(tmp_path)
    old_ts = time.time() - 60 * 86400
    for i in range(4):
        mem.events.append_event(
            "learn",
            {"project_root": str(tmp_path), "modules": ["old.py"], "operations": [{"target_file": "old.py", "kind": "split_module"}], "risks": []},
            {"failure_reason": "verify_failed"},
            False,
            timestamp=old_ts + i,
        )
    inject_success(tmp_path, "old.py", "split_module", 1)
    inject_failures(tmp_path, "fresh.py", "split_module", 4)
    scores = {"old.py": 10.0, "fresh.py": 10.0}
    reasons = {"old.py": ["god_module"], "fresh.py": ["god_module"]}
    apply_decay(scores, reasons, lambda _: "split_module", tmp_path)
    assert scores["old.py"] > scores["fresh.py"]


def test_decay_recovery_after_success(tmp_path: Path) -> None:
    """3 провала + 1 успех → приоритет восстанавливается (частично)."""
    from eurika.polygon.decay_polygon import inject_success

    (tmp_path / ".eurika").mkdir(parents=True)
    inject_failures(tmp_path, "recovered.py", "split_module", 3)
    scores_fail_only = {"recovered.py": 10.0}
    reasons = {"recovered.py": ["god_module"]}
    apply_decay(scores_fail_only, reasons, lambda _: "split_module", tmp_path)
    after_3_failures = scores_fail_only["recovered.py"]

    inject_success(tmp_path, "recovered.py", "split_module", 1)
    scores_with_success = {"recovered.py": 10.0}
    apply_decay(scores_with_success, reasons, lambda _: "split_module", tmp_path)
    after_recovery = scores_with_success["recovered.py"]

    assert after_3_failures < 10.0
    assert after_recovery > after_3_failures
    assert after_recovery < 10.0
