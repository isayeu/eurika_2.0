"""Smoke tests for assistant thesis night paper."""

from __future__ import annotations

from pathlib import Path

from eurika.ml.assistant_paper import (
    DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M,
    MAX_SAME_LIMIT_PLACES,
    apply_assistant_actions,
    assistant_entry_block_reason,
    assistant_reentry_cooldown_active,
    ensure_portfolio,
    format_assistant_book_for_prompt,
    load_pending,
    propose_thesis,
    register_assistant_reentry_cooldown,
    run_cycle,
    seed_theses,
)
from eurika.ml.market_store import save_candles


def _bars(n: int, start: float = 100.0) -> list[dict]:
    out = []
    for i in range(n):
        px = start + i * 0.05
        out.append(
            {
                "open_time": i * 60_000,
                "open": px,
                "high": px + 0.2,
                "low": px - 0.1,
                "close": px + 0.05,
                "volume": 10.0,
            }
        )
    return out


def _seed_symbol(root: Path, sym: str = "BTCUSDT", start: float = 50000.0) -> None:
    bars = _bars(50, start)
    for iv in ("15m", "1h", "1m"):
        save_candles(root, bars, symbol=sym, interval=iv, market="futures")
    ensure_portfolio(root)


def _place(root: Path, *, limit_px: float, symbol: str = "BTCUSDT") -> dict:
    return apply_assistant_actions(
        root,
        [
            {
                "symbol": symbol,
                "market": "futures",
                "action": "place",
                "side": "BUY",
                "entry_style": "limit",
                "limit_px": limit_px,
                "invalidate_px": limit_px * 0.99,
                "tp_pct": 0.01,
                "sl_pct": 0.008,
            }
        ],
    )


def test_propose_thesis_trend_pullback() -> None:
    c15 = _bars(40, 100.0)
    c1h = _bars(40, 95.0)
    th = propose_thesis("BTCUSDT", candles_15m=c15, candles_1h=c1h)
    assert th is not None
    assert th["symbol"] == "BTCUSDT"
    assert th["side"] == "BUY"
    assert th["entry_style"] in {"limit", "stop"}


def test_assistant_cycle_smoke(tmp_path: Path) -> None:
    sym = "ETHUSDT"
    bars = _bars(50, 2000.0)
    save_candles(tmp_path, bars, symbol=sym, interval="15m", market="futures")
    save_candles(tmp_path, bars, symbol=sym, interval="1h", market="futures")
    save_candles(tmp_path, bars, symbol=sym, interval="1m", market="futures")
    ensure_portfolio(tmp_path)
    out = run_cycle(tmp_path)
    assert "equity_usdt" in out
    assert (tmp_path / ".eurika" / "ml" / "assistant_journal.jsonl").is_file()


def test_seed_writes_journal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "eurika.ml.assistant_paper.sync_klines",
        lambda *a, **k: {"ok": True},
    )
    monkeypatch.setattr(
        "eurika.ml.assistant_paper.load_candles",
        lambda root, sym, iv, market="futures": _bars(45, 50000.0 if "BTC" in sym else 3000.0),
    )
    rows = seed_theses(tmp_path, symbols=["BTCUSDT", "ETHUSDT"])
    assert rows
    journal = (tmp_path / ".eurika" / "ml" / "assistant_journal.jsonl").read_text(encoding="utf-8")
    assert "SEED" in journal


def test_sl_registers_assistant_reentry_cooldown(tmp_path: Path) -> None:
    _seed_symbol(tmp_path)
    exit_ts = 1_700_000_000_000
    row = register_assistant_reentry_cooldown(
        tmp_path,
        symbol="ARBUSDT",
        market="futures",
        side="BUY",
        exit_ts_ms=exit_ts,
        bars_1m=DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M,
        exit_reason="sl",
    )
    assert int(row["until_ts"]) == exit_ts + DEFAULT_SL_REENTRY_COOLDOWN_BARS_1M * 60_000
    assert assistant_reentry_cooldown_active(
        tmp_path, symbol="ARBUSDT", market="futures", side="BUY", now_ts_ms=exit_ts + 60_000
    )
    reason = assistant_entry_block_reason(
        tmp_path,
        symbol="ARBUSDT",
        market="futures",
        side="BUY",
        level_px=0.1325,
        now_ts_ms=exit_ts + 60_000,
    )
    assert reason and "cooldown" in reason


def test_place_blocked_during_sl_cooldown(tmp_path: Path, monkeypatch) -> None:
    from eurika.ml.holistic_portfolio import ensure_holistic

    _seed_symbol(tmp_path)
    ensure_holistic(tmp_path)
    now = 1_800_000_000_000
    register_assistant_reentry_cooldown(
        tmp_path,
        symbol="BTCUSDT",
        market="futures",
        side="BUY",
        exit_ts_ms=now,
        exit_reason="sl",
    )
    monkeypatch.setattr("eurika.ml.assistant_paper._now_ms", lambda: now + 5 * 60_000)
    out = _place(tmp_path, limit_px=49000.0)
    assert int(out["applied"].get("place") or 0) == 0
    assert int(out["applied"].get("blocked") or 0) == 1
    assert load_pending(tmp_path) == []
    assert out["block_notes"]


