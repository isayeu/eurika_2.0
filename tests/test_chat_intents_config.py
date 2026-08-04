"""Tests for default intent config and user YAML overrides."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from eurika.api.chat_intents_config import (
    clear_cache,
    get_all_intents,
    get_intent_hints,
    match_direct_intent,
)


@pytest.fixture(autouse=True)
def _clear_intent_cache() -> Iterator[None]:
    clear_cache()
    yield
    clear_cache()


def test_defaults_apply_for_arbitrary_project(tmp_path: Path) -> None:
    """A project without .eurika/config/chat_intents.yaml still gets greeting/overview/recount."""
    assert match_direct_intent(tmp_path, "привет") == ("greeting", None)
    assert match_direct_intent(tmp_path, "что за проект открыт?") == ("project_overview", None)
    assert match_direct_intent(tmp_path, "сколько файлов в проекте?") == ("file_recount", None)
    assert match_direct_intent(tmp_path, "сколько всего там файлов?") == ("file_recount", None)
    assert match_direct_intent(tmp_path, "ты пересчитала файлы?") == ("file_recount", None)
    assert match_direct_intent(tmp_path, "что у нас дальше по развитию проекта?") == ("roadmap_next", None)


def test_defaults_skip_when_message_doesnt_match(tmp_path: Path) -> None:
    """Random messages stay unmatched (LLM/clarification path)."""
    assert match_direct_intent(tmp_path, "проанализируй код") is None
    assert match_direct_intent(tmp_path, "напиши тесты для serve.py") is None


def test_scan_intent_excludes_run_command_phrasing(tmp_path: Path) -> None:
    """`выполни команду eurika scan .` is run_command, not scan."""
    assert match_direct_intent(tmp_path, "выполни команду eurika scan .") is None
    assert match_direct_intent(tmp_path, "просканируй проект") == ("scan", "$ eurika scan .")


def test_identity_takes_priority_over_greeting(tmp_path: Path) -> None:
    """`ты кто?` should be identity, not greeting (greeting only matches bare hello)."""
    assert match_direct_intent(tmp_path, "ты кто?") == ("identity", None)


def test_identity_creator_question(tmp_path: Path) -> None:
    """Authorship of *this* assistant/project → identity; arbitrary «кто написал X» → not."""
    from eurika.api.chat_direct import resolve_direct_handler

    yes = (
        "кто тебя создал?",
        "кто твой создатель?",
        "кто написал твой код?",
        "кто написал эту программу?",
        "кто автор проекта?",
        "who created you?",
        "who is your creator?",
        "who wrote your code?",
        "who wrote this program?",
    )
    for q in yes:
        assert match_direct_intent(tmp_path, q) == ("identity", None), q
        assert resolve_direct_handler(tmp_path, q) == ("identity", None), q

    no = (
        "кто написал игру тетрис?",
        "кто написал linux?",
        "кто создал python?",
    )
    for q in no:
        assert match_direct_intent(tmp_path, q) is None, q
        assert resolve_direct_handler(tmp_path, q) != ("identity", None), q


def test_user_yaml_overrides_intent(tmp_path: Path) -> None:
    """User can change project_overview patterns by writing .eurika/config/chat_intents.yaml."""
    pytest.importorskip("yaml")
    cfg_dir = tmp_path / ".eurika" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "chat_intents.yaml").write_text(
        """
intents:
  project_overview:
    patterns:
      - "обзор проекта"
      - "give me overview"
""",
        encoding="utf-8",
    )
    clear_cache()
    assert match_direct_intent(tmp_path, "обзор проекта") == ("project_overview", None)
    assert match_direct_intent(tmp_path, "give me overview please") == ("project_overview", None)
    # The default patterns no longer apply because user replaced the intent.
    assert match_direct_intent(tmp_path, "что за проект?") is None


def test_user_yaml_adds_new_intent(tmp_path: Path) -> None:
    """User can introduce new intent ids (mapped to existing handler ids)."""
    pytest.importorskip("yaml")
    cfg_dir = tmp_path / ".eurika" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "chat_intents.yaml").write_text(
        """
intents:
  show_report:
    patterns:
      - "дай отчёт"
      - "give me the report"
""",
        encoding="utf-8",
    )
    clear_cache()
    assert match_direct_intent(tmp_path, "дай отчёт по проекту") == ("show_report", None)
    # Defaults still work for unrelated intents.
    assert match_direct_intent(tmp_path, "привет") == ("greeting", None)


def test_user_yaml_can_disable_intent_with_null(tmp_path: Path) -> None:
    """Setting an intent to null in user YAML removes it from defaults."""
    pytest.importorskip("yaml")
    cfg_dir = tmp_path / ".eurika" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "chat_intents.yaml").write_text(
        """
intents:
  greeting: null
""",
        encoding="utf-8",
    )
    clear_cache()
    assert match_direct_intent(tmp_path, "привет") is None


def test_get_all_intents_returns_merged(tmp_path: Path) -> None:
    """Diagnostic helper returns the merged intent map."""
    intents = get_all_intents(tmp_path)
    assert "greeting" in intents
    assert "project_overview" in intents
    assert "file_recount" in intents
    assert "scan" in intents


def test_get_intent_hints_default(tmp_path: Path) -> None:
    """Default hints mention key commands."""
    hints = get_intent_hints(tmp_path)
    assert "сколько" in hints.lower() or "what" in hints.lower() or "коммит" in hints.lower()


def test_normalize_intent_text_folds_yo(tmp_path: Path) -> None:
    """ё→е normalization for intent substring matching."""
    from eurika.api.chat_intents_config import normalize_intent_text

    assert normalize_intent_text("  Покажи   отчёт  ") == "покажи отчет"
    assert match_direct_intent(tmp_path, "привет") == ("greeting", None)


def test_user_yaml_overrides_intent_hints(tmp_path: Path) -> None:
    """User-provided intent_hints replace defaults."""
    pytest.importorskip("yaml")
    cfg_dir = tmp_path / ".eurika" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "chat_intents.yaml").write_text(
        "intent_hints: |\n  - Custom hint for this project.\n",
        encoding="utf-8",
    )
    clear_cache()
    assert "Custom hint" in get_intent_hints(tmp_path)
