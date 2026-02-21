"""Learning from GitHub (ROADMAP 3.0.5): curated repos, pattern library, apply-rate improvement."""

from .curated_repos import (
    CURATED_REPOS,
    clone_repo,
    load_curated_repos,
    ensure_repo_cloned,
)
from .github_search import search_repositories
from .pattern_library import (
    extract_patterns_from_repos,
    load_pattern_library,
    save_pattern_library,
)

__all__ = [
    "CURATED_REPOS",
    "clone_repo",
    "load_curated_repos",
    "ensure_repo_cloned",
    "extract_patterns_from_repos",
    "load_pattern_library",
    "save_pattern_library",
    "search_repositories",
]
