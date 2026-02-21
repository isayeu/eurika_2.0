"""
Knowledge Provider Layer (ROADMAP после 1.0 / review.md).

Абстракция: KnowledgeProvider.query(topic) -> StructuredKnowledge.
Не «поиск в интернете», а проверка через curated-источники.
LocalKnowledgeProvider — JSON-кэш; OfficialDocsProvider — опционально запрос по фиксированному URL (stdlib).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class StructuredKnowledge:
    """Структурированный ответ от провайдера: источник, фрагменты, метаданные."""

    topic: str
    source: str  # e.g. "local", "official_docs", "release_notes", "static_analyzer"
    fragments: List[Dict[str, Any]] = field(default_factory=list)  # [{ "title": str, "content": str }, ...]
    meta: Dict[str, Any] = field(default_factory=dict)  # e.g. url, version, confidence

    def is_empty(self) -> bool:
        return len(self.fragments) == 0


class KnowledgeProvider(ABC):
    """Провайдер знаний: по теме возвращает структурированный ответ."""

    @abstractmethod
    def query(self, topic: str) -> StructuredKnowledge:
        """Вернуть знания по теме. Не выполнять произвольный поиск в интернете."""
        pass


def _topic_key(topic: str) -> str:
    """Нормализация темы для ключа кэша."""
    return topic.strip().lower().replace(" ", "_") if topic else ""


class LocalKnowledgeProvider(KnowledgeProvider):
    """Локальный кэш из JSON. Формат: {"topics": {"topic_id": [{"title": "...", "content": "..."}, ...]}}."""

    def __init__(self, cache_path: str | Path | None = None) -> None:
        self.cache_path = Path(cache_path) if cache_path else None
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        if self.cache_path and self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._cache = data.get("topics", data) if isinstance(data, dict) else {}
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def query(self, topic: str) -> StructuredKnowledge:
        key = _topic_key(topic)
        fragments = self._cache.get(key, []) if key else []
        if not isinstance(fragments, list):
            fragments = []
        return StructuredKnowledge(
            topic=topic,
            source="local",
            fragments=[f for f in fragments if isinstance(f, dict)],
            meta={"cache_path": str(self.cache_path)} if self.cache_path else {},
        )


def _drop_script_style(html: str) -> str:
    """Remove <script>...</script> and <style>...</style> and their content (no nested tags)."""
    html = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
    return html


def _trim_doc_boilerplate(text: str) -> str:
    """Drop leading doc-site boilerplate (nav, header, breadcrumb) so content starts with real body."""
    # Sentinel: start from "What's New" / "Summary" / "Overview" typical in docs.python.org whatsnew
    for sentinel in (
        "What's New in Python",
        "Summary",
        "Overview",
        "Release highlights",
    ):
        m = re.search(re.escape(sentinel), text, re.IGNORECASE)
        if m:
            text = text[m.start() :]
            break
    # Drop common leading junk lines (repeat until no change)
    junk = (
        r"Python\s+[\d.]+\s+documentation\s*",
        r"Skip to main content\s*",
        r"Navigation\s*",
        r"Previous\s*",
        r"Next\s*",
        r"©\s*Copyright\s*",
        r"Copyright\s+©\s*",
    )
    for _ in range(3):
        orig = text
        for pat in junk:
            text = re.sub(r"^\s*" + pat, "", text, flags=re.IGNORECASE)
        text = text.lstrip()
        if text == orig:
            break
    return text.strip()


def _fetch_url(url: str, timeout: float = 5.0, max_chars: int = 8000) -> Optional[str]:
    """Fetch URL with stdlib; return body as text (strip HTML, drop script/style, trim boilerplate)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Eurika/1.0 (knowledge)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    raw = _drop_script_style(raw)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    text = _trim_doc_boilerplate(text)
    return text[:max_chars] if text else None


def _fetch_url_cached(
    url: str,
    cache_path: Path,
    ttl_seconds: float = 86400.0,
    timeout: float = 5.0,
    max_chars: int = 8000,
) -> Optional[str]:
    """Fetch URL; use cache if fresh (mtime within TTL), else fetch and write."""
    now = time.time()
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            fetched_at = data.get("fetched_at") or 0
            if now - fetched_at < ttl_seconds:
                return data.get("content")
        except (json.JSONDecodeError, OSError):
            pass
    text = _fetch_url(url, timeout=timeout, max_chars=max_chars)
    if text is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"content": text, "url": url, "fetched_at": now}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
    return text


def _cache_key_for_url(url: str, source: str) -> str:
    """Stable cache filename from url and source."""
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{source}_{h}.json"


# Curated PEP URLs for PEPProvider (topic key -> url). ROADMAP 2.9.3.
PEP_TOPIC_URLS: Dict[str, str] = {
    "pep_8": "https://peps.python.org/pep-0008/",
    "pep_257": "https://peps.python.org/pep-0257/",
    "pep_484": "https://peps.python.org/pep-0484/",
}


def _pep_topic_to_url(topic: str) -> Optional[str]:
    """Resolve PEP topic (pep_8, pep_257, pep_484) to URL. Also accept pep_0008 style."""
    key = _topic_key(topic)
    if key in PEP_TOPIC_URLS:
        return PEP_TOPIC_URLS[key]
    m = re.match(r"pep[_\-]?(\d+)", key)
    if m:
        num = m.group(1).zfill(4)
        return f"https://peps.python.org/pep-{num}/"
    return None


