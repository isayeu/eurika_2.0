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


def test_run_bug_hunt_success_parks_pending(tmp_path: Path, monkeypatch: Any) -> None:
    target = tmp_path / "eurika" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("def demo():\n    return 1\n", encoding="utf-8")
    ops = [_op(target="eurika/demo.py")]

    sandbox_path = tmp_path / ".eurika" / "sandbox" / "propose_bug_hunt_ok"
    sandbox_path.mkdir(parents=True)

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
