"""Pattern library from OSS curated repos (ROADMAP 3.0.5.3, KPI 4).

Extracts architecture smells (god_module, hub, bottleneck, cyclic_dependency)
and code smells (long_function, deep_nesting) from cloned repos.
Phase 2: code smell entries include snippet (first lines of function) for OSS examples.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from eurika.analysis.build_graph_summary import build_graph_and_summary_from_self_map
from eurika.smells.detector import get_remediation_hint

SNIPPET_MAX_LINES = 12


def _get_function_snippet(file_path: Path, func_name: str) -> str:
    """Extract first SNIPPET_MAX_LINES of function body for OSS example."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content)
        lines = content.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                start = (node.lineno or 1) - 1
                end = min(node.end_lineno or start + 1, start + SNIPPET_MAX_LINES)
                snippet_lines = lines[start:end]
                if len(snippet_lines) > 1 and snippet_lines[0].strip().startswith("def "):
                    return "\n".join(snippet_lines)
                return ""
    except (SyntaxError, OSError, UnicodeDecodeError):
        pass
    return ""


def _extract_code_smell_patterns(project_root: Path, project: str) -> dict[str, list[dict[str, Any]]]:
    """Extract long_function and deep_nesting from repo via CodeAwareness."""
    out: dict[str, list[dict[str, Any]]] = {"long_function": [], "deep_nesting": []}
    try:
        from code_awareness import CodeAwareness

        analyzer = CodeAwareness(project_root)
        for file_path in list(analyzer.scan_python_files())[:100]:  # limit for performance (ROADMAP 4.1)
            try:
                rel = str(file_path.relative_to(project_root)).replace("\\", "/")
                for smell in analyzer.find_smells(file_path):
                    if smell.kind not in out:
                        continue
                    hint = get_remediation_hint(smell.kind)
                    loc = getattr(smell, "location", "")
                    entry = {
                        "project": project,
                        "module": rel,
                        "location": loc,
                        "severity": getattr(smell, "metric", 0) or 0,
                        "hint": hint,
                    }
                    snippet = _get_function_snippet(file_path, loc)
                    if snippet:
                        entry["snippet"] = snippet
                    if len(out[smell.kind]) < 30:
                        out[smell.kind].append(entry)
            except Exception:
                continue
    except Exception:
        pass
    return out


def extract_before_after_patterns(cache_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """
    Extract before/after refactor pairs from OSS git history (Phase 5).
    Returns long_function_before_after, deep_nesting_before_after.
    """
    try:
        from eurika.learning.git_refactors import extract_before_after_from_repos

        return extract_before_after_from_repos(cache_dir, max_per_kind=10)
    except Exception:
        return {"long_function_before_after": [], "deep_nesting_before_after": []}


def extract_patterns_from_repos(cache_dir: Path) -> dict[str, Any]:
    """
    Extract architecture and code smell patterns from curated repos.

    Architecture: god_module, hub, bottleneck, cyclic_dependency from self_map.json.
    Code smells: long_function, deep_nesting from CodeAwareness (KPI 4).
    Phase 5: OSS before/after from git refactor commits.
    """
    patterns: dict[str, list[dict[str, Any]]] = {
        "god_module": [],
        "hub": [],
        "bottleneck": [],
        "cyclic_dependency": [],
        "long_function": [],
        "deep_nesting": [],
    }
    if not cache_dir.exists():
        return patterns
    for subdir in sorted(cache_dir.iterdir()):
        if not subdir.is_dir():
            continue
        project = subdir.name
        self_map = subdir / "self_map.json"
        if self_map.exists():
            try:
                graph, smells, _ = build_graph_and_summary_from_self_map(self_map)
                del graph
            except Exception:
                pass
            else:
                for s in smells:
                    hint = get_remediation_hint(s.type)
                    for node in (s.nodes or [])[:3]:
                        entry = {
                            "project": project,
                            "module": node,
                            "severity": round(s.severity, 2),
                            "hint": hint,
                        }
                        if s.type in patterns and len(patterns[s.type]) < 30:
                            patterns[s.type].append(entry)
        code_smells = _extract_code_smell_patterns(subdir, project)
        for kind in ("long_function", "deep_nesting"):
            for e in code_smells.get(kind, [])[:30]:
                if len(patterns[kind]) < 30:
                    patterns[kind].append(e)
    before_after = extract_before_after_patterns(cache_dir)
    for key in ("long_function_before_after", "deep_nesting_before_after"):
        patterns[key] = before_after.get(key, [])
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
