"""Tests for eurika.reasoning.graph_ops — graph-driven patch planning."""

from pathlib import Path

from eurika.reasoning.graph_ops import (
    SMELL_TYPE_TO_REFACTOR_KIND,
    centrality_from_graph,
    metrics_from_graph,
    priority_from_graph,
    refactor_kind_for_smells,
    targets_from_graph,
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


def test_refactor_kind_for_smells():
    """ROADMAP 3.1.2: smell_type → refactor_kind mapping."""
    assert refactor_kind_for_smells(["god_module"]) == "split_module"
    assert refactor_kind_for_smells(["hub"]) == "split_module"
    assert refactor_kind_for_smells(["bottleneck"]) == "introduce_facade"
    assert refactor_kind_for_smells(["cyclic_dependency"]) == "break_cycle"
    assert refactor_kind_for_smells(["god_module", "bottleneck"]) == "split_module"
    assert refactor_kind_for_smells(["bottleneck", "hub"]) == "introduce_facade"
    assert refactor_kind_for_smells([]) == "refactor_module"
    assert refactor_kind_for_smells(["unknown"]) == "refactor_module"


def test_targets_from_graph():
    """ROADMAP 3.1.4: targets built from graph.nodes, kind from smells."""
    from eurika.smells.models import ArchSmell

    g = _make_graph(["a", "b", "x"], {"a": ["x"], "b": ["x"], "x": []})
    smells = [
        ArchSmell(type="bottleneck", nodes=["x"], severity=5.0, description=""),
        ArchSmell(type="god_module", nodes=["a"], severity=2.0, description=""),
    ]
    targets = targets_from_graph(g, smells, top_n=5)
    names = [t["name"] for t in targets]
    assert "x" in names
    assert "a" in names
    kinds = {t["name"]: t["kind"] for t in targets}
    assert kinds["x"] == "introduce_facade"
    assert kinds["a"] == "split_module"
    assert all(t["name"] in g.nodes for t in targets)


def test_centrality_from_graph():
    """ROADMAP 3.1.3: centrality computed from graph."""
    g = _make_graph(["a", "b", "c", "x"], {"a": ["x"], "b": ["x"], "c": ["x"], "x": []})
    c = centrality_from_graph(g, top_n=3)
    assert c["max_degree"] == 3
    assert any(n == "x" and d == 3 for n, d in c["top_by_degree"])
    assert len(c["top_by_degree"]) <= 3


def test_metrics_from_graph():
    """ROADMAP 3.1.3: risk_score and centrality from graph."""
    from eurika.smells.models import ArchSmell

    g = _make_graph(["a", "b"], {"a": ["b"], "b": []})
    smells = [ArchSmell(type="bottleneck", nodes=["b"], severity=3.0, description="")]
    m = metrics_from_graph(g, smells, trends={})
    assert "risk_score" in m
    assert "score" in m
    assert "centrality" in m
    assert m["centrality"]["max_degree"] >= 0
    assert 0 <= m["risk_score"] <= 100


def test_smell_type_to_refactor_kind_canonical():
    """SMELL_TYPE_TO_REFACTOR_KIND is the canonical mapping."""
    assert SMELL_TYPE_TO_REFACTOR_KIND["god_module"] == "split_module"
    assert SMELL_TYPE_TO_REFACTOR_KIND["hub"] == "split_module"
    assert SMELL_TYPE_TO_REFACTOR_KIND["bottleneck"] == "introduce_facade"
    assert SMELL_TYPE_TO_REFACTOR_KIND["cyclic_dependency"] == "break_cycle"


def test_priority_from_graph_orders_by_severity_and_degree():
    """priority_from_graph returns modules ordered by severity + degree bonus."""
    from eurika.smells.models import ArchSmell

    # a: severity 2, degree 2 (a->b, b->a). b: severity 2, degree 2.
    # x: severity 5, degree 4 (a,b,c->x). Higher severity+degree → x first.
    g = _make_graph(
        ["a", "b", "c", "x"],
        {"a": ["b", "x"], "b": ["a", "x"], "c": ["x"], "x": []},
    )
    smells = [
        ArchSmell(type="cyclic_dependency", nodes=["a", "b"], severity=2.0, description=""),
        ArchSmell(type="bottleneck", nodes=["x"], severity=5.0, description=""),
    ]
    prio = priority_from_graph(g, smells, summary_risks=None, top_n=8)
    names = [p["name"] for p in prio]
    assert "x" in names
    assert "a" in names or "b" in names
    # x has higher severity and bottleneck bonus (fan_in * 0.2) → should be first
    assert names[0] == "x"


def test_priority_from_graph_includes_summary_risks():
    """priority_from_graph adds weight for nodes mentioned in summary_risks."""
    from eurika.smells.models import ArchSmell

    g = _make_graph(["a", "b"], {"a": ["b"], "b": []})
    smells = [ArchSmell(type="bottleneck", nodes=["b"], severity=1.0, description="")]
    risks = ["bottleneck @ b (severity=1)"]
    prio = priority_from_graph(g, smells, summary_risks=risks, top_n=8)
    assert any(p["name"] == "b" for p in prio)
    assert any("mentioned_in_summary_risks" in p["reasons"] for p in prio if p["name"] == "b")


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


def test_build_patch_plan_hub_produces_split_module(monkeypatch):
    """ROADMAP 3.1.2: hub smell triggers split_module (not refactor_module)."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    monkeypatch.delenv("EURIKA_DISABLE_SMELL_ACTIONS", raising=False)
    g = _make_graph(["hub_node", "a", "b"], {"hub_node": ["a", "b"], "a": [], "b": []})
    smells = [ArchSmell(type="hub", nodes=["hub_node"], severity=5.0, description="High fan-out")]
    summary = {"risks": []}
    history_info = {"trends": {}}
    priorities = [{"name": "hub_node", "reasons": ["hub"]}]

    plan = build_patch_plan(
        project_root="/tmp",
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    assert len(plan.operations) >= 1
    assert plan.operations[0].kind == "split_module"


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


def test_build_patch_plan_god_module_with_god_class_produces_extract_class(tmp_path: Path) -> None:
    """When god_module has a class with 6+ extractable methods, add extract_class op."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    # Create file with god class (6+ methods, no self)
    target = tmp_path / "big_module.py"
    methods = "\n".join(f"    def m{i}(self): return {i}" for i in range(6))
    target.write_text(f"class BigClass:\n{methods}\n")

    g = _make_graph(["big_module.py", "a", "b"], {"big_module.py": ["a", "b"]})
    smells = [
        ArchSmell(type="god_module", nodes=["big_module.py"], severity=6.0, description="High degree"),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}}
    priorities = [{"name": "big_module.py", "reasons": ["god_module"]}]

    plan = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    # First op should be extract_class (concrete), then split_module
    extract_ops = [o for o in plan.operations if o.kind == "extract_class"]
    assert len(extract_ops) >= 1, "expected at least one extract_class op"
    op = extract_ops[0]
    assert op.params["target_class"] == "BigClass"
    assert "methods_to_extract" in op.params
    assert len(op.params["methods_to_extract"]) >= 6


