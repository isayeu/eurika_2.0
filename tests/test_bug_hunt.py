"""C.14 v1.5 bug-hunt propose: pick → sandbox → Approvals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eurika.api.chat_direct import is_bug_hunt_request, is_polygon_propose_request
from eurika.orchestration.bug_hunt import (
    filter_bug_hunt_candidates,
    format_bug_hunt_summary,
    pick_bug_hunt_operation,
    run_bug_hunt_propose,
)
from eurika.orchestration.team_mode import has_pending_plan, load_pending_plan


def _op(
    *,
    target: str,
    kind: str = "extract_block_to_helper",
    smell: str = "deep_nesting",
) -> dict[str, Any]:
    return {
        "target_file": target,
        "kind": kind,
        "smell_type": smell,
        "description": f"{kind} on {target}",
        "params": {"location": "demo"},
        "diff": "",
    }


def test_filter_excludes_polygon_and_unsafe() -> None:
    ops = [
        _op(target="eurika/polygon/deep_nesting.py"),
        _op(target="eurika/knowledge/topics.py"),
        _op(target="eurika/api/chat.py", kind="todo_marker"),
        _op(target="eurika/api/ops.py", kind="llm_extract_block"),
    ]
    filtered = filter_bug_hunt_candidates(ops, deny=set(), allow_llm=False)
    assert len(filtered) == 1
    assert filtered[0]["target_file"] == "eurika/knowledge/topics.py"


def test_filter_skips_deny_pairs() -> None:
    ops = [
        _op(target="eurika/a.py"),
        _op(target="eurika/b.py"),
    ]
    filtered = filter_bug_hunt_candidates(
        ops,
        deny={("eurika/a.py", "extract_block_to_helper")},
        allow_llm=False,
    )
    assert [o["target_file"] for o in filtered] == ["eurika/b.py"]


def test_pick_prefers_safe_non_polygon(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._deny_keys",
        lambda _root: set(),
    )
    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._prefer_keys",
        lambda _root: {("eurika/knowledge/topics.py", "extract_nested_function")},
    )
    for rel in (
        "eurika/polygon/imports_ok.py",
        "eurika/api/foo.py",
        "eurika/knowledge/topics.py",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    ops = [
        _op(target="eurika/polygon/imports_ok.py", kind="remove_unused_import"),
        _op(target="eurika/api/foo.py", kind="extract_block_to_helper"),
        _op(
            target="eurika/knowledge/topics.py",
            kind="extract_nested_function",
            smell="long_function",
        ),
    ]
    picked = pick_bug_hunt_operation(tmp_path, operations=ops)
    assert picked is not None
    assert picked["target_file"] == "eurika/knowledge/topics.py"
    assert picked["kind"] == "extract_nested_function"


def test_filter_skips_market_ml_under_freeze() -> None:
    ops = [
        _op(target="eurika/ml/market_model.py"),
        _op(target="eurika/api/chat_utils.py"),
    ]
    filtered = filter_bug_hunt_candidates(ops, deny=set(), allow_llm=False)
    assert [o["target_file"] for o in filtered] == ["eurika/api/chat_utils.py"]


def test_filter_skips_trivial_extract_block() -> None:
    ops = [
        {
            "target_file": "cli/core_handlers_prove_cycle.py",
            "kind": "extract_block_to_helper",
            "description": "Extract nested block from cli/x.py:f (line 59, 3 lines)",
            "params": {"location": "f", "block_start_line": 59, "line_count": 3},
        },
        _op(target="eurika/alive.py"),
    ]
    filtered = filter_bug_hunt_candidates(ops, deny=set(), allow_llm=False)
    assert [o["target_file"] for o in filtered] == ["eurika/alive.py"]


def test_filter_skips_missing_target_files(tmp_path: Path) -> None:
    alive = tmp_path / "eurika" / "alive.py"
    alive.parent.mkdir(parents=True)
    alive.write_text("x = 1\n", encoding="utf-8")
    ops = [
        _op(target="eurika/night_train.py"),
        _op(target="eurika/alive.py"),
    ]
    filtered = filter_bug_hunt_candidates(
        ops, deny=set(), allow_llm=False, project_root=tmp_path
    )
    assert [o["target_file"] for o in filtered] == ["eurika/alive.py"]


def test_run_bug_hunt_blocks_when_pending_exists(tmp_path: Path) -> None:
    eurika = tmp_path / ".eurika"
    eurika.mkdir(parents=True)
    (eurika / "pending_plan.json").write_text(
        '{"operations":[{"kind":"x","target_file":"a.py","team_decision":"pending"}]}',
        encoding="utf-8",
    )
    out = run_bug_hunt_propose(
        tmp_path,
        operations=[_op(target="eurika/a.py")],
        sandbox=False,
    )
    assert out["ok"] is False
    assert "pending" in str(out.get("error") or "").lower()


def test_run_bug_hunt_sandbox_fail_does_not_park(
    tmp_path: Path, monkeypatch: Any
) -> None:
    target = tmp_path / "eurika" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("def demo():\n    return 1\n", encoding="utf-8")
    ops = [_op(target="eurika/demo.py")]

    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._preflight_bug_hunt_op",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "eurika.orchestration.propose_sandbox.create_propose_sandbox",
        lambda root, drill_id="bug_hunt", **_k: {
            "path": tmp_path / ".eurika" / "sandbox" / "propose_bug_hunt_x",
            "mode": "copy",
            "name": "propose_bug_hunt_x",
        },
    )
    sandbox_path = tmp_path / ".eurika" / "sandbox" / "propose_bug_hunt_x"
    sandbox_path.mkdir(parents=True)

    def _fail_verify(_root, _op, *, drill_id):
        return {"ok": False, "error": "syntax boom", "modified": []}

    monkeypatch.setattr(
        "eurika.orchestration.propose_sandbox.apply_and_smoke_verify",
        _fail_verify,
    )
    monkeypatch.setattr(
        "eurika.orchestration.propose_sandbox.remove_propose_sandbox",
        lambda *_a, **_k: None,
    )

    out = run_bug_hunt_propose(tmp_path, operations=ops, sandbox=True, web=False)
    assert out["ok"] is False
    assert "sandbox verify failed" in str(out.get("error") or "")
    assert not has_pending_plan(tmp_path)


def test_anti_repeat_skips_recent_then_falls_back(tmp_path: Path, monkeypatch: Any) -> None:
    from eurika.orchestration.bug_hunt import remember_bug_hunt_propose

    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._deny_keys",
        lambda _root: set(),
    )
    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._prefer_keys",
        lambda _root: set(),
    )
    for rel in ("eurika/a.py", "eurika/b.py"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    ops = [
        _op(target="eurika/a.py"),
        _op(target="eurika/b.py"),
    ]
    remember_bug_hunt_propose(tmp_path, target_file="eurika/a.py", kind="extract_block_to_helper")
    picked = pick_bug_hunt_operation(tmp_path, operations=ops)
    assert picked is not None
    assert picked["target_file"] == "eurika/b.py"
    remember_bug_hunt_propose(tmp_path, target_file="eurika/b.py", kind="extract_block_to_helper")
    # Both recent → fall back to a repeat (prefer lexically first after score).
    picked2 = pick_bug_hunt_operation(tmp_path, operations=ops)
    assert picked2 is not None
    assert picked2["target_file"] in {"eurika/a.py", "eurika/b.py"}


def test_smoke_bug_hunt_requires_change() -> None:
    from eurika.orchestration.bug_hunt import smoke_bug_hunt_change

    op = _op(target="eurika/demo.py", kind="extract_block_to_helper")
    same = smoke_bug_hunt_change(before="x", after="x", operation=op, modified=[])
    assert same["ok"] is False
    ok = smoke_bug_hunt_change(
        before="def f():\n    return 1\n",
        after="def _extracted_block_1():\n    return 1\ndef f():\n    return _extracted_block_1()\n",
        operation=op,
        modified=["eurika/demo.py"],
    )
    assert ok["ok"] is True


def test_smoke_bug_hunt_rejects_bare_extracted_call() -> None:
    """Regression: try/except extract that left `_extracted_block_*(...)` as Expr must fail smoke."""
    from eurika.orchestration.bug_hunt import smoke_bug_hunt_change

    op = _op(target="eurika/api/chat_vector.py", kind="extract_block_to_helper")
    bad = (
        "def _extracted_block_142(sim_cfg):\n"
        "    try:\n"
        "        threshold = float(sim_cfg)\n"
        "    except (TypeError, ValueError):\n"
        "        threshold = 0.7\n"
        "def match_fuzzy(sim_cfg):\n"
        "    threshold = 0.7\n"
        "    if sim_cfg is not None:\n"
        "        _extracted_block_142(sim_cfg)\n"
        "    return threshold\n"
    )
    result = smoke_bug_hunt_change(
        before="def match_fuzzy(sim_cfg):\n    return 0.7\n",
        after=bad,
        operation=op,
        modified=["eurika/api/chat_vector.py"],
    )
    assert result["ok"] is False
    assert "discards helper result" in str(result.get("error") or "")


def test_smoke_bug_hunt_allows_bare_call_mutating_param_dict() -> None:
    """Side-effect extract that only mutates kwargs[…] may use a bare call."""
    from eurika.orchestration.bug_hunt import smoke_bug_hunt_change

    op = _op(target="eurika/reasoning/architect.py", kind="extract_block_to_helper")
    after = (
        "def _extracted_block_184(api_key, base, kwargs, model):\n"
        "    kwargs['model'] = model\n"
        "    kwargs['api_base'] = base\n"
        "    if api_key:\n"
        "        kwargs['api_key'] = api_key\n"
        "def f(api_key, base, kwargs, model):\n"
        "    if base:\n"
        "        _extracted_block_184(api_key, base, kwargs, model)\n"
        "    return kwargs\n"
    )
    result = smoke_bug_hunt_change(
        before="def f(api_key, base, kwargs, model):\n    return kwargs\n",
        after=after,
        operation=op,
        modified=["eurika/reasoning/architect.py"],
    )
    assert result["ok"] is True


def test_smoke_bug_hunt_rejects_assign_without_helper_return() -> None:
    from eurika.orchestration.bug_hunt import smoke_bug_hunt_change

    op = _op(target="eurika/demo.py", kind="extract_block_to_helper")
    bad = (
        "def _extracted_block_1(x):\n"
        "    y = x + 1\n"
        "def f(x):\n"
        "    y = _extracted_block_1(x)\n"
        "    return y\n"
    )
    result = smoke_bug_hunt_change(
        before="def f(x):\n    return x\n",
        after=bad,
        operation=op,
        modified=["eurika/demo.py"],
    )
    assert result["ok"] is False
    assert "no return" in str(result.get("error") or "")


def test_smoke_bug_hunt_rejects_nested_formatting_churn() -> None:
    from eurika.orchestration.bug_hunt import smoke_bug_hunt_change

    op = {
        "target_file": "eurika/api/chat_host_ops.py",
        "kind": "extract_nested_function",
        "params": {"location": "run_llm_tool_loop", "nested_function_name": "_finalize"},
    }
    before = "def outer():\n    def _finalize():\n        return 1\n    return _finalize()\n" + ("x = 1\n" * 50)
    after = (
        "def _finalize():\n    return 1\n"
        "def outer():\n    return _finalize()\n"
        + ("x = '1'\n" * 50)
    )
    result = smoke_bug_hunt_change(
        before=before, after=after, operation=op, modified=["eurika/api/chat_host_ops.py"]
    )
    assert result["ok"] is False
    assert "formatting churn" in str(result.get("error") or "")


def test_filter_skips_trivial_nested_extract() -> None:
    ops = [
        {
            "target_file": "eurika/api/chat_host_ops.py",
            "kind": "extract_nested_function",
            "description": "Extract nested function _finalize from x:y (3 lines)",
            "params": {"location": "y", "nested_function_name": "_finalize", "line_count": 3},
        },
        _op(target="eurika/alive.py"),
    ]
    filtered = filter_bug_hunt_candidates(ops, deny=set(), allow_llm=False)
    assert [o["target_file"] for o in filtered] == ["eurika/alive.py"]


def test_run_bug_hunt_skips_noop_extract_and_tries_next(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Preflight no-op extract is skipped; next ranked candidate can park."""
    bad = tmp_path / "eurika" / "bad.py"
    good = tmp_path / "eurika" / "good.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("def demo():\n    return 1\n", encoding="utf-8")
    good.write_text("def demo():\n    return 1\n", encoding="utf-8")
    ops = [
        _op(target="eurika/bad.py"),
        _op(target="eurika/good.py"),
    ]

    def _preflight(root: Path, operation: dict[str, Any]) -> str | None:
        if operation.get("target_file") == "eurika/bad.py":
            return "extract_block returned None (would no-op)"
        return None

    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._preflight_bug_hunt_op",
        _preflight,
    )
    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._deny_keys",
        lambda _root: set(),
    )
    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._prefer_keys",
        lambda _root: set(),
    )

    out = run_bug_hunt_propose(tmp_path, operations=ops, sandbox=False, web=False)
    assert out["ok"] is True
    assert out["target_file"] == "eurika/good.py"
    assert has_pending_plan(tmp_path)
    pending = load_pending_plan(tmp_path)
    assert pending is not None
    assert len(out.get("skipped") or []) == 1


