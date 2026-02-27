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


def test_qt_main_window_smoke() -> None:
    recommended = os.environ.get("EURIKA_QT_SMOKE_PYTHON", "").strip()
    if sys.version_info >= (3, 14) and not recommended:
        pytest.skip(
            "Qt smoke should run under recommended Python (3.12/3.13). "
            "Set EURIKA_QT_SMOKE_PYTHON to isolated interpreter."
        )

    python_bin = recommended or sys.executable
    smoke_script = textwrap.dedent(
        """
        from PySide6.QtWidgets import QApplication
        from qt_app.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        assert window.windowTitle() == "Eurika Qt"
        assert window.root_edit is not None
        assert window.chat_send_btn is not None
        assert window.chat_apply_btn is not None
        assert window.chat_reject_btn is not None
        assert window.chat_pending_label is not None
        assert window.chat_provider_combo is not None
        assert window.learning_widget_text is not None
        assert window.chat_goal_view is not None
        assert window.ollama_start_btn is not None
        assert window.ollama_stop_btn is not None
        assert window.ollama_status is not None
        assert window.ollama_health is not None
        assert window.ollama_installed_combo is not None
        assert window.ollama_available_combo is not None
        assert window.ollama_search_edit is not None
        assert window.ollama_search_refresh_btn is not None
        assert window.ollama_custom_model_edit is not None
        assert window.ollama_install_btn is not None
        tab_names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "Models" in tab_names
        assert "Chat" in tab_names
        window.close()
        app.quit()
        print("SMOKE_OK")
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


def test_filter_available_ollama_models_returns_matches() -> None:
    names = MainWindow._filter_available_ollama_models("qwen")
    assert names
    assert all("qwen" in name for name in names)


def test_resolve_ollama_model_to_install_prefers_custom() -> None:
    model = MainWindow._resolve_ollama_model_to_install("deepseek-r1:14b", "qwen2.5-coder:7b")
    assert model == "deepseek-r1:14b"
    fallback = MainWindow._resolve_ollama_model_to_install("", "qwen2.5-coder:7b")
    assert fallback == "qwen2.5-coder:7b"


def test_response_requests_confirmation_detects_confirm_markers() -> None:
    text = "Подтвердите выполнение: `применяй token:b02d6842ee544f85` (или просто `применяй`)."
    assert MainWindow._response_requests_confirmation(text) is True
    assert MainWindow._extract_pending_token_from_text(text) == "b02d6842ee544f85"


def test_response_requests_confirmation_ignores_no_token_text() -> None:
    text = "Подтвердите выполнение: `применяй`."
    assert MainWindow._response_requests_confirmation(text) is False

