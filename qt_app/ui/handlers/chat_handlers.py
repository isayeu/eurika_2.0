"""Chat preferences, send, apply/reject handlers. ROADMAP 3.1-arch.3."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QInputDialog, QMessageBox

from ..chat_markdown import format_chat_line_html, parse_chat_action_url, shell_command_from_block
from ..main_window_helpers import ChatWorker, HostPrivilegeBridge, privilege_prompt_from_bridge
from ..tabs import terminal_tab

if TYPE_CHECKING:
    from ..main_window import MainWindow


def _chat_prompt_history_path(main: "MainWindow") -> Path | None:
    root = ""
    try:
        root = str(main._settings.get_project_root() or "").strip()
    except Exception:
        root = ""
    if not root:
        return None
    return Path(root) / ".eurika" / "chat_prompt_history.json"


def _load_chat_prompt_history(main: "MainWindow", settings_data: dict[str, Any]) -> None:
    if not hasattr(main, "chat_input") or not hasattr(main.chat_input, "set_history"):
        return
    import json

    prompts: list[str] = []
    path = _chat_prompt_history_path(main)
    if path is not None and path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("prompts"), list):
                prompts = [str(x) for x in raw["prompts"]]
            elif isinstance(raw, list):
                prompts = [str(x) for x in raw]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            prompts = []
    if not prompts:
        saved = settings_data.get("chat_prompt_history")
        if isinstance(saved, list):
            prompts = [str(x) for x in saved]
    main.chat_input.set_history(prompts)


def _save_chat_prompt_history(main: "MainWindow") -> None:
    if not hasattr(main, "chat_input") or not hasattr(main.chat_input, "history_snapshot"):
        return
    import json

    prompts = main.chat_input.history_snapshot()[-200:]
    path = _chat_prompt_history_path(main)
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"prompts": prompts}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
    # Mirror into qt_settings as backup when project path missing / write failed.
    try:
        data = main._settings.load()
        data["chat_prompt_history"] = prompts
        main._settings.save(data)
    except Exception:
        pass


def _restore_chat_session(main: "MainWindow") -> None:
    """Restore recent project-local conversation after launch/root change."""
    try:
        root = str(main._settings.get_project_root() or "").strip()
    except Exception:
        root = ""
    root_key = str(Path(root).resolve()) if root else ""
    if getattr(main, "_chat_history_root", None) == root_key:
        return
    main._chat_history_root = root_key
    main._chat_history.clear()
    main.chat_transcript.clear()
    main._chat_block_payloads = {}
    if not root_key:
        return
    from eurika.api.chat import load_chat_history

    restored = load_chat_history(Path(root_key), limit=80)
    main._chat_history.extend(restored)
    for item in restored:
        _remember_live_chat(main, item["role"], item["content"])
        _append_transcript(main,
            _format_chat_line(main, item["role"], item["content"])
        )
    if restored:
        _scroll_transcript_to_bottom(main)
    _reset_live_follow_offsets(main, Path(root_key))
    start_live_activity_follow(main)


def _live_chat_key(role: str, content: str) -> str:
    return f"{role}:{content.strip()[:800]}"


def _remember_live_chat(main: "MainWindow", role: str, content: str) -> bool:
    """True when this line is new and should be drawn."""
    seen = getattr(main, "_live_chat_seen", None)
    if not isinstance(seen, set):
        seen = set()
        main._live_chat_seen = seen
    key = _live_chat_key(role, content)
    if key in seen:
        return False
    seen.add(key)
    if len(seen) > 400:
        # Drop oldest-ish by rebuilding from history.
        main._live_chat_seen = {
            _live_chat_key(str(item.get("role")), str(item.get("content")))
            for item in list(getattr(main, "_chat_history", []) or [])[-200:]
        }
        main._live_chat_seen.add(key)
    return True


def _reset_live_follow_offsets(main: "MainWindow", root: Path) -> None:
    from eurika.agent.live_activity import activity_path, chat_history_path, file_end

    main._live_chat_offset = file_end(chat_history_path(root))
    main._live_activity_offset = file_end(activity_path(root))
    seen_ids = getattr(main, "_live_activity_ids", None)
    if not isinstance(seen_ids, set):
        main._live_activity_ids = set()
    else:
        seen_ids.clear()


def start_live_activity_follow(main: "MainWindow") -> None:
    """Poll workspace logs so API/Desktop work appears without a restart."""
    import os

    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    timer = getattr(main, "_live_activity_timer", None)
    if timer is None:
        timer = QTimer(main)
        timer.setInterval(700)
        timer.timeout.connect(lambda: poll_live_activity(main))
        main._live_activity_timer = timer
    if not timer.isActive():
        timer.start()


def poll_live_activity(main: "MainWindow") -> None:
    if getattr(main, "_is_closing", False):
        return
    try:
        root = Path(str(main._api._root()))
    except Exception:
        return
    from eurika.agent.live_activity import activity_path, chat_history_path, consume_jsonl

    chat_offset = int(getattr(main, "_live_chat_offset", 0) or 0)
    records, chat_offset = consume_jsonl(chat_history_path(root), chat_offset)
    main._live_chat_offset = chat_offset
    drew_chat = False
    for record in records:
        role = str(record.get("role") or "").strip().lower()
        content = str(record.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        if not _remember_live_chat(main, role, content):
            continue
        main._chat_history.append({"role": role, "content": content})
        _append_transcript(main, _format_chat_line(main, role, content))
        drew_chat = True
    if drew_chat:
        _scroll_transcript_to_bottom(main)
        _maybe_show_chat_tab(main)

    act_offset = int(getattr(main, "_live_activity_offset", 0) or 0)
    events, act_offset = consume_jsonl(activity_path(root), act_offset)
    main._live_activity_offset = act_offset
    seen_ids = getattr(main, "_live_activity_ids", None)
    if not isinstance(seen_ids, set):
        seen_ids = set()
        main._live_activity_ids = seen_ids
    for event in events:
        event_id = str(event.get("id") or "")
        phase = str(event.get("phase") or "")
        key = f"{event_id}:{phase}"
        if key in seen_ids:
            continue
        seen_ids.add(key)
        _apply_live_activity_event(main, event)


def _maybe_show_chat_tab(main: "MainWindow") -> None:
    chat_input = getattr(main, "chat_input", None)
    if chat_input is not None and chat_input.hasFocus():
        return
    if hasattr(main, "tabs") and hasattr(main, "chat_tab_index"):
        main.tabs.setCurrentIndex(main.chat_tab_index)
    inner = getattr(main, "chat_inner_tabs", None)
    if inner is not None and hasattr(main, "chat_dialog_subtab_index"):
        inner.setCurrentIndex(main.chat_dialog_subtab_index)


def _apply_live_activity_event(main: "MainWindow", event: dict[str, Any]) -> None:
    title = str(event.get("title") or event.get("method") or "API").strip()
    phase = str(event.get("phase") or "")
    client = str(event.get("client") or "api")
    kind = str(event.get("kind") or "")
    visible = phase == "start" or kind == "http"
    if visible:
        suffix = ""
        if phase == "done" and event.get("ok") is False:
            suffix = " — fail"
        elif phase == "done" and kind == "http":
            suffix = " — ok"
        line = f"[API {client}] {title}{suffix}"
        if hasattr(main, "status_label"):
            main.status_label.setText(line[:120])
        if hasattr(main, "terminal_emulator_output") and main.terminal_emulator_output:
            main.terminal_emulator_output.append(line)
        _append_transcript(main, _format_chat_line(main, "assistant", line))
        _scroll_transcript_to_bottom(main)
        if kind in {"chat", "http"}:
            _maybe_show_chat_tab(main)
        if phase == "start":
            return
    if phase != "done":
        return
    cmd = str(event.get("terminal_cmd") or "").strip()
    out = str(event.get("terminal_output") or "").strip()
    if cmd or out:
        if hasattr(main, "terminal_emulator_output") and main.terminal_emulator_output:
            if cmd:
                main.terminal_emulator_output.append(f"[API] {cmd}")
            if out:
                terminal_tab._append_stream(main, out)
            code = event.get("terminal_exit_code")
            if code is not None:
                main.terminal_emulator_output.append(f"[API done] exit_code={code}\n")
            chat_input = getattr(main, "chat_input", None)
            if chat_input is None or not chat_input.hasFocus():
                if hasattr(main, "tabs") and hasattr(main, "terminal_tab_index"):
                    main.tabs.setCurrentIndex(main.terminal_tab_index)
    err = str(event.get("error") or "").strip()
    if err:
        _append_transcript(main,
            _format_chat_line(main, "assistant", f"[API error] {err}", is_error=True)
        )
        _scroll_transcript_to_bottom(main)
    elif event.get("ok") is False:
        if hasattr(main, "status_label"):
            main.status_label.setText(f"API failed: {title[:80]}")
    elif hasattr(main, "status_label") and not getattr(main, "_chat_worker", None):
        main.status_label.setText(f"API done: {title[:80]}")


def refresh_chat_mention_candidates(main: "MainWindow") -> None:
    """Reload @-mention catalog from project self_map (Cursor-like autocomplete)."""
    if not hasattr(main, "chat_input") or not hasattr(main.chat_input, "refresh_mentions_from_root"):
        return
    root = ""
    try:
        root = str(main._settings.get_project_root() or "").strip()
    except Exception:
        root = ""
    if not root and hasattr(main, "root_edit"):
        root = (main.root_edit.text() or "").strip()
    main.chat_input.refresh_mentions_from_root(root or None)
    if hasattr(main.chat_input, "set_project_root"):
        main.chat_input.set_project_root(root or None)


def current_chat_provider(main: MainWindow) -> str:
    combo = getattr(main, "chat_provider_combo", None)
    if combo is None:
        return "auto"
    data = combo.currentData()
    if isinstance(data, str) and data.strip():
        return data.strip()
    text = (combo.currentText() or "").strip().lower()
    if text in {"auto", "openai", "ollama", "codex", "cursor"}:
        return text
    return "auto"


def set_chat_provider(main: MainWindow, provider: str) -> None:
    combo = getattr(main, "chat_provider_combo", None)
    if combo is None:
        return
    wanted = (provider or "auto").strip()
    idx = combo.findData(wanted)
    if idx < 0:
        idx = combo.findText(wanted)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


def _chat_source_label(provider: str) -> str:
    return {
        "auto": "LLM: авто",
        "openai": "LLM: облако",
        "codex": "LLM: Codex",
        "ollama": "LLM: Ollama",
        "cursor": "LLM: Cursor",
    }.get((provider or "auto").strip().lower(), "LLM: —")


def _chat_source_tooltip(main: MainWindow, provider: str) -> str:
    base = "Активный источник ответа (Models → Источник)"
    key = (provider or "auto").strip().lower()
    if key == "cursor":
        combo = getattr(main, "chat_cursor_model_combo", None)
        model = str(combo.currentText() if combo is not None else "").strip()
        router_combo = getattr(main, "chat_cursor_router_combo", None)
        router = str(router_combo.currentText() if router_combo is not None else "").strip()
        lines = [base]
        if model:
            lines.append(f"Модель: {model}")
        if router and router_combo is not None and router_combo.isEnabled():
            lines.append(f"Router: {router}")
        return "\n".join(lines)
    if key in {"openai", "codex"}:
        field = getattr(main, "chat_openai_model", None)
        model = field.text().strip() if field is not None else ""
        return f"{base}\nМодель: {model}" if model else base
    if key == "ollama":
        combo = getattr(main, "chat_ollama_model", None)
        model = str(combo.currentText() if combo is not None else "").strip()
        return f"{base}\nМодель: {model}" if model else base
    return base


def _sync_chat_llm_badge(main: MainWindow) -> None:
    badge = getattr(main, "chat_llm_source_label", None)
    if badge is None:
        return
    provider = current_chat_provider(main)
    badge.setText(_chat_source_label(provider))
    badge.setToolTip(_chat_source_tooltip(main, provider))


def sync_chat_provider_panels(main: MainWindow) -> None:
    """Show only the settings that belong to the selected chat source."""
    provider = current_chat_provider(main)
    cloud = getattr(main, "chat_cloud_box", None)
    ollama = getattr(main, "chat_ollama_box", None)
    cursor = getattr(main, "chat_cursor_box", None)
    if cloud is not None:
        cloud.setVisible(provider in {"auto", "openai", "codex"})
    if ollama is not None:
        ollama.setVisible(provider in {"auto", "ollama"})
    if cursor is not None:
        cursor.setVisible(provider == "cursor")
    hint = getattr(main, "chat_provider_hint", None)
    if hint is not None:
        hint.setText(
            {
                "auto": "Сначала облако (Groq и т.п.), если ключа нет — Ollama.",
                "openai": "Только облако. Ollama и Cursor не вызываются.",
                "codex": "Только Codex / OpenAI API.",
                "ollama": "Только локальная Ollama.",
                "cursor": "Ответ через Cursor. Groq и Ollama не используются.",
            }.get(provider, "")
        )
    _sync_chat_llm_badge(main)
    sync_cursor_router_enabled(main)


def on_chat_provider_changed(main: MainWindow, *_args: object) -> None:
    sync_chat_provider_panels(main)
    save_chat_preferences(main)
    try:
        from eurika.utils.env import apply_qt_chat_routing

        apply_qt_chat_routing()
    except Exception:
        pass
    if hasattr(main, "_refresh_openai_api_status"):
        main._refresh_openai_api_status()
    refresh_cursor_api_status(main)


def _fill_cursor_model_combo(main: MainWindow, catalog: list[dict[str, str]], selected: str) -> None:
    combo = getattr(main, "chat_cursor_model_combo", None)
    if combo is None:
        return
    combo.blockSignals(True)
    combo.clear()
    seen: set[str] = set()
    for item in catalog:
        mid = str(item.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        combo.addItem(str(item.get("label") or mid), mid)
    if selected and combo.findData(selected) < 0:
        combo.addItem(selected, selected)
    idx = combo.findData(selected) if selected else -1
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)
    sync_cursor_router_enabled(main)


def _load_cursor_model_prefs(main: MainWindow, data: dict) -> None:
    if not hasattr(main, "chat_cursor_model_combo"):
        return
    from eurika.agent.cursor_judge import DEFAULT_CURSOR_MODEL, stub_model_catalog

    saved = str(data.get("chat_cursor_model") or "").strip() or DEFAULT_CURSOR_MODEL
    if saved in {"auto-smart", "auto"}:
        saved = "default"
    _fill_cursor_model_combo(main, stub_model_catalog(), saved)
    router = str(data.get("chat_cursor_router") or "").strip()
    if hasattr(main, "chat_cursor_router_combo"):
        combo = main.chat_cursor_router_combo
        combo.blockSignals(True)
        idx = combo.findData(router)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
    refresh_cursor_api_status(main)
    sync_cursor_router_enabled(main)


def sync_cursor_router_enabled(main: MainWindow) -> None:
    if not hasattr(main, "chat_cursor_router_combo") or not hasattr(main, "chat_cursor_model_combo"):
        return
    from eurika.agent.cursor_judge import is_router_model

    mid = str(main.chat_cursor_model_combo.currentData() or "")
    enabled = is_router_model(mid)
    main.chat_cursor_router_combo.setEnabled(enabled)
    form = getattr(main, "chat_cursor_form", None)
    if form is not None:
        try:
            form.setRowVisible(main.chat_cursor_router_combo, enabled)
        except Exception:
            main.chat_cursor_router_combo.setVisible(enabled)
    _sync_chat_llm_badge(main)


def refresh_cursor_api_status(main: MainWindow) -> None:
    label = getattr(main, "cursor_api_status", None)
    if label is None:
        return
    from eurika.agent.cursor_judge import cursor_key_status

    root = "."
    try:
        root = str(main._settings.get_project_root() or "").strip() or "."
    except Exception:
        root = "."
    st = cursor_key_status(root)
    if st.get("api_key_set"):
        mid = ""
        if hasattr(main, "chat_cursor_model_combo"):
            mid = str(main.chat_cursor_model_combo.currentData() or "")
        label.setText(f"Cursor API: ключ есть · {mid or '—'}")
        label.setToolTip("CURSOR_API_KEY в .env. Refresh подтягивает каталог моделей аккаунта.")
    else:
        label.setText("Cursor API: нет ключа — CURSOR_API_KEY в .env")
        label.setToolTip("Ключ не коммитится. Models → Cursor model станет живым после Refresh.")


def refresh_cursor_models(main: MainWindow) -> None:
    """Fetch Cursor model catalog; keep current selection when possible."""
    from eurika.agent.cursor_judge import list_model_catalog, stub_model_catalog

    combo = getattr(main, "chat_cursor_model_combo", None)
    if combo is None:
        return
    selected = str(combo.currentData() or "")
    root = "."
    try:
        root = str(main._settings.get_project_root() or "").strip() or "."
    except Exception:
        root = "."
    try:
        catalog = list_model_catalog(root)
        if not catalog:
            catalog = stub_model_catalog()
        _fill_cursor_model_combo(main, catalog, selected)
        refresh_cursor_api_status(main)
        save_chat_preferences(main)
    except Exception as exc:
        refresh_cursor_api_status(main)
        label = getattr(main, "cursor_api_status", None)
        if label is not None:
            label.setText(f"Cursor API: ошибка каталога ({type(exc).__name__})")
            label.setToolTip(str(exc))


def load_chat_preferences(main: MainWindow) -> None:
    data = main._settings.load()
    provider = str(data.get("chat_provider", "auto"))
    if provider not in {"auto", "openai", "ollama", "codex", "cursor"}:
        provider = "auto"
    set_chat_provider(main, provider)
    main.chat_openai_model.setText(str(data.get("chat_openai_model", "")))
    if hasattr(main, "chat_api_preset_combo"):
        from eurika.utils.llm_presets import detect_llm_api_preset, get_llm_api_preset

        saved_preset = str(data.get("chat_api_preset", "")).strip().lower()
        if saved_preset and get_llm_api_preset(saved_preset) is None:
            saved_preset = ""
        if not saved_preset:
            import os

            saved_preset = detect_llm_api_preset(os.environ.get("OPENAI_BASE_URL"))
        combo = main.chat_api_preset_combo
        combo.blockSignals(True)
        idx = combo.findData(saved_preset)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
    saved_ollama = str(data.get("chat_ollama_model", "")).strip()
    if saved_ollama:
        combo = main.chat_ollama_model
        if combo.findText(saved_ollama) < 0:
            combo.addItem(saved_ollama)
        combo.setCurrentText(saved_ollama)
    _load_cursor_model_prefs(main, data)
    timeout_val = data.get("chat_timeout_sec", 600)
    try:
        timeout = int(timeout_val)
    except (TypeError, ValueError):
        timeout = 600
    # Prompt ↑/↓ history (project-local; fallback qt_settings).
    _load_chat_prompt_history(main, data)
    _restore_chat_session(main)
    start_live_activity_follow(main)
    refresh_chat_mention_candidates(main)
    main.chat_timeout_spin.setValue(min(9999, max(0, timeout)))
    main.ollama_hsa_edit.setText(str(data.get("ollama_hsa_override_gfx", "")))
    main.ollama_rocr_edit.setText(str(data.get("ollama_rocr_visible_devices", "")))
    main.ollama_hip_edit.setText(str(data.get("ollama_hip_visible_devices", "")))
    cuda_saved = data.get("ollama_cuda")
    vulkan_saved = data.get("ollama_vulkan")
    from . import ollama_handlers

    if cuda_saved is None and vulkan_saved is None:
        # First run: on NVIDIA prefer Vulkan (CUDA package often needs newer driver than 470).
        use_vulkan = ollama_handlers.detect_nvidia_gpu()
        use_cuda = False
    else:
        use_cuda = bool(cuda_saved)
        use_vulkan = bool(vulkan_saved) and not use_cuda
    main.ollama_cuda_check.blockSignals(True)
    main.ollama_vulkan_check.blockSignals(True)
    main.ollama_cuda_check.setChecked(use_cuda)
    main.ollama_vulkan_check.setChecked(use_vulkan)
    main.ollama_cuda_check.blockSignals(False)
    main.ollama_vulkan_check.blockSignals(False)
    main.ollama_cuda_devices_edit.setText(str(data.get("ollama_cuda_visible_devices", "0")))
    vk_devices = data.get("ollama_vk_visible_devices")
    if vk_devices is None and use_vulkan and ollama_handlers.detect_nvidia_gpu():
        # Optimus: NVIDIA is often Vulkan device 1 (Intel=0).
        vk_devices = "1"
    main.ollama_vk_devices_edit.setText(str(vk_devices if vk_devices is not None else ""))
    ollama_handlers.sync_ollama_gpu_fields(main)
    main.ollama_custom_model_edit.setText(str(data.get("ollama_custom_model", "")))
    saved_available = str(data.get("ollama_available_model", "")).strip()
    main._saved_available_model = saved_available
    from . import ml_handlers

    ml_handlers.load_ml_preferences(main)
    sync_chat_provider_panels(main)


def focus_agent_mode(main: MainWindow) -> None:
    """Chat-first: stay on Chat → Агент and focus the compose box."""
    if hasattr(main, "chat_tab_index"):
        main.tabs.setCurrentIndex(main.chat_tab_index)
    if hasattr(main, "chat_inner_tabs") and hasattr(main, "chat_dialog_subtab_index"):
        main.chat_inner_tabs.setCurrentIndex(main.chat_dialog_subtab_index)
    if hasattr(main, "chat_input"):
        main.chat_input.setFocus()


def focus_market_mode(main: MainWindow) -> None:
    """Chat-first: open Chat → Market as a mode, not a separate app."""
    if hasattr(main, "chat_tab_index"):
        main.tabs.setCurrentIndex(main.chat_tab_index)
    if hasattr(main, "chat_inner_tabs") and hasattr(main, "chat_market_subtab_index"):
        main.chat_inner_tabs.setCurrentIndex(main.chat_market_subtab_index)


def focus_learn_mode(main: MainWindow) -> None:
    """Chat-first: Learn lives under Models → ML."""
    if hasattr(main, "models_tab_index"):
        main.tabs.setCurrentIndex(main.models_tab_index)
    if hasattr(main, "models_inner_tabs") and hasattr(main, "models_ml_subtab_index"):
        main.models_inner_tabs.setCurrentIndex(main.models_ml_subtab_index)


def focus_terminal_mode(main: MainWindow) -> None:
    """Chat-first: jump from Agent context panel to Terminal."""
    if hasattr(main, "terminal_tab_index"):
        main.tabs.setCurrentIndex(main.terminal_tab_index)
        if hasattr(main, "terminal_emulator_input"):
            main.terminal_emulator_input.setFocus()


def focus_approvals_mode(main: MainWindow) -> None:
    """Chat-first: jump from Agent context panel to Approvals; load team-mode plan quietly."""
    if hasattr(main, "approvals_tab_index"):
        main.tabs.setCurrentIndex(main.approvals_tab_index)
    try:
        payload = main._api.get_pending_plan()
        operations = payload.get("operations") if isinstance(payload, dict) else None
        if isinstance(operations, list) and operations and not payload.get("error"):
            from . import approve_handlers

            approve_handlers.load_pending_plan(main)
    except Exception:
        pass


def _pending_preview_fingerprint(
    pending_plan: dict[str, Any] | None,
    pending_git: dict[str, Any] | None,
) -> str:
    """Stable id for the current HITL pending item (plan or git commit)."""
    if isinstance(pending_plan, dict) and pending_plan:
        token = str(pending_plan.get("token") or "").strip()
        if token:
            return f"plan:{token}"
        intent = str(pending_plan.get("intent") or "").strip()
        target = str(pending_plan.get("target") or "").strip()
        return f"plan:{intent}:{target}"
    if isinstance(pending_git, dict) and pending_git.get("message"):
        token = str(pending_git.get("token") or "").strip()
        if token:
            return f"git:{token}"
        return f"git:{str(pending_git.get('message') or '')[:64]}"
    return ""


def _sync_pending_diff_gate(main: MainWindow, fingerprint: str) -> None:
    """Reset Diff-seen flag when pending fingerprint changes."""
    prev = str(getattr(main, "_pending_diff_gate_fp", "") or "")
    if fingerprint != prev:
        main._pending_diff_gate_fp = fingerprint
        main._pending_diff_seen_fp = ""
    if not fingerprint:
        main._pending_diff_gate_fp = ""
        main._pending_diff_seen_fp = ""


def _mark_pending_diff_seen(main: MainWindow, fingerprint: str) -> None:
    if fingerprint:
        main._pending_diff_seen_fp = fingerprint


def _pending_diff_was_seen(main: MainWindow, fingerprint: str) -> bool:
    return bool(fingerprint) and str(getattr(main, "_pending_diff_seen_fp", "") or "") == fingerprint


def _apply_allowed_for_pending(
    main: MainWindow,
    *,
    has_effective_pending: bool,
    previewable: bool,
    fingerprint: str,
) -> bool:
    """Apply only after Diff preview for this pending (fallback without preview stays allowed)."""
    if not has_effective_pending:
        return False
    if not previewable:
        return True
    return _pending_diff_was_seen(main, fingerprint)


def refresh_chat_goal_view(main: MainWindow) -> None:
    from eurika.api.chat_context import format_agent_context_panel
    from eurika.api.task_executor import is_pending_plan_valid

    state = main._api.get_chat_dialog_state()
    state_dict: dict[str, Any] = state if isinstance(state, dict) else {}
    raw_pending_plan = state_dict.get("pending_plan")
    pending_plan: dict[str, Any] = (
        raw_pending_plan if isinstance(raw_pending_plan, dict) else {}
    )
    plan_valid = bool(pending_plan) and is_pending_plan_valid(pending_plan)
    plan_stale = bool(pending_plan) and not plan_valid
    if plan_valid:
        main._pending_plan_token = str(pending_plan.get("token") or "")
    main.chat_goal_view.setPlainText(
        format_agent_context_panel(
            state_dict, plan_valid=plan_valid, plan_stale=plan_stale
        )
    )
    raw_pending_git = state_dict.get("pending_git_commit")
    pending_git = raw_pending_git if isinstance(raw_pending_git, dict) else None
    has_pending_plan = plan_valid
    has_pending_git = isinstance(pending_git, dict) and bool(pending_git.get("message"))
    has_effective_pending = has_pending_plan or has_pending_git or main._pending_plan_fallback_active
    can_preview = bool(pending_plan) or has_pending_git
    gate_plan = pending_plan if bool(pending_plan) else None
    gate_git = pending_git if has_pending_git and not bool(pending_plan) else None
    fingerprint = _pending_preview_fingerprint(gate_plan, gate_git)
    _sync_pending_diff_gate(main, fingerprint)
    if hasattr(main, "chat_diff_btn"):
        main.chat_diff_btn.setEnabled(can_preview)
    if can_preview:
        preview_pending_chat_plan(main)
    elif hasattr(main, "chat_diff_view"):
        main.chat_diff_view.clear()
    # Expired plan: Diff for view only — never unlock Apply.
    allow_apply = (not plan_stale) and _apply_allowed_for_pending(
        main,
        has_effective_pending=has_effective_pending,
        previewable=can_preview and not plan_stale,
        fingerprint=fingerprint,
    )
    main.chat_apply_btn.setEnabled(allow_apply)
    main.chat_reject_btn.setEnabled(
        has_effective_pending or plan_stale
    )
    if has_pending_plan:
        pending_intent = str(pending_plan.get("intent") or "-")
        pending_target = str(pending_plan.get("target") or "").strip()
        if pending_target:
            main.chat_pending_label.setText(
                f"Pending plan: intent={pending_intent}, target={pending_target}"
            )
        else:
            main.chat_pending_label.setText(f"Pending plan: intent={pending_intent}")
        steps = pending_plan.get("steps") or []
        if isinstance(steps, list) and steps:
            tooltip = "Plan steps:\n" + "\n".join(
                (f"- {str(step)}" for step in steps[:6])
            )
            main.chat_pending_label.setToolTip(tooltip)
            main.chat_reject_btn.setToolTip(tooltip)
        else:
            main.chat_pending_label.setToolTip("")
            main.chat_reject_btn.setToolTip("")
        if allow_apply:
            main.chat_apply_btn.setToolTip("Apply pending plan (Diff уже просмотрен)")
        else:
            main.chat_apply_btn.setToolTip("Сначала Diff — Apply откроется после preview")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setToolTip("Обновить unified diff pending-плана")
    elif plan_stale:
        pending_intent = str(pending_plan.get("intent") or "-")
        main.chat_pending_label.setText(f"Pending plan: expired ({pending_intent})")
        main.chat_pending_label.setToolTip("Plan TTL expired — Reject to clear.")
        main.chat_apply_btn.setToolTip("Cannot apply: plan expired")
        main.chat_reject_btn.setToolTip("Clear expired pending plan")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setToolTip("Обновить diff expired плана (только просмотр)")
    elif has_pending_git and isinstance(pending_git, dict):
        main._pending_plan_token = str(pending_git.get("token") or "")
        msg_preview = str(pending_git.get("message", ""))[:50]
        main.chat_pending_label.setText(f"Pending git commit: {msg_preview}...")
        main.chat_pending_label.setToolTip(f"Commit message: {pending_git.get('message', '-')}")
        if allow_apply:
            main.chat_apply_btn.setToolTip("Apply git commit (preview уже просмотрен)")
        else:
            main.chat_apply_btn.setToolTip("Сначала Diff — Apply откроется после preview")
        main.chat_reject_btn.setToolTip("Reject git commit")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setToolTip("Обновить preview pending git commit")
    elif main._pending_plan_fallback_active:
        if main._pending_plan_token:
            main.chat_pending_label.setText(
                f"Pending plan: token={main._pending_plan_token}"
            )
        else:
            main.chat_pending_label.setText("Pending plan: awaiting confirmation")
        main.chat_pending_label.setToolTip("Awaiting confirmation from chat response.")
        main.chat_apply_btn.setToolTip("Apply pending action")
        main.chat_reject_btn.setToolTip("Reject pending action")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setEnabled(False)
            main.chat_diff_btn.setToolTip("Diff недоступен до синхронизации dialog_state")
    else:
        main._pending_plan_token = ""
        main.chat_pending_label.setText("Pending plan: none")
        main.chat_pending_label.setToolTip("")
        main.chat_apply_btn.setToolTip("")
        main.chat_reject_btn.setToolTip("")
        if hasattr(main, "chat_diff_btn"):
            main.chat_diff_btn.setToolTip("Нет pending-плана для Diff")


def save_chat_preferences(main: MainWindow) -> None:
    data = main._settings.load()
    data["chat_provider"] = current_chat_provider(main)
    data["chat_openai_model"] = main.chat_openai_model.text().strip()
    if hasattr(main, "chat_api_preset_combo"):
        data["chat_api_preset"] = str(main.chat_api_preset_combo.currentData() or "")
    data["chat_ollama_model"] = main.chat_ollama_model.currentText().strip()
    if hasattr(main, "chat_cursor_model_combo"):
        data["chat_cursor_model"] = str(main.chat_cursor_model_combo.currentData() or "")
    if hasattr(main, "chat_cursor_router_combo"):
        data["chat_cursor_router"] = str(main.chat_cursor_router_combo.currentData() or "")
    data["chat_timeout_sec"] = main.chat_timeout_spin.value()
    data["ollama_hsa_override_gfx"] = main.ollama_hsa_edit.text().strip()
    data["ollama_rocr_visible_devices"] = main.ollama_rocr_edit.text().strip()
    data["ollama_hip_visible_devices"] = main.ollama_hip_edit.text().strip()
    data["ollama_cuda"] = bool(main.ollama_cuda_check.isChecked())
    data["ollama_vulkan"] = bool(main.ollama_vulkan_check.isChecked())
    data["ollama_cuda_visible_devices"] = main.ollama_cuda_devices_edit.text().strip()
    data["ollama_vk_visible_devices"] = main.ollama_vk_devices_edit.text().strip()
    data["ollama_custom_model"] = main.ollama_custom_model_edit.text().strip()
    data["ollama_available_model"] = main.ollama_available_combo.currentText().strip()
    if hasattr(main, "ml_torch_device_combo"):
        data["torch_device"] = main.ml_torch_device_combo.currentText().strip() or "cpu"
    main._settings.save(data)


def on_chat_api_preset_changed(main: MainWindow, *_args: object) -> None:
    """Fill remote model + nudge provider when user picks a cloud preset."""
    if not hasattr(main, "chat_api_preset_combo"):
        return
    from eurika.utils.llm_presets import get_llm_api_preset

    preset_id = str(main.chat_api_preset_combo.currentData() or "")
    preset = get_llm_api_preset(preset_id)
    if preset is None:
        save_chat_preferences(main)
        if hasattr(main, "_refresh_openai_api_status"):
            main._refresh_openai_api_status()
        return
    main.chat_openai_model.setText(preset.default_model)
    # Cloud preset implies remote OpenAI-compatible path.
    if current_chat_provider(main) in {"auto", "ollama"}:
        set_chat_provider(main, "openai")
        sync_chat_provider_panels(main)
    save_chat_preferences(main)
    if hasattr(main, "_refresh_openai_api_status"):
        main._refresh_openai_api_status()


def current_chat_api_preset_id(main: MainWindow) -> str:
    if not hasattr(main, "chat_api_preset_combo"):
        return ""
    return str(main.chat_api_preset_combo.currentData() or "")


def current_chat_openai_base_url(main: MainWindow) -> str:
    from eurika.utils.llm_presets import resolve_preset_base_url

    return resolve_preset_base_url(current_chat_api_preset_id(main))


def _chat_block_payloads(main: "MainWindow") -> dict[str, str]:
    store = getattr(main, "_chat_block_payloads", None)
    if not isinstance(store, dict):
        store = {}
        main._chat_block_payloads = store
    return store


def _chat_image_root(main: "MainWindow") -> Path | None:
    root = ""
    try:
        root = str(main._settings.get_project_root() or "").strip()
    except Exception:
        root = ""
    if not root and hasattr(main, "root_edit"):
        root = (main.root_edit.text() or "").strip()
    return Path(root) if root else None


def _format_chat_line(
    main: "MainWindow",
    role: str,
    text: str,
    *,
    is_error: bool = False,
) -> str:
    """Format chat line: isolated message card + light markdown (code, images)."""
    return format_chat_line_html(
        role,
        text,
        is_error=is_error,
        payloads=_chat_block_payloads(main),
        image_root=_chat_image_root(main),
    )


def _append_transcript(main: "MainWindow", html: str) -> None:
    """Insert a self-contained HTML card without leaking Qt list formatting."""
    view = getattr(main, "chat_transcript", None)
    if view is None or not html:
        return
    from PySide6.QtGui import QTextBlockFormat, QTextCursor

    cursor = view.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertHtml(html)
    cursor.insertBlock(QTextBlockFormat())
    view.setTextCursor(cursor)


def redraw_chat_transcript(main: "MainWindow") -> None:
    """Rebuild the transcript from history (theme change / layout refresh)."""
    view = getattr(main, "chat_transcript", None)
    if view is None:
        return
    main._chat_block_payloads = {}
    view.clear()
    for item in list(getattr(main, "_chat_history", []) or []):
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        if role not in {"user", "assistant"} or not content:
            continue
        _append_transcript(main, _format_chat_line(main, role, content))
    _scroll_transcript_to_bottom(main)


def _flash_chat_chip_status(main: "MainWindow", message: str) -> None:
    """Brief non-blocking status for Copy/Run (does not fight active typing)."""
    if getattr(main, "_chat_worker", None) is not None:
        main.status_label.setText(message)
        return
    label = getattr(main, "chat_typing_label", None)
    if label is None:
        main.status_label.setText(message)
        return
    label.setText(message)
    label.setVisible(True)

    def _hide() -> None:
        if getattr(main, "_chat_worker", None) is not None:
            return
        label.clear()
        label.setVisible(False)

    QTimer.singleShot(1600, _hide)


def on_chat_anchor_clicked(main: "MainWindow", url: QUrl) -> None:
    """Handle eurika-chat://copy|run/<id> chips inside the transcript."""
    parsed = parse_chat_action_url(url.toString())
    if not parsed:
        return
    action, block_id = parsed
    payloads = _chat_block_payloads(main)
    code = payloads.get(block_id)
    if code is None:
        _flash_chat_chip_status(main, "блок кода устарел — очистите чат или дождитесь нового ответа")
        return
    if action == "copy":
        QGuiApplication.clipboard().setText(code)
        _flash_chat_chip_status(main, "скопировано в буфер")
        return
    if action == "run":
        cmd = shell_command_from_block(code)
        if not cmd:
            _flash_chat_chip_status(main, "пустая команда")
            return
        if hasattr(main, "terminal_tab_index"):
            main.tabs.setCurrentIndex(main.terminal_tab_index)
        started = terminal_tab.execute_command_from_chat(main, cmd)
        if started:
            _flash_chat_chip_status(main, f"запуск в Terminal: {cmd[:80]}")
        else:
            _flash_chat_chip_status(main, "Terminal занят — дождитесь завершения")
        return


