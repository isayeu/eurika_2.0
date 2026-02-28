"""Tests for R5 plugin interface (eurika.plugins)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.plugins import load_plugins, run_plugins, detect_smells_with_plugins
from eurika.plugins.registry import _load_entry_point, _is_valid_smell
from eurika.smells.detector import ArchSmell


def test_load_entry_point_valid() -> None:
    """Valid entry point loads callable."""
    fn = _load_entry_point("eurika.smells.detector:detect_architecture_smells")
    assert fn is not None
    assert callable(fn)


def test_load_entry_point_invalid() -> None:
    """Invalid entry point returns None."""
    assert _load_entry_point("") is None
    assert _load_entry_point("no_colon") is None
    assert _load_entry_point("nonexistent.module:foo") is None


def test_is_valid_smell() -> None:
    """_is_valid_smell accepts ArchSmell-like objects."""
    s = ArchSmell(type="x", nodes=["a.py"], severity=1.0, description="")
    assert _is_valid_smell(s) is True
    assert _is_valid_smell(type("X", (), {"type": "x", "nodes": []})()) is False


def test_load_plugins_empty(tmp_path: Path) -> None:
    """No config returns empty plugin list."""
    assert load_plugins(tmp_path) == []


def test_load_plugins_from_toml(tmp_path: Path) -> None:
    """Plugins from .eurika/plugins.toml are loaded."""
    (tmp_path / ".eurika").mkdir()
    toml = tmp_path / ".eurika" / "plugins.toml"
    toml.write_text(
        '[[plugins]]\nentry_point = "tests.fixtures.eurika_plugin_example:analyze"',
        encoding="utf-8",
    )
    plugins = load_plugins(tmp_path)
    assert len(plugins) == 1
    assert callable(plugins[0])


def test_run_plugins_example(tmp_path: Path) -> None:
    """Example plugin runs and returns smells when main.py exists."""
    (tmp_path / ".eurika").mkdir()
    (tmp_path / ".eurika" / "plugins.toml").write_text(
        '[[plugins]]\nentry_point = "tests.fixtures.eurika_plugin_example:analyze"',
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text("x = 1", encoding="utf-8")
    results = run_plugins(tmp_path)
    assert len(results) == 1
    plugin_id, smells = results[0]
    assert "eurika_plugin_example" in plugin_id
    assert len(smells) == 1
    assert smells[0].type == "example_plugin_smell"
    assert "main.py" in smells[0].nodes[0]


def test_run_plugins_example_no_main(tmp_path: Path) -> None:
    """Example plugin returns empty when main.py absent."""
    (tmp_path / ".eurika").mkdir()
    (tmp_path / ".eurika" / "plugins.toml").write_text(
        '[[plugins]]\nentry_point = "tests.fixtures.eurika_plugin_example:analyze"',
        encoding="utf-8",
    )
    results = run_plugins(tmp_path)
    assert len(results) == 1
    _, smells = results[0]
    assert smells == []


def test_detect_smells_with_plugins_no_plugins(tmp_path: Path) -> None:
    """Without plugins, returns eurika smells only (if self_map exists)."""
    self_map = tmp_path / "self_map.json"
    self_map.write_text(
        '{"modules":[{"path":"a.py","lines":10}],"dependencies":{},"summary":{}}',
        encoding="utf-8",
    )
    eurika, plugin_results = detect_smells_with_plugins(tmp_path)
    assert isinstance(eurika, list)
    assert isinstance(plugin_results, list)
    assert len(plugin_results) == 0


def test_detect_smells_with_plugins_skip_plugins(tmp_path: Path) -> None:
    """include_plugins=False skips plugin loading."""
    (tmp_path / "self_map.json").write_text("{}", encoding="utf-8")
    eurika, plugin_results = detect_smells_with_plugins(tmp_path, include_plugins=False)
    assert plugin_results == []
