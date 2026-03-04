"""Application theme: light/dark palette and style."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


def apply_app_theme(app: QApplication, dark: bool) -> None:
    """Apply light or dark theme to the application."""
    if dark:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(230, 230, 230))
        palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.Text, QColor(230, 230, 230))
        palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(230, 230, 230))
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(100, 160, 220))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(60, 100, 150))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(130, 130, 130))
        app.setPalette(palette)
        if "Fusion" in QStyleFactory.keys():
            app.setStyle("Fusion")
    else:
        app.setPalette(app.style().standardPalette())
        if "Fusion" in QStyleFactory.keys():
            app.setStyle("Fusion")