def _scroll_transcript_to_bottom(main: "MainWindow") -> None:
    """Scroll Session chat history transcript to show newest messages."""
    if hasattr(main, "chat_transcript") and main.chat_transcript:
        bar = main.chat_transcript.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())


def _show_chat_typing(main: MainWindow) -> None:
    label = getattr(main, "chat_typing_label", None)
    if label is not None:
        label.setText("Eurika печатает…")
        label.setVisible(True)


def _hide_chat_typing(main: MainWindow) -> None:
    label = getattr(main, "chat_typing_label", None)
    if label is not None:
        label.clear()
        label.setVisible(False)


def _set_chat_busy(main: MainWindow, *, busy: bool) -> None:
    main.chat_send_btn.setEnabled(not busy)
    cancel_btn = getattr(main, "chat_cancel_btn", None)
    if cancel_btn is not None:
        cancel_btn.setEnabled(busy)
    if busy:
        _show_chat_typing(main)
    else:
        _hide_chat_typing(main)


def dispatch_chat_message(main: MainWindow, message: str) -> None:
    if not message:
        return
    if main._chat_worker is not None and main._chat_worker.isRunning():
        QMessageBox.information(main, "Chat", "Chat request already in progress.")
        return
    save_chat_preferences(main)
    provider = current_chat_provider(main)
    openai_model = main.chat_openai_model.text().strip()
    ollama_model = main.chat_ollama_model.currentText().strip()
    timeout_sec = main.chat_timeout_spin.value()
    openai_base_url = current_chat_openai_base_url(main)
    cursor_model = ""
    cursor_optimize = ""
    if hasattr(main, "chat_cursor_model_combo"):
        cursor_model = str(main.chat_cursor_model_combo.currentData() or "")
    if hasattr(main, "chat_cursor_router_combo"):
        cursor_optimize = str(main.chat_cursor_router_combo.currentData() or "")
    _append_transcript(main, _format_chat_line(main, "user", message))
    main._chat_history.append({"role": "user", "content": message})
    _remember_live_chat(main, "user", message)
    main.chat_input.clear()
    main._chat_cancelled = False
    _set_chat_busy(main, busy=True)
    main.status_label.setText("State: chat-running")
    bridge = getattr(main, "_host_privilege_bridge", None)
    if bridge is None:
        bridge = HostPrivilegeBridge(main)
        main._host_privilege_bridge = bridge
    worker = ChatWorker(
        api=main._api,
        message=message,
        # The current message is already passed separately to chat_send.
        history=list(main._chat_history[:-1]),
        provider=provider,
        openai_model=openai_model,
        ollama_model=ollama_model,
        timeout_sec=timeout_sec,
        openai_base_url=openai_base_url,
        cursor_model=cursor_model,
        cursor_optimize=cursor_optimize,
        run_command_with_result=lambda cmd: _run_command_subprocess(cmd, str(main._api._root())),
        privilege_prompt=privilege_prompt_from_bridge(bridge),
    )
    main._chat_worker = worker
    worker.finished_payload.connect(lambda p: on_chat_result(main, p))
    worker.failed.connect(lambda e: on_chat_error(main, e))
    worker.cancelled.connect(lambda: on_chat_cancelled(main))
    worker.finished.connect(lambda: on_chat_finished(main))
    worker.system_action_occurred.connect(lambda cmd: on_system_action(main, cmd))
    worker.start()


