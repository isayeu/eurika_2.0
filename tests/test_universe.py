"""Tests for spot-balance → multi-quote universe helper."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.ml.universe import (
    asset_to_usdt_symbol,
    candidate_symbols,
    resolve_pair_for_asset,
    symbols_from_balance_rows,
    symbols_from_balances,
)


def test_asset_to_usdt_symbol() -> None:
    assert asset_to_usdt_symbol("eth") == "ETHUSDT"
    assert asset_to_usdt_symbol("USDT") is None
    assert asset_to_usdt_symbol("LDETH") is None


def test_candidate_symbols_priority() -> None:
    cands = candidate_symbols("XYZ")
    assert cands[0] == "XYZUSDT"
    assert "XYZBTC" in cands
    assert "XYZETH" in cands
    assert "BTCbtc".upper() not in {c.lower() for c in candidate_symbols("BTC")}  # no BTCBTC
    assert candidate_symbols("BTC")[0] == "BTCUSDT"


def test_resolve_falls_back_to_btc_bridge() -> None:
    def probe(sym: str) -> bool:
        return sym == "RAREBTC"

    assert resolve_pair_for_asset("RARE", probe=probe) == "RAREBTC"
    assert resolve_pair_for_asset("RARE", probe=lambda _s: False) is None
    assert resolve_pair_for_asset("RARE") == "RAREUSDT"  # no probe → prefer USDT


def test_symbols_from_balance_rows() -> None:
    st = symbols_from_balance_rows(
        [
            {"asset": "USDT", "free": "10"},
            {"asset": "ETH", "free": "0.1"},
            {"asset": "SOL", "free": "1"},
            {"asset": "LDBTC", "free": "0.01"},
        ]
    )
    assert st["symbols"] == ["ETHUSDT", "SOLUSDT"]
    assert "USDT" in st["skipped"]
    assert st["fallback_used"] is False


def test_symbols_with_probe_mixed_quotes() -> None:
    def probe(sym: str) -> bool:
        return sym in {"ETHUSDT", "OBSCUREBTC"}

    st = symbols_from_balance_rows(
        [
            {"asset": "ETH", "free": "1"},
            {"asset": "OBSCURE", "free": "2"},
            {"asset": "DEAD", "free": "3"},
        ],
        probe=probe,
    )
    assert st["symbols"] == ["ETHUSDT", "OBSCUREBTC"]
    assert "DEAD" in st["skipped"]
    assert st["bridges"]["OBSCURE"] == "BTC"


def test_symbols_fallback_when_empty() -> None:
    st = symbols_from_balance_rows([{"asset": "USDT", "free": "5"}], fallback="BTCUSDT")
    assert st["symbols"] == ["BTCUSDT"]
    assert st["fallback_used"] is True


def test_symbols_from_balances_mocked(tmp_path: Path) -> None:
    def fetch(*, min_free: float = 0.0):
        return {
            "ok": True,
            "balances": [
                {"asset": "BNB", "free": "1", "locked": "0"},
                {"asset": "ETH", "free": "0.2", "locked": "0"},
            ],
            "count": 2,
            "error": None,
        }

    def probe(sym: str) -> bool:
        return sym.endswith("USDT")

    st = symbols_from_balances(
        fetch_balances=fetch,
        max_symbols=8,
        project_root=tmp_path,
        probe=probe,
    )
    assert st["ok"] is True
    assert st["symbols"] == ["BNBUSDT", "ETHUSDT"]
    assert st["error"] is None
    assert (tmp_path / ".eurika" / "ml" / "pair_cache.json").is_file()
    assert (tmp_path / ".eurika" / "ml" / "universe_snapshot.json").is_file()


def test_balances_dns_blip_uses_snapshot(tmp_path: Path) -> None:
    from eurika.ml.universe import save_universe_snapshot

    save_universe_snapshot(
        tmp_path,
        ["ADAUSDT", "BTCUSDT", "ETHUSDT"],
    )

    def boom(*, min_free: float = 0.0):
        raise OSError("Временный сбой в разрешении имен")

    st = symbols_from_balances(
        fetch_balances=boom,
        project_root=tmp_path,
        fallback="ETHUSDT",
    )
    assert st["ok"] is False
    assert st["stale"] is True
    assert st["source"] == "snapshot"
    assert st["symbols"] == ["ADAUSDT", "BTCUSDT", "ETHUSDT"]


def test_balances_dns_blip_uses_open_positions(tmp_path: Path) -> None:
    from eurika.ml.market_store import ml_root

    path = ml_root(tmp_path) / "open_paper.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "positions": [
                    {"symbol": "RENDERUSDT", "action": "SELL"},
                    {"symbol": "ADAUSDT", "action": "BUY"},
                ]
            }
        ),
        encoding="utf-8",
    )

    def boom(*, min_free: float = 0.0):
        return {"ok": False, "balances": [], "count": 0, "error": "dns"}

    st = symbols_from_balances(
        fetch_balances=boom,
        project_root=tmp_path,
        fallback="ETHUSDT",
    )
    assert st["source"] == "open_positions"
    assert st["symbols"] == ["ADAUSDT", "RENDERUSDT"]


def test_to_usdt_perp_and_futures_filter() -> None:
    from eurika.ml.universe import symbols_for_futures, to_usdt_perp_symbol

    assert to_usdt_perp_symbol("ETHFDUSD") == "ETHUSDT"
    assert to_usdt_perp_symbol("BTCUSDT") == "BTCUSDT"
    assert to_usdt_perp_symbol("SOL") == "SOLUSDT"

    out = symbols_for_futures(
        ["ETHFDUSD", "SOLBTC", "NOPEUSDT"],
        probe=lambda s: s in {"ETHUSDT", "SOLUSDT"},
        use_probe=True,
    )
    assert out["symbols"] == ["ETHUSDT", "SOLUSDT"]
    assert "NOPEUSDT" in out["skipped"]
    assert out["fallback_used"] is False


def test_ticker_lists_save_load(tmp_path: Path) -> None:
    from eurika.ml.universe import load_ticker_lists, save_ticker_lists

    path = save_ticker_lists(tmp_path, spot=["btcusdt", "ETHUSDT", "btcusdt"], futures=["SOLUSDT"])
    assert path.is_file()
    data = load_ticker_lists(tmp_path)
    assert data["spot"] == ["BTCUSDT", "ETHUSDT"]
    assert data["futures"] == ["SOLUSDT"]
    save_ticker_lists(tmp_path, futures=["ONGUSDT", "bad!"])
    data2 = load_ticker_lists(tmp_path)
    assert data2["spot"] == ["BTCUSDT", "ETHUSDT"]  # unchanged
    assert data2["futures"] == ["ONGUSDT"]
