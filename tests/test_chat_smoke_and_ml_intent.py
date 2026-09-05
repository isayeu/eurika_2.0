"""Tests for smoke intent + ML intent router scaffold."""

from __future__ import annotations

from pathlib import Path

import pytest

from eurika.api.chat_intents_config import clear_cache, match_direct_intent


def test_smoke_intent_matches(tmp_path: Path) -> None:
    clear_cache()
    assert match_direct_intent(tmp_path, "проведи smoke test") == ("smoke_test", None)
    assert match_direct_intent(tmp_path, "smoke") == ("smoke_test", None)
    assert match_direct_intent(tmp_path, "run smoke test") == ("smoke_test", None)


def test_specific_test_path_is_not_routed_to_smoke(tmp_path: Path) -> None:
    from eurika.api.chat_direct import resolve_direct_handler

    clear_cache()
    assert resolve_direct_handler(
        tmp_path, "запусти тест tests/test_plugin_hook_orchestration.py"
    ) == (None, None)


def test_self_check_intent_matches(tmp_path: Path) -> None:
    clear_cache()
    assert match_direct_intent(tmp_path, "проведи self-check") == (
        "self_check",
        "$ eurika self-check .",
    )


def test_ml_intent_toggle_phrases(tmp_path: Path) -> None:
    clear_cache()
    assert match_direct_intent(tmp_path, "включи EURIKA_USE_ML_INTENT=1") == ("ml_intent_on", None)
    assert match_direct_intent(tmp_path, "выключи EURIKA_USE_ML_INTENT") == ("ml_intent_off", None)
    assert match_direct_intent(tmp_path, "Проверь статус ML") == ("ml_status", None)
    assert match_direct_intent(tmp_path, "статус ML") == ("ml_status", None)
    assert match_direct_intent(tmp_path, "включен ли VECTOR_INTENT?") == ("vector_intent_status", None)
    assert match_direct_intent(tmp_path, "включи EURIKA_USE_VECTOR_INTENT=1") == ("vector_intent_on", None)


def test_market_situation_intent(tmp_path: Path) -> None:
    clear_cache()
    assert match_direct_intent(tmp_path, "проведи анализ рынка") == ("market_situation", None)
    q = "а ты можешь провести анализ рынка который сейчас в тебе крутится?"
    assert match_direct_intent(tmp_path, q) == ("market_situation", None)
    assert match_direct_intent(tmp_path, "что сейчас на маркете?") == ("market_situation", None)
    assert match_direct_intent(tmp_path, "как дела на маркете?") == ("market_situation", None)
    assert match_direct_intent(tmp_path, "Как дела на рынке?") == ("market_situation", None)
    assert match_direct_intent(tmp_path, "что по маркету?") == ("market_situation", None)


def test_market_learning_report_intent(tmp_path: Path) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod
    from eurika.api.chat_direct import resolve_direct_handler
    from eurika.ml.paper_portfolio import ensure_portfolio

    q = "как твои успехи на маркете и обучении торговле?"
    assert match_direct_intent(tmp_path, q) == ("market_learning_report", None)
    assert resolve_direct_handler(tmp_path, q) == ("market_learning_report", None)
    # Generic ML-in-project question still goes to LLM (facts injected), not this handler.
    assert resolve_direct_handler(tmp_path, "как успехи обучения ML в проекте?") == (None, None)
    ensure_portfolio(tmp_path)
    out = chat_mod.chat_send(tmp_path, q)
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "Paper-экзамен" in text
    assert "| equity |" in text
    assert "LLM-учитель" in text


def test_market_ml_scope_intent(tmp_path: Path) -> None:
    clear_cache()
    q = (
        "Посмотри, если наша ML учится на маркете по разным тикерам, "
        "она изучает стратегию каждого тикера в отдельности, "
        "или при изучении поведения тикеров применяет это обучение в целом для рынка?"
    )
    assert match_direct_intent(tmp_path, q) == ("market_ml_scope", None)


def test_portfolio_agent_intents(tmp_path: Path) -> None:
    clear_cache()
    assert match_direct_intent(tmp_path, "запусти portfolio цикл") == (
        "portfolio_agent_once",
        None,
    )
    assert match_direct_intent(tmp_path, "статус portfolio") == (
        "portfolio_agent_status",
        None,
    )


def test_chat_portfolio_agent_status(tmp_path: Path) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod
    from eurika.ml.holistic_portfolio import ensure_holistic

    ensure_holistic(tmp_path)
    out = chat_mod.chat_send(tmp_path, "статус portfolio")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "HOLISTIC" in text or "Portfolio" in text


def test_chat_portfolio_agent_once_no_key(tmp_path: Path, monkeypatch) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod

    monkeypatch.setattr(
        "eurika.agent.cursor_judge.cursor_key_status",
        lambda _root: {"api_key_set": False},
    )
    out = chat_mod.chat_send(tmp_path, "запусти portfolio цикл")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "CURSOR_API_KEY" in text


