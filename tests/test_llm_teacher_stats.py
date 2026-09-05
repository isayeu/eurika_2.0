"""Tests for LLM teacher history stats (Chat direct answer)."""

from __future__ import annotations

import json
from pathlib import Path

from eurika.api.chat_intents_config import clear_cache, match_direct_intent
from eurika.ml.llm_teacher_stats import (
    format_llm_shadow_report,
    format_llm_teacher_stats_report,
    llm_teacher_history_stats,
)


def test_llm_teacher_stats_counts(tmp_path: Path) -> None:
    ml = tmp_path / ".eurika" / "ml"
    ml.mkdir(parents=True)
    path = ml / "llm_teacher_samples.jsonl"
    rows = [
        {
            "ts": 1000,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "enter": "yes",
            "settled": True,
            "skip": False,
            "edge": 0.01,
            "settle_source": "live",
        },
        {
            "ts": 2000,
            "symbol": "ETHUSDT",
            "side": "HOLD",
            "enter": "wait",
            "settled": True,
            "skip": False,
            "edge": -0.02,
            "settle_source": "llm_path",
        },
        {
            "ts": 3000,
            "symbol": "ADAUSDT",
            "side": "HOLD",
            "enter": "no",
            "settled": True,
            "skip": True,
            "edge": 0.005,
        },
        {"ts": 4000, "symbol": "SOLUSDT", "side": "BUY", "enter": "yes", "settled": False},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    st = llm_teacher_history_stats(tmp_path, refresh=False)
    assert st["total"] == 4
    assert st["pending"] == 1
    assert st["graded_n"] == 2
    assert st["plus_n"] == 1
    assert st["minus_n"] == 1
    assert st["skipped"] == 1

    text = format_llm_teacher_stats_report(st)
    assert "в плюсе" in text
    assert "**1**" in text
    assert "llm_path" in text


def test_llm_teacher_execution_intent(tmp_path: Path) -> None:
    from eurika.api import chat as chat_mod
    from eurika.ml.paper_portfolio import ensure_portfolio

    clear_cache()
    ml = tmp_path / ".eurika" / "ml"
    ml.mkdir(parents=True)
    (ml / "llm_teacher_samples.jsonl").write_text(
        json.dumps({"ts": 1, "symbol": "X", "side": "BUY", "source": "cursor"}) + "\n",
        encoding="utf-8",
    )
    ensure_portfolio(tmp_path)
    q = "ML хоть раз отработала по совету LLM?"
    assert match_direct_intent(tmp_path, q) == ("llm_teacher_execution", None)
    out = chat_mod.chat_send(tmp_path, q)
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "не исполняет" in text.lower() or "Нет" in text
    assert "eurika-cmds" not in text
    assert "python -c" not in text


def test_llm_teacher_stats_intent_and_chat(tmp_path: Path) -> None:
    from eurika.api import chat as chat_mod
    from eurika.api.chat_direct import resolve_direct_handler
    from eurika.ml.paper_portfolio import ensure_portfolio

    clear_cache()
    ml = tmp_path / ".eurika" / "ml"
    ml.mkdir(parents=True)
    (ml / "llm_teacher_samples.jsonl").write_text(
        json.dumps(
            {
                "ts": 1,
                "symbol": "X",
                "side": "BUY",
                "enter": "yes",
                "settled": True,
                "skip": False,
                "edge": 0.001,
                "settle_source": "live",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ensure_portfolio(tmp_path)

    q = "проверь сколько прогнозов по LLM вышло в плюс за все время"
    assert match_direct_intent(tmp_path, q) == ("llm_teacher_stats", None)
    assert resolve_direct_handler(tmp_path, q) == ("llm_teacher_stats", None)

    out = chat_mod.chat_send(tmp_path, q)
    text = out.get("text") or ""
    assert out.get("error") is None
    assert "LLM-учитель" in text
    assert "в плюсе" in text
    assert "python -c" not in text


def test_llm_shadow_report_intent_and_chat(tmp_path: Path) -> None:
    from eurika.api import chat as chat_mod
    from eurika.api.chat_direct import resolve_direct_handler
    from eurika.ml.llm_shadow import save_shadow_portfolio
    from eurika.ml.paper_portfolio import ensure_portfolio

    clear_cache()
    ensure_portfolio(tmp_path)
    save_shadow_portfolio(
        tmp_path,
        {
            "version": 1,
            "start_equity_usdt": 1000.0,
            "equity_usdt": 1005.0,
            "margin_used_usdt": 0.0,
            "realized_pnl_usdt": 5.0,
            "risk_frac": 0.01,
            "max_margin_frac": 0.30,
        },
    )
    q = "как дела у llm shadow?"
    assert match_direct_intent(tmp_path, q) == ("llm_shadow_report", None)
    assert resolve_direct_handler(tmp_path, q) == ("llm_shadow_report", None)
    text = format_llm_shadow_report(tmp_path)
    assert "LLM Shadow Portfolio" in text
    out = chat_mod.chat_send(tmp_path, q)
    assert out.get("error") is None
    assert "LLM Shadow Portfolio" in (out.get("text") or "")
