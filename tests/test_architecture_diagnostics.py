"""Tests for architecture_diagnostics (v0.8: severity_level, remediation hints)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.smells.detector import (
    REMEDIATION_HINTS,
    get_remediation_hint,
    severity_to_level,
)


def test_severity_to_level():
    assert severity_to_level(0) == "low"
    assert severity_to_level(3) == "low"
    assert severity_to_level(5) == "medium"
    assert severity_to_level(8) == "medium"
    assert severity_to_level(12) == "high"
    assert severity_to_level(17) == "high"
    assert severity_to_level(20) == "critical"
    assert severity_to_level(100) == "critical"


def test_get_remediation_hint():
    assert "split" in get_remediation_hint("god_module").lower()
    assert "facade" in get_remediation_hint("bottleneck").lower()
    assert "cycle" in get_remediation_hint("cyclic_dependency").lower()
    assert "extract" in get_remediation_hint("hub").lower()
    # Unknown type returns generic hint
    hint = get_remediation_hint("unknown_type")
    assert "review" in hint.lower() or len(hint) > 0


def test_remediation_hints_cover_known_types():
    for t in ("god_module", "bottleneck", "hub", "cyclic_dependency"):
        assert t in REMEDIATION_HINTS
        assert len(REMEDIATION_HINTS[t]) > 20
