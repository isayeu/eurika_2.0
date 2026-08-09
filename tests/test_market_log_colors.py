"""Unit tests for Market transcript HTML coloring (no Qt widgets)."""

from __future__ import annotations

from qt_app.ui.handlers import market_handlers as mh


def test_format_market_line_kind_badge_and_strip_prefix() -> None:
    html_line = mh._format_market_line(
        "анализ: BTCUSDT окно=+0.1%, burst=+1.20, break=+0.0100 → совет: ПОКУПКА",
        kind="analysis",
    )
    assert 'color:#0f766e">анализ</span>' in html_line
    assert "анализ: анализ" not in html_line
    assert "ПОКУПКА" in html_line
    assert "#15803d" in html_line  # buy highlight
    assert "#a16207" in html_line  # burst number


def test_format_outcome_success_vs_fail() -> None:
    ok = mh._format_market_line(
        "итог: BTCUSDT ПОКУПКА → удача (прибыль): edge=+0.01",
        kind="outcome",
    )
    bad = mh._format_market_line(
        "итог: BTCUSDT ПРОДАЖА → неудача (убыток): edge=-0.01",
        kind="outcome",
    )
    assert 'color:#15803d">итог</span>' in ok
    assert 'color:#b91c1c">итог</span>' in bad
    assert "#b91c1c" in bad


def test_format_shadow_outcome_has_distinct_badge() -> None:
    line = mh._format_market_line(
        "закрыто теневых сделок: 2 — метки записаны, запускаем дообучение",
        kind="shadow_outcome",
    )
    assert 'color:#7c3aed">итог тени</span>' in line


def test_format_error_and_paper() -> None:
    err = mh._format_market_line("сеть недоступна", is_error=True)
    assert "ошибка" in err and "#b91c1c" in err
    paper = mh._format_market_line("сделка: бумажная ПОКУПКА @ 1", kind="paper")
    assert 'color:#1d4ed8">сделка</span>' in paper
