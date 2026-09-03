"""Qt UX for Market → Portfolio agent «Цикл» button."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from qt_app.ui.handlers import market_portfolio_agent as mpa


def test_run_once_busy_shows_message(monkeypatch) -> None:
    messages: list[tuple[str, dict[str, Any]]] = []

    def _append(_main: object, text: str, **kwargs: Any) -> None:
        messages.append((text, kwargs))

    monkeypatch.setattr(
        "qt_app.ui.handlers.market_portfolio_agent._focus_market_feed",
        lambda _m: None,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.market_handlers.append_market_message",
        _append,
    )
    main = SimpleNamespace(
        _is_closing=False,
        _market_portfolio_worker=object(),
    )
    mpa.run_once(main, force=True)
    assert messages
    assert "уже выполняется" in messages[0][0]


def test_run_once_no_key_shows_message(monkeypatch, tmp_path) -> None:
    messages: list[str] = []

    def _append(_main: object, text: str, **_kw: Any) -> None:
        messages.append(text)

    monkeypatch.setattr(
        "qt_app.ui.handlers.market_portfolio_agent._focus_market_feed",
        lambda _m: None,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.market_handlers.append_market_message",
        _append,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.market_handlers.update_market_status_label",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "eurika.agent.cursor_judge.cursor_key_status",
        lambda _r: {"api_key_set": False},
    )
    main = SimpleNamespace(
        _is_closing=False,
        _market_portfolio_worker=None,
        _market_root=str(tmp_path),
        market_portfolio_once_btn=SimpleNamespace(setEnabled=lambda *_a: None),
    )
    mpa.run_once(main, force=True)
    assert any("CURSOR_API_KEY" in m for m in messages)


def test_run_once_starts_with_launch_message(monkeypatch, tmp_path) -> None:
    messages: list[str] = []
    started: list[str] = []

    def _append(_main: object, text: str, **_kw: Any) -> None:
        messages.append(text)

    def _start(_main: object, root: str) -> None:
        started.append(root)

    monkeypatch.setattr(
        "qt_app.ui.handlers.market_portfolio_agent._focus_market_feed",
        lambda _m: None,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.market_handlers.append_market_message",
        _append,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.market_handlers.update_market_status_label",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "eurika.agent.cursor_judge.cursor_key_status",
        lambda _r: {"api_key_set": True},
    )
    monkeypatch.setattr(mpa, "_start_worker", _start)
    main = SimpleNamespace(
        _is_closing=False,
        _market_portfolio_worker=None,
        _market_root=str(tmp_path),
        market_portfolio_once_btn=SimpleNamespace(setEnabled=lambda *_a: None),
    )
    mpa.run_once(main, force=True)
    assert any("запуск цикла" in m for m in messages)
    assert started == [str(tmp_path)]


def test_on_ok_uses_digest(monkeypatch) -> None:
    messages: list[str] = []

    def _append(_main: object, text: str, **_kw: Any) -> None:
        messages.append(text)

    monkeypatch.setattr(
        "qt_app.ui.handlers.market_handlers.append_market_message",
        _append,
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.market_handlers.update_market_status_label",
        lambda *_a, **_k: None,
    )
    main = SimpleNamespace(
        _is_closing=False,
        _market_portfolio_worker=None,
        market_portfolio_once_btn=SimpleNamespace(setEnabled=lambda *_a: None),
    )
    captured: dict[str, Any] = {}

    class _FakeWorker:
        def __init__(self, *_a, **_k) -> None:
            self.finished_ok = SimpleNamespace(connect=lambda fn: captured.setdefault("ok", fn))
            self.failed = SimpleNamespace(connect=lambda fn: captured.setdefault("fail", fn))
            self.finished = SimpleNamespace(connect=lambda fn: captured.setdefault("done", fn))

        def start(self) -> None:
            pass

        def deleteLater(self) -> None:
            pass

    monkeypatch.setattr(mpa, "MarketPortfolioWorker", _FakeWorker)
    mpa._start_worker(main, "/tmp")
    assert "ok" in captured
    captured["ok"](
        {
            "ok": True,
            "digest": "Portfolio агент — цикл OK\nБанк: equity 1000.17$",
            "actions_n": 1,
            "body": "## Цикл ...",
        }
    )
    assert messages
    assert "Банк:" in messages[0]
    assert "[eq=" not in messages[0]
