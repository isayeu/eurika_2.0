"""Tests for Models → ML (PyTorch) handlers."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

from qt_app.ui.handlers import ml_handlers


def test_apply_torch_device_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EURIKA_TORCH_DEVICE", raising=False)
    assert ml_handlers.apply_torch_device_env("CUDA") == "cuda"
    assert os.environ.get("EURIKA_TORCH_DEVICE") == "cuda"
    assert ml_handlers.apply_torch_device_env("nope") == "cpu"
    assert os.environ.get("EURIKA_TORCH_DEVICE") == "cpu"


def test_refresh_ml_status_updates_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = SimpleNamespace(
        ml_torch_device_combo=SimpleNamespace(currentText=lambda: "cpu"),
        ml_torch_available=SimpleNamespace(setText=lambda v: setattr(labels, "avail", v)),
        ml_torch_version=SimpleNamespace(setText=lambda v: setattr(labels, "ver", v)),
        ml_torch_cuda=SimpleNamespace(setText=lambda v: setattr(labels, "cuda", v)),
        ml_torch_resolved=SimpleNamespace(setText=lambda v: setattr(labels, "dev", v)),
        ml_torch_smoke=SimpleNamespace(setText=lambda v: setattr(labels, "smoke", v)),
        ml_torch_output=SimpleNamespace(
            append=lambda _t: None,
            toPlainText=lambda: "",
            setPlainText=lambda _t: None,
        ),
        root_edit=SimpleNamespace(text=lambda: "."),
        ml_market_trades=SimpleNamespace(setText=lambda v: setattr(labels, "trades", v)),
        ml_market_accuracy=SimpleNamespace(setText=lambda v: setattr(labels, "macc", v)),
        ml_market_live=SimpleNamespace(setText=lambda v: setattr(labels, "live", v)),
        ml_market_pnl=SimpleNamespace(setText=lambda v: setattr(labels, "pnl", v)),
        ml_market_opens=SimpleNamespace(setText=lambda v: setattr(labels, "opens", v), setToolTip=lambda _t: None),
        ml_market_model=SimpleNamespace(setText=lambda v: setattr(labels, "model", v)),
        ml_market_candles=SimpleNamespace(setText=lambda v: setattr(labels, "candles", v)),
    )
    monkeypatch.setattr(
        "eurika.ml.torch_runtime.torch_status",
        lambda run_smoke_check=True: {
            "available": True,
            "version": "2.1.0-test",
            "device": "cpu",
            "cuda": False,
            "smoke_ok": True,
            "error": None,
        },
    )
    monkeypatch.setattr(
        "eurika.ml.torch_runtime.format_torch_block",
        lambda st: "PYTORCH\n  available: yes",
    )
    monkeypatch.setattr(
        "eurika.ml.learning_status.market_learning_status",
        lambda root: {
            "paper": {"count": 10, "buys": 6, "sells": 4, "accuracy": 0.4},
            "live": {"count": 2, "correct": 1, "accuracy": 0.5},
            "portfolio": {
                "equity_usdt": 1000.0,
                "session_pnl_usdt": 0.0,
                "margin_used_usdt": 10.0,
                "max_margin_usdt": 300.0,
            },
            "pnl": {
                "all": {"sum_edge": -0.02, "n": 10},
                "live": {"sum_edge": -0.01, "n": 2, "sum_pnl_usdt": -0.5},
                "session": {"sum_edge": -0.005, "n": 1},
            },
            "opens": {"count": 1, "positions": [{"symbol": "ETHUSDT", "action": "SELL", "entry": 1.0}]},
            "model": {"weights_exist": True, "samples": 10, "train_accuracy": 0.6, "device": "cpu"},
            "market": {"series": [{"symbol": "ETHUSDT", "interval": "15m", "count": 50}]},
        },
    )
    st = ml_handlers.refresh_ml_status(cast(Any, labels), run_smoke=True, append_log=False)
    assert st["available"] is True
    assert labels.avail == "yes"
    assert labels.ver == "2.1.0-test"
    assert labels.smoke == "ok"
    assert "10" in labels.trades
    assert labels.macc == "0.400"
    assert "сессия=" in labels.pnl
