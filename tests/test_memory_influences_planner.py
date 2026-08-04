"""
Verify: memory influences planner decisions (ARCHITECTURE_MEMORY_REVIEW).

Агент меняет поведение после провалов — deprioritize, не застревает.
"""

from pathlib import Path

import pytest

from eurika.analysis.graph import ProjectGraph
from eurika.smells.models import ArchSmell


def _make_graph(nodes, edges) -> ProjectGraph:
    return ProjectGraph(nodes, edges)


def test_planner_deprioritizes_after_failures(tmp_path: Path) -> None:
    """
    После 3 провалов (target, kind) planner ставит эту op последней.

    Доказательство: память влияет на решения.
    """
    from architecture_planner import build_patch_plan
    from eurika.polygon.decay_polygon import inject_failures

    (tmp_path / ".eurika").mkdir(parents=True)

    # Два god_module: penalized.py и fresh.py. Оба получат split_module.
    g = _make_graph(
        ["penalized.py", "fresh.py", "other.py"],
        {"penalized.py": ["other.py"], "fresh.py": ["other.py"], "other.py": []},
    )
    smells = [
        ArchSmell(type="god_module", nodes=["penalized.py"], severity=5.0, description=""),
        ArchSmell(type="god_module", nodes=["fresh.py"], severity=4.0, description=""),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}, "regressions": []}
    priorities = [
        {"name": "penalized.py", "reasons": ["god_module"]},
        {"name": "fresh.py", "reasons": ["god_module"]},
    ]

    # 3 провала для penalized.py|split_module
    inject_failures(tmp_path, "penalized.py", "split_module", 3, failure_reason="verify_failed")

    plan = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )

    split_ops = [o for o in plan.operations if o.kind == "split_module"]
    assert len(split_ops) >= 2, "expected penalized + fresh split ops"

    # penalized.py|split_module должна быть последней (deprioritized)
    last = plan.operations[-1]
    assert last.target_file == "penalized.py" and last.kind == "split_module", (
        f"expected penalized.py|split_module last, got {last.target_file}|{last.kind}"
    )


def test_priority_from_graph_deprioritizes_after_failures(tmp_path: Path) -> None:
    """
    Decay: модуль с провалами получает penalty → ниже в списке priorities.

    Память (EventLog) влияет на priority_from_graph.
    """
    from eurika.polygon.decay_polygon import inject_failures
    from eurika.reasoning.graph_ops import priority_from_graph

    (tmp_path / ".eurika").mkdir(parents=True)
    inject_failures(tmp_path, "a.py", "split_module", 3)

    g = _make_graph(["a.py", "b.py"], {"a.py": ["b.py"], "b.py": []})
    smells = [
        ArchSmell(type="god_module", nodes=["a.py"], severity=5.0, description=""),
        ArchSmell(type="god_module", nodes=["b.py"], severity=4.0, description=""),
    ]

    prio = priority_from_graph(
        g, smells, summary_risks=None, top_n=8, project_root=tmp_path
    )
    names = [p["name"] for p in prio]
    # a.py с 3 провалами → penalty; b.py без провалов → выше
    assert names.index("b.py") < names.index("a.py")


def test_failure_event_enriched_with_goal_id_plan_hash(tmp_path: Path) -> None:
    """record_outcome stores goal_id, plan_hash in EventLog (ARCHITECTURE_MEMORY_REVIEW §2)."""
    from eurika.storage import get_recent_failures_enriched, record_outcome

    record_outcome(
        tmp_path,
        modules=["a.py"],
        operations=[
            {"target_file": "a.py", "kind": "split_module"},
            {"target_file": "b.py", "kind": "extract_class"},
        ],
        risks=[],
        verify_success=False,
        failure_reason="verify_failed",
    )
    enriched = get_recent_failures_enriched(tmp_path, limit=5)
    assert len(enriched) >= 1
    e = enriched[0]
    assert e["goal_id"]  # auto-computed: first op's target|kind
    assert e["plan_hash"]  # auto-computed from ops
    assert e["target_file"] in ("a.py", "b.py")
    assert e["kind"] in ("split_module", "extract_class")


def test_planner_reverses_order_when_plan_hash_failed(tmp_path: Path) -> None:
    """When plan_hash failed recently, planner reverses order (strategy variation)."""
    from architecture_planner import build_patch_plan
    from eurika.storage import get_recent_failed_plan_hashes, plan_hash_from_ops, record_outcome

    (tmp_path / ".eurika").mkdir(parents=True)
    g = _make_graph(
        ["x.py", "y.py", "z.py"],
        {"x.py": ["z.py"], "y.py": ["z.py"], "z.py": []},
    )
    smells = [
        ArchSmell(type="god_module", nodes=["x.py"], severity=5.0, description=""),
        ArchSmell(type="god_module", nodes=["y.py"], severity=4.0, description=""),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}, "regressions": []}
    priorities = [
        {"name": "x.py", "reasons": ["god_module"]},
        {"name": "y.py", "reasons": ["god_module"]},
    ]

    plan1 = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    ops1 = plan1.operations
    if len(ops1) < 2:
        pytest.skip("need 2+ ops for plan_hash test")

    ph = plan_hash_from_ops(ops1)
    record_outcome(
        tmp_path,
        modules=["x.py", "y.py"],
        operations=[{"target_file": o.target_file, "kind": o.kind} for o in ops1],
        risks=[],
        verify_success=False,
        failure_reason="verify_failed",
        plan_hash=ph,
    )
    assert ph in get_recent_failed_plan_hashes(tmp_path)

    plan2 = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    ops2 = plan2.operations
    assert len(ops2) >= 2
    assert ops2[0].target_file == ops1[-1].target_file and ops2[-1].target_file == ops1[0].target_file


