"""Entrypoint for Eurika Qt desktop shell."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from qt_app.services.settings_service import SettingsService
from qt_app.ui.main_window import MainWindow
from qt_app.ui.styles import set_theme_dark
from qt_app.ui.theme import apply_app_theme
from eurika.utils.env import load_project_dotenv


def main() -> int:
    app = QApplication(sys.argv)
    # Avoid xdg-desktop-portal QDBusError: "App info not found for ''"
    app.setOrganizationName("Eurika")
    app.setApplicationName("Eurika")
    app.setDesktopFileName("eurika")
    load_project_dotenv(".")
    settings = SettingsService()
    theme = settings.get_theme()
    is_dark = theme == "dark"
    set_theme_dark(is_dark)
    apply_app_theme(app, is_dark)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