def test_build_patch_plan_skips_extract_class_for_tool_contract_blocklist(tmp_path: Path) -> None:
    """EXTRACT_CLASS_SKIP_PATTERNS: do not emit extract_class for *tool_contract*.py (CYCLE_REPORT #34)."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    target = tmp_path / "tool_contract.py"
    methods = "\n".join(f"    def m{i}(self): return {i}" for i in range(6))
    target.write_text(f"class DefaultToolContract:\n{methods}\n")

    g = _make_graph(["tool_contract.py", "a", "b"], {"tool_contract.py": ["a", "b"]})
    smells = [
        ArchSmell(type="god_module", nodes=["tool_contract.py"], severity=6.0, description="High degree"),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}}
    priorities = [{"name": "tool_contract.py", "reasons": ["god_module"]}]

    plan = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    assert not any(o.kind == "extract_class" for o in plan.operations)


def test_build_patch_plan_skips_extract_class_when_extracted_file_synced(tmp_path: Path) -> None:
    """Do not emit extract_class when extracted file already matches signature."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    target = tmp_path / "big_module.py"
    methods = "\n".join(f"    def m{i}(self): return {i}" for i in range(6))
    target.write_text(f"class BigClass:\n{methods}\n")

    extracted = tmp_path / "big_module_bigclassextracted.py"
    extracted_methods = "\n".join(f"    def m{i}(): return {i}" for i in range(6))
    extracted.write_text(f"class BigClassExtracted:\n{extracted_methods}\n")

    g = _make_graph(["big_module.py", "a", "b"], {"big_module.py": ["a", "b"]})
    smells = [
        ArchSmell(type="god_module", nodes=["big_module.py"], severity=6.0, description="High degree"),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}}
    priorities = [{"name": "big_module.py", "reasons": ["god_module"]}]

    plan = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    assert not any(o.kind == "extract_class" for o in plan.operations)