def test_run_bug_hunt_success_parks_pending(tmp_path: Path, monkeypatch: Any) -> None:
    target = tmp_path / "eurika" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("def demo():\n    return 1\n", encoding="utf-8")
    ops = [_op(target="eurika/demo.py")]

    sandbox_path = tmp_path / ".eurika" / "sandbox" / "propose_bug_hunt_ok"
    sandbox_path.mkdir(parents=True)

    monkeypatch.setattr(
        "eurika.orchestration.bug_hunt._preflight_bug_hunt_op",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "eurika.orchestration.propose_sandbox.create_propose_sandbox",
        lambda root, drill_id="bug_hunt", **_k: {
            "path": sandbox_path,
            "mode": "copy",
            "name": "propose_bug_hunt_ok",
        },
    )
    monkeypatch.setattr(
        "eurika.orchestration.propose_sandbox.apply_and_smoke_verify",
        lambda *_a, **_k: {"ok": True, "modified": ["eurika/demo.py"]},
    )
    monkeypatch.setattr(
        "eurika.orchestration.propose_sandbox.remove_propose_sandbox",
        lambda *_a, **_k: None,
    )

    out = run_bug_hunt_propose(
        tmp_path, operations=ops, sandbox=True, web=False, keep_sandbox=True
    )
    assert out["ok"] is True
    assert out["target_file"] == "eurika/demo.py"
    assert has_pending_plan(tmp_path)
    plan = load_pending_plan(tmp_path)
    assert plan is not None
    assert plan["operations"][0]["target_file"] == "eurika/demo.py"
    assert "Approvals" in format_bug_hunt_summary(out)
    stamp = tmp_path / ".eurika" / "bug_hunt.json"
    assert stamp.is_file()
    assert "eurika/demo.py" in stamp.read_text(encoding="utf-8")


