"""Project Creation pipeline v0."""
from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path

from eurika.api.chat_direct import resolve_direct_handler
from eurika.api.chat_intent_detectors import detect_create, detect_create_project
from eurika.api.project_bootstrap import (
    create_project,
    format_create_project_text,
    resolve_create_project_path,
)
from eurika.api.project_scaffolds import parse_path_and_scaffold
from eurika.api.serve_exec import EXEC_WHITELIST, exec_eurika_command


def test_resolve_bare_name_is_sibling(tmp_path: Path) -> None:
    current = tmp_path / "eurika_main"
    current.mkdir()
    got = resolve_create_project_path(current, "demo_app")
    assert got == (tmp_path / "demo_app").resolve()


def test_create_project_bootstraps(tmp_path: Path) -> None:
    target = tmp_path / "new_proj"
    result = create_project(target, name="New Proj")
    assert result["ok"] is True
    assert result["created_dir"] is True
    assert (target / ".eurika").is_dir()
    assert (target / ".eurika" / "project_bootstrap.json").is_file()
    assert json.loads((target / ".eurika" / "events.json").read_text(encoding="utf-8")) == {
        "events": []
    }
    assert (target / "self_map.json").is_file()
    assert (target / "README.md").is_file()
    again = create_project(target)
    assert again["ok"] is True
    assert again["already"] is True


def test_force_bootstrap_preserves_existing_event_history(tmp_path: Path) -> None:
    target = tmp_path / "project"
    assert create_project(target)["ok"] is True
    events = target / ".eurika" / "events.json"
    original = '{"events": [{"type": "patch", "result": true}]}\n'
    events.write_text(original, encoding="utf-8")

    result = create_project(target, force=True)

    assert result["ok"] is True
    assert events.read_text(encoding="utf-8") == original


def test_detect_create_project_beats_file_create() -> None:
    assert detect_create_project("создай проект demo") == ("create_project", "demo")
    assert detect_create("создай проект demo.py") is None
    assert detect_create_project("создай проект demo.py") == ("create_project", "demo.py")
    assert detect_create("создай файл foo.py") == ("create", "foo.py")


def test_chat_and_cli_init(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    current = tmp_path / "workspace"
    current.mkdir()
    assert resolve_direct_handler(current, "создай проект")[0] == "create_project"
    assert resolve_direct_handler(current, "создай проект sibling_demo")[0] == "create_project"
    assert resolve_direct_handler(current, "создай проект sibling_demo как python")[0] == "create_project"

    from cli.core_handlers_init import handle_init

    dest = tmp_path / "cli_created"
    code = handle_init(
        Namespace(
            path=dest,
            name="CLI",
            force=False,
            no_readme=False,
            json=True,
            quiet=False,
            scaffold="minimal",
        )
    )
    assert code == 0
    assert (dest / ".eurika").is_dir()
    text = format_create_project_text(create_project(dest))
    assert "Project Creation" in text or "инициализирован" in text.lower() or "Уже" in text


def test_exec_whitelist_includes_init() -> None:
    assert "init" in EXEC_WHITELIST


def test_exec_init_runs_for_selected_project_root(tmp_path: Path) -> None:
    out = exec_eurika_command(tmp_path, "init . --json --no-readme", timeout=60)
    assert out.get("exit_code") == 0, out
    assert (tmp_path / ".eurika").is_dir()


def test_parse_path_and_scaffold_peels_known_id() -> None:
    assert parse_path_and_scaffold("demo как python") == ("demo", "python")
    assert parse_path_and_scaffold("demo --scaffold python-cli") == ("demo", "python-cli")
    assert parse_path_and_scaffold("demo python") == ("demo", "python")
    # Lone token that is a scaffold id stays the directory name.
    assert parse_path_and_scaffold("python") == ("python", "minimal")
    assert parse_path_and_scaffold("demo.py") == ("demo.py", "minimal")


def test_python_scaffold_writes_src_and_tests(tmp_path: Path) -> None:
    target = tmp_path / "demo_lib"
    result = create_project(target, name="Demo Lib", scaffold="python")
    assert result["ok"] is True
    assert result["scaffold"] == "python"
    assert (target / "pyproject.toml").is_file()
    assert (target / "src" / "demo_lib" / "__init__.py").is_file()
    assert (target / "tests" / "test_smoke.py").is_file()
    assert (target / ".gitignore").is_file()
    assert not (target / "src" / "demo_lib" / "__main__.py").is_file()
    stamp = json.loads((target / ".eurika" / "project_bootstrap.json").read_text(encoding="utf-8"))
    assert stamp["scaffold"] == "python"


def test_python_cli_scaffold_adds_main(tmp_path: Path) -> None:
    target = tmp_path / "demo_cli"
    result = create_project(target, scaffold="python-cli")
    assert result["ok"] is True
    main = target / "src" / "demo_cli" / "__main__.py"
    assert main.is_file()
    assert "def main()" in main.read_text(encoding="utf-8")


def test_unknown_scaffold_is_rejected(tmp_path: Path) -> None:
    result = create_project(tmp_path / "x", scaffold="django")
    assert result["ok"] is False
    assert "unknown scaffold" in str(result.get("error"))


def test_scaffold_does_not_overwrite_existing_readme(tmp_path: Path) -> None:
    target = tmp_path / "keep_readme"
    target.mkdir()
    (target / "README.md").write_text("keep me\n", encoding="utf-8")
    result = create_project(target, scaffold="python")
    assert result["ok"] is True
    assert (target / "README.md").read_text(encoding="utf-8") == "keep me\n"
    assert (target / "pyproject.toml").is_file()


def test_exec_init_cannot_create_project_outside_selected_root(tmp_path: Path) -> None:
    dest = tmp_path / "via_exec"
    out = exec_eurika_command(tmp_path, f"init {dest} --json --no-readme", timeout=60)
    assert out.get("exit_code") == -1
    assert "limited to the selected project_root" in str(out.get("error"))
    assert not dest.exists()