def send_chat_message(main: MainWindow) -> None:
    message = main.chat_input.toPlainText().strip()
    if message and hasattr(main.chat_input, "add_to_history"):
        main.chat_input.add_to_history(message)
        _save_chat_prompt_history(main)
    dispatch_chat_message(main, message)


def cancel_chat_request(main: MainWindow) -> None:
    worker = main._chat_worker
    if worker is None or not worker.isRunning():
        return
    main._chat_cancelled = True
    worker.cancel()
    label = getattr(main, "chat_typing_label", None)
    if label is not None:
        label.setText("Отмена…")
        label.setVisible(True)
    main.chat_cancel_btn.setEnabled(False)


def apply_pending_chat_plan(main: MainWindow) -> None:
    state = main._api.get_chat_dialog_state()
    state_dict: dict[str, Any] = state if isinstance(state, dict) else {}
    raw_plan = state_dict.get("pending_plan")
    pending_plan = raw_plan if isinstance(raw_plan, dict) else {}
    raw_git = state_dict.get("pending_git_commit")
    pending_git = raw_git if isinstance(raw_git, dict) else None
    has_git = isinstance(pending_git, dict) and bool(pending_git.get("message"))
    previewable = bool(pending_plan) or has_git
    gate_git = pending_git if has_git and not bool(pending_plan) else None
    fingerprint = _pending_preview_fingerprint(
        pending_plan if pending_plan else None, gate_git
    )
    if previewable and not _pending_diff_was_seen(main, fingerprint):
        preview_pending_chat_plan(main)
        if not _pending_diff_was_seen(main, fingerprint):
            QMessageBox.information(
                main,
                "Chat",
                "Сначала посмотри Diff в панели Контекст, затем Apply.",
            )
            return
    token = main._pending_plan_token.strip()
    msg = f"применяй token:{token}" if token else "применяй"
    main._pending_plan_fallback_active = False
    dispatch_chat_message(main, msg)


