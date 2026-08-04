"""Tests for structured chat task interpretation."""

from eurika.api.chat_intent import interpret_task, parse_mentions


def test_interpret_task_detects_ui_tabs_intent() -> None:
    out = interpret_task("какие вкладки есть в твоем UI?")
    assert out.intent == "ui_tabs"
    assert out.confidence >= 0.9


def test_interpret_task_detects_ui_tabs_count_query() -> None:
    out = interpret_task("сколько у тебя вкладок в UI?")
    assert out.intent == "ui_tabs"
    assert out.confidence >= 0.9


def test_interpret_task_detects_add_empty_tab_request() -> None:
    out = interpret_task("после вкладки Chat создать пустую вкладку в UI")
    assert out.intent == "ui_add_empty_tab"
    assert out.target == "qt_app/ui/main_window.py"
    assert out.confidence >= 0.8


def test_interpret_task_detects_add_terminal_tab_request() -> None:
    out = interpret_task("создай вкладку Terminal, с эмулятором терминала")
    assert out.intent == "ui_add_empty_tab"
    assert out.target == "qt_app/ui/main_window.py"
    assert out.entities.get("tab_name") == "Terminal"
    assert out.confidence >= 0.8


def test_interpret_task_detects_remove_new_tab_request() -> None:
    out = interpret_task("удали вкладку New Tab в UI")
    assert out.intent == "ui_remove_tab"
    assert out.target == "qt_app/ui/main_window.py"
    assert out.entities.get("tab_name") == "New Tab"


def test_interpret_task_marks_ambiguous_imperative_for_clarification() -> None:
    out = interpret_task("сделай как лучше")
    assert out.intent == "ambiguous_request"
    assert out.needs_clarification is True
    assert out.clarifying_question


def test_parse_mentions_extracts_module_and_smell() -> None:
    """Examples from actual scan: god_module @ patch_engine.py, code_awareness.py."""
    m = parse_mentions("рефактори @patch_engine.py с учётом @god_module")
    assert m["modules"] == ["patch_engine.py"]
    assert "god_module" in m["smells"]
    assert "Scope" in m["scope_note"]


def test_parse_mentions_extracts_multiple_modules() -> None:
    """Examples from scan: cli/core_handlers, eurika/api/chat."""
    m = parse_mentions("проверь @cli/core_handlers.py и @eurika/api/chat.py")
    assert "cli/core_handlers.py" in m["modules"]
    assert "eurika/api/chat.py" in m["modules"]


def test_interpret_task_refactor_with_at_module_uses_as_target() -> None:
    """ROADMAP 3.6.5: refactor + @module sets target from mention.
    Example from scan risks: god_module @ patch_engine.py (severity=14).
    """
    out = interpret_task("рефактори @patch_engine.py")
    assert out.intent == "refactor"
    assert out.target == "patch_engine.py"
    assert out.entities.get("scope_modules") == "patch_engine.py"


def test_interpret_task_preserves_existing_refactor_intent() -> None:
    out = interpret_task("рефактори src/main.py")
    assert out.intent == "refactor"
    assert out.target == "src/main.py"
    assert out.requires_confirmation is True
    assert out.risk_level in {"high", "medium"}


def test_interpret_task_continue_uses_recent_user_intent() -> None:
    out = interpret_task(
        "продолжай",
        history=[
            {"role": "user", "content": "рефактори src/main.py"},
            {"role": "assistant", "content": "ok"},
        ],
    )
    assert out.intent == "refactor"
    assert out.target == "src/main.py"
    assert out.confidence >= 0.7


def test_interpret_task_extracts_goal_constraints_actions_sections() -> None:
    msg = (
        "цель: проверить выполнение\n"
        "границы: только в текущем репозитории\n"
        "задачи: после вкладки Chat добавить пустую вкладку"
    )
    out = interpret_task(msg)
    assert "проверить выполнение" in out.goal
    assert "только в текущем репозитории" in out.constraints
    assert out.actions


def test_interpret_task_detects_run_tests_intent() -> None:
    out = interpret_task("запусти тесты tests/test_chat_api.py")
    assert out.intent == "run_tests"
    assert out.target == "tests/test_chat_api.py"
    assert out.requires_confirmation is False


def test_interpret_task_detects_run_lint_intent() -> None:
    out = interpret_task("запусти линтер")
    assert out.intent == "run_lint"
    assert out.requires_confirmation is False


def test_interpret_task_detects_run_command_intent() -> None:
    out = interpret_task("выполни команду eurika scan .")
    assert out.intent == "run_command"
    assert "eurika scan" in (out.target or "")
    assert out.requires_confirmation is True


def test_interpret_task_detects_code_edit_patch_instruction() -> None:
    out = interpret_task('замени в файле qt_app/ui/main_window.py "Chat" на "ChatX"')
    assert out.intent == "code_edit_patch"
    assert out.target == "qt_app/ui/main_window.py"
    assert out.entities.get("old_text") == "Chat"
    assert out.entities.get("new_text") == "ChatX"


def test_interpret_task_detects_structured_patch_json_block() -> None:
    payload = """
```json
{
  "intent": "code_edit_patch",
  "target": "qt_app/ui/main_window.py",
  "old_text": "Chat",
  "new_text": "ChatX",
  "verify_target": "tests/test_qt_smoke.py"
}
```
""".strip()
    out = interpret_task(payload)
    assert out.intent == "code_edit_patch"
    assert out.target == "qt_app/ui/main_window.py"
    assert out.entities.get("old_text") == "Chat"
    assert out.entities.get("new_text") == "ChatX"
    assert out.entities.get("verify_target") == "tests/test_qt_smoke.py"


def test_interpret_task_detects_structured_patch_batch_json_block() -> None:
    payload = """
```json
{
  "intent": "code_edit_patch",
  "operations": [
    {"target": "a.py", "old_text": "x = 1", "new_text": "x = 2"},
    {"target": "b.py", "old_text": "y = 1", "new_text": "y = 2"}
  ],
  "verify_target": "tests/test_ok.py"
}
```
""".strip()
    out = interpret_task(payload)
    assert out.intent == "code_edit_patch"
    assert out.target == "a.py"
    assert out.entities.get("verify_target") == "tests/test_ok.py"
    assert out.entities.get("operations_json")


def test_interpret_task_rejects_structured_patch_unknown_schema_version() -> None:
    payload = """
```json
{
  "schema_version": 2,
  "intent": "code_edit_patch",
  "target": "a.py",
  "old_text": "x = 1",
  "new_text": "x = 2"
}
```
""".strip()
    out = interpret_task(payload)
    assert out.intent is None


def test_interpret_task_detects_structured_patch_dry_run_flag() -> None:
    payload = """
```json
{
  "schema_version": 1,
  "intent": "code_edit_patch",
  "target": "a.py",
  "old_text": "x = 1",
  "new_text": "x = 2",
  "dry_run": true
}
```
""".strip()
    out = interpret_task(payload)
    assert out.intent == "code_edit_patch"
    assert out.entities.get("dry_run") == "1"
