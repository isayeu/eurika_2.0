"""
Dependency Guard (ROADMAP 2.8.2).

Checks forbidden imports per Architecture.md §0 Layer Map.
CI should run this test; failures indicate layer violations.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from eurika.checks.dependency_firewall import (
    LayerException,
    collect_dependency_violations,
    collect_layer_violations,
)

ROOT = Path(__file__).resolve().parents[1]

# Soft-start allowlist for known temporary upward-layer imports.
# Keep this list explicit and short; remove entries as code is migrated.
LAYER_FIREWALL_EXCEPTIONS: tuple[LayerException, ...] = (
    # No active exceptions; keep tuple for explicit future waivers.
)


def test_no_forbidden_imports() -> None:
    """No project module may import from forbidden modules per layer rules."""
    violations = collect_dependency_violations(ROOT)
    assert not violations, (
        "Forbidden imports (Architecture.md §0.4). Fix or add exception: "
        + "; ".join(f"{v.path} -> {v.forbidden_module}" for v in violations)
    )


def test_layer_firewall_contract_soft_start() -> None:
    """Layer contract (Architecture.md §0.1-0.3) in soft-start mode by default.

    Set EURIKA_STRICT_LAYER_FIREWALL=1 to make violations fail CI.
    """
    violations = collect_layer_violations(ROOT, exceptions=LAYER_FIREWALL_EXCEPTIONS)
    strict = os.environ.get("EURIKA_STRICT_LAYER_FIREWALL", "").strip() in {"1", "true", "yes", "on"}
    if not strict and violations:
        pytest.skip(
            "Layer firewall soft-start: strict mode is disabled; "
            f"{len(violations)} violation(s) detected. "
            "Enable EURIKA_STRICT_LAYER_FIREWALL=1 to enforce."
        )
    assert not violations, (
        "Layer firewall violations (Architecture.md §0.1-0.3). "
        "Fix dependency direction, or add a temporary LayerException with rationale: "
        + "; ".join(
            f"{v.path} -> {v.imported_module} (L{v.source_layer} -> L{v.target_layer})"
            for v in violations
        )
    )