def test_same_limit_place_cap(tmp_path: Path) -> None:
    from eurika.ml.assistant_paper import save_pending
    from eurika.ml.holistic_portfolio import ensure_holistic, reconcile_holistic, save_holistic

    _seed_symbol(tmp_path)
    ensure_holistic(tmp_path)
    for i in range(MAX_SAME_LIMIT_PLACES):
        out = _place(tmp_path, limit_px=0.1325, symbol="BTCUSDT")
        assert int(out["applied"]["place"]) == 1, f"place #{i + 1} should succeed"
        # clear pending so next place is not ignored as duplicate open book
        save_pending(tmp_path, [])
        h = reconcile_holistic(tmp_path)
        h["trade_margin_usdt"] = 0.0
        h["cash_free_usdt"] = float(h.get("equity_usdt") or 1000.0)
        save_holistic(tmp_path, h)

    blocked = _place(tmp_path, limit_px=0.1325, symbol="BTCUSDT")
    assert int(blocked["applied"]["place"]) == 0
    assert int(blocked["applied"]["blocked"]) == 1
    assert any("уровень" in n or "place" in n for n in blocked["block_notes"])

    # different level still allowed
    other = _place(tmp_path, limit_px=0.14, symbol="BTCUSDT")
    assert int(other["applied"]["place"]) == 1


def test_enforce_assistant_tp_sl_floor() -> None:
    from eurika.ml.assistant_paper import (
        DEFAULT_ASSISTANT_SL_PCT,
        DEFAULT_ASSISTANT_TP_PCT,
        MIN_ASSISTANT_TP_SL_RATIO,
        enforce_assistant_tp_sl,
    )

    tp, sl = enforce_assistant_tp_sl(0.01, 0.008)
    assert sl == 0.008
    assert tp >= sl * MIN_ASSISTANT_TP_SL_RATIO
    # already good ~3:1 stays
    tp2, sl2 = enforce_assistant_tp_sl(DEFAULT_ASSISTANT_TP_PCT, DEFAULT_ASSISTANT_SL_PCT)
    assert tp2 == DEFAULT_ASSISTANT_TP_PCT
    assert sl2 == DEFAULT_ASSISTANT_SL_PCT


def test_place_bumps_weak_rr(tmp_path: Path) -> None:
    from eurika.ml.holistic_portfolio import ensure_holistic
    from eurika.ml.assistant_paper import MIN_ASSISTANT_TP_SL_RATIO, load_pending

    _seed_symbol(tmp_path)
    ensure_holistic(tmp_path)
    out = apply_assistant_actions(
        tmp_path,
        [
            {
                "symbol": "BTCUSDT",
                "market": "futures",
                "action": "place",
                "side": "BUY",
                "entry_style": "limit",
                "limit_px": 49000.0,
                "invalidate_px": 48500.0,
                "tp_pct": 0.01,
                "sl_pct": 0.008,
            }
        ],
    )
    assert int(out["applied"]["place"]) == 1
    order = load_pending(tmp_path)[0]
    assert float(order["tp_pct"]) >= float(order["sl_pct"]) * MIN_ASSISTANT_TP_SL_RATIO


def test_structure_arm_default_raised() -> None:
    from eurika.ml.assistant_paper import DEFAULT_STRUCTURE_ARM_MFE_PCT

    assert DEFAULT_STRUCTURE_ARM_MFE_PCT >= 0.01


def test_book_prompt_lists_reentry_guards(tmp_path: Path) -> None:
    import time

    _seed_symbol(tmp_path)
    now = int(time.time() * 1000)
    register_assistant_reentry_cooldown(
        tmp_path,
        symbol="ARBUSDT",
        market="futures",
        side="BUY",
        exit_ts_ms=now,
        exit_reason="sl",
    )
    text = format_assistant_book_for_prompt(tmp_path)
    assert "REENTRY GUARDS" in text
    assert "ARBUSDT" in text


def test_portfolio_rules_show_rr_example() -> None:
    from eurika.ml.portfolio_agent import PORTFOLIO_AGENT_RULES

    assert "0.024" in PORTFOLIO_AGENT_RULES
    assert "0.008" in PORTFOLIO_AGENT_RULES
    assert "3×SL" in PORTFOLIO_AGENT_RULES or "3xSL" in PORTFOLIO_AGENT_RULES.lower() or "TP≈3" in PORTFOLIO_AGENT_RULES
