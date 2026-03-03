"""Tests for eurika.evaluation.delta_evaluator (ROADMAP §5.7 evaluation layer)."""

from eurika.evaluation import compute_delta


def test_compute_delta_improvement() -> None:
    """compute_delta returns success when after >= before."""
    scores = [0.3, 0.7]
    call_count = [0]

    def mfg(_g, _s, _t):
        idx = call_count[0]
        call_count[0] += 1
        return {"score": scores[idx] if idx < 2 else 0}

    old_s = type("S", (), {"graph": None, "smells": []})()
    new_s = type("S", (), {"graph": None, "smells": []})()
    r = compute_delta(old_s, new_s, mfg)
    assert r["before_score"] == 0.3
    assert r["after_score"] == 0.7
    assert r["success"] is True


def test_compute_delta_regression() -> None:
    """compute_delta returns success=False when after < before."""
    scores = [0.8, 0.3]
    call_count = [0]

    def mfg(_g, _s, _t):
        idx = call_count[0]
        call_count[0] += 1
        return {"score": scores[idx] if idx < 2 else 0}

    old_s = type("S", (), {"graph": None, "smells": []})()
    new_s = type("S", (), {"graph": None, "smells": []})()
    r = compute_delta(old_s, new_s, mfg)
    assert r["before_score"] == 0.8
    assert r["after_score"] == 0.3
    assert r["success"] is False