def reject_pending_chat_plan(main: MainWindow) -> None:
    main._pending_plan_fallback_active = False
    main._pending_diff_seen_fp = ""
    main._pending_diff_gate_fp = ""
    dispatch_chat_message(main, "отклонить")


def preview_pending_chat_plan(main: MainWindow) -> None:
    """Show unified diff / summary for chat pending_plan in the Agent context panel."""
    if not hasattr(main, "chat_diff_view"):
        return
    state = main._api.get_chat_dialog_state()
    pending_plan = state.get("pending_plan") if isinstance(state, dict) else None
    pending_git = state.get("pending_git_commit") if isinstance(state, dict) else None
    has_plan = isinstance(pending_plan, dict) and bool(pending_plan)
    has_git = isinstance(pending_git, dict) and bool(pending_git.get("message"))
    gate_git = pending_git if has_git and not has_plan else None
    fingerprint = _pending_preview_fingerprint(
        pending_plan if has_plan else None, gate_git
    )
    if isinstance(pending_git, dict) and pending_git.get("message") and not has_plan:
        msg = str(pending_git.get("message") or "")
        token = str(pending_git.get("token") or "")
        main.chat_diff_view.setPlainText(
            f"Pending git commit\ntoken={token or '-'}\n\n{msg}"
        )
        _mark_pending_diff_seen(main, fingerprint)
        if fingerprint and (
            main._pending_plan_fallback_active
            or has_git
            or bool(getattr(main, "_pending_plan_token", ""))
        ):
            main.chat_apply_btn.setEnabled(True)
            main.chat_apply_btn.setToolTip("Apply git commit (preview уже просмотрен)")
        return
    try:
        result = main._api.preview_chat_pending_plan(
            pending_plan if isinstance(pending_plan, dict) else None
        )
    except Exception as exc:
        main.chat_diff_view.setPlainText(f"Preview error: {exc}")
        _mark_pending_diff_seen(main, fingerprint)
        return
    if not isinstance(result, dict):
        main.chat_diff_view.setPlainText("Preview error: empty result")
        _mark_pending_diff_seen(main, fingerprint)
        return
    header_bits = [
        f"intent={result.get('intent') or '-'}",
        f"target={result.get('target') or '-'}",
    ]
    if result.get("expired"):
        header_bits.append("expired=yes")
    if result.get("token"):
        header_bits.append(f"token={result.get('token')}")
    body = str(result.get("unified_diff") or result.get("summary") or "").strip()
    err = result.get("error")
    parts = [" | ".join(header_bits)]
    if err:
        parts.append(f"error: {err}")
    if body:
        parts.append("")
        parts.append(body)
    elif not err:
        parts.append("(no diff)")
    main.chat_diff_view.setPlainText("\n".join(parts))
    _mark_pending_diff_seen(main, fingerprint)
    from eurika.api.task_executor import is_pending_plan_valid

    plan_ok = has_plan and is_pending_plan_valid(pending_plan)  # type: ignore[arg-type]
    if plan_ok or has_git:
        main.chat_apply_btn.setEnabled(True)
        main.chat_apply_btn.setToolTip("Apply pending (Diff уже просмотрен)")


