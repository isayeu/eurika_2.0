"""Ollama server and model install handlers. ROADMAP 3.1-arch.3."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QProcess

from ..main_window_helpers import parse_ollama_pull_progress, strip_ansi

if TYPE_CHECKING:
    from ..main_window import MainWindow


AVAILABLE_OLLAMA_MODELS = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "llama3.1:8b",
    "llama3.2:3b",
    "mistral:7b",
    "phi4:latest",
    "deepseek-r1:8b",
    "deepseek-r1:14b",
    "gemma2:9b",
    "codellama:13b",
]


def wire_ollama_process(main: MainWindow) -> None:
    main._ollama_process.started.connect(lambda: on_ollama_started(main))
    main._ollama_process.readyReadStandardOutput.connect(lambda: on_ollama_stdout(main))
    main._ollama_process.readyReadStandardError.connect(lambda: on_ollama_stderr(main))
    main._ollama_process.finished.connect(lambda c, s: on_ollama_finished(main, c, s))
    main._ollama_process.errorOccurred.connect(lambda e: on_ollama_error(main, e))


def wire_ollama_task_process(main: MainWindow) -> None:
    main._ollama_task_process.readyReadStandardOutput.connect(
        lambda: on_ollama_task_stdout(main)
    )
    main._ollama_task_process.readyReadStandardError.connect(
        lambda: on_ollama_task_stderr(main)
    )
    main._ollama_task_process.finished.connect(
        lambda c, s: on_ollama_task_finished(main, c, s)
    )
    main._ollama_task_process.errorOccurred.connect(
        lambda e: on_ollama_task_error(main, e)
    )


def setup_ollama_health_timer(main: MainWindow) -> None:
    main._ollama_health_timer.setInterval(10000)
    main._ollama_health_timer.timeout.connect(lambda: refresh_ollama_health(main))
    main._ollama_health_timer.start()
    refresh_ollama_health(main)
    refresh_ollama_catalog(main)


def start_ollama_server(main: MainWindow) -> None:
    if main._ollama_process.state() != QProcess.NotRunning:
        main.ollama_status.setText("Ollama: already running")
        sync_ollama_buttons(main)
        return
    from .chat_handlers import save_chat_preferences

    save_chat_preferences(main)
    from PySide6.QtCore import QProcessEnvironment

    env = QProcessEnvironment.systemEnvironment()
    env.insert("HSA_OVERRIDE_GFX_VERSION", main.ollama_hsa_edit.text().strip() or "10.3.0")
    env.insert("ROCR_VISIBLE_DEVICES", main.ollama_rocr_edit.text().strip() or "0")
    env.insert("HIP_VISIBLE_DEVICES", main.ollama_hip_edit.text().strip() or "0")
    main._ollama_process.setProcessEnvironment(env)
    main._ollama_process.setWorkingDirectory(main.root_edit.text().strip() or ".")
    main.ollama_output.append(
        f"$ HSA_OVERRIDE_GFX_VERSION={env.value('HSA_OVERRIDE_GFX_VERSION')} "
        f"ROCR_VISIBLE_DEVICES={env.value('ROCR_VISIBLE_DEVICES')} "
        f"HIP_VISIBLE_DEVICES={env.value('HIP_VISIBLE_DEVICES')} ollama serve"
    )
    main.ollama_status.setText("Ollama: starting...")
    sync_ollama_buttons(main)
    main._ollama_process.start("ollama", ["serve"])


def stop_ollama_server(main: MainWindow) -> None:
    if main._ollama_process.state() == QProcess.NotRunning:
        main.ollama_status.setText("Ollama: stopped")
        sync_ollama_buttons(main)
        return
    main.ollama_status.setText("Ollama: stopping...")
    shutdown_qprocess(main._ollama_process, timeout_ms=1200)


def on_ollama_started(main: MainWindow) -> None:
    main.ollama_status.setText("Ollama: running")
    sync_ollama_buttons(main)
    refresh_ollama_health(main)


def on_ollama_stdout(main: MainWindow) -> None:
    data = bytes(main._ollama_process.readAllStandardOutput()).decode(
        "utf-8", errors="replace"
    )
    for line in data.splitlines():
        if line.strip():
            main.ollama_output.append(line)


def on_ollama_stderr(main: MainWindow) -> None:
    data = bytes(main._ollama_process.readAllStandardError()).decode(
        "utf-8", errors="replace"
    )
    for line in data.splitlines():
        if line.strip():
            main.ollama_output.append(f"[stderr] {line}")


def on_ollama_finished(
    main: MainWindow, exit_code: int, _status: QProcess.ExitStatus
) -> None:
    main.ollama_status.setText(f"Ollama: stopped (exit={exit_code})")
    main.ollama_health.setText("API: unavailable")
    sync_ollama_buttons(main)


def on_ollama_error(main: MainWindow, _error: QProcess.ProcessError) -> None:
    msg = main._ollama_process.errorString() or "Unknown process error"
    main.ollama_output.append(f"[error] {msg}")
    main.ollama_status.setText("Ollama: error")
    main.ollama_health.setText("API: unavailable")
    sync_ollama_buttons(main)


def sync_ollama_buttons(main: MainWindow) -> None:
    running = main._ollama_process.state() != QProcess.NotRunning
    main.ollama_start_btn.setEnabled(not running)
    main.ollama_stop_btn.setEnabled(running)


def refresh_ollama_health(main: MainWindow) -> None:
    healthy = main._api.is_ollama_healthy()
    main.ollama_health.setText("API: healthy" if healthy else "API: unavailable")
    if healthy:
        refresh_ollama_models(main)
    else:
        main._last_models_error = ""


def refresh_ollama_models(main: MainWindow, user_initiated: bool = False) -> None:
    try:
        models = main._api.list_ollama_models()
    except Exception as exc:
        main.ollama_health.setText("API: unavailable")
        err_text = str(exc)
        if user_initiated:
            main.ollama_output.append(
                "[models] Ollama API недоступен. Нажми `Start Ollama`, затем повтори `Refresh installed`."
            )
            main.ollama_install_status.setText("Installed: API unavailable")
        elif err_text != main._last_models_error:
            main.ollama_install_status.setText("Installed: API unavailable")
        main._last_models_error = err_text
        return
    main._last_models_error = ""
    current = main.ollama_installed_combo.currentText()
    main.ollama_installed_combo.blockSignals(True)
    main.ollama_installed_combo.clear()
    if models:
        main.ollama_installed_combo.addItems(models)
        if current and current in models:
            main.ollama_installed_combo.setCurrentText(current)
    else:
        main.ollama_installed_combo.addItem("(no local models)")
    main.ollama_installed_combo.blockSignals(False)


def sync_chat_model_from_installed(main: MainWindow, value: str) -> None:
    text = (value or "").strip()
    if not text or text.startswith("("):
        return
    main.chat_ollama_model.setText(text)
    from .chat_handlers import save_chat_preferences

    save_chat_preferences(main)


def install_selected_ollama_model(main: MainWindow) -> None:
    if main._ollama_task_process.state() != QProcess.NotRunning:
        main.ollama_install_status.setText("Install: busy")
        return
    from .chat_handlers import save_chat_preferences

    save_chat_preferences(main)
    model = resolve_ollama_model_to_install(
        main.ollama_custom_model_edit.text(), main.ollama_available_combo.currentText()
    )
    if not model:
        main.ollama_install_status.setText("Install: select or input model")
        return
    main._ollama_task_mode = "pull"
    main._ollama_task_stdout = ""
    main._ollama_task_model = model
    main.ollama_install_status.setText(f"Install: pulling `{model}`...")
    main.ollama_output.append(f"$ ollama pull {model}")
    main.ollama_pull_progress_row.setVisible(True)
    main.ollama_pull_progress.setValue(0)
    main.ollama_pull_progress_label.setText("")
    main._ollama_task_process.start("ollama", ["pull", model])


def refresh_ollama_catalog(main: MainWindow) -> None:
    from .chat_handlers import save_chat_preferences

    save_chat_preferences(main)
    query = main.ollama_search_edit.text().strip() or "qwen"
    names = filter_available_ollama_models(query)
    current = main.ollama_available_combo.currentText()
    main.ollama_available_combo.clear()
    if names:
        main.ollama_available_combo.addItems(names)
        if current in names:
            main.ollama_available_combo.setCurrentText(current)
        if (
            main._saved_available_model
            and main.ollama_available_combo.findText(main._saved_available_model) >= 0
        ):
            main.ollama_available_combo.setCurrentText(main._saved_available_model)
            main._saved_available_model = ""
        main.ollama_install_status.setText(f"Catalog: {len(names)} models (filtered)")
        return
    main.ollama_available_combo.addItems(AVAILABLE_OLLAMA_MODELS)
    if (
        main._saved_available_model
        and main.ollama_available_combo.findText(main._saved_available_model) >= 0
    ):
        main.ollama_available_combo.setCurrentText(main._saved_available_model)
        main._saved_available_model = ""
    main.ollama_install_status.setText("Catalog: no matches, showing full list")


def on_ollama_task_stdout(main: MainWindow) -> None:
    chunk = bytes(main._ollama_task_process.readAllStandardOutput()).decode(
        "utf-8", errors="replace"
    )
    main._ollama_task_stdout += chunk
    for line in chunk.splitlines():
        clean = strip_ansi(line).strip()
        if clean:
            main.ollama_output.append(clean)


def on_ollama_task_stderr(main: MainWindow) -> None:
    chunk = bytes(main._ollama_task_process.readAllStandardError()).decode(
        "utf-8", errors="replace"
    )
    main._ollama_task_stdout += chunk
    for line in chunk.splitlines():
        clean = strip_ansi(line).strip()
        if clean:
            main.ollama_output.append(f"[stderr] {clean}")
            if main._ollama_task_mode == "pull":
                parsed = parse_ollama_pull_progress(clean)
                if parsed:
                    pct, label = parsed
                    main.ollama_pull_progress.setValue(pct)
                    main.ollama_pull_progress_label.setText(label)


def on_ollama_task_finished(
    main: MainWindow, exit_code: int, _status: QProcess.ExitStatus
) -> None:
    main.ollama_pull_progress_row.setVisible(False)
    main.ollama_pull_progress_label.setText("")
    if main._ollama_task_mode == "pull":
        if exit_code == 0:
            main.ollama_install_status.setText("Install: done")
            refresh_ollama_models(main)
            if main._ollama_task_model:
                main.chat_ollama_model.setText(main._ollama_task_model)
                if (
                    main.ollama_installed_combo.findText(main._ollama_task_model) >= 0
                ):
                    main.ollama_installed_combo.setCurrentText(main._ollama_task_model)
                main.ollama_custom_model_edit.setText("")
            refresh_ollama_health(main)
        else:
            main.ollama_install_status.setText(f"Install: failed (exit={exit_code})")
    else:
        main.ollama_install_status.setText("Install: idle")
    main._ollama_task_mode = ""
    main._ollama_task_model = ""


def on_ollama_task_error(main: MainWindow, _error: QProcess.ProcessError) -> None:
    main.ollama_pull_progress_row.setVisible(False)
    main.ollama_pull_progress_label.setText("")
    msg = main._ollama_task_process.errorString() or "Unknown process error"
    main.ollama_output.append(f"[install error] {msg}")
    main.ollama_install_status.setText("Install: error")
    main._ollama_task_mode = ""
    main._ollama_task_model = ""


def filter_available_ollama_models(query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return list(AVAILABLE_OLLAMA_MODELS)
    return [m for m in AVAILABLE_OLLAMA_MODELS if q in m.lower()]


def resolve_ollama_model_to_install(custom_value: str, selected_value: str) -> str:
    custom = (custom_value or "").strip()
    if custom:
        return custom
    selected = (selected_value or "").strip()
    if not selected or selected.startswith("("):
        return ""
    return selected


def shutdown_qprocess(process: QProcess, *, timeout_ms: int = 1500) -> None:
    if process.state() == QProcess.NotRunning:
        return
    process.terminate()
    if process.waitForFinished(timeout_ms):
        return
    process.kill()
    process.waitForFinished(timeout_ms)
