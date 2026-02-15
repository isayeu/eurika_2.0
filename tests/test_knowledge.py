"""Tests for eurika.knowledge (Knowledge Provider Layer contract)."""
import json
from pathlib import Path
from unittest.mock import patch
from eurika.knowledge import CompositeKnowledgeProvider, KnowledgeProvider, LocalKnowledgeProvider, OfficialDocsProvider, ReleaseNotesProvider, StaticAnalyzerProvider, StructuredKnowledge

def test_structured_knowledge_empty() -> None:
    k = StructuredKnowledge(topic='python_3_12', source='local', fragments=[], meta={})
    assert k.is_empty() is True
    assert k.topic == 'python_3_12'
    assert k.source == 'local'

def test_structured_knowledge_non_empty() -> None:
    k = StructuredKnowledge(topic='pep_701', source='official_docs', fragments=[{'title': 'PEP 701', 'content': 'syntax'}], meta={'url': 'https://peps.python.org/pep-0701/'})
    assert k.is_empty() is False
    assert len(k.fragments) == 1
    assert k.fragments[0]['title'] == 'PEP 701'

def test_local_knowledge_provider_query() -> None:
    p = LocalKnowledgeProvider()
    k = p.query('any_topic')
    assert isinstance(k, StructuredKnowledge)
    assert k.source == 'local'
    assert k.topic == 'any_topic'
    assert k.is_empty() is True

def test_local_knowledge_provider_loads_cache(tmp_path: Path) -> None:
    cache_file = tmp_path / 'knowledge.json'
    cache_file.write_text(json.dumps({'topics': {'python_3_12': [{'title': "What's New", 'content': 'PEP 701 syntax'}], 'pep_701': [{'title': 'PEP 701', 'content': 'f-strings'}]}}, ensure_ascii=False), encoding='utf-8')
    p = LocalKnowledgeProvider(cache_path=cache_file)
    k = p.query('python_3_12')
    assert k.source == 'local'
    assert k.is_empty() is False
    assert len(k.fragments) == 1
    assert k.fragments[0]['title'] == "What's New"
    assert 'cache_path' in k.meta
    k2 = p.query('PEP 701')
    assert k2.is_empty() is False
    assert k2.fragments[0]['title'] == 'PEP 701'
    k3 = p.query('unknown_topic')
    assert k3.is_empty() is True

def test_local_knowledge_provider_no_cache() -> None:
    p = LocalKnowledgeProvider(cache_path='/nonexistent/path/knowledge.json')
    k = p.query('x')
    assert k.is_empty() is True
    assert k.source == 'local'

def test_official_docs_provider_stub() -> None:
    p = OfficialDocsProvider()
    k = p.query('python_typing')
    assert k.source == 'official_docs'
    assert k.topic == 'python_typing'
    assert k.is_empty() is True

def test_release_notes_provider_topic_not_in_map() -> None:
    """ReleaseNotesProvider with empty topic_urls returns empty for any topic."""
    p = ReleaseNotesProvider(topic_urls={})
    k = p.query('python_3_12')
    assert k.source == 'release_notes'
    assert k.topic == 'python_3_12'
    assert k.is_empty() is True

def test_release_notes_provider_unknown_topic_returns_empty() -> None:
    """With default topic_urls, topic not in allow-list returns empty (no network)."""
    p = ReleaseNotesProvider()
    k = p.query('unknown_topic')
    assert k.source == 'release_notes'
    assert k.is_empty() is True

def test_release_notes_provider_fetch_mocked() -> None:
    from io import BytesIO
    from urllib.response import addinfourl
    body = b"<html><body><p>What's New in Python 3.12</p><p>Breaking changes.</p></body></html>"
    p = ReleaseNotesProvider(topic_urls={'python_3_12': 'https://docs.python.org/3/whatsnew/3.12.html'})
    with patch('eurika.knowledge.base.urllib.request.urlopen') as m:
        m.return_value.__enter__.return_value = addinfourl(BytesIO(body), {}, 'https://example.com', 200)
        k = p.query('python_3_12')
    assert k.source == 'release_notes'
    assert not k.is_empty()
    assert len(k.fragments) == 1
    assert 'Release notes' in k.fragments[0]['title'] or 'python_3_12' in k.fragments[0]['title']
    assert "What's New" in k.fragments[0]['content'] or 'Breaking' in k.fragments[0]['content']

