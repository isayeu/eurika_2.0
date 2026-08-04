"""Tests for eurika.utils.web_search."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch
from urllib.response import addinfourl

from eurika.utils.web_search import (
    extract_web_search_query,
    format_web_search_results,
    resolve_web_search_provider,
    search_web,
    web_search_enabled,
)


def test_extract_web_search_query_strips_prefix() -> None:
    assert extract_web_search_query("найди в интернете про Kivy Builder") == "Kivy Builder"
    assert extract_web_search_query("погугли sqlite WAL mode") == "sqlite WAL mode"
    assert extract_web_search_query("web search python 3.14 release") == "python 3.14 release"


def test_resolve_provider_prefers_tavily_key(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    assert resolve_web_search_provider("auto") == "tavily"


def test_resolve_provider_falls_back_to_duckduckgo(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    assert resolve_web_search_provider("auto") == "duckduckgo"


def test_search_web_tavily_mocked(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    payload = json.dumps(
        {
            "results": [
                {"title": "Kivy docs", "url": "https://kivy.org", "content": "Python UI framework"},
            ]
        }
    ).encode()

    def _fake_json(url, *args, **kwargs):
        return json.loads(payload.decode())

    with patch("eurika.utils.web_search._http_json", side_effect=_fake_json):
        results, provider, err = search_web("kivy documentation", provider="tavily")
    assert err is None
    assert provider == "tavily"
    assert len(results) == 1
    assert results[0].title == "Kivy docs"


def test_search_web_duckduckgo_html_mocked(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    html = """
    <div class="result results_links_deep highlight">
      <a class="result__a" href="https://example.com/kivy">Kivy Framework</a>
      <a class="result__snippet">Open source Python library</a>
    </div>
    """
    with patch("urllib.request.urlopen") as m:
        m.return_value.__enter__.return_value = addinfourl(
            BytesIO(html.encode()), {}, "https://html.duckduckgo.com/html/", 200
        )
        results, provider, err = search_web("kivy", provider="duckduckgo")
    assert provider == "duckduckgo"
    assert err is None
    assert len(results) == 1
    assert "Kivy" in results[0].title


def test_format_web_search_results() -> None:
    from eurika.utils.web_search import WebSearchResult

    text = format_web_search_results(
        "kivy",
        [WebSearchResult("Kivy", "https://kivy.org", "UI toolkit", "duckduckgo")],
        provider="duckduckgo",
    )
    assert "Kivy" in text
    assert "https://kivy.org" in text


def test_web_search_disabled(monkeypatch) -> None:
    monkeypatch.setenv("EURIKA_WEB_SEARCH", "0")
    assert web_search_enabled() is False
    results, provider, err = search_web("test")
    assert results == []
    assert "disabled" in (err or "")
