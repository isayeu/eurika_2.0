"""Tests for trusted, fail-open hooks at canonical pipeline boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from eurika.plugins.hooks import (
    HookContext,
    HookRegistry,
    dispatch_project_hooks,
    load_hook_registry,
)


def _context(event: str = "after_apply") -> HookContext:
    return HookContext.snapshot(
        event=event,
        project_root=".",
        payload={"modified": ["a.py"]},
        metadata={"source": "test"},
    )


def test_hook_registry_preserves_order_and_event_isolation() -> None:
    seen: list[str] = []
    registry = HookRegistry()
    registry.register("after_apply", lambda _ctx: seen.append("first"), plugin_id="first")
    registry.register("after_apply", lambda _ctx: seen.append("second"), plugin_id="second")
    registry.register("after_verify", lambda _ctx: seen.append("verify"), plugin_id="verify")

    rows = registry.execute(_context())
    assert seen == ["first", "second"]
    assert [row.status for row in rows] == ["ok", "ok"]
    assert registry.count() == 3


def test_hook_context_is_json_safe_and_immutable(tmp_path: Path) -> None:
    source = {"files": [Path("a.py")]}
    context = HookContext.snapshot(
        event="after_scan",
        project_root=tmp_path,
        payload=source,
        metadata={"scan_reason": "standalone"},
    )
    source["files"].append(Path("later.py"))
    assert context.payload["files"] == ("a.py",)
    assert context.stage == "scan"
    assert context.schema_version == 1
    with pytest.raises(TypeError):
        context.payload["new"] = True  # type: ignore[index]


def test_hook_exceptions_and_system_exit_are_fail_open() -> None:
    seen: list[str] = []
    registry = HookRegistry()

    def stop(_ctx: HookContext) -> None:
        raise SystemExit(2)

    registry.register("after_verify", stop, plugin_id="stop")
    registry.register("after_verify", lambda _ctx: seen.append("ok"), plugin_id="ok")
    rows = registry.execute(_context("after_verify"))
    assert seen == ["ok"]
    assert rows[0].status == "exception"
    assert rows[0].error == "SystemExit: 2"
    assert rows[1].status == "ok"


def test_duplicate_and_unknown_events() -> None:
    registry = HookRegistry()
    hook = lambda _ctx: None
    assert registry.register("after_plan", hook, plugin_id="same") is True
    assert registry.register("after_plan", hook, plugin_id="same") is False
    with pytest.raises(ValueError, match="unsupported"):
        registry.register("after_delete", hook)


def test_load_hooks_from_both_config_formats(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    (tmp_path / ".eurika" / "plugins.toml").write_text(
        "\n".join(
            [
                "[[hooks]]",
                'event = "after_apply"',
                'entry_point = "tests.fixtures.eurika_hook_example:capture"',
                "",
                "[[hooks]]",
                'event = "after_apply"',
                'entry_point = "tests.fixtures.eurika_hook_example:capture"',
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[tool.eurika.hooks]",
                'after_verify = "tests.fixtures.eurika_hook_example:fail"',
            ]
        ),
        encoding="utf-8",
    )
    registry = load_hook_registry(tmp_path)
    assert registry.count("after_apply") == 1
    assert registry.count("after_verify") == 1


def test_dispatch_audits_success_and_failure(tmp_path: Path) -> None:
    (tmp_path / ".eurika").mkdir()
    (tmp_path / ".eurika" / "plugins.toml").write_text(
        "\n".join(
            [
                "[[hooks]]",
                'event = "after_verify"',
                'entry_point = "tests.fixtures.eurika_hook_example:capture"',
                "",
                "[[hooks]]",
                'event = "after_verify"',
                'entry_point = "tests.fixtures.eurika_hook_example:fail"',
            ]
        ),
        encoding="utf-8",
    )
    rows = dispatch_project_hooks(
        tmp_path,
        "after_verify",
        payload={"verify": {"success": True}},
    )
    assert [row["status"] for row in rows] == ["ok", "exception"]

    from eurika.storage import ProjectMemory

    events = ProjectMemory(tmp_path).events.by_type("plugin_hook")
    assert len(events) == 2
    assert [event.result for event in events] == [True, False]
