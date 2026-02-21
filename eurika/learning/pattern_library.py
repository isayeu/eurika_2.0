"""Pattern library from OSS curated repos (ROADMAP 3.0.5.3).

Extracts architecture smells (god_module, hub, bottleneck, cyclic_dependency)
from cloned repos and builds a JSON pattern library for Knowledge layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from architecture_pipeline import _build_graph_and_summary_from_self_map  # noqa: PLC0415
from eurika.smells.detector import get_remediation_hint


def extract_patterns_from_repos(cache_dir: Path) -> dict[str, Any]:
    """
    Extract architecture smell patterns from curated repos with self_map.json.

    Returns dict: { "god_module": [...], "hub": [...], "bottleneck": [...], "cyclic_dependency": [...] }
    Each entry: {"project": str, "module": str, "severity": float, "hint": str}
    """
    patterns: dict[str, list[dict[str, Any]]] = {
        "god_module": [],
        "hub": [],
        "bottleneck": [],
        "cyclic_dependency": [],
    }
    if not cache_dir.exists():
        return patterns
    for subdir in sorted(cache_dir.iterdir()):
        if not subdir.is_dir():
            continue
        self_map = subdir / "self_map.json"
        if not self_map.exists():
            continue
        project = subdir.name
        try:
            graph, smells, _ = _build_graph_and_summary_from_self_map(self_map)
            del graph  # unused
        except Exception:
            continue
        for s in smells:
            hint = get_remediation_hint(s.type)
            for node in (s.nodes or [])[:3]:  # top 3 nodes per smell
                entry = {
                    "project": project,
                    "module": node,
                    "severity": round(s.severity, 2),
                    "hint": hint,
                }
                if s.type in patterns and len(patterns[s.type]) < 20:
                    patterns[s.type].append(entry)
    return patterns


def save_pattern_library(data: dict[str, Any], path: Path) -> None:
    """Save pattern library to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_pattern_library(path: Path) -> dict[str, Any]:
    """Load pattern library from JSON. Returns empty dict if missing."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
