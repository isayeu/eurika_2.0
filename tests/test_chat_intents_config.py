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


def test_neskolko_failov_is_not_file_recount(tmp_path: Path) -> None:
    """«несколько файлов» contains «сколько» as a substring — must not dump a file inventory."""
    from eurika.api.chat_direct import resolve_direct_handler

    msg = (
        "думаю правильно будет так, разберем на примере крайнего редактирования.\n"
        "1) ты поготавливаешь полный патч, возможно несколько файлов.\n"
        "2) говоришь, готово мой друг.\n"
        "3) Я иду во вкладку Approvals, Загружаю план, просматриваю и решаю применять или нет.\n"
        "бедет ли так лучше?"
    )
    assert match_direct_intent(tmp_path, msg) != ("file_recount", None)
    assert match_direct_intent(tmp_path, "возможно несколько файлов") != ("file_recount", None)
    assert resolve_direct_handler(tmp_path, msg)[0] != "file_recount"
    assert match_direct_intent(tmp_path, "сколько файлов?") == ("file_recount", None)


def test_project_ls_does_not_match_inside_goals(tmp_path: Path) -> None:
    """Space-padded « ls » must not fire on the letters inside «goals»."""
    from eurika.api.chat_direct import resolve_direct_handler

    backlog = (
        "Дальше по бэклогу — мелкий chat UX / goals polish; Market только journal."
    )
    assert match_direct_intent(tmp_path, backlog) == ("roadmap_next", None)
    assert resolve_direct_handler(tmp_path, backlog)[0] == "roadmap_next"
    assert match_direct_intent(tmp_path, "выполни ls") == ("project_ls", "$ ls -la")
    assert match_direct_intent(tmp_path, "ls") == ("project_ls", "$ ls -la")
    assert match_direct_intent(tmp_path, "read goals.py") is None


def test_continue_dev_beats_ml_vector_toggle(tmp_path: Path, monkeypatch) -> None:
    """«приступай» is continue_dev — never soft-route to vector_intent_off."""
    from eurika.api.chat_direct import resolve_direct_handler, _accept_soft_handler

    assert match_direct_intent(tmp_path, "приступай") == ("continue_dev", None)
    assert resolve_direct_handler(tmp_path, "приступай")[0] == "continue_dev"
    assert resolve_direct_handler(tmp_path, "продолжай разработку")[0] == "continue_dev"
    assert _accept_soft_handler("vector_intent_off", "приступай") is False
    assert _accept_soft_handler("ml_intent_on", "приступай") is False

    monkeypatch.setenv("EURIKA_USE_ML_INTENT", "1")

    def _fake_ml(_root, _msg, **_kw):
        return ("vector_intent_off", None)

    monkeypatch.setattr("eurika.ml.intent_router.match_ml_intent", _fake_ml)
    # Direct YAML still wins before ML.
    assert resolve_direct_handler(tmp_path, "приступай")[0] == "continue_dev"
    # If YAML missed, soft accept would still block the toggle.
    assert _accept_soft_handler("vector_intent_off", "xyz") is False


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


def test_os_check_not_roadmap_verify(tmp_path: Path) -> None:
    """«операционка» = host OS health; soft must not invent roadmap_verify."""
    from eurika.api.chat_direct import (
        _accept_soft_handler,
        is_host_health_request,
        is_os_env_check_request,
        is_roadmap_verify_request,
        resolve_direct_handler,
    )

    msg = "Можешь проверить мою операционку? Хорошо ли она настроена?"
    assert is_host_health_request(msg) is True
    assert is_os_env_check_request(msg) is False
    assert is_roadmap_verify_request(msg) is False
    assert _accept_soft_handler("roadmap_verify", msg) is False
    assert resolve_direct_handler(tmp_path, msg)[0] == "host_health"
    assert resolve_direct_handler(tmp_path, "проверь фазу 2.7")[0] == "roadmap_verify"
    assert resolve_direct_handler(tmp_path, "проведи self-check")[0] == "self_check"
    assert is_roadmap_verify_request("проверь фазу CR-B") is True


def test_dir_contents_goes_to_llm_not_show_file(tmp_path: Path) -> None:
    """«содержимое каталога» → LLM tool-loop; soft must not invent show_file."""
    from eurika.api.chat_direct import (
        _accept_soft_handler,
        is_ls_request,
        is_show_file_request,
        resolve_direct_handler,
    )

    msg = "покажи содержимое каталога проекта"
    assert is_ls_request(msg) is True
    assert is_show_file_request(msg) is False
    assert _accept_soft_handler("show_file", msg) is False
    assert _accept_soft_handler("project_ls", msg) is False
    assert resolve_direct_handler(tmp_path, msg)[0] is None
    assert is_show_file_request("покажи файл eurika/api/chat.py") is True
    assert resolve_direct_handler(tmp_path, "покажи файл README.md")[0] == "show_file"


