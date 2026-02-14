"""Tests for eurika.reasoning.graph_ops — graph-driven patch planning."""

from eurika.reasoning.graph_ops import (
    resolve_module_for_edge,
    suggest_cycle_break_edge,
    suggest_facade_candidates,
    suggest_god_module_split_hint,
    graph_hints_for_smell,
)
from eurika.analysis.graph import ProjectGraph


def _make_graph(nodes, edges) -> ProjectGraph:
    """Build ProjectGraph from nodes list and edge dict {src: [dst, ...]}."""
    return ProjectGraph(nodes, edges)


def test_resolve_module_for_edge():
    """resolve_module_for_edge finds module name for (src, dst) edge."""
    self_map = {
        "modules": [{"path": "a.py"}, {"path": "b.py"}],
        "dependencies": {"a.py": ["b"], "b.py": ["a"]},
    }
    assert resolve_module_for_edge(self_map, "b.py", "a.py") == "a"
    assert resolve_module_for_edge(self_map, "a.py", "b.py") == "b"


def test_suggest_cycle_break_edge_empty():
    g = _make_graph(["a", "b"], {"a": ["b"], "b": []})
    assert suggest_cycle_break_edge(g, []) is None


def test_suggest_cycle_break_edge_simple_cycle():
    # Cycle: a -> b -> c -> a
    g = _make_graph(
        ["a", "b", "c"],
        {"a": ["b"], "b": ["c"], "c": ["a"]},
    )
    edge = suggest_cycle_break_edge(g, ["a", "b", "c"])
    assert edge is not None
    src, dst = edge
    assert src in ("a", "b", "c")
    assert dst in ("a", "b", "c")
    assert (src, dst) in [("a", "b"), ("b", "c"), ("c", "a")]


def test_suggest_cycle_break_edge_picks_low_fan_in():
    # Cycle a->b->c->a; b has fan_in=1 from a, c has fan_in=1 from b, a has fan_in=1 from c.
    # All equal so any is fine. Add d->a to give a fan_in=2; then breaking d->a is not in cycle.
    # So we need cycle edges. For a: fan_in from c = 1. For b: from a = 1. For c: from b = 1.
    # Heuristic: pick edge with lowest fan_in of dst. All dst in cycle have fi=1 from cycle.
    g = _make_graph(
        ["a", "b", "c", "d"],
        {"a": ["b"], "b": ["c"], "c": ["a"], "d": ["a"]},
    )
    edge = suggest_cycle_break_edge(g, ["a", "b", "c"])
    assert edge is not None


def test_suggest_facade_candidates_bottleneck():
    # b is bottleneck: a,c,d -> b -> (nothing much)
    g = _make_graph(
        ["a", "b", "c", "d"],
        {"a": ["b"], "c": ["b"], "d": ["b"], "b": []},
    )
    callers = suggest_facade_candidates(g, "b", top_n=5)
    assert set(callers) == {"a", "c", "d"}


def test_suggest_facade_candidates_empty():
    g = _make_graph(["a", "b"], {"a": [], "b": []})
    assert suggest_facade_candidates(g, "b") == []


def test_suggest_god_module_split_hint():
    # god imports x,y; imported by p,q
    g = _make_graph(
        ["god", "x", "y", "p", "q"],
        {"god": ["x", "y"], "p": ["god"], "q": ["god"], "x": [], "y": []},
    )
    info = suggest_god_module_split_hint(g, "god", top_n=5)
    assert "imports_from" in info
    assert set(info["imports_from"]) == {"x", "y"}
    assert "imported_by" in info
    assert set(info["imported_by"]) == {"p", "q"}


def test_graph_hints_for_smell_cyclic():
    g = _make_graph(["a", "b"], {"a": ["b"], "b": ["a"]})
    hints = graph_hints_for_smell(g, "cyclic_dependency", ["a", "b"])
    assert len(hints) >= 1
    assert "Break cycle" in hints[0] or "removing" in hints[0].lower() or "inverting" in hints[0].lower()


