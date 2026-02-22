"""
Dependency Guard (ROADMAP 2.8.2).

Checks forbidden imports per Architecture.md §0 Layer Map.
CI should run this test; failures indicate layer violations.
"""
from __future__ import annotations

from pathlib import Path

from eurika.checks.dependency_firewall import collect_dependency_violations

ROOT = Path(__file__).resolve().parents[1]


def test_no_forbidden_imports() -> None:
    """No project module may import from forbidden modules per layer rules."""
    violations = collect_dependency_violations(ROOT)
    assert not violations, (
        "Forbidden imports (Architecture.md §0.4). Fix or add exception: "
        + "; ".join(f"{v.path} -> {v.forbidden_module}" for v in violations)
    )
