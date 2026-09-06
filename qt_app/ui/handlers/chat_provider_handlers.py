"""Chat LLM provider, Cursor catalog, and preference persistence."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..main_window import MainWindow


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
    combo.blockSignals(True)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


def _chat_source_label(provider: str) -> str:
    return {
        "auto": "LLM: авто",
        "openai": "LLM: облако",
        "codex": "LLM: Codex",
        "ollama": "LLM: Ollama",
        "cursor": "LLM: Cursor",
    }.get((provider or "auto").strip().lower(), "LLM: —")


def _chat_source_tooltip(main: MainWindow, provider: str) -> str:
    """Build tooltip for the LLM source badge showing model and router details."""
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


def on_cursor_model_changed(main: MainWindow, *_args: object) -> None:
    """Persist Cursor model immediately (Models has no Save/Apply)."""
    sync_cursor_router_enabled(main)
    save_chat_preferences(main)
    try:
        from eurika.utils.env import apply_qt_chat_routing

        apply_qt_chat_routing()
    except Exception:
        pass
    refresh_cursor_api_status(main)


def on_cursor_router_changed(main: MainWindow, *_args: object) -> None:
    """Persist Router mode immediately."""
    save_chat_preferences(main)
    try:
        from eurika.utils.env import apply_qt_chat_routing

        apply_qt_chat_routing()
    except Exception:
        pass
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