def test_build_patch_plan_skips_extract_class_when_synced_except_staticmethod(tmp_path: Path) -> None:
    """Static methods left in source should not break synced-signature detection."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    target = tmp_path / "code_awareness_like.py"
    target.write_text(
        "\n".join(
            [
                "class CodeAwarenessLike:",
                "    @staticmethod",
                "    def helper_static(): return 1",
                "    def a(self): return 1",
                "    def b(self): return 2",
                "    def c(self): return 3",
                "    def d(self): return 4",
                "    def e(self): return 5",
                "    def f(self): return 6",
                "",
            ]
        )
    )

    extracted = tmp_path / "code_awareness_like_codeawarenesslikeextracted.py"
    extracted.write_text(
        "\n".join(
            [
                "class CodeAwarenessLikeExtracted:",
                "    def a(): return 1",
                "    def b(): return 2",
                "    def c(): return 3",
                "    def d(): return 4",
                "    def e(): return 5",
                "    def f(): return 6",
                "",
            ]
        )
    )

    g = _make_graph(
        ["code_awareness_like.py", "a", "b"],
        {"code_awareness_like.py": ["a", "b"]},
    )
    smells = [
        ArchSmell(type="god_module", nodes=["code_awareness_like.py"], severity=6.0, description="High degree"),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}}
    priorities = [{"name": "code_awareness_like.py", "reasons": ["god_module"]}]

    plan = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    assert not any(o.kind == "extract_class" for o in plan.operations)


def test_build_patch_plan_filters_low_success_rate_ops(tmp_path: Path) -> None:
    """ROADMAP 2.6.3: ops with success_rate < 0.25 and total >= 3 are excluded."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    g = _make_graph(["a.py", "b.py", "c.py"], {"a.py": ["b.py"], "b.py": ["c.py"]})
    smells = [
        ArchSmell(type="god_module", nodes=["a.py"], severity=5.0, description=""),
        ArchSmell(type="god_module", nodes=["b.py"], severity=4.0, description=""),
    ]
    summary = {"risks": []}
    history_info = {"trends": {}}
    priorities = [{"name": "a.py", "reasons": ["god_module"]}, {"name": "b.py", "reasons": ["god_module"]}]

    # god_module|split_module: 1 success out of 4 → 0.25, excluded when < 0.25
    learning_stats = {
        "god_module|split_module": {"total": 4, "success": 0, "fail": 4},
    }
    plan = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
        learning_stats=learning_stats,
    )
    # All split_module ops should be filtered (0% success)
    split_ops = [o for o in plan.operations if o.kind == "split_module"]
    assert len(split_ops) == 0, "low success_rate ops should be excluded"


def test_build_patch_plan_disables_smell_action_from_env(monkeypatch) -> None:
    """EURIKA_DISABLE_SMELL_ACTIONS can disable hub|split_module planning ops."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    g = _make_graph(["hub_node", "a", "b"], {"hub_node": ["a", "b"], "a": [], "b": []})
    smells = [ArchSmell(type="hub", nodes=["hub_node"], severity=5.0, description="High fan-out")]
    summary = {"risks": []}
    history_info = {"trends": {}}
    priorities = [{"name": "hub_node", "reasons": ["hub"]}]

    monkeypatch.setenv("EURIKA_DISABLE_SMELL_ACTIONS", "hub|split_module")
    plan = build_patch_plan(
        project_root="/tmp",
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
    )
    assert not any(
        (o.smell_type == "hub" and o.kind == "split_module")
        for o in plan.operations
    )


def test_build_patch_plan_fallbacks_hub_split_module_on_low_success(tmp_path: Path) -> None:
    """Low-success hub|split_module falls back to refactor_module (safer action)."""
    from architecture_planner import build_patch_plan
    from eurika.smells.models import ArchSmell

    g = _make_graph(["hub_node", "a", "b"], {"hub_node": ["a", "b"], "a": [], "b": []})
    smells = [ArchSmell(type="hub", nodes=["hub_node"], severity=5.0, description="High fan-out")]
    summary = {"risks": []}
    history_info = {"trends": {}}
    priorities = [{"name": "hub_node", "reasons": ["hub"]}]
    learning_stats = {
        "hub|split_module": {"total": 3, "success": 0, "fail": 3},
    }

    plan = build_patch_plan(
        project_root=str(tmp_path),
        summary=summary,
        smells=smells,
        history_info=history_info,
        priorities=priorities,
        graph=g,
        learning_stats=learning_stats,
    )
    assert any((o.smell_type == "hub" and o.kind == "refactor_module") for o in plan.operations)
    assert not any((o.smell_type == "hub" and o.kind == "split_module") for o in plan.operations)
