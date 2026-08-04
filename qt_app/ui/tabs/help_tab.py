"""Help tab: index of project documents with descriptions. ROADMAP 3.1-arch."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qt_app.ui.styles import TAB_MARGINS, get_secondary_hint

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow

# docs/ relative to project root (qt_app/../docs)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DOCS_PATH = _PROJECT_ROOT / "docs"

_DOCUMENTS = [
    ("Vision", "VISION.md", "Продукт: Cursor-shell + Learn + Market paper; окно наблюдения"),
    ("Onboarding", "ONBOARDING.md", "Onboarding ≤ 10 мин — eurika-qt / scan → doctor → fix"),
    ("UI", "UI.md", "Qt UI: вкладки Models/Chat/Market, тема, shortcuts"),
    ("Chat", "CHAT.md", "Команды вкладки Chat, интенты, LLM, веб-поиск, переменные .env"),
    ("Memory", "MEMORY.md", "EventLog, FailureLog, LearningStore, Market ML на диске"),
    ("Architecture", "Architecture.md", "L0–L6 слои, fix-cycle pipeline, dependency direction, Execution Model"),
    ("Dependency Firewall", "DEPENDENCY_FIREWALL.md", "Layer rules, ImportRule, EURIKA_STRICT_LAYER_FIREWALL"),
    ("API Boundaries", "API_BOUNDARIES.md", "Публичные фасады: from eurika.X import …"),
    ("CLI", "CLI.md", "CLI команды, рекомендуемый цикл scan→doctor→fix"),
    ("ROADMAP", "ROADMAP.md", "План задач, фазы, Execution Model"),
    ("Bounded Evolution", "BOUNDED_EVOLUTION.md", "Лимиты логов, памяти, planner"),
    ("Hardware", "HARDWARE.md", "Железо, Ollama, PyTorch"),
    ("Troubleshooting", "TROUBLESHOOTING.md", "Типовые ошибки и решения"),
]


def _open_doc(path: Path) -> None:
    if path.exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def build_help_tab(main: MainWindow) -> None:
    """Build Help tab: document index with descriptions and Open buttons."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(*TAB_MARGINS)

    header = QLabel(
        "Документация проекта Eurika. Щёлкните Open — откроется в редакторе по умолчанию."
    )
    header.setWordWrap(True)
    layout.addWidget(header)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setContentsMargins(0, 0, 0, 0)

    content = QWidget()
    grid = QGridLayout(content)
    grid.setColumnStretch(1, 1)

    for row, (title, filename, desc) in enumerate(_DOCUMENTS):
        path = _DOCS_PATH / filename
        exists = path.exists()

        name_label = QLabel(title)
        name_label.setStyleSheet("font-weight: bold;")
        grid.addWidget(name_label, row, 0)

        desc_label = QLabel(desc + (" (файл не найден)" if not exists else ""))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(get_secondary_hint())
        grid.addWidget(desc_label, row, 1)

        open_btn = QPushButton("Open")
        open_btn.setEnabled(exists)
        open_btn.setFixedWidth(60)
        if exists:
            open_btn.clicked.connect(lambda checked=False, p=path: _open_doc(p))
        open_btn.setToolTip(str(path) if exists else f"Не найден: {path}")
        grid.addWidget(open_btn, row, 2)

    scroll.setWidget(content)
    layout.addWidget(scroll, 1)
    main.tabs.addTab(tab, "Помощь")
