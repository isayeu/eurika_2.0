"""Unit tests for Market transcript HTML (compact feed + chat-like cards)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from qt_app.ui.handlers import market_handlers as mh


def test_noise_filter_drops_tick_spam() -> None:
    assert mh.is_market_feed_noise("sync", "BTCUSDT 15m: добавлено=1")
    assert mh.is_market_feed_noise("analysis", "BTCUSDT → совет: ПОКУПКА")
    assert mh.is_market_feed_noise("hold", "отклонён — ход не окупает")
    assert mh.is_market_feed_noise("wait", "ждём 1m")
    assert mh.is_market_feed_noise("info", "universe (futures): fut=BTCUSDT")
    assert mh.is_market_feed_noise("info", "инфо: universe (spot): BTCUSDT")
    assert not mh.is_market_feed_noise("paper", "бумажная ПОКУПКА")
    assert not mh.is_market_feed_noise("outcome", "удача")
    assert not mh.is_market_feed_noise("learn", "дообучение")
    assert not mh.is_market_feed_noise("cursor_hour", "LLM 15м: разбор")
    assert not mh.is_market_feed_noise("info", "Live paper включён")
    assert not mh.is_market_feed_noise("error", "сеть недоступна")


def test_format_market_line_is_chat_like_card() -> None:
    html_line = mh._format_market_line(
        "сделка: бумажная ПОКУПКА @ 1",
        kind="paper",
    )
    assert "<table" in html_line
    assert ">сделка</b>" in html_line or "><b>сделка</b>" in html_line
    assert "ПОКУПКА" in html_line
    assert "#15803d" in html_line  # buy highlight
    assert "сделка: сделка" not in html_line


def test_format_outcome_success_vs_fail() -> None:
    ok = mh._format_market_line(
        "итог: BTCUSDT ПОКУПКА → удача (прибыль): edge=+0.01",
        kind="outcome",
    )
    bad = mh._format_market_line(
        "итог: BTCUSDT ПРОДАЖА → неудача (убыток): edge=-0.01",
        kind="outcome",
    )
    assert 'bgcolor="#15803d"' in ok or "#15803d" in ok
    assert 'bgcolor="#b91c1c"' in bad
    assert "удача" in ok and "неудача" in bad


def test_format_shadow_outcome_has_distinct_badge() -> None:
    line = mh._format_market_line(
        "закрыто теневых сделок: 2 — метки записаны, запускаем дообучение",
        kind="shadow_outcome",
    )
    assert "итог тени" in line
    assert "#7c3aed" in line


def test_format_error_and_cursor_hour_markdown() -> None:
    err = mh._format_market_line("сеть недоступна", is_error=True)
    assert "ошибка" in err and "#b91c1c" in err
    line = mh._format_market_line(
        "LLM 15м: # Заголовок\n\n- пункт один\n- пункт два",
        kind="cursor_hour",
    )
    assert "LLM 15м" in line
    assert "<b>Заголовок</b>" in line or "Заголовок" in line
    assert "<li>" in line or "пункт один" in line


def test_append_skips_noise_without_persist(monkeypatch, tmp_path) -> None:
    calls: list[tuple] = []

    def _fake_append(*args, **kwargs):
        calls.append((args, kwargs))
        return tmp_path / "j.jsonl"

    monkeypatch.setattr("eurika.ml.market_journal.append_market_journal", _fake_append)
    main: Any = SimpleNamespace(
        _market_root=str(tmp_path),
        market_transcript=None,
        chat_transcript=None,
        root_edit=SimpleNamespace(text=lambda: str(tmp_path)),
    )
    mh.append_market_message(main, "анализ: шум", kind="analysis")
    mh.append_market_message(main, "universe (futures): BTC", kind="info")
    assert calls == []
    mh.append_market_message(main, "бумажная ПОКУПКА @ 1", kind="paper")
    assert len(calls) == 1


def test_market_root_does_not_follow_opened_coding_workspace(tmp_path) -> None:
    coding_workspace = tmp_path / "external-project"
    coding_workspace.mkdir()
    main: Any = SimpleNamespace(
        _market_root=str(tmp_path / "eurika-product"),
        root_edit=SimpleNamespace(text=lambda: str(coding_workspace)),
    )

    assert mh._project_root(main) == str(tmp_path / "eurika-product")