def test_chat_bug_hunt_intent_not_polygon() -> None:
    assert is_bug_hunt_request("найди баг в коде")
    assert is_bug_hunt_request("bug hunt")
    assert is_bug_hunt_request("предложи улучшение кода")
    assert not is_bug_hunt_request("предложи полигон эксперимент")
    assert is_polygon_propose_request("предложи полигон эксперимент")
    assert not is_polygon_propose_request("найди баг")


def test_chat_learn_patterns_intent() -> None:
    from eurika.api.chat_direct import is_learn_patterns_request, resolve_direct_handler
    from pathlib import Path

    assert is_learn_patterns_request("обнови паттерны")
    assert is_learn_patterns_request("learn-github")
    assert not is_learn_patterns_request("найди баг")
    hid, cmd = resolve_direct_handler(Path("."), "обнови OSS паттерны")
    assert hid == "learn_patterns"
    assert "learn-github" in (cmd or "")
    assert "--build-patterns" in (cmd or "")


def test_desktop_commands_include_bug_hunt_and_learn_github() -> None:
    from eurika.agent.panels import COMMANDS

    assert "bug-hunt" in COMMANDS
    assert "learn-github" in COMMANDS


def test_format_summary_oss_missing_nudge() -> None:
    text = format_bug_hunt_summary(
        {
            "ok": True,
            "kind": "extract_block_to_helper",
            "target_file": "eurika/a.py",
            "pending_plan": ".eurika/pending_plan.json",
            "sandbox": True,
            "oss_missing": True,
            "oss_examples": 0,
        }
    )
    assert "pattern_library" in text
    assert "обнови паттерны" in text


def test_idle_includes_bug_hunt_in_rotation() -> None:
    from eurika.orchestration.idle_self_dev import IDLE_DRILLS, DRILL_SUMMARY, next_drill

    assert "bug_hunt" in IDLE_DRILLS
    assert IDLE_DRILLS[-1] == "bug_hunt"
    assert "bug_hunt" in DRILL_SUMMARY
    assert next_drill("llm_extract") == "bug_hunt"
