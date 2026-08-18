"""Scroll wrappers that do not force the main window taller than the screen.

VerticalScrollArea keeps QTabWidget page height compact instead of expanding to content.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QWidget


class VerticalScrollArea(QScrollArea):
    """Vertical scroll whose sizeHint stays compact so QTabWidget can shrink."""

    def __init__(
        self,
        content: QWidget | None = None,
        *,
        hint_width: int = 640,
        hint_height: int = 360,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._hint_width = hint_width
        self._hint_height = hint_height
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if content is not None:
            self.setWidget(content)

    def sizeHint(self) -> QSize:
        return QSize(self._hint_width, self._hint_height)

    def minimumSizeHint(self) -> QSize:
        return QSize(240, 160)
