"""Tests for universal task executor capability registry."""

from pathlib import Path
import subprocess

from eurika.api.task_executor import (
    build_task_spec,
    execute_spec,
    is_pending_plan_valid,
    make_pending_plan,
)
from eurika.api import task_executor as exec_mod


def test_make_pending_plan_has_token_and_ttl() -> None:
    spec = build_task_spec(intent="create", target="x.py")
    plan = make_pending_plan(spec, ttl_sec=120)
    assert plan.get("token")
    assert int(plan.get("expires_ts", 0)) > int(plan.get("created_ts", 0))
    assert is_pending_plan_valid(plan) is True


def test_execute_ui_add_empty_tab_updates_file(tmp_path: Path) -> None:
    target = tmp_path / "qt_app" / "ui"
    target.mkdir(parents=True, exist_ok=True)
    file_path = target / "main_window.py"
    file_path.write_text(
        "def x():\n"
        "    tab = object()\n"
        "    self = type('S', (), {'tabs': object()})()\n"
        "    self.tabs.addTab(tab, \"Chat\")\n",
        encoding="utf-8",
    )
    spec = build_task_spec(intent="ui_add_empty_tab", target="qt_app/ui/main_window.py")
    report = execute_spec(tmp_path, spec)
    assert report.ok is True
    assert "qt_app/ui/main_window.py" in report.artifacts_changed
    updated = file_path.read_text(encoding="utf-8")
    assert 'self.tabs.addTab(QWidget(), "New Tab")' in updated


