from pathlib import Path
import os
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("PySide6")

from qt_app.ui.main_window import MainWindow
from qt_app.ui.handlers import ollama_handlers, chat_handlers, command_handlers


def test_qt_main_window_smoke() -> None:
    python_bin = os.environ.get("EURIKA_QT_SMOKE_PYTHON", "").strip() or sys.executable
    smoke_script = textwrap.dedent(
        """
        import sys
        from PySide6.QtWidgets import QApplication
        from qt_app.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        assert window.windowTitle() == "Eurika Qt"
        assert window.root_edit is not None
        assert window.chat_send_btn is not None
        assert window.chat_cancel_btn is not None
        assert window.chat_typing_label is not None
        assert window.chat_apply_btn is not None
        assert window.chat_reject_btn is not None
        assert window.chat_pending_label is not None
        assert window.chat_provider_combo is not None
        assert window.learning_widget_text is not None
        assert window.chat_goal_view is not None
        assert window.ollama_start_btn is not None
        assert window.ollama_stop_btn is not None
        assert window.ollama_cuda_check is not None
        assert window.ollama_cuda_devices_edit is not None
        assert window.ollama_vulkan_check is not None
        assert window.ollama_status is not None
        assert window.ollama_health is not None
        assert window.ollama_installed_combo is not None
        assert window.ollama_available_combo is not None
        assert window.ollama_custom_model_edit is not None
        assert window.ollama_install_btn is not None
        assert window.models_inner_tabs is not None
        assert window.models_inner_tabs.count() == 2
        assert window.models_inner_tabs.tabText(0) == "LLM"
        assert window.models_inner_tabs.tabText(1) == "ML"
        assert window.ml_torch_device_combo is not None
        assert window.ml_torch_refresh_btn is not None
        assert window.ml_torch_output is not None
        tab_names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "Graph" in tab_names
        assert "Models" in tab_names
        assert "Chat" in tab_names
        assert "Terminal" in tab_names
        assert window.terminal_emulator_input is not None
        assert window.terminal_emulator_output is not None
        assert window.terminal_emulator_stop_btn is not None
        assert window.terminal_emulator_clear_btn is not None
        from qt_app.ui.main_window_helpers import TerminalView
        assert isinstance(window.terminal_emulator_output, TerminalView)
        assert window.terminal_emulator_output.toPlainText().endswith("$ ")
        print("SMOKE_OK")
        sys.exit(0)
        """
    )
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    result = subprocess.run(
        [python_bin, "-c", smoke_script],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=45,
        env=env,
    )
    combined = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    if result.returncode == 0 and "smoke_ok" in combined:
        return
    if "smoke_ok" in combined and (
        "bus error" in combined
        or "signal: 7" in combined
        or "destroyqcoreapplication" in combined
    ):
        pytest.skip("Qt smoke completed, child process crashed on teardown (known environment issue).")
    raise AssertionError(
        "Qt smoke subprocess failed:\n"
        f"python={python_bin}\n"
        f"exit={result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_available_ollama_models_not_empty() -> None:
    from qt_app.ui.handlers.ollama_handlers import AVAILABLE_OLLAMA_MODELS

    assert len(AVAILABLE_OLLAMA_MODELS) >= 10


def test_resolve_ollama_model_to_install_prefers_custom() -> None:
    model = ollama_handlers.resolve_ollama_model_to_install("deepseek-r1:14b", "qwen2.5-coder:7b")
    assert model == "deepseek-r1:14b"
    fallback = ollama_handlers.resolve_ollama_model_to_install("", "qwen2.5-coder:7b")
    assert fallback == "qwen2.5-coder:7b"


def test_response_requests_confirmation_detects_confirm_markers() -> None:
    text = "Подтвердите выполнение: `применяй token:b02d6842ee544f85` (или просто `применяй`)."
    assert chat_handlers.response_requests_confirmation(text) is True
    assert chat_handlers.extract_pending_token_from_text(text) == "b02d6842ee544f85"


def test_response_requests_confirmation_ignores_no_token_text() -> None:
    text = "Подтвердите выполнение: `применяй`."
    assert chat_handlers.response_requests_confirmation(text) is False


def test_pending_diff_gate_requires_preview_then_resets() -> None:
    """Apply unlocks only after Diff seen for current pending fingerprint."""
    from typing import cast

    from qt_app.ui.main_window import MainWindow

    class _GateHost:
        def __init__(self) -> None:
            self._pending_diff_gate_fp = ""
            self._pending_diff_seen_fp = ""

    host = cast(MainWindow, _GateHost())
    fp = chat_handlers._pending_preview_fingerprint({"token": "deadbeef"}, None)
    assert fp == "plan:deadbeef"
    chat_handlers._sync_pending_diff_gate(host, fp)
    assert (
        chat_handlers._apply_allowed_for_pending(
            host, has_effective_pending=True, previewable=True, fingerprint=fp
        )
        is False
    )
    chat_handlers._mark_pending_diff_seen(host, fp)
    assert (
        chat_handlers._apply_allowed_for_pending(
            host, has_effective_pending=True, previewable=True, fingerprint=fp
        )
        is True
    )
    chat_handlers._sync_pending_diff_gate(host, "plan:other")
    assert chat_handlers._pending_diff_was_seen(host, "plan:other") is False
    assert (
        chat_handlers._apply_allowed_for_pending(
            host,
            has_effective_pending=True,
            previewable=False,
            fingerprint="",
        )
        is True
    )



def test_terminal_view_prompt_history_and_append_preserves_partial() -> None:
    """Classic TerminalView: prompt, history, append keeps partial command."""
    from PySide6.QtWidgets import QApplication
    from qt_app.ui.main_window_helpers import TerminalView

    app = QApplication.instance() or QApplication([])
    view = TerminalView()
    assert view.toPlainText().endswith("$ ")
    view.set_command_text("ls -la")
    assert view.current_command() == "ls -la"
    view.add_to_history("pwd")
    view.add_to_history("ls")
    view.set_command_text("")
    # simulate Up history
    view._history_index = -1
    view._pending_from_history = view.current_command()
    view._history_index = 0
    view.set_command_text(view._history[-1])
    assert view.current_command() == "ls"
    view.set_command_text("partial")
    view.append("[Chat] hello")
    assert "[Chat] hello" in view.toPlainText()
    assert view.current_command() == "partial"
    assert view.toPlainText().endswith("$ partial")
    submitted: list[str] = []
    view.command_submitted.connect(submitted.append)
    view.add_to_history("echo hi")
    view.set_command_text("echo hi")
    cmd = view.commit_command_line()
    assert cmd.strip() == "echo hi"
    assert view.is_input_locked()
    view.unlock_input()
    assert view.toPlainText().endswith("$ ")


def test_validate_project_root_rejects_empty() -> None:
    ok, msg = command_handlers.validate_project_root('')
    assert ok is False
    assert 'empty' in msg.lower() or 'browse' in msg.lower()


def test_validate_project_root_accepts_path_with_pyproject(tmp_path: Path) -> None:
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n', encoding='utf-8')
    ok, msg = command_handlers.validate_project_root(str(tmp_path))
    assert ok is True
    assert msg == ''


def test_validate_project_root_accepts_path_with_self_map(tmp_path: Path) -> None:
    (tmp_path / 'self_map.json').write_text('{}', encoding='utf-8')
    ok, msg = command_handlers.validate_project_root(str(tmp_path))
    assert ok is True


def test_validate_project_root_rejects_missing_path() -> None:
    ok, msg = command_handlers.validate_project_root('/nonexistent/path/xyz')
    assert ok is False
    assert 'exist' in msg.lower() or 'not found' in msg.lower()


def test_validate_project_root_rejects_dir_without_markers(tmp_path: Path) -> None:
    ok, msg = command_handlers.validate_project_root(str(tmp_path))
    assert ok is False
    assert 'pyproject' in msg.lower() or 'self_map' in msg.lower() or 'python' in msg.lower()


def test_validate_project_root_accepts_python_sources_only(tmp_path: Path) -> None:
    (tmp_path / 'app.py').write_text('print("ok")\n', encoding='utf-8')
    ok, msg = command_handlers.validate_project_root(str(tmp_path))
    assert ok is True
    assert msg == ''

