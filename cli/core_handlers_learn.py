"""Learn-github handler (P0.4 split)."""

from __future__ import annotations

import os
import sys
from typing import Any

from .core_handlers_common import _check_path, _err


def handle_learn_github(args: Any) -> int:
    """Clone curated OSS repos, optionally scan, build pattern library."""
    path = args.path.resolve()
    if _check_path(path) != 0:
        return 1
    from eurika.learning import load_curated_repos, ensure_repo_cloned, search_repositories

    search_query = getattr(args, "search", None)
    search_limit = getattr(args, "search_limit", 5)
    if search_query:
        try:
            token = os.environ.get("GITHUB_TOKEN", "")
            repos = search_repositories(search_query, per_page=search_limit, token=token or None)
            if not repos:
                _err("no repositories found for search query")
                return 1
            q_preview = (search_query[:50] + "…") if len(search_query) > 50 else search_query
            print(f"eurika learn-github: search '{q_preview}' -> {len(repos)} repos", file=sys.stderr)
        except RuntimeError as e:
            _err(str(e))
            return 1
    else:
        config_path = getattr(args, "config", None)
        if config_path is None:
            cfg = path / "docs" / "curated_repos.example.json"
            config_path = cfg if cfg.exists() else None
        repos = load_curated_repos(config_path)
    cache_dir = path.resolve().parent / "curated_repos"
    do_scan = getattr(args, "scan", False)
    do_patterns = getattr(args, "build_patterns", False)

    if not repos:
        _err("no curated repos found")
        return 1
    print(f"eurika learn-github: {len(repos)} repos, cache={cache_dir}", file=sys.stderr)
    ok = 0
    for repo in repos:
        name = repo.get("name", "?")
        dest, err = ensure_repo_cloned(repo, cache_dir)
        if dest:
            ok += 1
            print(f"  {name}: {dest}", file=sys.stderr)
            if do_scan:
                from runtime_scan import run_scan

                run_scan(dest)
        else:
            print(f"  {name}: clone failed — {err or 'unknown'}", file=sys.stderr)
    if do_patterns or do_scan:
        from eurika.learning.pattern_library import extract_patterns_from_repos, save_pattern_library

        lib_path = path / ".eurika" / "pattern_library.json"
        data = extract_patterns_from_repos(cache_dir)
        save_pattern_library(data, lib_path)
        total = sum(len(v) for v in data.values() if isinstance(v, list))
        projects = {
            str(project)
            for v in data.values()
            if isinstance(v, list)
            for e in v
            if isinstance(e, dict)
            for project in [e.get("project")]
            if project
        }
        proj_str = ", ".join(sorted(projects)) if projects else "none"
        print(f"eurika learn-github: pattern library written ({total} entries from {len(projects)} repo(s): {proj_str}) -> {lib_path}", file=sys.stderr)
    print(f"eurika learn-github: {ok}/{len(repos)} repos available", file=sys.stderr)
    return 0 if ok > 0 else 1
