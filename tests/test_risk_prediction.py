"""Tests for R5 risk prediction (eurika.reasoning.risk_prediction)."""

from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eurika.reasoning.risk_prediction import predict_module_regression_risk


def test_risk_prediction_empty_project(tmp_path: Path) -> None:
    """Empty project returns empty predictions (no self_map)."""
    result = predict_module_regression_risk(tmp_path, top_n=5)
    assert result == []


def test_risk_prediction_with_self_map(tmp_path: Path) -> None:
    """Project with self_map returns predictions."""
    import json

    self_map = {
        "modules": [
            {"path": "a.py", "lines": 50},
            {"path": "b.py", "lines": 30},
        ],
        "dependencies": {"a.py": ["b"]},
    }
    (tmp_path / "self_map.json").write_text(
        json.dumps(self_map, indent=2), encoding="utf-8"
    )
    result = predict_module_regression_risk(tmp_path, top_n=5)
    assert isinstance(result, list)
    for item in result:
        assert "module" in item
        assert "score" in item
        assert "reasons" in item
