"""Tests for session digest («пока тебя не было»)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.chat_intents_config import clear_cache, match_direct_intent
from eurika.ml import session_digest as sd
from eurika.ml.paper_portfolio import ensure_portfolio
from eurika.ml.paper_trader import paper_trades_path


def test_digest_empty_lookback(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    data = sd.build_session_digest(tmp_path, now_ms=2_000_000_000_000, mark_seen=False)
    assert data["ok"] is True
    assert data["since_kind"] == "lookback"
    assert data["filled"] == 0
    text = sd.format_session_digest(data)
    assert "ПОКА ТЕБЯ НЕ БЫЛО" in text
    assert "банки (3 отдельных" in text
    assert "Live/MLP exam" in text
    assert "Portfolio/holistic" in text
    assert "LLM shadow" in text
    assert "сделок не было" in text or "fill=0" in text


def test_digest_three_banks_deltas(tmp_path: Path) -> None:
    from eurika.ml.earn_monitor import save_earn_positions
    from eurika.ml.holistic_portfolio import ensure_holistic, save_holistic
    from eurika.ml.llm_shadow import ensure_shadow_portfolio, save_shadow_portfolio

    ensure_portfolio(tmp_path)
    ensure_holistic(tmp_path)
    ensure_shadow_portfolio(tmp_path)
    save_earn_positions(
        tmp_path,
        [
            {
                "id": "earn-test",
                "asset": "USDT",
                "kind": "flexible",
                "amount": 800.0,
                "apr": 0.0275,
                "accrued_usdt": 0.0,
            }
        ],
    )
    h = ensure_holistic(tmp_path)
    h["cash_free_usdt"] = 200.17
    h["earn_principal_usdt"] = 800.0
    h["earn_accrued_usdt"] = 0.0
    h["trade_margin_usdt"] = 0.0
    h["trade_realized_pnl_usdt"] = 0.17
    h["equity_usdt"] = 1000.17
    h["migrated_legacy"] = False
    h["legacy_margin_repaired"] = True
    save_holistic(tmp_path, h)
    sh = ensure_shadow_portfolio(tmp_path)
    sh["equity_usdt"] = 994.0
    save_shadow_portfolio(tmp_path, sh)

    t0 = 1_700_000_000_000
    path = sd.session_seen_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "seen_ms": t0,
                "equity_usdt": 1000.0,
                "equity_portfolio_usdt": 1000.0,
                "equity_shadow_usdt": 1000.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    data = sd.build_session_digest(tmp_path, now_ms=t0 + 60_000, mark_seen=False)
    assert "banks" in data
    assert abs(float(data["banks"]["portfolio"]["equity_usdt"]) - 1000.17) < 0.01
    assert abs(float(data["banks"]["portfolio"]["delta_usdt"]) - 0.17) < 0.01
    assert abs(float(data["banks"]["shadow"]["delta_usdt"]) - (-6.0)) < 0.01
    text = sd.format_session_digest(data)
    assert "Portfolio/holistic" in text
    assert "LLM shadow" in text
    assert "earn=800" in text


def test_digest_since_last_seen_with_trades(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    t0 = 1_700_000_000_000
    sd.mark_session_seen(tmp_path, equity_usdt=1000.0)
    # Force seen_ms in the past
    path = sd.session_seen_path(tmp_path)
    path.write_text(
        '{"seen_ms": %d, "equity_usdt": 1000.0}\n' % t0,
        encoding="utf-8",
    )
    trades = paper_trades_path(tmp_path)
    trades.parent.mkdir(parents=True, exist_ok=True)
    trades.write_text(
        "\n".join(
            [
                '{"live":true,"action":"BUY","edge":0.003,"exit_ts":%d,"exit_reason":"model","pnl_usdt":0.3}'
                % (t0 + 60_000),
                '{"live":true,"action":"SELL","edge":-0.011,"exit_ts":%d,"exit_reason":"sl","pnl_usdt":-1.1}'
                % (t0 + 120_000),
                '{"live":true,"action":"BUY","edge":0.0,"exit_ts":%d,"exit_reason":"cancel_side_flip"}'
                % (t0 + 180_000),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    data = sd.build_session_digest(tmp_path, now_ms=t0 + 200_000, mark_seen=False)
    assert data["since_kind"] == "last_seen"
    assert data["filled"] == 2
    assert data["cancelled"] == 1
    assert data["by_exit"].get("model") == 1
    assert data["by_exit"].get("sl") == 1
    assert abs(float(data["sum_edge"]) - (-0.008)) < 1e-9
    text = sd.format_session_digest(data)
    assert "model=1" in text
    assert "sl=1" in text


def test_session_digest_intent(tmp_path: Path) -> None:
    clear_cache()
    assert match_direct_intent(tmp_path, "что было пока меня не было?") == ("session_digest", None)
    assert match_direct_intent(tmp_path, "пока тебя не было") == ("session_digest", None)
    assert match_direct_intent(tmp_path, "какие новости пока меня не было?") == ("session_digest", None)


def test_chat_system_access_not_web_search(tmp_path: Path, monkeypatch) -> None:
    """«доступ к системе» must answer capabilities — never DuckDuckGo."""
    clear_cache()
    from eurika.api import chat as chat_mod
    from eurika.api.chat_intents_config import match_direct_intent
    from eurika.api.chat_direct import resolve_direct_handler

    q = "у тебя есть доступ к системе и системным командам?"
    assert match_direct_intent(tmp_path, q) == ("capabilities", None)
    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")
    monkeypatch.setattr(
        "eurika.api.chat_vector.match_fuzzy_intent",
        lambda *_a, **_k: ("web_search", None, 0.95),
    )
    assert resolve_direct_handler(tmp_path, q) == ("capabilities", None)
    monkeypatch.setattr(
        "eurika.reasoning.architect.call_llm_with_prompt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )
    out = chat_mod.chat_send(tmp_path, q)
    text = out.get("text") or ""
    assert "Результаты поиска" not in text
    assert "Terminal" in text or "терминал" in text.lower()
    assert "локальный доступ" in text


def test_chat_session_digest(tmp_path: Path) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod

    ensure_portfolio(tmp_path)
    out = chat_mod.chat_send(tmp_path, "пока меня не было")
    assert out.get("error") is None
    assert "ПОКА ТЕБЯ НЕ БЫЛО" in (out.get("text") or "")
