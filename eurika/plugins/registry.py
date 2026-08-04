"""R5 3.2: Plugin registration from .eurika/plugins.toml or pyproject [tool.eurika.plugins]."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, List

from eurika.smells.detector import ArchSmell


def _load_entry_point(entry_point: str) -> Callable[[Path], List[ArchSmell]] | None:
    """Load callable from 'module:attr' string. Returns None on error."""
    if ":" not in entry_point:
        return None
    module_name, attr_name = entry_point.strip().rsplit(":", 1)
    if not module_name or not attr_name:
        return None
    try:
        mod = importlib.import_module(module_name)
        fn = getattr(mod, attr_name, None)
        if callable(fn):
            return fn
    except Exception:
        pass
    return None


def _load_toml(text: str) -> dict:
    """Load TOML; use tomllib (3.11+) or tomli if available."""
    try:
        import tomllib  # type: ignore[import-not-found]
        return tomllib.loads(text)
    except ImportError:
        pass
    try:
        import tomli  # type: ignore[import-not-found]
        return tomli.loads(text)
    except ImportError:
        pass
    return {}


def _plugins_from_toml(plugins_path: Path) -> List[Callable[[Path], List[ArchSmell]]]:
    """Load plugins from .eurika/plugins.toml. Format: [[plugins]] entry_point = "mod:attr"."""
    result: List[Callable[[Path], List[ArchSmell]]] = []
    if not plugins_path.exists():
        return result
    try:
        data = _load_toml(plugins_path.read_text(encoding="utf-8"))
    except Exception:
        return result
    plugins = data.get("plugins")
    if isinstance(plugins, list):
        for item in plugins:
            if isinstance(item, dict) and "entry_point" in item:
                ep = str(item["entry_point"]).strip()
                fn = _load_entry_point(ep)
                if fn:
                    result.append(fn)
    return result


def _plugins_from_pyproject(project_root: Path) -> List[Callable[[Path], List[ArchSmell]]]:
    """Load plugins from pyproject.toml [tool.eurika.plugins]. Format: name = "mod:attr"."""
    result: List[Callable[[Path], List[ArchSmell]]] = []
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return result
    try:
        data = _load_toml(pyproject.read_text(encoding="utf-8"))
    except Exception:
        return result
    tool = data.get("tool") or {}
    eurika = tool.get("eurika") or {}
    plugins = eurika.get("plugins")
    if isinstance(plugins, dict):
        for ep in plugins.values():
            fn = _load_entry_point(str(ep))
            if fn:
                result.append(fn)
    return result


def load_plugins(project_root: Path) -> List[Callable[[Path], List[ArchSmell]]]:
    """
    Load all registered analyzer plugins.

    Sources (in order): .eurika/plugins.toml, pyproject.toml [tool.eurika.plugins].
    Returns list of callables analyze(project_root) -> List[ArchSmell].
    """
    plugins: List[Callable[[Path], List[ArchSmell]]] = []
    root = Path(project_root).resolve()
    eurika_dir = root / ".eurika"
    toml_path = eurika_dir / "plugins.toml"
    seen: set[str] = set()
    for fn in _plugins_from_toml(toml_path) + _plugins_from_pyproject(root):
        key = getattr(fn, "__module__", "") + "." + getattr(fn, "__name__", "")
        if key not in seen:
            seen.add(key)
            plugins.append(fn)
    return plugins


def run_plugins(project_root: Path) -> List[tuple[str, List[ArchSmell]]]:
    """
    Run all loaded plugins and return (plugin_id, smells) pairs.

    plugin_id is module:attr for logging. Failed plugins are skipped.
    """
    root = Path(project_root).resolve()
    result: List[tuple[str, List[ArchSmell]]] = []
    for fn in load_plugins(root):
        plugin_id = f"{getattr(fn, '__module__', '?')}:{getattr(fn, '__name__', '?')}"
        try:
            smells = fn(root)
            if isinstance(smells, list):
                result.append((plugin_id, [s for s in smells if _is_valid_smell(s)]))
        except Exception:
            pass  # Skip failed plugins
    return result


def _is_valid_smell(obj: Any) -> bool:
    """Check if object has ArchSmell-like structure (type, nodes, severity, description)."""
    if not hasattr(obj, "type") or not hasattr(obj, "nodes"):
        return False
    nodes = getattr(obj, "nodes", None)
    return isinstance(nodes, list) and len(nodes) > 0
