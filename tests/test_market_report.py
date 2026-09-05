"""Tests for Market dashboard report."""

from __future__ import annotations

from pathlib import Path

from eurika.ml.llm_shadow import apply_shadow_actions, parse_shadow_actions
from eurika.ml.market_report import format_market_dashboard_report, format_now_books_block
from eurika.ml.market_store import save_candles
from eurika.ml.paper_portfolio import ensure_portfolio


def _seed(root: Path, symbol: str = "ETHUSDT", market: str = "futures") -> None:
    bars = [
        {
            "open_time": i * 60_000,
            "open": 2000.0,
            "high": 2010.0,
            "low": 1990.0,
            "close": 2005.0,
            "volume": 1.0,
        }
        for i in range(30)
    ]
    save_candles(root, bars, symbol=symbol, interval="15m", market=market)
    save_candles(root, bars, symbol=symbol, interval="1m", market=market)
    save_candles(root, bars, symbol=symbol, interval="1h", market=market)


def test_format_market_dashboard_report_has_sections(tmp_path: Path) -> None:
    ensure_portfolio(tmp_path)
    _seed(tmp_path)
    apply_shadow_actions(
        tmp_path,
        parse_shadow_actions(
            '{"shadow_actions":[{"symbol":"ETHUSDT","market":"fut","action":"place","side":"BUY",'
            '"entry_style":"limit","limit_px":1990.0,"tp_pct":0.01,"sl_pct":0.008}]}'
        ),
    )
    text = format_market_dashboard_report(tmp_path)
    assert "# Market отчёт" in text
    assert "## Сейчас (opens / pending)" in text
    assert "### Portfolio agent trade opens" in text
    assert "### Portfolio earn (paper)" in text
    assert "# Portfolio agent — статус" in text
    assert "Банк:" in text or "HOLISTIC CASH POOL" in text
    assert "### LLM shadow pending" in text
    assert "ETHUSDT" in text
    assert "1990" in text
    assert "Paper-экзамен" in text or "## Paper" in text
    assert "LLM Shadow Portfolio" in text
    assert "| тикер |" in text

    now = format_now_books_block(tmp_path)
    assert "Portfolio agent pending" in now
    assert "LLM shadow pending" in now
    assert "limit" in now
