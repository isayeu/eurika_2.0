"""Tiny CPU policy models: entry HOLD/BUY/SELL + exit HOLD/CLOSE + entry style.

Persists under ``.eurika/ml/weights/``. Live Binance orders are never placed.
Entry policy is a small MLP so feature combinations (RSI+MACD+BB+structure) are learnable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from eurika.ml.exec_tf import EXIT_FEATURE_NAMES
from eurika.ml.features import FEATURE_NAMES
from eurika.ml.market_store import ml_root, read_jsonl_rows
from eurika.ml.paper_trader import is_executed_trade, load_paper_trades
from eurika.ml.torch_runtime import preferred_device, torch_available

ACTION_TO_IDX = {"HOLD": 0, "BUY": 1, "SELL": 2}
IDX_TO_ACTION = {0: "HOLD", 1: "BUY", 2: "SELL"}

EXIT_TO_IDX = {"HOLD": 0, "CLOSE": 1}
IDX_TO_EXIT = {0: "HOLD", 1: "CLOSE"}

STYLE_TO_IDX = {"market": 0, "limit": 1, "stop": 2, "oco": 3}
IDX_TO_STYLE = {0: "market", 1: "limit", 2: "stop", 3: "oco"}
CANCELABLE_ENTRY_STYLES = ("limit", "stop", "oco")
# If market wins but best cancelable is within this gap → prefer cancelable
# (pending can be invalidated/expired; market fills immediately).
DEFAULT_CANCELABLE_STYLE_MARGIN = 0.08

POLICY_HIDDEN = 32
POLICY_ARCH = "mlp2"
STYLE_HIDDEN = 16
STYLE_ARCH = "mlp2"


def weights_dir(project_root: str | Path) -> Path:
    return ml_root(project_root) / "weights"


def weights_path(project_root: str | Path) -> Path:
    return weights_dir(project_root) / "market_policy.pt"


def meta_path(project_root: str | Path) -> Path:
    return weights_dir(project_root) / "meta.json"


def exit_weights_path(project_root: str | Path) -> Path:
    return weights_dir(project_root) / "market_exit.pt"


def exit_meta_path(project_root: str | Path) -> Path:
    return weights_dir(project_root) / "exit_meta.json"


def exit_samples_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "exit_samples.jsonl"


def levels_weights_path(project_root: str | Path) -> Path:
    return weights_dir(project_root) / "market_levels.pt"


def levels_meta_path(project_root: str | Path) -> Path:
    return weights_dir(project_root) / "levels_meta.json"


def style_weights_path(project_root: str | Path) -> Path:
    return weights_dir(project_root) / "market_style.pt"


def style_meta_path(project_root: str | Path) -> Path:
    return weights_dir(project_root) / "style_meta.json"


def style_samples_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "style_samples.jsonl"


# Soft bounds for predicted fractions (not UI %).
LEVELS_MIN = (0.0005, 0.0005, 0.0)  # tp, sl, trail
LEVELS_MAX = (0.03, 0.02, 0.015)


def _pad_feature_vec(vec: Sequence[float], n_feat: int) -> list[float]:
    out = [float(v) for v in vec]
    if len(out) < n_feat:
        out.extend([0.0] * (n_feat - len(out)))
    elif len(out) > n_feat:
        out = out[:n_feat]
    return out


def _build_mlp(n_in: int, n_hidden: int, n_out: int) -> Any:
    import torch.nn as nn

    return nn.Sequential(
        nn.Linear(int(n_in), int(n_hidden)),
        nn.ReLU(),
        nn.Linear(int(n_hidden), int(n_out)),
    )


def _state_looks_like_mlp(state: Mapping[str, Any]) -> bool:
    keys = set(state.keys())
    return "0.weight" in keys and "2.weight" in keys


def _entry_timing_ok(row: dict[str, Any]) -> bool:
    """Accept entry label only if timing looks favorable (or legacy row without MFE)."""
    if "mfe_pct" not in row and "entry_timing_score" not in row:
        return True
    tp = float(row.get("tp_pct") or 0.0)
    mfe = float(row.get("mfe_pct") or 0.0)
    score = float(row.get("entry_timing_score") or 0.0)
    if tp > 0 and mfe >= tp - 1e-12:
        return True
    return score > 0.0


# Sample weights: prefer |pnl_usdt|; else |edge| scaled so ~1% ≈ $1 unit.
SAMPLE_WEIGHT_PNL_SCALE = 0.5
SAMPLE_WEIGHT_EDGE_SCALE = 50.0  # abs(edge)*50 → 1% edge adds +0.5 like $1 pnl
SAMPLE_WEIGHT_MIN = 0.25
SAMPLE_WEIGHT_MAX = 8.0


def sample_weight_from_row(row: Mapping[str, Any]) -> float:
    """Weight by money impact: |pnl_usdt| preferred, else |edge|.

    Base 1.0; larger wins/losses pull the entry MLP harder than tiny noise trades.
    """
    pnl = row.get("pnl_usdt")
    if isinstance(pnl, (int, float)):
        mag = abs(float(pnl))
        raw = 1.0 + SAMPLE_WEIGHT_PNL_SCALE * mag
    else:
        edge = row.get("edge")
        if isinstance(edge, (int, float)):
            mag = abs(float(edge))
            raw = 1.0 + SAMPLE_WEIGHT_EDGE_SCALE * mag
        else:
            raw = 1.0
    return max(SAMPLE_WEIGHT_MIN, min(SAMPLE_WEIGHT_MAX, float(raw)))


# Exit weights: boost CLOSE when path had real MFE and/or giveback (bank the fade).
EXIT_WEIGHT_MFE_SCALE = 40.0
EXIT_WEIGHT_GIVEBACK_SCALE = 80.0
EXIT_WEIGHT_HOLD_GIVEBACK = 0.7  # downweight HOLD after fade started


def exit_sample_weight_from_row(row: Mapping[str, Any]) -> float:
    """Weight exit samples: CLOSE with +MFE/giveback > flat HOLD noise."""
    label = str(row.get("exit_label") or "").upper()
    try:
        mfe = float(row.get("mfe_pct") or 0.0)
    except (TypeError, ValueError):
        mfe = 0.0
    try:
        giveback = float(row.get("giveback") or 0.0)
    except (TypeError, ValueError):
        giveback = 0.0
    if giveback <= 0.0 and isinstance(row.get("unrealized_edge"), (int, float)):
        giveback = max(0.0, mfe - float(row["unrealized_edge"]))
    mfe = max(0.0, mfe)
    giveback = max(0.0, giveback)
    if label == "CLOSE":
        raw = 1.0 + EXIT_WEIGHT_MFE_SCALE * mfe + EXIT_WEIGHT_GIVEBACK_SCALE * giveback
        return max(SAMPLE_WEIGHT_MIN, min(SAMPLE_WEIGHT_MAX, float(raw)))
    if label == "HOLD" and giveback > 1e-12 and mfe > 1e-12:
        return max(SAMPLE_WEIGHT_MIN, float(EXIT_WEIGHT_HOLD_GIVEBACK))
    return 1.0


def _rows_to_xy(
    rows: Sequence[dict[str, Any]],
) -> tuple[list[list[float]], list[int], list[float]]:
    """Supervise: good timing + correct → action; else HOLD. Third list = sample weights.

    Legacy rows without MFE fields keep correct→action behaviour.
    """
    xs: list[list[float]] = []
    ys: list[int] = []
    ws: list[float] = []
    n_feat = len(FEATURE_NAMES)
    for row in rows:
        if not is_executed_trade(row):
            continue
        if str(row.get("kind") or "") == "exit_sample":
            continue
        vec = row.get("feature_vec")
        if isinstance(vec, list) and len(vec) > 0:
            vec = _pad_feature_vec(vec, n_feat)
        else:
            feat = row.get("features")
            if isinstance(feat, dict):
                vec = [float(feat.get(name, 0.0)) for name in FEATURE_NAMES]
            else:
                continue
        action = str(row.get("action") or "HOLD").upper()
        if action not in ACTION_TO_IDX:
            continue
        if row.get("correct") and _entry_timing_ok(row):
            label = ACTION_TO_IDX[action]
        else:
            label = ACTION_TO_IDX["HOLD"]
        xs.append([float(v) for v in vec])
        ys.append(label)
        ws.append(sample_weight_from_row(row))
    return xs, ys, ws


def train_market_policy(
    project_root: str | Path,
    *,
    epochs: int = 40,
    lr: float = 0.05,
    hidden: int = POLICY_HIDDEN,
) -> dict[str, Any]:
    """Train tiny MLP classifier on paper trades. Requires torch extra.

    Loss is sample-weighted by ``pnl_usdt`` (else ``edge``) so equity-relevant
    outcomes matter more than flat correct/incorrect counts.
    """
    if not torch_available():
        return {
            "ok": False,
            "error": "torch not available (pip install -e '.[torch]')",
            "path": str(weights_path(project_root)),
        }
    import torch

    rows = load_paper_trades(project_root)
    xs, ys, ws = _rows_to_xy(rows)
    if len(xs) < 8:
        return {
            "ok": False,
            "error": f"need >= 8 labeled rows, have {len(xs)}",
            "path": str(weights_path(project_root)),
            "samples": len(xs),
        }

    device = preferred_device()
    n_feat = len(FEATURE_NAMES)
    h = max(8, int(hidden))
    x_t = torch.tensor(xs, dtype=torch.float32, device=device)
    y_t = torch.tensor(ys, dtype=torch.long, device=device)
    w_t = torch.tensor(ws, dtype=torch.float32, device=device)
    model = _build_mlp(n_feat, h, 3).to(device)
    opt = torch.optim.SGD(model.parameters(), lr=lr)
    loss_fn = torch.nn.CrossEntropyLoss(reduction="none")
    model.train()
    last_loss = 0.0
    for _ in range(max(1, int(epochs))):
        opt.zero_grad()
        logits = model(x_t)
        per = loss_fn(logits, y_t)
        loss = (per * w_t).mean()
        loss.backward()
        opt.step()
        last_loss = float(loss.detach().cpu().item())

    model.eval()
    with torch.no_grad():
        pred = model(x_t).argmax(dim=1)
        acc = float((pred == y_t).float().mean().cpu().item())
        w_mean = float(w_t.mean().cpu().item())
        w_max = float(w_t.max().cpu().item())

    wdir = weights_dir(project_root)
    wdir.mkdir(parents=True, exist_ok=True)
    wpath = weights_path(project_root)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "n_features": n_feat,
            "hidden": h,
            "arch": POLICY_ARCH,
        },
        wpath,
    )
    meta = {
        "n_features": n_feat,
        "feature_names": list(FEATURE_NAMES),
        "classes": list(IDX_TO_ACTION[i] for i in range(3)),
        "samples": len(xs),
        "train_accuracy": round(acc, 4),
        "final_loss": round(last_loss, 6),
        "epochs": int(epochs),
        "device": device,
        "weights": str(wpath),
        "timing_filter": True,
        "sample_weight": "pnl_usdt|edge",
        "sample_weight_mean": round(w_mean, 4),
        "sample_weight_max": round(w_max, 4),
        "arch": POLICY_ARCH,
        "hidden": h,
        "note": "train_accuracy is in-sample on paper_trades.jsonl; loss weighted by pnl_usdt/edge",
    }
    meta_path(project_root).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "error": None, **meta}


def load_policy_model(project_root: str | Path) -> Any | None:
    """Load entry MLP. Incompatible legacy Linear / wrong shape → None (momentum fallback)."""
    if not torch_available() or not weights_path(project_root).is_file():
        return None
    import torch

    blob = torch.load(weights_path(project_root), map_location="cpu")
    if not isinstance(blob, dict) or "state_dict" not in blob:
        return None
    state = blob["state_dict"]
    n_feat = int(blob.get("n_features") or 0)
    target = len(FEATURE_NAMES)
    arch = str(blob.get("arch") or "")
    hidden = int(blob.get("hidden") or POLICY_HIDDEN)

    if n_feat != target:
        return None
    if arch == POLICY_ARCH or _state_looks_like_mlp(state):
        model = _build_mlp(target, hidden, 3)
        try:
            model.load_state_dict(state)
        except Exception:
            return None
        model.eval()
        return model
    return None


def predict_action(project_root: str | Path, features: Sequence[float]) -> dict[str, Any]:
    """Infer HOLD/BUY/SELL; falls back to momentum if no weights."""
    from eurika.ml.paper_trader import momentum_policy

    vec = _pad_feature_vec(features, len(FEATURE_NAMES))
    model = load_policy_model(project_root)
    if model is None:
        action = momentum_policy(vec)
        return {"action": action, "source": "momentum", "probs": None}
    import torch

    with torch.no_grad():
        logits = model(torch.tensor([vec], dtype=torch.float32))
        probs = torch.softmax(logits, dim=1)[0].tolist()
        idx = int(logits.argmax(dim=1).item())
    return {
        "action": IDX_TO_ACTION.get(idx, "HOLD"),
        "source": "model",
        "probs": {"HOLD": probs[0], "BUY": probs[1], "SELL": probs[2]},
    }


# Soft entry: break HOLD-argmax deadlock when a side is competitive (live logs ~0.52/0.25/0.23).
DEFAULT_SOFT_HOLD_MAX = 0.55
DEFAULT_SOFT_SIDE_MIN = 0.24
DEFAULT_SOFT_SIDE_GAP = 0.015


def soften_entry_action(
    pred: Mapping[str, Any],
    *,
    hold_max: float = DEFAULT_SOFT_HOLD_MAX,
    side_min: float = DEFAULT_SOFT_SIDE_MIN,
    side_gap: float = DEFAULT_SOFT_SIDE_GAP,
) -> dict[str, Any]:
    """If argmax is HOLD but a side is close, take BUY/SELL (source model/soft)."""
    out = dict(pred)
    action = str(out.get("action") or "HOLD").upper()
    probs = out.get("probs") if isinstance(out.get("probs"), dict) else None
    if action != "HOLD" or not probs:
        return out
    hold_p = float(probs.get("HOLD") or 0.0)
    buy_p = float(probs.get("BUY") or 0.0)
    sell_p = float(probs.get("SELL") or 0.0)
    if hold_p >= float(hold_max):
        return out
    if buy_p >= sell_p:
        side, side_p, other_p = "BUY", buy_p, sell_p
    else:
        side, side_p, other_p = "SELL", sell_p, buy_p
    if side_p < float(side_min):
        return out
    if (side_p - other_p) < float(side_gap):
        return out
    out["action"] = side
    src = str(out.get("source") or "model")
    out["source"] = f"{src}/soft" if not src.endswith("/soft") else src
    out["soft_entry"] = True
    return out


def _momentum_fading(feat: Mapping[str, Any], *, for_sell: bool) -> bool:
    """True when RSI/MACD/BB deltas show impulse exhaustion (culmination).

    SELL after +burst: need downward turn. BUY after −burst: need bounce.
    Requires ≥2 of 3 delta votes so one noisy series does not unlock alone.
    """
    rsi_d = float(feat.get("rsi_delta") or 0.0)
    macd_d = float(feat.get("macd_hist_delta") or 0.0)
    bb_d = float(feat.get("bb_pos_delta") or 0.0)
    if for_sell:
        votes = int(rsi_d < -0.5) + int(macd_d < 0.0) + int(bb_d < -0.02)
    else:
        votes = int(rsi_d > 0.5) + int(macd_d > 0.0) + int(bb_d > 0.02)
    return votes >= 2


def entry_setup_ok(action: str, features: Mapping[str, Any] | Sequence[float] | None) -> bool:
    """Live proxy for good timing (no hindsight MFE): skip exhausted / adverse-burst entries.

    Strong +burst still blocks SELL **unless** momentum deltas show fade
    (post-culmination short). Symmetric for BUY on −burst bounce.
    """
    act = (action or "").upper()
    if act not in ("BUY", "SELL"):
        return False
    feat: dict[str, Any]
    if isinstance(features, Mapping):
        feat = dict(features)
    elif isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
        names = FEATURE_NAMES
        feat = {
            names[i]: float(features[i])
            for i in range(min(len(names), len(features)))
        }
    else:
        return True
    d_lo = float(feat.get("dist_to_low_40") or feat.get("dist_to_low_win") or 0.5)
    d_hi = float(feat.get("dist_to_high_40") or feat.get("dist_to_high_win") or 0.5)
    burst = float(feat.get("atr_burst") or 0.0)
    # Near opposite extreme → late entry.
    if act == "BUY" and d_lo >= 0.92:
        return False
    if act == "SELL" and d_hi >= 0.92:
        return False
    if act == "BUY" and burst < -2.0 and not _momentum_fading(feat, for_sell=False):
        return False
    if act == "SELL" and burst > 2.0 and not _momentum_fading(feat, for_sell=True):
        return False
    return True


def load_exit_samples(project_root: str | Path) -> list[dict[str, Any]]:
    return read_jsonl_rows(exit_samples_path(project_root))


def append_exit_samples(project_root: str | Path, samples: Sequence[dict[str, Any]]) -> int:
    if not samples:
        return 0
    path = exit_samples_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for row in samples:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def _exit_rows_to_xy(
    rows: Sequence[dict[str, Any]],
) -> tuple[list[list[float]], list[int], list[float]]:
    xs: list[list[float]] = []
    ys: list[int] = []
    ws: list[float] = []
    n_feat = len(EXIT_FEATURE_NAMES)
    for row in rows:
        vec = row.get("feature_vec")
        if not isinstance(vec, list) or len(vec) == 0:
            continue
        vec = _pad_feature_vec(vec, n_feat)
        label_s = str(row.get("exit_label") or "").upper()
        if label_s not in EXIT_TO_IDX:
            continue
        xs.append([float(v) for v in vec])
        ys.append(EXIT_TO_IDX[label_s])
        ws.append(exit_sample_weight_from_row(row))
    return xs, ys, ws


def train_market_exit_policy(
    project_root: str | Path,
    *,
    epochs: int = 40,
    lr: float = 0.05,
) -> dict[str, Any]:
    """Train HOLD/CLOSE exit linear model on retro 1m samples.

    CLOSE rows with positive MFE / giveback get higher sample weight so the
    model learns to bank fades instead of waiting for horizon.
    """
    if not torch_available():
        return {
            "ok": False,
            "error": "torch not available (pip install -e '.[torch]')",
            "path": str(exit_weights_path(project_root)),
        }
    import torch
    import torch.nn as nn

    rows = load_exit_samples(project_root)
    xs, ys, ws = _exit_rows_to_xy(rows)
    if len(xs) < 8:
        return {
            "ok": False,
            "error": f"need >= 8 exit samples, have {len(xs)}",
            "path": str(exit_weights_path(project_root)),
            "samples": len(xs),
        }

    device = preferred_device()
    x_t = torch.tensor(xs, dtype=torch.float32, device=device)
    y_t = torch.tensor(ys, dtype=torch.long, device=device)
    w_t = torch.tensor(ws, dtype=torch.float32, device=device)
    n_feat = len(EXIT_FEATURE_NAMES)
    model = nn.Linear(n_feat, 2).to(device)
    opt = torch.optim.SGD(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss(reduction="none")
    model.train()
    last_loss = 0.0
    for _ in range(max(1, int(epochs))):
        opt.zero_grad()
        logits = model(x_t)
        per = loss_fn(logits, y_t)
        loss = (per * w_t).sum() / w_t.sum().clamp_min(1e-8)
        loss.backward()
        opt.step()
        last_loss = float(loss.detach().cpu().item())

    model.eval()
    with torch.no_grad():
        pred = model(x_t).argmax(dim=1)
        acc = float((pred == y_t).float().mean().cpu().item())

    w_mean = float(sum(ws) / max(1, len(ws)))
    w_max = float(max(ws)) if ws else 1.0
    wdir = weights_dir(project_root)
    wdir.mkdir(parents=True, exist_ok=True)
    wpath = exit_weights_path(project_root)
    torch.save({"state_dict": model.state_dict(), "n_features": n_feat}, wpath)
    meta = {
        "n_features": n_feat,
        "feature_names": list(EXIT_FEATURE_NAMES),
        "classes": list(IDX_TO_EXIT[i] for i in range(2)),
        "samples": len(xs),
        "train_accuracy": round(acc, 4),
        "final_loss": round(last_loss, 6),
        "epochs": int(epochs),
        "device": device,
        "weights": str(wpath),
        "sample_weight": "close_mfe|giveback",
        "sample_weight_mean": round(w_mean, 4),
        "sample_weight_max": round(w_max, 4),
    }
    exit_meta_path(project_root).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "error": None, **meta}


def load_exit_model(project_root: str | Path) -> Any | None:
    if not torch_available() or not exit_weights_path(project_root).is_file():
        return None
    import torch
    import torch.nn as nn

    blob = torch.load(exit_weights_path(project_root), map_location="cpu")
    if not isinstance(blob, dict) or "state_dict" not in blob:
        return None
    state = blob["state_dict"]
    n_feat = int(blob.get("n_features") or len(EXIT_FEATURE_NAMES))
    target = len(EXIT_FEATURE_NAMES)
    if n_feat == target:
        model = nn.Linear(n_feat, 2)
        model.load_state_dict(state)
    else:
        old = nn.Linear(n_feat, 2)
        old.load_state_dict(state)
        model = nn.Linear(target, 2)
        with torch.no_grad():
            model.weight.zero_()
            model.bias.copy_(old.bias)
            cols = min(n_feat, target)
            model.weight[:, :cols] = old.weight[:, :cols]
    model.eval()
    return model


def predict_exit(project_root: str | Path, features: Sequence[float]) -> dict[str, Any]:
    """Infer HOLD/CLOSE; default HOLD if no exit weights."""
    vec = _pad_feature_vec(features, len(EXIT_FEATURE_NAMES))
    model = load_exit_model(project_root)
    if model is None:
        return {"action": "HOLD", "source": "none", "probs": None}
    import torch

    with torch.no_grad():
        logits = model(torch.tensor([vec], dtype=torch.float32))
        probs = torch.softmax(logits, dim=1)[0].tolist()
        idx = int(logits.argmax(dim=1).item())
    return {
        "action": IDX_TO_EXIT.get(idx, "HOLD"),
        "source": "model",
        "probs": {"HOLD": probs[0], "CLOSE": probs[1]},
    }


def _clamp_levels(tp: float, sl: float, trail: float) -> tuple[float, float, float]:
    tp_o = max(LEVELS_MIN[0], min(LEVELS_MAX[0], float(tp)))
    sl_o = max(LEVELS_MIN[1], min(LEVELS_MAX[1], float(sl)))
    trail_o = max(LEVELS_MIN[2], min(LEVELS_MAX[2], float(trail)))
    return tp_o, sl_o, trail_o


def _ideal_levels_from_row(row: dict[str, Any]) -> Optional[tuple[float, float, float]]:
    """Teacher targets from realized MFE/MAE path (skip cancels / empty paths)."""
    if row.get("pending_cancelled"):
        return None
    if str(row.get("exit_reason") or "").startswith("cancel"):
        return None
    mfe = float(row.get("mfe_pct") or 0.0)
    mae = float(row.get("mae_pct") or 0.0)
    if mfe <= 0 and mae <= 0:
        return None
    # Capture most of favorable move; give SL a bit beyond adverse; trail ~1/3 of MFE.
    tp = mfe * 0.85 if mfe > 0 else float(row.get("tp_pct") or LEVELS_MIN[0])
    sl = max(mae * 1.15, LEVELS_MIN[1]) if mae > 0 else float(row.get("sl_pct") or LEVELS_MIN[1])
    trail = mfe * 0.35 if mfe > mae else max(0.0, mfe * 0.2)
    return _clamp_levels(tp, sl, trail)


def _levels_rows_to_xy(rows: Sequence[dict[str, Any]]) -> tuple[list[list[float]], list[list[float]]]:
    xs: list[list[float]] = []
    ys: list[list[float]] = []
    n_feat = len(FEATURE_NAMES)
    for row in rows:
        if str(row.get("kind") or "") == "exit_sample":
            continue
        targets = _ideal_levels_from_row(row)
        if targets is None:
            continue
        vec = row.get("feature_vec")
        if isinstance(vec, list) and len(vec) > 0:
            vec = _pad_feature_vec(vec, n_feat)
        else:
            feat = row.get("features")
            if isinstance(feat, dict):
                vec = [float(feat.get(name, 0.0)) for name in FEATURE_NAMES]
            else:
                continue
        xs.append([float(v) for v in vec])
        ys.append([targets[0], targets[1], targets[2]])
    return xs, ys


def _heuristic_levels(features: Sequence[float] | Mapping[str, Any] | None) -> tuple[float, float, float]:
    """Bootstrap levels from volatility / burst before levels weights exist."""
    vol = 0.003
    burst = 0.0
    if isinstance(features, Mapping):
        vol = abs(float(features.get("volatility") or vol))
        burst = abs(float(features.get("atr_burst") or 0.0))
    elif isinstance(features, Sequence) and len(features) >= 5:
        # FEATURE_NAMES: volatility index 4, atr_burst 7
        vol = abs(float(features[4])) if len(features) > 4 else vol
        burst = abs(float(features[7])) if len(features) > 7 else 0.0
    scale = 1.0 + min(2.0, burst)
    tp = max(0.001, vol * 2.5 * scale)
    sl = max(0.0008, vol * 1.8 * scale)
    trail = max(0.0, vol * 1.2 * scale)
    return _clamp_levels(tp, sl, trail)


def train_market_levels_policy(
    project_root: str | Path,
    *,
    epochs: int = 40,
    lr: float = 0.05,
) -> dict[str, Any]:
    """Train Linear regressor: features → (tp, sl, trail) fractions."""
    if not torch_available():
        return {
            "ok": False,
            "error": "torch not available (pip install -e '.[torch]')",
            "path": str(levels_weights_path(project_root)),
        }
    import torch
    import torch.nn as nn

    rows = load_paper_trades(project_root)
    xs, ys = _levels_rows_to_xy(rows)
    if len(xs) < 8:
        return {
            "ok": False,
            "error": f"need >= 8 levels samples, have {len(xs)}",
            "path": str(levels_weights_path(project_root)),
            "samples": len(xs),
        }

    device = preferred_device()
    x_t = torch.tensor(xs, dtype=torch.float32, device=device)
    y_t = torch.tensor(ys, dtype=torch.float32, device=device)
    n_feat = len(FEATURE_NAMES)
    model = nn.Linear(n_feat, 3).to(device)
    opt = torch.optim.SGD(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    model.train()
    last_loss = 0.0
    for _ in range(max(1, int(epochs))):
        opt.zero_grad()
        pred = torch.nn.functional.softplus(model(x_t))
        loss = loss_fn(pred, y_t)
        loss.backward()
        opt.step()
        last_loss = float(loss.detach().cpu().item())

    model.eval()
    with torch.no_grad():
        pred = torch.nn.functional.softplus(model(x_t))
        mae = float((pred - y_t).abs().mean().cpu().item())

    wdir = weights_dir(project_root)
    wdir.mkdir(parents=True, exist_ok=True)
    wpath = levels_weights_path(project_root)
    torch.save({"state_dict": model.state_dict(), "n_features": n_feat}, wpath)
    meta = {
        "n_features": n_feat,
        "feature_names": list(FEATURE_NAMES),
        "outputs": ["tp_pct", "sl_pct", "trail_pct"],
        "samples": len(xs),
        "train_mae": round(mae, 6),
        "final_loss": round(last_loss, 6),
        "epochs": int(epochs),
        "device": device,
        "weights": str(wpath),
    }
    levels_meta_path(project_root).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "error": None, **meta}


def load_levels_model(project_root: str | Path) -> Any | None:
    if not torch_available() or not levels_weights_path(project_root).is_file():
        return None
    import torch
    import torch.nn as nn

    blob = torch.load(levels_weights_path(project_root), map_location="cpu")
    if not isinstance(blob, dict) or "state_dict" not in blob:
        return None
    state = blob["state_dict"]
    n_feat = int(blob.get("n_features") or len(FEATURE_NAMES))
    target = len(FEATURE_NAMES)
    if n_feat == target:
        model = nn.Linear(n_feat, 3)
        model.load_state_dict(state)
    else:
        old = nn.Linear(n_feat, 3)
        old.load_state_dict(state)
        model = nn.Linear(target, 3)
        with torch.no_grad():
            model.weight.zero_()
            model.bias.copy_(old.bias)
            cols = min(n_feat, target)
            model.weight[:, :cols] = old.weight[:, :cols]
    model.eval()
    return model


def predict_levels(
    project_root: str | Path,
    features: Sequence[float] | Mapping[str, Any] | None,
    *,
    fallback_tp: float = 0.0,
    fallback_sl: float = 0.0,
    fallback_trail: float = 0.0,
) -> dict[str, Any]:
    """Infer tp/sl/trail fractions. Model → heuristic → UI fallbacks.

    If fallback_* > 0 they also act as soft ceilings (do not exceed UI caps).
    """
    vec: list[float]
    feat_map: Mapping[str, Any] | None
    if isinstance(features, Mapping):
        feat_map = features
        vec = [float(features.get(name, 0.0)) for name in FEATURE_NAMES]
    elif isinstance(features, Sequence) and len(features) > 0:
        feat_map = None
        vec = _pad_feature_vec(features, len(FEATURE_NAMES))
    else:
        feat_map = None
        vec = [0.0] * len(FEATURE_NAMES)

    model = load_levels_model(project_root)
    source = "heuristic"
    if model is not None:
        import torch

        with torch.no_grad():
            raw = torch.nn.functional.softplus(model(torch.tensor([vec], dtype=torch.float32)))[0].tolist()
        tp, sl, trail = _clamp_levels(float(raw[0]), float(raw[1]), float(raw[2]))
        source = "model"
    else:
        tp, sl, trail = _heuristic_levels(feat_map if feat_map is not None else vec)

    # Prefer learned/heuristic; only use UI fallback if still zero
    fb_tp = max(0.0, float(fallback_tp))
    fb_sl = max(0.0, float(fallback_sl))
    fb_tr = max(0.0, float(fallback_trail))
    if tp <= 0 and fb_tp > 0:
        tp = fb_tp
    if sl <= 0 and fb_sl > 0:
        sl = fb_sl
    if trail <= 0 and fb_tr > 0:
        trail = fb_tr
    # Soft ceiling from UI when user set a positive spin
    if fb_tp > 0:
        tp = min(tp, fb_tp)
    if fb_sl > 0:
        sl = min(sl, fb_sl)
    if fb_tr > 0:
        trail = min(trail, fb_tr)
    tp, sl, trail = _clamp_levels(tp, sl, trail)
    return {
        "tp_pct": tp,
        "sl_pct": sl,
        "trail_pct": trail,
        "source": source,
    }


def load_style_samples(project_root: str | Path) -> list[dict[str, Any]]:
    return read_jsonl_rows(style_samples_path(project_root))


def append_style_samples(project_root: str | Path, samples: Sequence[dict[str, Any]]) -> int:
    if not samples:
        return 0
    path = style_samples_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for row in samples:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def _style_rows_to_xy(rows: Sequence[dict[str, Any]]) -> tuple[list[list[float]], list[int]]:
    xs: list[list[float]] = []
    ys: list[int] = []
    n_feat = len(FEATURE_NAMES)
    for row in rows:
        style = str(row.get("style_label") or row.get("entry_style") or "").strip().lower()
        if style not in STYLE_TO_IDX:
            continue
        vec = row.get("feature_vec")
        if isinstance(vec, list) and len(vec) > 0:
            vec = _pad_feature_vec(vec, n_feat)
        else:
            feat = row.get("features")
            if isinstance(feat, dict):
                vec = [float(feat.get(name, 0.0)) for name in FEATURE_NAMES]
            else:
                continue
        xs.append([float(v) for v in vec])
        ys.append(STYLE_TO_IDX[style])
    return xs, ys


def train_entry_style_policy(
    project_root: str | Path,
    *,
    epochs: int = 40,
    lr: float = 0.05,
    hidden: int = STYLE_HIDDEN,
) -> dict[str, Any]:
    """Train MLP: entry features → market|limit|stop|oco."""
    if not torch_available():
        return {
            "ok": False,
            "error": "torch not available (pip install -e '.[torch]')",
            "path": str(style_weights_path(project_root)),
        }
    import torch

    rows = load_style_samples(project_root)
    xs, ys = _style_rows_to_xy(rows)
    if len(xs) < 8:
        return {
            "ok": False,
            "error": f"need >= 8 style samples, have {len(xs)}",
            "path": str(style_weights_path(project_root)),
            "samples": len(xs),
        }

    device = preferred_device()
    n_feat = len(FEATURE_NAMES)
    h = max(8, int(hidden))
    x_t = torch.tensor(xs, dtype=torch.float32, device=device)
    y_t = torch.tensor(ys, dtype=torch.long, device=device)
    model = _build_mlp(n_feat, h, 4).to(device)
    opt = torch.optim.SGD(model.parameters(), lr=lr)
    loss_fn = torch.nn.CrossEntropyLoss()
    model.train()
    last_loss = 0.0
    for _ in range(max(1, int(epochs))):
        opt.zero_grad()
        logits = model(x_t)
        loss = loss_fn(logits, y_t)
        loss.backward()
        opt.step()
        last_loss = float(loss.detach().cpu().item())

    model.eval()
    with torch.no_grad():
        pred = model(x_t).argmax(dim=1)
        acc = float((pred == y_t).float().mean().cpu().item())

    wdir = weights_dir(project_root)
    wdir.mkdir(parents=True, exist_ok=True)
    wpath = style_weights_path(project_root)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "n_features": n_feat,
            "hidden": h,
            "arch": STYLE_ARCH,
        },
        wpath,
    )
    meta = {
        "n_features": n_feat,
        "feature_names": list(FEATURE_NAMES),
        "classes": list(IDX_TO_STYLE[i] for i in range(4)),
        "samples": len(xs),
        "train_accuracy": round(acc, 4),
        "final_loss": round(last_loss, 6),
        "epochs": int(epochs),
        "device": device,
        "weights": str(wpath),
        "arch": STYLE_ARCH,
        "hidden": h,
        "note": "train_accuracy is in-sample on style_samples.jsonl",
    }
    style_meta_path(project_root).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "error": None, **meta}


def load_style_model(project_root: str | Path) -> Any | None:
    if not torch_available() or not style_weights_path(project_root).is_file():
        return None
    import torch

    blob = torch.load(style_weights_path(project_root), map_location="cpu")
    if not isinstance(blob, dict) or "state_dict" not in blob:
        return None
    state = blob["state_dict"]
    n_feat = int(blob.get("n_features") or 0)
    target = len(FEATURE_NAMES)
    if n_feat != target:
        return None
    hidden = int(blob.get("hidden") or STYLE_HIDDEN)
    model = _build_mlp(target, hidden, 4)
    try:
        model.load_state_dict(state)
    except Exception:
        return None
    model.eval()
    return model


def prefer_cancelable_entry_style(
    style: str,
    probs: Mapping[str, float] | None,
    *,
    margin: float = DEFAULT_CANCELABLE_STYLE_MARGIN,
) -> dict[str, Any]:
    """Prefer limit/stop/oco when competitive with market (cancelable pending).

    If argmax is already cancelable, keep it. If market wins but the best
    cancelable style is within ``margin``, switch to that cancelable style.
    """
    st = str(style or "market").strip().lower()
    if st not in STYLE_TO_IDX:
        st = "market"
    if not probs:
        return {"style": st, "biased": False, "from": st}
    if st in CANCELABLE_ENTRY_STYLES:
        return {"style": st, "biased": False, "from": st}

    p_mkt = float(probs.get("market") or 0.0)
    best_s = ""
    best_p = -1.0
    for name in CANCELABLE_ENTRY_STYLES:
        p = float(probs.get(name) or 0.0)
        if p > best_p:
            best_p = p
            best_s = name
    gap = max(0.0, float(margin))
    if best_s and best_p >= p_mkt - gap - 1e-12:
        return {"style": best_s, "biased": True, "from": st, "alt_prob": best_p, "market_prob": p_mkt}
    return {"style": st, "biased": False, "from": st}


def predict_entry_style(
    project_root: str | Path,
    features: Sequence[float] | Mapping[str, Any] | None,
    *,
    rng: Any = None,
    prefer_cancelable: bool = True,
    cancelable_margin: float = DEFAULT_CANCELABLE_STYLE_MARGIN,
) -> dict[str, Any]:
    """Infer market/limit/stop/oco; heuristic bootstrap until style weights exist."""
    from eurika.ml.paper_orders import choose_entry_style

    if isinstance(features, Mapping):
        feat_map: dict[str, Any] = {str(k): v for k, v in features.items()}
        vec = [float(features.get(name, 0.0)) for name in FEATURE_NAMES]
    elif isinstance(features, Sequence) and len(features) > 0:
        feat_map = {}
        vec = _pad_feature_vec(features, len(FEATURE_NAMES))
    else:
        feat_map = {}
        vec = [0.0] * len(FEATURE_NAMES)

    model = load_style_model(project_root)
    if model is None:
        style = choose_entry_style(feat_map or None, rng=rng)
        return {"style": style, "source": "heuristic", "probs": None}

    import torch

    with torch.no_grad():
        logits = model(torch.tensor([vec], dtype=torch.float32))
        probs_t = torch.softmax(logits, dim=1)[0]
        probs = probs_t.tolist()
        idx = int(logits.argmax(dim=1).item())
    raw_style = IDX_TO_STYLE.get(idx, "market")
    prob_map = {IDX_TO_STYLE[i]: probs[i] for i in range(4)}
    source = "model"
    style = raw_style
    if prefer_cancelable:
        biased = prefer_cancelable_entry_style(raw_style, prob_map, margin=cancelable_margin)
        style = str(biased.get("style") or raw_style)
        if biased.get("biased"):
            source = "model/cancelable"
    return {
        "style": style,
        "source": source,
        "probs": prob_map,
        "raw_style": raw_style,
    }


def model_status(project_root: str | Path) -> dict[str, Any]:
    meta_file = meta_path(project_root)
    meta: Optional[dict[str, Any]] = None
    if meta_file.is_file():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            meta = {"error": "unreadable meta"}
    exit_meta: Optional[dict[str, Any]] = None
    em = exit_meta_path(project_root)
    if em.is_file():
        try:
            exit_meta = json.loads(em.read_text(encoding="utf-8"))
        except Exception:
            exit_meta = {"error": "unreadable exit meta"}
    levels_meta: Optional[dict[str, Any]] = None
    lm = levels_meta_path(project_root)
    if lm.is_file():
        try:
            levels_meta = json.loads(lm.read_text(encoding="utf-8"))
        except Exception:
            levels_meta = {"error": "unreadable levels meta"}
    style_meta: Optional[dict[str, Any]] = None
    sm = style_meta_path(project_root)
    if sm.is_file():
        try:
            style_meta = json.loads(sm.read_text(encoding="utf-8"))
        except Exception:
            style_meta = {"error": "unreadable style meta"}
    return {
        "weights_exist": weights_path(project_root).is_file(),
        "weights": str(weights_path(project_root)),
        "meta": meta,
        "exit_weights_exist": exit_weights_path(project_root).is_file(),
        "exit_weights": str(exit_weights_path(project_root)),
        "exit_meta": exit_meta,
        "levels_weights_exist": levels_weights_path(project_root).is_file(),
        "levels_weights": str(levels_weights_path(project_root)),
        "levels_meta": levels_meta,
        "style_weights_exist": style_weights_path(project_root).is_file(),
        "style_weights": str(style_weights_path(project_root)),
        "style_meta": style_meta,
        "torch_available": torch_available(),
    }