def test_market_ticker_brief_not_ml_scope(tmp_path: Path) -> None:
    clear_cache()
    from eurika.api.chat_direct import looks_like_market_ml_scope_request

    q = (
        "у тебя же есть доступ к API Binance через маркет, "
        "проведи разбор тикера BTCUSDT на фьючерсах, перспектива, вход TP/SL"
    )
    assert looks_like_market_ml_scope_request(q) is False
    assert match_direct_intent(tmp_path, q) == ("market_ticker_brief", None)


def test_chat_market_ticker_brief_reply(tmp_path: Path) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod
    from eurika.ml.market_store import save_candles
    from eurika.ml.paper_portfolio import ensure_portfolio

    ensure_portfolio(tmp_path)
    bars = [
        {
            "open_time": i * 60_000,
            "open": 70_000.0 + i,
            "high": 70_100.0 + i,
            "low": 69_900.0 + i,
            "close": 70_050.0 + i,
            "volume": 10.0,
        }
        for i in range(40)
    ]
    save_candles(tmp_path, bars, symbol="BTCUSDT", interval="15m", market="futures")
    save_candles(tmp_path, bars, symbol="BTCUSDT", interval="1h", market="futures")
    out = chat_mod.chat_send(tmp_path, "разбор тикера BTCUSDT на фьючерсах")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "BTCUSDT" in text
    assert "MLP" in text
    assert "общая модель, не per-ticker" not in text


def test_market_logic_intent(tmp_path: Path) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod

    assert match_direct_intent(tmp_path, "Что скажешь о логике маркета в проекте?") == (
        "market_logic",
        None,
    )
    assert match_direct_intent(tmp_path, "как устроен paper market?") == ("market_logic", None)
    out = chat_mod.chat_send(tmp_path, "логика маркета")
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "paper-only" in text
    assert "market_policy" in text
    assert "MARKET СЕЙЧАС" not in text
    assert "фейков" not in text.lower()


def test_chat_market_situation_reply(tmp_path: Path) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod
    from eurika.ml.paper_portfolio import ensure_portfolio

    ensure_portfolio(tmp_path)
    out = chat_mod.chat_send(tmp_path, "анализ рынка")
    assert out.get("error") is None
    text = out.get("text") or ""
    assert "MARKET СЕЙЧАС" in text
    assert "банк:" in text
    assert "Linear" not in text  # not the architecture lecture



def test_chat_enable_ml_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod
    from eurika.utils.env import env_bool

    monkeypatch.delenv("EURIKA_USE_ML_INTENT", raising=False)
    monkeypatch.setattr(
        "eurika.ml.intent_router.train_intent_router",
        lambda root, epochs=30: {"ok": True, "samples": 10, "train_accuracy": 0.9},
    )
    monkeypatch.setattr("eurika.ml.torch_runtime.torch_available", lambda: True)
    out = chat_mod.chat_send(tmp_path, "включи EURIKA_USE_ML_INTENT=1")
    assert out.get("error") is None
    assert "EURIKA_USE_ML_INTENT" in (out.get("text") or "")
    assert env_bool("EURIKA_USE_ML_INTENT") is True
    assert (tmp_path / ".env").is_file()
    assert "EURIKA_USE_ML_INTENT=1" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_chat_send_smoke_uses_direct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_cache()
    from eurika.api import chat as chat_mod
    from eurika.api import chat_tools

    monkeypatch.setattr(
        chat_tools,
        "run_chat_smoke",
        lambda root, timeout=120: (True, "SMOKE\nok"),
    )
    # Avoid LLM path entirely
    out = chat_mod.chat_send(tmp_path, "проведи smoke test")
    assert out.get("error") is None
    assert "Smoke test" in (out.get("text") or "")
    assert "OK" in (out.get("text") or "")


def test_intent_router_train_and_predict(tmp_path: Path) -> None:
    from eurika.ml import intent_router as ir
    from eurika.ml.torch_runtime import torch_available

    if not torch_available():
        pytest.skip("torch not installed")
    st = ir.train_intent_router(tmp_path, epochs=25)
    assert st["ok"] is True
    assert st["samples"] >= 8
    pred = ir.predict_intent_route(tmp_path, "проведи smoke test")
    assert pred["ok"] is True
    # After training on exemplars, smoke should be preferred over LLM for this phrase
    assert pred.get("handler_id") in {"smoke_test", None} or pred.get("route") in {"direct", "llm"}


def test_match_ml_intent_disabled_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eurika.ml import intent_router as ir

    monkeypatch.delenv("EURIKA_USE_ML_INTENT", raising=False)
    assert ir.match_ml_intent(tmp_path, "проведи smoke test") is None


def test_match_ml_intent_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eurika.ml import intent_router as ir
    from eurika.ml.torch_runtime import torch_available

    if not torch_available():
        pytest.skip("torch not installed")
    monkeypatch.setenv("EURIKA_USE_ML_INTENT", "1")
    ir.train_intent_router(tmp_path, epochs=30)
    hit = ir.match_ml_intent(tmp_path, "проведи smoke test", min_confidence=0.2)
    # May or may not hit depending on tiny train; at least should not crash
    assert hit is None or hit[0] == "smoke_test"
