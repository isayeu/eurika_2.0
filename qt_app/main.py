"""Entrypoint for Eurika Qt desktop shell."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Root-level modules (patch_apply, patch_engine, …) — same bootstrap as eurika_cli.
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from PySide6.QtWidgets import QApplication

from qt_app.services.settings_service import SettingsService
from qt_app.ui.main_window import MainWindow
from qt_app.ui.styles import set_theme_dark
from qt_app.ui.theme import apply_app_theme
from eurika.utils.env import apply_qt_chat_routing, load_project_dotenv


def main() -> int:
    app = QApplication(sys.argv)
    # Avoid xdg-desktop-portal QDBusError: "App info not found for ''"
    app.setOrganizationName("Eurika")
    app.setApplicationName("Eurika")
    app.setDesktopFileName("eurika")
    load_project_dotenv(".")
    apply_qt_chat_routing()
    try:
        from eurika.agent.cursor_bridge_gc import prune_orphan_cursor_bridges

        # os._exit on previous runs skipped atexit → leftover node bridges.
        prune_orphan_cursor_bridges(only_dead_callback=True)
    except Exception:
        pass
    settings = SettingsService()
    theme = settings.get_theme()
    is_dark = theme == "dark"
    set_theme_dark(is_dark)
    apply_app_theme(app, is_dark)
    win = MainWindow()
    win.show()
    code = int(app.exec())
    # ChatWorker / gateway request threads can still be blocked in urllib after the
    # window closed; a normal return waits on them (up to the 10 min HTTP timeout).
    # os._exit skips atexit — close Cursor SDK bridge explicitly first.
    try:
        from eurika.agent.cursor_bridge_gc import shutdown_cursor_sdk

        shutdown_cursor_sdk()
    except Exception:
        pass
    os._exit(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