def _run_command_subprocess(cmd: str, project_root: str) -> tuple[str, int]:
    """Run command in worker thread (avoids blocking GUI). Returns (output, exit_code)."""
    import subprocess

    from ..main_window_helpers import strip_ansi

    try:
        r = subprocess.run(
            ["bash", "-c", cmd],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=None,
        )
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        return (strip_ansi(out), r.returncode)
    except subprocess.TimeoutExpired:
        return ("timeout", -1)
    except Exception as e:
        return (str(e), -1)


def on_system_action(main: MainWindow, cmd: str) -> None:
    """Emit Chat action to Terminal tab.

    Shell lines (``$ …``) are logged only — handlers execute via
    ``run_command_with_result`` and mirror output through ``on_chat_result``
    to avoid double-run. Comment / note emits (``# …``) stay log-only.
    """
    if hasattr(main, "terminal_emulator_output") and main.terminal_emulator_output:
        main.terminal_emulator_output.append(f"[Chat] {cmd}")
        if hasattr(main, "terminal_tab_index"):
            main.tabs.setCurrentIndex(main.terminal_tab_index)


def on_chat_result(main: MainWindow, payload: dict[str, Any]) -> None:
    if getattr(main, "_chat_cancelled", False):
        return
    if "terminal_output" in payload and hasattr(main, "terminal_emulator_output"):
        cmd = payload.get("terminal_cmd", "")
        out = payload.get("terminal_output", "")
        code = payload.get("terminal_exit_code", -1)
        if hasattr(main, "terminal_tab_index"):
            main.tabs.setCurrentIndex(main.terminal_tab_index)
        if cmd:
            main.terminal_emulator_output.append(f"[Chat] {cmd}")
        if out:
            terminal_tab._append_stream(main, out)
        main.terminal_emulator_output.append(f"[done] exit_code={code}\n")
    text = str(payload.get("text", "")).strip()
    err = payload.get("error")
    # Prefer structured chat text over dumping raw tool output as [error].
    if err and not text:
        _append_transcript(main, _format_chat_line(main, "assistant", f"[error]: {err}", is_error=True))
        return
    if err and text:
        # Keep a short note; do not replace the expert reply with a raw dump.
        err_s = str(err).strip()
        if len(err_s) > 280:
            err_s = err_s[:240] + "…"
        _append_transcript(main,
            _format_chat_line(main, "assistant", f"[note]: {err_s}", is_error=True)
        )
    if not text:
        _append_transcript(main, _format_chat_line(main, "assistant", "(empty response)"))
        refresh_chat_goal_view(main)
        return
    _append_transcript(main, _format_chat_line(main, "assistant", text))
    main._chat_history.append({"role": "assistant", "content": text})
    _remember_live_chat(main, "assistant", text)
    main.chat_feedback_helpful_btn.setEnabled(True)
    main.chat_feedback_not_btn.setEnabled(True)
    refresh_chat_goal_view(main)
    activate_pending_controls_from_response(main, text)
    QTimer.singleShot(100, lambda: refresh_chat_goal_view(main))


