"""Cost gate: open a paper position only when the expected move pays the fee.

Measured on the first live week (2026-07-31…08-07): the entry signal has a real
but small gross edge (+0.034%/trade, t=2.67) while the round-trip fee is
0.089%/trade, so 297 trades a day turned +3.2 USDT of gross into −12.5 USDT net.
The edge is not spread evenly — it lives where the move is expanding relative to
its own baseline, and there the gross edge clears the fee several times over.

The gate is skeleton, not a hand-written indicator rule: the only fixed part is
the arithmetic "expected edge must cover the fee with a margin". The threshold
itself is calibrated from ``paper_trades.jsonl`` and re-measured with the model
heads, so it follows the market and the fee schedule instead of a magic number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from eurika.ml.features import FEATURE_NAMES
from eurika.ml.market_store import ml_root

# Expansion of the move vs its own recent baseline: volume z-score and ATR
# burst. Both are already in the feature vector; the score is the weaker of the
# two, so a trade needs volume *and* range to be waking up at the same time.
EXPANSION_FEATURES = ("vol_z", "atr_burst")

# Expected edge must cover the fee with this margin (1.5 = 50% headroom).
DEFAULT_COST_MULT = 1.5
# Used until the first calibration; validated out-of-sample on 08-05…08-07.
DEFAULT_EXPANSION_MIN = 0.5
# Scanned from permissive to strict; the first entries are low enough to mean
# "no gate needed" when even a quiet market pays for itself.
CANDIDATE_THRESHOLDS = (-3.0, -2.0, -1.0, -0.5, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
# Evidence window a threshold must justify itself on: the trades it would admit
# that a one-step stricter threshold would not. Wider than the candidate spacing
# so single-band noise cannot flip the decision.
BAND_WIDTH = 0.5
# Below this a mean is noise, not a measurement.
MIN_CALIB_SAMPLES = 40


def cost_gate_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "weights" / "entry_cost_gate.json"


def expansion_score(features: Mapping[str, Any] | Sequence[float] | None) -> float | None:
    """How much the move is expanding right now. None when features are unusable."""
    feat: Mapping[str, Any]
    if isinstance(features, Mapping):
        feat = features
    elif isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
        feat = {
            FEATURE_NAMES[i]: features[i]
            for i in range(min(len(FEATURE_NAMES), len(features)))
        }
    else:
        return None
    values: list[float] = []
    for name in EXPANSION_FEATURES:
        raw = feat.get(name)
        if raw is None:
            return None
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            return None
    return min(values) if values else None


_GATE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def load_cost_gate(project_root: str | Path) -> dict[str, Any]:
    """Calibrated gate, or the validated default when nothing is measured yet.

    Read on every live tick, so the parsed config is cached until the file
    changes.
    """
    path = cost_gate_path(project_root)
    key = str(path)
    try:
        stamp = path.stat().st_mtime
    except OSError:
        stamp = 0.0
    cached = _GATE_CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return dict(cached[1])
    conf = _read_cost_gate(path)
    _GATE_CACHE[key] = (stamp, conf)
    return dict(conf)


def _read_cost_gate(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict) and data.get("expansion_min") is not None:
            try:
                return {
                    "expansion_min": float(data["expansion_min"]),
                    "expected_edge": float(data.get("expected_edge") or 0.0),
                    "cost_mult": float(data.get("cost_mult") or DEFAULT_COST_MULT),
                    "samples": int(data.get("samples") or 0),
                    "source": "calibrated",
                }
            except (TypeError, ValueError):
                pass
    return {
        "expansion_min": DEFAULT_EXPANSION_MIN,
        "expected_edge": 0.0,
        "cost_mult": DEFAULT_COST_MULT,
        "samples": 0,
        "source": "default",
    }


def cost_gate_ok(
    features: Mapping[str, Any] | Sequence[float] | None,
    *,
    fee: float,
    gate: Mapping[str, Any] | None = None,
    project_root: str | Path | None = None,
) -> tuple[bool, str]:
    """True when the setup is expected to earn more than it costs to trade.

    Returns ``(ok, reason)``; the reason is journal-ready and carries the numbers
    so a rejected entry can be audited later.
    """
    conf = dict(gate) if gate is not None else load_cost_gate(project_root or ".")
    score = expansion_score(features)
    if score is None:
        return True, ""
    threshold = float(conf.get("expansion_min") or DEFAULT_EXPANSION_MIN)
    if score >= threshold:
        return True, ""
    mult = float(conf.get("cost_mult") or DEFAULT_COST_MULT)
    need = mult * max(0.0, float(fee))
    return False, (
        f"ход не окупает комиссию (расширение {score:+.2f} < {threshold:+.2f}; "
        f"нужен эдж ≥ {100 * need:.3f}% при комиссии {100 * float(fee):.3f}%)"
    )


def _gross_edge(row: Mapping[str, Any]) -> float | None:
    """Directional return before costs — what the entry earned, fee aside."""
    action = str(row.get("action") or "").upper()
    if action not in ("BUY", "SELL"):
        return None
    try:
        ret = float(row.get("ret"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return ret if action == "BUY" else -ret


def _row_fee(row: Mapping[str, Any]) -> float:
    try:
        return abs(float(row.get("fee")))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _mean_edge(rows: Sequence[tuple[float, float, float]]) -> float:
    return sum(r[1] for r in rows) / len(rows) if rows else 0.0


def _pays(rows: Sequence[tuple[float, float, float]], cost_mult: float) -> bool:
    if not rows:
        return False
    mean_fee = sum(r[2] for r in rows) / len(rows)
    return _mean_edge(rows) >= float(cost_mult) * mean_fee


def calibrate_cost_gate(
    project_root: str | Path,
    *,
    cost_mult: float = DEFAULT_COST_MULT,
    min_samples: int = MIN_CALIB_SAMPLES,
    rows: Sequence[Mapping[str, Any]] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Pick the lowest expansion threshold whose realized edge still pays the fee.

    Scans candidate thresholds from permissive to strict and stops at the first
    one where the mean gross edge of everything above it covers ``cost_mult``
    fees. Lowest-that-works keeps trade flow (and therefore labels) as high as
    the economics allow.
    """
    if rows is None:
        from eurika.ml.paper_trader import load_paper_trades

        rows = load_paper_trades(project_root)
    samples: list[tuple[float, float, float]] = []  # expansion, gross edge, fee
    for row in rows:
        if str(row.get("exit_reason") or "").startswith("cancel"):
            continue
        score = expansion_score(row.get("feature_vec") or row.get("features"))
        edge = _gross_edge(row)
        if score is None or edge is None:
            continue
        samples.append((score, edge, _row_fee(row)))

    chosen: float | None = None
    expected = 0.0
    used = 0
    for threshold in CANDIDATE_THRESHOLDS:
        tail = [s for s in samples if s[0] >= threshold]
        if len(tail) < int(min_samples):
            break
        # The band this threshold would admit must pay for itself, not hide
        # behind the stronger setups above it. Without evidence from the band
        # the gate stays where it is — that is what stops it from unlocking
        # itself once its own filtering has emptied the region below.
        band = [s for s in samples if threshold <= s[0] < threshold + BAND_WIDTH]
        if len(band) < int(min_samples):
            continue
        if not _pays(band, cost_mult) or not _pays(tail, cost_mult):
            continue
        chosen, expected, used = threshold, _mean_edge(tail), len(tail)
        break

    out: dict[str, Any] = {
        "version": 1,
        "expansion_features": list(EXPANSION_FEATURES),
        "cost_mult": float(cost_mult),
        "expansion_min": float(chosen if chosen is not None else DEFAULT_EXPANSION_MIN),
        "expected_edge": float(expected),
        "samples": int(used),
        "scanned": int(len(samples)),
        "calibrated": chosen is not None,
        "note": (
            "expansion = min(vol_z, atr_burst); open only when the expected gross "
            "edge covers cost_mult x fee"
        ),
    }
    if write:
        path = cost_gate_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
