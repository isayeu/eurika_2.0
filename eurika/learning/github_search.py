"""GitHub repository search (ROADMAP 3.0.5.2).

Search repos by language, stars, topics. Uses GitHub REST API.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def search_repositories(
    query: str,
    *,
    per_page: int = 10,
    sort: str = "stars",
    token: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search GitHub repos. Returns list of {url, name, branch}.

    query: GitHub search qualifiers, e.g. "language:python stars:>1000"
    token: GITHUB_TOKEN for higher rate limits (optional).
    """
    q = query.strip() or "language:python"
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={urllib.parse.quote(q)}"
        f"&sort={urllib.parse.quote(sort)}"
        f"&per_page={min(per_page, 30)}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Eurika/1.0",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError("GitHub rate limit; set GITHUB_TOKEN for more requests") from e
        raise RuntimeError(f"GitHub API error: {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e

    items = data.get("items") or []
    result: list[dict[str, Any]] = []
    for it in items:
        clone_url = it.get("clone_url") or it.get("html_url", "").rstrip("/") + ".git"
        full_name = it.get("full_name", "").split("/")[-1]
        branch = it.get("default_branch") or "main"
        if clone_url:
            result.append({"url": clone_url, "name": full_name, "branch": branch})
    return result