def on_chat_error(main: MainWindow, error: str) -> None:
    if getattr(main, "_chat_cancelled", False):
        return
    _append_transcript(main, _format_chat_line(main, "assistant", f"[exception]: {error}", is_error=True))
    refresh_chat_goal_view(main)


def activate_pending_controls_from_response(main: MainWindow, text: str) -> None:
    raw = str(text or "")
    if not response_requests_confirmation(raw):
        main._pending_plan_fallback_active = False
        return
    token = extract_pending_token_from_text(raw)
    if not token:
        main._pending_plan_fallback_active = False
        return
    main._pending_plan_token = token
    main._pending_plan_fallback_active = True
    main.chat_reject_btn.setEnabled(True)
    main.chat_pending_label.setText(f"Pending plan: token={token}")
    # Re-run gate: auto-Diff may already unlock Apply for this token.
    refresh_chat_goal_view(main)
    _append_transcript(main,
        _format_chat_line(
            main,
            "assistant",
            "Доступны действия: [Reject] сразу; [Apply] после Diff в панели Контекст.",
        )
    )


def extract_pending_token_from_text(text: str) -> str:
    m = re.search(r"token:([a-fA-F0-9]{8,32})", str(text or ""))
    if not m:
        return ""
    return str(m.group(1))


def response_requests_confirmation(text: str) -> bool:
    lowered = str(text or "").lower()
    return "применяй token:" in lowered