class PEPProvider(KnowledgeProvider):
    """PEP (Python Enhancement Proposals) by number. Fetches from peps.python.org (ROADMAP 2.9.3)."""

    def __init__(
        self,
        topic_urls: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
        cache_dir: Optional[Path] = None,
        ttl_seconds: float = 86400.0,
    ) -> None:
        self.topic_urls = topic_urls if topic_urls is not None else dict(PEP_TOPIC_URLS)
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl_seconds = ttl_seconds

    def query(self, topic: str) -> StructuredKnowledge:
        url = self.topic_urls.get(_topic_key(topic)) or _pep_topic_to_url(topic)
        if not url:
            return StructuredKnowledge(topic=topic, source="pep", fragments=[], meta={})
        if self.cache_dir:
            cache_path = self.cache_dir / _cache_key_for_url(url, "pep")
            text = _fetch_url_cached(url, cache_path, self.ttl_seconds, self.timeout)
        else:
            text = _fetch_url(url, timeout=self.timeout)
        if not text:
            return StructuredKnowledge(topic=topic, source="pep", fragments=[], meta={"url": url})
        return StructuredKnowledge(
            topic=topic,
            source="pep",
            fragments=[{"title": f"PEP: {topic}", "content": text}],
            meta={"url": url},
        )


# Curated URLs for OfficialDocsProvider (topic key -> url). No arbitrary search.
OFFICIAL_DOCS_TOPIC_URLS: Dict[str, str] = {
    "python_3_14": "https://docs.python.org/3/whatsnew/3.14.html",
    "python_3_13": "https://docs.python.org/3/whatsnew/3.13.html",
    "python_3_12": "https://docs.python.org/3/whatsnew/3.12.html",
    "python_3_11": "https://docs.python.org/3/whatsnew/3.11.html",
}


class OfficialDocsProvider(KnowledgeProvider):
    """Официальная документация по фиксированным URL (allow-list). Сеть — только curated."""

    def __init__(
        self,
        topic_urls: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
        cache_dir: Optional[Path] = None,
        ttl_seconds: float = 86400.0,
    ) -> None:
        self.topic_urls = OFFICIAL_DOCS_TOPIC_URLS if topic_urls is None else topic_urls
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl_seconds = ttl_seconds

    def query(self, topic: str) -> StructuredKnowledge:
        key = _topic_key(topic)
        url = self.topic_urls.get(key)
        if not url:
            return StructuredKnowledge(topic=topic, source="official_docs", fragments=[], meta={})
        if self.cache_dir:
            cache_path = self.cache_dir / _cache_key_for_url(url, "official_docs")
            text = _fetch_url_cached(url, cache_path, self.ttl_seconds, self.timeout)
        else:
            text = _fetch_url(url, timeout=self.timeout)
        if not text:
            return StructuredKnowledge(topic=topic, source="official_docs", fragments=[], meta={"url": url})
        return StructuredKnowledge(
            topic=topic,
            source="official_docs",
            fragments=[{"title": f"Official docs: {key}", "content": text}],
            meta={"url": url},
        )


# Curated URLs for ReleaseNotesProvider (topic key -> url). No arbitrary search.
RELEASE_NOTES_TOPIC_URLS: Dict[str, str] = {
    "python_3_14": "https://docs.python.org/3/whatsnew/3.14.html",
    "python_3_13": "https://docs.python.org/3/whatsnew/3.13.html",
    "python_3_12": "https://docs.python.org/3/whatsnew/3.12.html",
    "python_3_11": "https://docs.python.org/3/whatsnew/3.11.html",
}


class ReleaseNotesProvider(KnowledgeProvider):
    """Release notes / What's New по фиксированным URL (allow-list). Сеть — только curated."""

    def __init__(
        self,
        topic_urls: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
        cache_dir: Optional[Path] = None,
        ttl_seconds: float = 86400.0,
    ) -> None:
        self.topic_urls = RELEASE_NOTES_TOPIC_URLS if topic_urls is None else topic_urls
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl_seconds = ttl_seconds

    def query(self, topic: str) -> StructuredKnowledge:
        key = _topic_key(topic)
        url = self.topic_urls.get(key)
        if not url:
            return StructuredKnowledge(topic=topic, source="release_notes", fragments=[], meta={})
        if self.cache_dir:
            cache_path = self.cache_dir / _cache_key_for_url(url, "release_notes")
            text = _fetch_url_cached(url, cache_path, self.ttl_seconds, self.timeout)
        else:
            text = _fetch_url(url, timeout=self.timeout)
        if not text:
            return StructuredKnowledge(topic=topic, source="release_notes", fragments=[], meta={"url": url})
        return StructuredKnowledge(
            topic=topic,
            source="release_notes",
            fragments=[{"title": f"Release notes: {key}", "content": text}],
            meta={"url": url},
        )


class StaticAnalyzerProvider(KnowledgeProvider):
    """Результаты mypy, pylint, flake8, AST. Пока — заглушка, без вызовов анализаторов."""

    def query(self, topic: str) -> StructuredKnowledge:
        return StructuredKnowledge(topic=topic, source="static_analyzer", fragments=[], meta={})


class CompositeKnowledgeProvider(KnowledgeProvider):
    """Объединяет несколько провайдеров: по каждой теме запрашивает всех и склеивает фрагменты."""

    def __init__(self, providers: List[KnowledgeProvider]) -> None:
        self.providers = list(providers)

    def query(self, topic: str) -> StructuredKnowledge:
        all_fragments: List[Dict[str, Any]] = []
        for p in self.providers:
            kn = p.query(topic)
            if not kn.is_empty():
                for f in kn.fragments:
                    frag = dict(f)
                    title = frag.get("title") or ""
                    if kn.source and not title.startswith("["):
                        frag["title"] = f"[{kn.source}] {title}"
                    all_fragments.append(frag)
        return StructuredKnowledge(
            topic=topic,
            source="composite",
            fragments=all_fragments,
            meta={"providers": len(self.providers)},
        )