def test_static_analyzer_provider_stub() -> None:
    p = StaticAnalyzerProvider()
    k = p.query('mypy')
    assert k.source == 'static_analyzer'
    assert k.topic == 'mypy'
    assert k.is_empty() is True

def test_composite_knowledge_provider_merges_fragments() -> None:
    """CompositeKnowledgeProvider queries all providers and merges fragments with source prefix."""

    class StubA(KnowledgeProvider):

        def query(self, topic: str):
            return StructuredKnowledge(topic=topic, source='a', fragments=[{'title': 'From A', 'content': 'a'}], meta={})

    class StubB(KnowledgeProvider):

        def query(self, topic: str):
            return StructuredKnowledge(topic=topic, source='b', fragments=[{'title': 'From B', 'content': 'b'}], meta={})
    comp = CompositeKnowledgeProvider([StubA(), StubB()])
    k = comp.query('x')
    assert k.source == 'composite'
    assert not k.is_empty()
    assert len(k.fragments) == 2
    titles = [f['title'] for f in k.fragments]
    assert '[a] From A' in titles
    assert '[b] From B' in titles

def test_official_docs_provider_topic_not_in_map() -> None:
    """OfficialDocsProvider with empty map returns empty for any topic."""
    p = OfficialDocsProvider(topic_urls={})
    k = p.query('python_3_12')
    assert k.source == 'official_docs'
    assert k.is_empty() is True

def test_official_docs_provider_fetch_mocked() -> None:
    """OfficialDocsProvider returns one fragment when URL is in map and fetch succeeds (mocked)."""
    from io import BytesIO
    from urllib.response import addinfourl
    body = b"<html><body><p>What's new in Python 3.12</p><p>Type parameter syntax.</p></body></html>"
    p = OfficialDocsProvider(topic_urls={'python_3_12': 'https://docs.python.org/3/whatsnew/3.12.html'})
    with patch('eurika.knowledge.base.urllib.request.urlopen') as m:
        m.return_value.__enter__.return_value = addinfourl(BytesIO(body), {}, 'https://example.com', 200)
        k = p.query('python_3_12')
    assert k.source == 'official_docs'
    assert not k.is_empty()
    assert len(k.fragments) == 1
    assert "What's new" in k.fragments[0]['content'] or 'Type parameter' in k.fragments[0]['content']
    assert k.meta.get('url', '').endswith('3.12.html')

def test_official_docs_provider_uses_cache(tmp_path) -> None:
    """When cache_dir has fresh content, provider returns it without network."""
    from eurika.knowledge.base import _cache_key_for_url
    url = 'https://docs.python.org/3/whatsnew/3.12.html'
    cache_dir = tmp_path / '.eurika' / 'knowledge_cache'
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / _cache_key_for_url(url, 'official_docs')
    import json
    import time
    cache_file.write_text(json.dumps({'content': 'Cached Python 3.12 summary', 'url': url, 'fetched_at': time.time()}), encoding='utf-8')
    p = OfficialDocsProvider(topic_urls={'python_3_12': url}, cache_dir=cache_dir, ttl_seconds=3600)
    with patch('eurika.knowledge.base.urllib.request.urlopen') as m:
        k = p.query('python_3_12')
    assert not k.is_empty()
    assert 'Cached Python 3.12 summary' in k.fragments[0]['content']
    m.assert_not_called()

def test_fetch_html_cleanup() -> None:
    """HTML cleanup: drop script/style, trim leading boilerplate so content starts with body text."""
    from eurika.knowledge.base import _drop_script_style, _trim_doc_boilerplate
    html_with_junk = "<script>alert(1);</script><style>.nav { }</style>Python 3.12 documentation Skip to main content Navigation What's New in Python 3.12 Summary New syntax. Type parameter."
    cleaned = _drop_script_style(html_with_junk)
    assert 'alert' not in cleaned
    assert '.nav' not in cleaned
    text = "Python 3.12 documentation Skip Navigation What's New in Python 3.12 Summary New syntax."
    trimmed = _trim_doc_boilerplate(text)
    assert trimmed.startswith("What's New") or trimmed.startswith('Summary') or 'New syntax' in trimmed
    assert 'Python 3.12 documentation' not in trimmed