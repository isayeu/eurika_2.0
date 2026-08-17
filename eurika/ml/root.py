"""Resolve the stable data root for Eurika's built-in Market subsystem."""

from __future__ import annotations

import os
from pathlib import Path


def _source_checkout_root(module_path: Path) -> Path | None:
    candidate = module_path.resolve().parents[2]
    if (
        (candidate / ".git").is_dir()
        and (candidate / "pyproject.toml").is_file()
        and (candidate / "eurika" / "ml").is_dir()
    ):
        return candidate
    return None


def resolve_market_root() -> Path:
    """Return a Market root that is independent from the opened coding workspace."""
    configured = os.environ.get("EURIKA_MARKET_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    # Source checkout: Market and its learned state belong to the Eurika project
    # itself, not to whichever external repository is open in the editor.
    source_root = _source_checkout_root(Path(__file__))
    if source_root is not None:
        return source_root

    # Installed distribution: keep writable product state in one stable location.
    return (Path.home() / ".eurika" / "market").resolve()
