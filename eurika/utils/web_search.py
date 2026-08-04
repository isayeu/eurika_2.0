"""Optional web search for Eurika chat (stdlib + API providers).

Providers (auto priority when provider=auto):
  1. Tavily — TAVILY_API_KEY
  2. Brave — BRAVE_SEARCH_API_KEY
  3. DuckDuckGo HTML — no key (fallback)

Disable entirely: EURIKA_WEB_SEARCH=0
Force provider: EURIKA_WEB_SEARCH_PROVIDER=duckduckgo|tavily|brave|auto
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Tuple

_USER_AGENT = "Eurika/3.0 (web-search; +https://github.com/eurika)"


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    source: str


def web_search_enabled() -> bool:
    val = os.environ.get("EURIKA_WEB_SEARCH", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def resolve_web_search_provider(explicit: str = "auto") -> str:
    choice = (explicit or os.environ.get("EURIKA_WEB_SEARCH_PROVIDER", "auto")).strip().lower()
    if choice in ("tavily", "brave", "duckduckgo"):
        return choice
    if os.environ.get("TAVILY_API_KEY", "").strip():
        return "tavily"
    if os.environ.get("BRAVE_SEARCH_API_KEY", "").strip():
        return "brave"
    return "duckduckgo"


def extract_web_search_query(message: str) -> str:
    """Strip search-intent prefixes and return the query."""
    msg = (message or "").strip()
    if not msg:
        return ""
    patterns = (
        r"^(?:найди|поищи|search|find)\s+(?:в\s+)?(?:интернете|internet|web|google)\s*(?:про|о|about|for)?\s*(.+)$",
        r"^(?:погугли|загугли|google)\s+(.+)$",
        r"^web\s+search\s+(.+)$",
        r"^search\s+the\s+web\s+(?:for\s+)?(.+)$",
        r"^интернет[-\s]поиск\s+(.+)$",
    )
    lowered = msg.lower()
    for pat in patterns:
        m = re.match(pat, lowered, flags=re.IGNORECASE)
        if m:
            # Preserve original casing from tail of message where possible.
            tail = msg[m.start(1) :].strip(" ?!.")
            return tail
    return msg.strip(" ?!.")


def _http_json(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> dict:
    hdrs = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _search_tavily(query: str, api_key: str, *, max_results: int) -> List[WebSearchResult]:
    body = json.dumps(
        {"api_key": api_key, "query": query, "max_results": max_results, "include_answer": False}
    ).encode("utf-8")
    data = _http_json(
        "https://api.tavily.com/search",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    out: List[WebSearchResult] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("content") or item.get("snippet") or "").strip()
        if title and url:
            out.append(WebSearchResult(title=title, url=url, snippet=snippet, source="tavily"))
    return out[:max_results]


def _search_brave(query: str, api_key: str, *, max_results: int) -> List[WebSearchResult]:
    qs = urllib.parse.urlencode({"q": query, "count": str(max_results)})
    data = _http_json(
        f"https://api.search.brave.com/res/v1/web/search?{qs}",
        headers={"X-Subscription-Token": api_key},
    )
    web = data.get("web") or {}
    out: List[WebSearchResult] = []
    for item in web.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("description") or "").strip()
        if title and url:
            out.append(WebSearchResult(title=title, url=url, snippet=snippet, source="brave"))
    return out[:max_results]


def _parse_duckduckgo_html(body: str, *, max_results: int) -> List[WebSearchResult]:
    out: List[WebSearchResult] = []
    blocks = re.split(r'<div class="result\s', body, flags=re.IGNORECASE)
    for block in blocks[1:]:
        m_link = re.search(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not m_link:
            continue
        m_snip = re.search(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        url = html_lib.unescape(m_link.group(1).strip())
        title = re.sub(r"<[^>]+>", " ", m_link.group(2))
        title = html_lib.unescape(re.sub(r"\s+", " ", title).strip())
        snippet = ""
        if m_snip:
            snippet = re.sub(r"<[^>]+>", " ", m_snip.group(1))
            snippet = html_lib.unescape(re.sub(r"\s+", " ", snippet).strip())
        if title and url:
            out.append(WebSearchResult(title=title, url=url, snippet=snippet, source="duckduckgo"))
        if len(out) >= max_results:
            break
    return out


def _search_duckduckgo(query: str, *, max_results: int) -> List[WebSearchResult]:
    payload = urllib.parse.urlencode({"q": query}).encode("utf-8")
    req = urllib.request.Request(
        "https://html.duckduckgo.com/html/",
        data=payload,
        headers={
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return _parse_duckduckgo_html(body, max_results=max_results)


def search_web(
    query: str,
    *,
    max_results: int = 5,
    provider: str = "auto",
) -> Tuple[List[WebSearchResult], str, Optional[str]]:
    """
    Search the web. Returns (results, provider_used, error_message).

    On API failure falls back to DuckDuckGo when a paid provider was selected.
    """
    q = (query or "").strip()
    if not q:
        return [], "none", "empty query"
    if not web_search_enabled():
        return [], "none", "web search disabled (EURIKA_WEB_SEARCH=0)"

    chosen = resolve_web_search_provider(provider)
    errors: list[str] = []

    if chosen == "tavily":
        key = os.environ.get("TAVILY_API_KEY", "").strip()
        if key:
            try:
                results = _search_tavily(q, key, max_results=max_results)
                if results:
                    return results, "tavily", None
                errors.append("tavily: no results")
            except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"tavily: {exc}")
        else:
            errors.append("tavily: missing TAVILY_API_KEY")

    if chosen == "brave":
        key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
        if key:
            try:
                results = _search_brave(q, key, max_results=max_results)
                if results:
                    return results, "brave", None
                errors.append("brave: no results")
            except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"brave: {exc}")
        else:
            errors.append("brave: missing BRAVE_SEARCH_API_KEY")

    try:
        results = _search_duckduckgo(q, max_results=max_results)
        if results:
            note = "; ".join(errors) if errors and chosen != "duckduckgo" else None
            return results, "duckduckgo", note
        return [], "duckduckgo", "; ".join(errors) if errors else "no results"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        err = "; ".join(errors + [f"duckduckgo: {exc}"])
        return [], "duckduckgo", err


def format_web_search_results(query: str, results: List[WebSearchResult], *, provider: str, note: Optional[str] = None) -> str:
    """Format search hits for chat."""
    lines = [f'Результаты поиска в интернете по запросу «{query}» (провайдер: `{provider}`):', ""]
    if not results:
        lines.append("Ничего не найдено.")
        if note:
            lines.append(f"Примечание: {note}")
        return "\n".join(lines)
    for i, hit in enumerate(results, 1):
        lines.append(f"**{i}. {hit.title}**")
        lines.append(f"- URL: {hit.url}")
        if hit.snippet:
            lines.append(f"- {hit.snippet[:400]}{'…' if len(hit.snippet) > 400 else ''}")
        lines.append("")
    if note:
        lines.append(f"_Fallback: {note}_")
    lines.append("Уточни запрос или попроси «покажи файл …» для локального проекта.")
    return "\n".join(lines).rstrip()
