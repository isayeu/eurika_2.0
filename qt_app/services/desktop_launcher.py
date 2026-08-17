"""Resolve a safe detached launch command for Eurika Desktop."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any


def desktop_launch_spec(
    project_root: str | Path,
    *,
    python_executable: str | None = None,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return an argv-only launch spec, preferring the packaged application."""
    root = Path(project_root).expanduser().resolve()
    repository = (
        Path(repository_root).expanduser().resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    desktop = repository / "eurika-desktop"
    packaged = desktop / "release" / "linux-unpacked" / "eurika-desktop"
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env["EURIKA_PYTHON"] = python_executable or sys.executable
    env["EURIKA_WORKSPACE"] = str(root)
    if (
        packaged.is_file()
        and os.access(packaged, os.X_OK)
        and _packaged_is_current(desktop, packaged)
    ):
        return {
            "program": str(packaged),
            "args": [],
            "cwd": str(desktop),
            "env": env,
            "source": "package",
        }
    npm = shutil.which("npm")
    if npm and (desktop / "package.json").is_file():
        return {
            "program": npm,
            "args": ["--prefix", str(desktop), "start"],
            "cwd": str(repository),
            "env": env,
            "source": "development",
        }
    return {
        "error": "Eurika Desktop is not built and npm is unavailable",
        "hint": "Run: npm --prefix eurika-desktop install && npm --prefix eurika-desktop run dist:linux",
    }


def _packaged_is_current(desktop: Path, packaged: Path) -> bool:
    """False when renderer/electron sources are newer than the unpacked binary."""
    package_mtime = packaged.stat().st_mtime
    watched = (
        desktop / "src",
        desktop / "electron",
        desktop / "index.html",
        desktop / "package.json",
    )
    for root in watched:
        if root.is_file() and root.stat().st_mtime > package_mtime:
            return False
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix in {".ts", ".css", ".html", ".json"} and path.stat().st_mtime > package_mtime:
                return False
    return True