def on_chat_cancelled(main: MainWindow) -> None:
    main._chat_cancelled = True


def on_chat_finished(main: MainWindow) -> None:
    cancelled = getattr(main, "_chat_cancelled", False)
    main._chat_cancelled = False
    _set_chat_busy(main, busy=False)
    main.status_label.setText("State: idle")
    if main._chat_worker is not None:
        main._chat_worker.deleteLater()
        main._chat_worker = None
    if cancelled:
        _append_transcript(main,
            _format_chat_line(
                main,
                "assistant",
                "[отменено] Запрос прерван. Ollama может ещё завершить процесс в фоне.",
            )
        )
        _scroll_transcript_to_bottom(main)
        return


def clear_chat_session(main: MainWindow) -> None:
    try:
        from eurika.api.chat import clear_chat_history

        clear_chat_history(main._api._root())
    except Exception:
        pass
    main._chat_history.clear()
    main.chat_transcript.clear()
    main._chat_block_payloads = {}
    main._live_chat_seen = set()
    try:
        _reset_live_follow_offsets(main, main._api._root())
    except Exception:
        pass
    main.chat_feedback_helpful_btn.setEnabled(False)
    main.chat_feedback_not_btn.setEnabled(False)
    refresh_chat_goal_view(main)


def submit_chat_feedback(main: MainWindow, *, helpful: bool) -> None:
    """Save feedback for last user+assistant exchange (ROADMAP 3.6.8 Phase 3)."""
    history = getattr(main, "_chat_history", []) or []
    if len(history) < 2:
        return
    user_msg = ""
    assistant_msg = ""
    for i in range(len(history) - 1, -1, -1):
        role = (history[i].get("role") or "").strip()
        content = (history[i].get("content") or "").strip()
        if role == "assistant" and not assistant_msg:
            assistant_msg = content
        elif role == "user" and not user_msg:
            user_msg = content
        if user_msg and assistant_msg:
            break
    if not user_msg or not assistant_msg:
        return
    clarification: str | None = None
    if not helpful:
        text, ok = QInputDialog.getText(
            main,
            "Уточнение",
            "Что имели в виду? (необязательно):",
            text="",
        )
        if ok and text:
            clarification = text.strip()
    main._api.save_chat_feedback(
        user_message=user_msg,
        assistant_message=assistant_msg,
        helpful=helpful,
        clarification=clarification,
    )
    main.chat_feedback_helpful_btn.setEnabled(False)
    main.chat_feedback_not_btn.setEnabled(False)
