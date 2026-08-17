from __future__ import annotations

import os
from pathlib import Path

from qt_app.services.desktop_launcher import desktop_launch_spec


def test_desktop_launcher_prefers_packaged_binary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repository = tmp_path / "repo"
    binary = repository / "eurika-desktop" / "release" / "linux-unpacked" / "eurika-desktop"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    spec = desktop_launch_spec(
        project,
        python_executable="/venv/bin/python",
        repository_root=repository,
    )

    assert spec["program"] == str(binary)
    assert spec["source"] == "package"
    assert spec["env"]["EURIKA_PYTHON"] == "/venv/bin/python"
    assert spec["env"]["EURIKA_WORKSPACE"] == str(project)
    assert "ELECTRON_RUN_AS_NODE" not in spec["env"]


def test_desktop_launcher_skips_stale_package(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repository = tmp_path / "repo"
    desktop = repository / "eurika-desktop"
    src = desktop / "src"
    src.mkdir(parents=True)
    (desktop / "package.json").write_text("{}", encoding="utf-8")
    (src / "main.ts").write_text("export {}\n", encoding="utf-8")
    binary = desktop / "release" / "linux-unpacked" / "eurika-desktop"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    older = (src / "main.ts").stat().st_mtime - 60
    os.utime(binary, (older, older))
    monkeypatch.setattr("qt_app.services.desktop_launcher.shutil.which", lambda _name: "/usr/bin/npm")

    spec = desktop_launch_spec(project, repository_root=repository)

    assert spec["source"] == "development"
    assert spec["program"] == "/usr/bin/npm"


def test_desktop_launcher_falls_back_to_npm(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repository = tmp_path / "repo"
    desktop = repository / "eurika-desktop"
    desktop.mkdir(parents=True)
    (desktop / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("qt_app.services.desktop_launcher.shutil.which", lambda _name: "/usr/bin/npm")

    spec = desktop_launch_spec(project, repository_root=repository)

    assert spec["program"] == "/usr/bin/npm"
    assert spec["args"] == ["--prefix", str(desktop), "start"]
    assert spec["source"] == "development"