def test_soft_vector_must_not_invent_identity_or_file_recount(tmp_path: Path, monkeypatch) -> None:
    """Polygon/code questions must not fuzzy-map to identity or file_recount."""
    from eurika.api.chat_direct import _accept_soft_handler, resolve_direct_handler

    poly = "По файлу eurika/polygon/extractable_block.py: что вернёт polygon_extractable_block(5)?"
    numbers = "polygon_refactor_code_smell_try_except([1, 2, 3]) — два числа."
    assert _accept_soft_handler("identity", poly) is False
    assert _accept_soft_handler("file_recount", numbers) is False
    assert _accept_soft_handler("greeting", poly) is False
    assert _accept_soft_handler("capabilities", poly) is False
    assert resolve_direct_handler(tmp_path, "ты кто?")[0] == "identity"
    assert resolve_direct_handler(tmp_path, "сколько файлов?")[0] == "file_recount"

    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")

    def _fake_identity(_root, _msg, **_kw):
        return ("identity", None, 0.99)

    monkeypatch.setattr("eurika.api.chat_vector.match_fuzzy_intent", _fake_identity)
    assert resolve_direct_handler(tmp_path, poly)[0] is None

    def _fake_recount(_root, _msg, **_kw):
        return ("file_recount", None, 0.99)

    monkeypatch.setattr("eurika.api.chat_vector.match_fuzzy_intent", _fake_recount)
    assert resolve_direct_handler(tmp_path, numbers)[0] is None


def test_bare_ls_still_host_shell(tmp_path: Path) -> None:
    from eurika.api.chat_direct import resolve_direct_handler

    assert resolve_direct_handler(tmp_path, "ls")[0] == "host_shell"
    assert resolve_direct_handler(tmp_path, "ls -la")[0] == "host_shell"
    assert resolve_direct_handler(tmp_path, "покажи дерево проекта")[0] is None


def test_git_status_not_commit_handler(tmp_path: Path) -> None:
    from eurika.api.chat_direct import (
        is_git_commit_request,
        is_git_status_request,
        resolve_direct_handler,
    )

    assert is_git_status_request("git diff") is True
    assert is_git_commit_request("git diff") is False
    assert resolve_direct_handler(tmp_path, "git diff")[0] == "host_shell"
    assert resolve_direct_handler(tmp_path, "покажи diff")[0] is None
    assert resolve_direct_handler(tmp_path, "собери коммит")[0] == "git_commit"
    assert resolve_direct_handler(tmp_path, "закоммить и запушь")[0] == "git_commit"
    assert resolve_direct_handler(tmp_path, "запушь")[0] == "git_push"


def test_long_eval_brief_does_not_hijack_git_or_reject(tmp_path: Path) -> None:
    from eurika.api.chat_direct import (
        is_apply_confirmation,
        is_git_commit_request,
        is_git_push_request,
        is_reject_confirmation,
        is_roadmap_verify_request,
        resolve_direct_handler,
    )

    brief = (
        "Сравни Qt Chat и Desktop по git HITL.\n"
        "Qt: chat_handlers git_commit / git_push, pending, применяй.\n"
        "Desktop: есть ли тот же preview перед git commit и git push?\n"
        "Упомяни Apply/Reject только как UI-кнопки. Не пиши файлы."
    )
    assert is_git_commit_request(brief) is False
    assert is_git_push_request(brief) is False
    assert is_reject_confirmation(brief) is False
    assert is_apply_confirmation(brief) is False
    assert is_reject_confirmation("отклонить") is True
    assert resolve_direct_handler(tmp_path, brief)[0] is None
    assert resolve_direct_handler(tmp_path, "отклонить")[0] is None
    assert resolve_direct_handler(tmp_path, "собери коммит")[0] == "git_commit"


def test_long_brief_does_not_hijack_apply_or_roadmap_verify() -> None:
    from eurika.api.chat_direct import is_apply_confirmation, is_roadmap_verify_request

    apply_brief = (
        "Задача: саморазвитие, файлы не меняй и ops не применяй.\n"
        "1) freeze Market\n"
        "2) только doctor --no-llm"
    )
    assert is_apply_confirmation(apply_brief) is False
    assert is_apply_confirmation("применяй") is True
    assert is_apply_confirmation("применяй token:abcd1234") is True
    assert is_apply_confirmation("apply token:abcd1234") is True

    plan_brief = (
        "Задача саморазвития, только диагностика, файлы репозитория не меняй.\n"
        "Контекст: ROADMAP — работа над своим кодом (scan/doctor, план без записи).\n"
        "VISION — freeze Market ML."
    )
    assert is_roadmap_verify_request(plan_brief) is False
    assert is_roadmap_verify_request("проверь фазу 2.7") is True
    assert is_roadmap_verify_request("проверь фазу CR-B") is True
    assert is_roadmap_verify_request("verify phase 3.0") is True
    assert is_roadmap_verify_request("сверь roadmap") is True
    from eurika.api.chat_direct import resolve_direct_handler

    assert resolve_direct_handler(Path("."), plan_brief)[0] is None
    assert resolve_direct_handler(Path("."), "проверь фазу 2.7")[0] == "roadmap_verify"
