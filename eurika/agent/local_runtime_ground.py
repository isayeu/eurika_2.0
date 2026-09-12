"""Grounding helpers for final chat responses (cited paths vs tool observations)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .workspace import _search_source_kind

CITED_RELATIVE_PATH = re.compile(
    r"(?<![A-Za-z0-9_./])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|mjs|cjs|json|md))"
)


def normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def cited_relative_paths(text: str) -> list[str]:
    return [normalize_rel(path) for path in CITED_RELATIVE_PATH.findall(text or "")]


def observed_paths(observations: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip() and not Path(value).is_absolute():
            paths.add(normalize_rel(value))

    for item in observations:
        if not isinstance(item, dict):
            continue
        add(item.get("path"))
        payload = item.get("result")
        if isinstance(payload, dict):
            add(payload.get("path"))
            for extra in payload.get("paths") or []:
                add(extra)
            for match in payload.get("matches") or []:
                if isinstance(match, dict):
                    add(match.get("path"))
    return paths


def ungrounded_cited_paths(text: str, observations: list[dict[str, Any]]) -> list[str]:
    observed = observed_paths(observations)
    bad: list[str] = []
    for path in cited_relative_paths(text):
        if path not in observed:
            bad.append(path)
    return bad


def non_implementation_citations(text: str) -> list[str]:
    cited = cited_relative_paths(text)
    if not cited:
        return []
    impl = [path for path in cited if _search_source_kind(path) == "implementation"]
    # H3: a docs/plan answer may cite only docs/*.md. tests/ still cannot stand in for code.
    tests = [path for path in cited if _search_source_kind(path) == "test"]
    return tests if tests and not impl else []


def _has_last_check(observations: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(item, dict) and item.get("tool") == "last_check"
        for item in observations
    )


def _has_real_edit(observations: list[dict[str, Any]]) -> bool:
    for item in observations:
        if not isinstance(item, dict) or item.get("tool") != "edit":
            continue
        if item.get("error"):
            continue
        return True
    return False


def grounded_fallback(observations: list[dict[str, Any]], user_message: str = "") -> str:
    if _has_last_check(observations) and not _has_real_edit(observations):
        try:
            from eurika.api.last_check import last_check_is_the_task

            fix = last_check_is_the_task(user_message)
        except Exception:
            fix = False
        if fix:
            return (
                "Last check failed (see .eurika/last_check.log). "
                "No surgical edit was emitted this turn — say «исправь ошибки» again "
                "or Load Approvals if a plan is already parked."
            )
    observed = sorted(observed_paths(observations))
    docs = [path for path in observed if _search_source_kind(path) == "docs"]
    if docs:
        # Path inventory is not an answer. Caller fills DEVELOPMENT / VISION brief.
        return ""
    impl = [path for path in observed if _search_source_kind(path) == "implementation"]
    if impl:
        return "From tool observations: " + ", ".join(impl[:8]) + "."
    tests = [path for path in observed if _search_source_kind(path) == "test"]
    if tests:
        return (
            "Tests are not the implementation. "
            f"Observed test files: {', '.join(tests[:5])}. "
            "Search and read the production module they import (eurika/)."
        )
    return ""
