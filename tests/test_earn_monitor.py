"""Tests for paper earn monitor."""

from __future__ import annotations

from pathlib import Path

from eurika.ml.earn_monitor import (
    accrue_earn_yield,
    apply_earn_actions,
    ensure_earn_portfolio,
    format_earn_book_for_prompt,
    load_earn_positions,
)


def test_earn_deposit_and_accrue(tmp_path: Path) -> None:
    ensure_earn_portfolio(tmp_path)
    rates = {
        "products": [
            {"asset": "USDT", "kind": "flexible", "apr": 0.05, "product_id": "flex:USDT"},
        ]
    }
    out = apply_earn_actions(
        tmp_path,
        [{"product": "earn", "action": "deposit", "asset": "USDT", "amount_usdt": 400, "earn_type": "flexible"}],
        rates=rates,
    )
    assert int(out["applied"]["deposit"]) == 1
    assert len(load_earn_positions(tmp_path)) == 1
    from eurika.ml.holistic_portfolio import load_holistic

    assert float(load_holistic(tmp_path)["cash_free_usdt"]) == 600.0

    port = ensure_earn_portfolio(tmp_path)
    later = int(port.get("last_accrue_ms") or 0) + 86_400_000
    acc = accrue_earn_yield(tmp_path, now_ms=later)
    assert float(acc["accrued_usdt"]) > 0.0


def test_format_earn_book(tmp_path: Path) -> None:
    ensure_earn_portfolio(tmp_path)
    text = format_earn_book_for_prompt(tmp_path, rates={"products": []})
    assert "EARN PAPER BOOK" in text