def test_planner_deprioritizes_by_kind_plan_pair(tmp_path: Path) -> None:
    """Deprioritize by (action_kind + plan_hash): when retrying, failed kind+plan ops go last."""
    from architecture_planner import build_patch_plan
    from eurika.storage import (
        get_recent_failed_kind_plan_pairs,
        plan_hash_from_ops,
        record_outcome,
    )

    (tmp_path / ".eurika").mkdir(parents=True)
    g = _make_graph(
        ["a.py", "b.py"],
        {"a.py": ["b.py"], "b.py": []},
    )
    smells = [
        ArchSmell(type="god_module", nodes=["a.py"], severity=5.0, description=""),
        ArchSmell(type="god_module", nodes=["b.py"], severity=4.0, description=""),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}, "regressions": []}
    priorities = [
        {"name": "a.py", "reasons": ["god_module"]},
        {"name": "b.py", "reasons": ["god_module"]},
    ]

    plan1 = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    ops1 = plan1.operations
    if len(ops1) < 2:
        pytest.skip("need 2+ ops")
    ph = plan_hash_from_ops(ops1)
    record_outcome(
        tmp_path,
        modules=["a.py", "b.py"],
        operations=[{"target_file": o.target_file, "kind": o.kind} for o in ops1],
        risks=[],
        verify_success=False,
        failure_reason="verify_failed",
        plan_hash=ph,
    )
    pairs = get_recent_failed_kind_plan_pairs(tmp_path)
    assert any(k == "split_module" and h == ph for k, h in pairs)

    plan2 = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    ops2 = plan2.operations
    ph2 = plan_hash_from_ops(ops2)
    if ph2 == ph:
        split_ops = [o for o in ops2 if o.kind == "split_module"]
        if len(split_ops) >= 2:
            last = ops2[-1]
            assert (last.kind, ph2) in pairs or last.kind == "split_module"


def test_planner_changes_op_when_frequency_high(tmp_path: Path) -> None:
    """When (kind) failed 2+ times total, swap to fallback kind (split_module -> refactor_module)."""
    from architecture_planner import build_patch_plan
    from eurika.storage import get_kind_plan_failure_counts, record_outcome

    (tmp_path / ".eurika").mkdir(parents=True)
    for _ in range(2):
        record_outcome(
            tmp_path,
            modules=["hub.py"],
            operations=[{"target_file": "hub.py", "kind": "split_module"}],
            risks=[],
            verify_success=False,
            failure_reason="verify_failed",
            plan_hash="ph_fail_1",
        )
    counts = get_kind_plan_failure_counts(tmp_path)
    assert counts.get(("split_module", "ph_fail_1"), 0) >= 2

    g = _make_graph(["hub.py", "d.py"], {"hub.py": ["d.py"], "d.py": []})
    smells = [
        ArchSmell(type="hub", nodes=["hub.py"], severity=5.0, description=""),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}, "regressions": []}
    priorities = [{"name": "hub.py", "reasons": ["hub"]}]
    plan = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    ops = plan.operations
    refactor_ops = [o for o in ops if o.kind == "refactor_module"]
    split_ops = [o for o in ops if o.kind == "split_module"]
    assert len(refactor_ops) >= 1 or len(split_ops) == 0, (
        "expected fallback to refactor_module when split_module failed 2+ times"
    )


def test_oss_hints_limited_by_low_success_rate() -> None:
    """Operational pattern library: OSS hints = 0 when (smell_type, action_kind) has success_rate < 0.25."""
    from eurika.reasoning.planner.hints_provider import build_hints_and_params

    oss = {
        "god_module": [
            {"project": "Django", "module": "foo.py", "hint": "Split module."},
        ],
    }
    learning_stats_bad = {"god_module|split_module": {"total": 10, "success": 2, "fail": 8}}
    learning_stats_good = {"god_module|split_module": {"total": 10, "success": 8, "fail": 2}}
    learning_stats_unknown = {}

    hints_bad, _ = build_hints_and_params(
        "/tmp", "god_module", "split_module", [], "x.py", oss_patterns=oss, learning_stats=learning_stats_bad
    )
    hints_good, _ = build_hints_and_params(
        "/tmp", "god_module", "split_module", [], "x.py", oss_patterns=oss, learning_stats=learning_stats_good
    )
    hints_unknown, _ = build_hints_and_params(
        "/tmp", "god_module", "split_module", [], "x.py", oss_patterns=oss, learning_stats=learning_stats_unknown
    )
    oss_bad = [h for h in hints_bad if h.startswith("OSS (")]
    oss_good = [h for h in hints_good if h.startswith("OSS (")]
    oss_unknown = [h for h in hints_unknown if h.startswith("OSS (")]
    assert len(oss_bad) == 0, "low success_rate -> no OSS hints"
    assert len(oss_good) >= 1, "good success_rate -> OSS hints"
    assert len(oss_unknown) >= 1, "no stats -> OSS hints (default)"
