"""Tests for learn-github (ROADMAP 4.1: --light, --limit-repos)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def test_learn_github_light_config_loads(tmp_path: Path) -> None:
    """--light uses curated_repos.light.json when present."""
    from eurika.learning import load_curated_repos

    light_cfg = tmp_path / "curated_repos.light.json"
    light_cfg.write_text(
        '{"repos":[{"url":"https://github.com/encode/starlette.git","name":"starlette","branch":"main"}]}',
        encoding="utf-8",
    )
    repos = load_curated_repos(light_cfg)
    assert len(repos) == 1
    assert repos[0]["name"] == "starlette"


def test_learn_github_limit_repos_slices(tmp_path: Path) -> None:
    """--limit-repos restricts number of repos processed."""
    from cli.core_handlers_learn import handle_learn_github

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    cache_dir = tmp_path.parent / "curated_repos"
    cache_dir.mkdir(exist_ok=True)
    (cache_dir / "starlette").mkdir(exist_ok=True)
    (cache_dir / "starlette" / "self_map.json").write_text("{}", encoding="utf-8")

    args = SimpleNamespace(
        path=tmp_path.resolve(),
        config=None,
        search=None,
        search_limit=5,
        limit_repos=1,
        light=False,
        scan=False,
        build_patterns=True,
    )
    with patch("eurika.learning.ensure_repo_cloned", return_value=(cache_dir / "starlette", "")):
        code = handle_learn_github(args)
    assert code == 0
    lib_path = tmp_path / ".eurika" / "pattern_library.json"
    assert lib_path.exists()
