"""Tests for GitHub search (ROADMAP 3.0.5.2)."""

import json
from unittest.mock import patch


def test_search_repositories_mock() -> None:
    """search_repositories returns repos from mocked API response."""
    from eurika.learning.github_search import search_repositories

    mock_response = {
        "items": [
            {"clone_url": "https://github.com/foo/bar.git", "full_name": "foo/bar", "default_branch": "main"},
            {"clone_url": "https://github.com/baz/qux.git", "full_name": "baz/qux", "default_branch": "master"},
        ]
    }
    body = json.dumps(mock_response).encode()

    def fake_urlopen(*args, **kwargs):
        class FakeResp:
            def read(self):
                return body
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
        return FakeResp()

    with patch("eurika.learning.github_search.urllib.request.urlopen", side_effect=fake_urlopen):
        result = search_repositories("language:python", per_page=5)
    assert len(result) == 2
    assert result[0]["url"] == "https://github.com/foo/bar.git"
    assert result[0]["name"] == "bar"
    assert result[0]["branch"] == "main"
    assert result[1]["name"] == "qux"
    assert result[1]["branch"] == "master"


def test_search_repositories_empty() -> None:
    """search_repositories handles empty response."""
    from eurika.learning.github_search import search_repositories

    def fake_urlopen(*args, **kwargs):
        class FakeResp:
            def read(self):
                return b'{"items": []}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
        return FakeResp()

    with patch("eurika.learning.github_search.urllib.request.urlopen", side_effect=fake_urlopen):
        result = search_repositories("nonexistent:xyz")
    assert result == []