def test_execute_ui_add_empty_tab_with_terminal_name(tmp_path: Path) -> None:
    target = tmp_path / "qt_app" / "ui"
    target.mkdir(parents=True, exist_ok=True)
    file_path = target / "main_window.py"
    file_path.write_text(
        "def x():\n"
        "    tab = object()\n"
        "    self = type('S', (), {'tabs': object()})()\n"
        "    self.tabs.addTab(tab, \"Chat\")\n",
        encoding="utf-8",
    )
    spec = build_task_spec(
        intent="ui_add_empty_tab",
        target="qt_app/ui/main_window.py",
        entities={"tab_name": "Terminal"},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is True
    updated = file_path.read_text(encoding="utf-8")
    assert 'self.tabs.addTab(QWidget(), "Terminal")' in updated


def test_execute_ui_remove_tab_updates_file(tmp_path: Path) -> None:
    target = tmp_path / "qt_app" / "ui"
    target.mkdir(parents=True, exist_ok=True)
    file_path = target / "main_window.py"
    file_path.write_text(
        "def x():\n"
        "    tab = object()\n"
        "    self = type('S', (), {'tabs': object()})()\n"
        "    self.tabs.addTab(tab, \"Chat\")\n"
        "    self.tabs.addTab(QWidget(), \"New Tab\")\n",
        encoding="utf-8",
    )
    spec = build_task_spec(
        intent="ui_remove_tab",
        target="qt_app/ui/main_window.py",
        entities={"tab_name": "New Tab"},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is True
    updated = file_path.read_text(encoding="utf-8")
    assert '"New Tab"' not in updated


def test_execute_create_rejects_path_traversal(tmp_path: Path) -> None:
    spec = build_task_spec(intent="create", target="../hack.py")
    report = execute_spec(tmp_path, spec)
    assert report.ok is False
    assert report.error == "invalid path"


def test_execute_run_tests_uses_pytest_and_returns_status(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    spec = build_task_spec(intent="run_tests", target="tests/test_ok.py")
    report = execute_spec(tmp_path, spec)
    assert report.summary in {"tests passed", "tests failed"}
    assert isinstance(report.verification, dict)
    assert report.verification.get("runner") == "pytest"


def test_execute_run_command_rejects_disallowed_binary(tmp_path: Path) -> None:
    spec = build_task_spec(intent="run_command", target="rm -rf /")
    report = execute_spec(tmp_path, spec)
    assert report.ok is False
    assert "command not allowed" in (report.error or "")


def test_execute_code_edit_patch_success_with_verify(tmp_path: Path) -> None:
    target = tmp_path / "file.py"
    target.write_text("x = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    spec = build_task_spec(
        intent="code_edit_patch",
        target="file.py",
        entities={"old_text": "x = 1", "new_text": "x = 2", "verify_target": "tests/test_ok.py"},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is True
    assert "file.py" in report.artifacts_changed
    assert target.read_text(encoding="utf-8") == "x = 2\n"


def test_execute_code_edit_patch_rolls_back_on_verify_fail(tmp_path: Path) -> None:
    target = tmp_path / "file.py"
    target.write_text("x = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    spec = build_task_spec(
        intent="code_edit_patch",
        target="file.py",
        entities={"old_text": "x = 1", "new_text": "x = 3", "verify_target": "tests/test_bad.py"},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is False
    assert "verify failed" in (report.error or "")
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_execute_code_edit_patch_batch_success(tmp_path: Path) -> None:
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text("x = 1\n", encoding="utf-8")
    file_b.write_text("y = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    ops = (
        '[{"target":"a.py","old_text":"x = 1","new_text":"x = 2"},'
        '{"target":"b.py","old_text":"y = 1","new_text":"y = 2"}]'
    )
    spec = build_task_spec(
        intent="code_edit_patch",
        target="a.py",
        entities={"operations_json": ops, "verify_target": "tests/test_ok.py"},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is True
    assert sorted(report.artifacts_changed) == ["a.py", "b.py"]
    assert file_a.read_text(encoding="utf-8") == "x = 2\n"
    assert file_b.read_text(encoding="utf-8") == "y = 2\n"


def test_execute_code_edit_patch_batch_rolls_back_on_verify_fail(tmp_path: Path) -> None:
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text("x = 1\n", encoding="utf-8")
    file_b.write_text("y = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    ops = (
        '[{"target":"a.py","old_text":"x = 1","new_text":"x = 2"},'
        '{"target":"b.py","old_text":"y = 1","new_text":"y = 2"}]'
    )
    spec = build_task_spec(
        intent="code_edit_patch",
        target="a.py",
        entities={"operations_json": ops, "verify_target": "tests/test_bad.py"},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is False
    assert "verify failed" in (report.error or "")
    assert file_a.read_text(encoding="utf-8") == "x = 1\n"
    assert file_b.read_text(encoding="utf-8") == "y = 1\n"


def test_execute_code_edit_patch_batch_rejects_too_many_operations(tmp_path: Path) -> None:
    ops = "[" + ",".join(
        ['{"target":"a.py","old_text":"x","new_text":"y"}' for _ in range(21)]
    ) + "]"
    spec = build_task_spec(
        intent="code_edit_patch",
        target="a.py",
        entities={"operations_json": ops},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is False
    assert "too many operations" in (report.error or "")


def test_run_pytest_accepts_passed_with_bus_error(tmp_path: Path, monkeypatch) -> None:
    class _R:
        returncode = 135
        stdout = "... [100%]\n3 passed in 0.15s\n"
        stderr = "bus error"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _R())
    out = exec_mod._run_pytest(tmp_path, ["-q"], timeout=5)
    assert out.get("ok") is True
    assert "bus error" in str(out.get("warning") or "").lower()


def test_execute_code_edit_patch_dry_run_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "file.py"
    target.write_text("x = 1\n", encoding="utf-8")
    spec = build_task_spec(
        intent="code_edit_patch",
        target="file.py",
        entities={"old_text": "x = 1", "new_text": "x = 2", "dry_run": "1"},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is True
    assert "dry-run" in report.summary
    assert "file.py" in str((report.verification or {}).get("output") or "")
    assert "- x = 1" in str((report.verification or {}).get("output") or "")
    assert "+ x = 2" in str((report.verification or {}).get("output") or "")
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_execute_code_edit_patch_batch_dry_run_does_not_write(tmp_path: Path) -> None:
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text("x = 1\n", encoding="utf-8")
    file_b.write_text("y = 1\n", encoding="utf-8")
    ops = (
        '[{"target":"a.py","old_text":"x = 1","new_text":"x = 2"},'
        '{"target":"b.py","old_text":"y = 1","new_text":"y = 2"}]'
    )
    spec = build_task_spec(
        intent="code_edit_patch",
        target="a.py",
        entities={"operations_json": ops, "dry_run": "1"},
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is True
    assert "dry-run" in report.summary
    out = str((report.verification or {}).get("output") or "")
    assert "a.py" in out and "b.py" in out
    assert "- x = 1" in out and "+ x = 2" in out
    assert file_a.read_text(encoding="utf-8") == "x = 1\n"
    assert file_b.read_text(encoding="utf-8") == "y = 1\n"


def test_execute_code_edit_patch_dry_run_masks_sensitive_values(tmp_path: Path) -> None:
    target = tmp_path / "secrets.py"
    target.write_text("API_KEY=sk_live_1234567890abcdef\n", encoding="utf-8")
    spec = build_task_spec(
        intent="code_edit_patch",
        target="secrets.py",
        entities={
            "old_text": "API_KEY=sk_live_1234567890abcdef",
            "new_text": "API_KEY=sk_live_1234567890xyz",
            "dry_run": "1",
        },
    )
    report = execute_spec(tmp_path, spec)
    assert report.ok is True
    out = str((report.verification or {}).get("output") or "")
    assert "sk_live_1234567890abcdef" not in out
    assert "sk_live_1234567890xyz" not in out
    assert "API_KEY=***" in out