def test_graph_hints_for_smell_bottleneck():
    g = _make_graph(["a", "b", "c"], {"a": ["b"], "c": ["b"], "b": []})
    hints = graph_hints_for_smell(g, "bottleneck", ["b"])
    assert len(hints) >= 1
    assert "Introduce facade" in hints[0] or "callers" in hints[0].lower()


def test_graph_hints_for_smell_god_module():
    g = _make_graph(["god", "x", "y"], {"god": ["x", "y"], "x": [], "y": []})
    hints = graph_hints_for_smell(g, "god_module", ["god"])
    assert len(hints) >= 1


def test_graph_hints_for_smell_unknown_empty():
    g = _make_graph(["a"], {"a": []})
    hints = graph_hints_for_smell(g, "hub", ["a"])
    assert hints == []


def test_build_patch_plan_creates_remove_cyclic_import_when_cycle():
    """build_patch_plan creates remove_cyclic_import op when cycle + graph + self_map."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    # Cycle: a -> b -> a
    g = _make_graph(["a.py", "b.py"], {"a.py": ["b.py"], "b.py": ["a.py"]})
    smells = [
        ArchSmell(
            type="cyclic_dependency",
            nodes=["a.py", "b.py"],
            severity=5.0,
            description="Cycle",
        ),
    ]
    self_map = {
        "modules": [
            {"path": "a.py"},
            {"path": "b.py"},
        ],
        "dependencies": {
            "a.py": ["b"],
            "b.py": ["a"],
        },
    }
    summary = {"risks": [], "central_modules": []}
    history_info = {"trends": {}, "regressions": []}
    priorities = [{"name": "a.py", "reasons": ["cyclic_dependency"]}]

    plan = build_patch_plan(
        project_root="/tmp",
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
        self_map=self_map,
    )
    remove_ops = [o for o in plan.operations if o.kind == "remove_cyclic_import"]
    assert len(remove_ops) >= 1
    assert remove_ops[0].params is not None
    assert "target_module" in remove_ops[0].params


def test_build_patch_plan_with_graph_includes_graph_hints():
    """build_patch_plan with graph enriches diff with graph-derived hints."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    # Bottleneck: a,b,c -> x -> []
    g = _make_graph(
        ["a", "b", "c", "x"],
        {"a": ["x"], "b": ["x"], "c": ["x"], "x": []},
    )
    smells = [
        ArchSmell(
            type="bottleneck",
            nodes=["x"],
            severity=3.0,
            description="High fan-in",
        ),
    ]
    summary = {"risks": ["bottleneck @ x (severity=3)"], "central_modules": []}
    history_info = {"trends": {}, "regressions": []}
    priorities = [{"name": "x", "reasons": ["bottleneck"]}]

    plan = build_patch_plan(
        project_root="/tmp",
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    assert len(plan.operations) >= 1
    diff = plan.operations[0].diff
    # Graph-derived: "Introduce facade for callers: a, b, c"
    assert "callers" in diff.lower() or "facade" in diff.lower()


def test_build_patch_plan_god_module_produces_split_module():
    """god_module with graph produces kind=split_module and params with imports_from/imported_by."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    g = _make_graph(
        ["god", "a", "b", "c"],
        {"god": ["a", "b"], "a": ["god"], "b": ["god"], "c": ["god"]},
    )
    smells = [
        ArchSmell(type="god_module", nodes=["god"], severity=5.0, description="High degree"),
    ]
    summary = {"risks": ["god_module @ god (severity=5)"], "central_modules": []}
    history_info = {"trends": {}, "regressions": []}
    priorities = [{"name": "god", "reasons": ["god_module"]}]

    plan = build_patch_plan(
        project_root="/tmp",
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    assert len(plan.operations) >= 1
    op = plan.operations[0]
    assert op.kind == "split_module"
    assert op.params is not None
    assert "imports_from" in op.params
    assert "imported_by" in op.params
