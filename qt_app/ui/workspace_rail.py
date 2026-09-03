"""Collapsible left rail: Cursor-like workspaces (folder) and chats (threads)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from qt_app.ui.main_window import MainWindow

_ROLE_KIND = int(Qt.ItemDataRole.UserRole)
_ROLE_PATH = int(Qt.ItemDataRole.UserRole) + 1
_ROLE_CHAT = int(Qt.ItemDataRole.UserRole) + 2


def workspace_display_name(path: str) -> str:
    name = Path(path.rstrip("/")).name.strip()
    return name or path or "(workspace)"


def build_workspace_rail(main: MainWindow) -> tuple[QWidget, QPushButton]:
    toggle = QPushButton("‹")
    toggle.setObjectName("workspaceRailToggle")
    toggle.setFixedWidth(28)
    toggle.setToolTip("Свернуть / развернуть панель воркспейсов")
    toggle.clicked.connect(lambda: toggle_workspace_rail(main))

    rail = QFrame()
    rail.setObjectName("workspaceRail")
    rail.setMinimumWidth(160)
    rail.setMaximumWidth(280)
    layout = QVBoxLayout(rail)
    layout.setContentsMargins(4, 0, 8, 0)
    layout.setSpacing(4)
    title = QLabel("Воркспейсы")
    title.setObjectName("workspaceRailTitle")
    layout.addWidget(title)
    tree = QTreeWidget()
    tree.setObjectName("workspaceRailTree")
    tree.setColumnCount(2)
    tree.setHeaderHidden(True)
    tree.setRootIsDecorated(True)
    header = tree.header()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    tree.setColumnWidth(1, 28)
    tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    tree.customContextMenuRequested.connect(
        lambda pos: _on_chat_context_menu(main, pos)
    )
    tree.itemClicked.connect(lambda item, col: _on_workspace_item(main, item, col))
    layout.addWidget(tree, 1)
    main.workspace_rail = rail
    main.workspace_toggle_btn = toggle
    main.workspace_tree = tree
    collapsed = False
    if hasattr(main, "_settings"):
        collapsed = bool(main._settings.load().get("workspace_rail_collapsed"))
    apply_workspace_rail_collapsed(main, collapsed)
    refresh_workspace_rail(main)
    return rail, toggle


def apply_workspace_rail_collapsed(main: MainWindow, collapsed: bool) -> None:
    rail = getattr(main, "workspace_rail", None)
    toggle = getattr(main, "workspace_toggle_btn", None)
    if rail is not None:
        rail.setVisible(not collapsed)
    if toggle is not None:
        toggle.setText("›" if collapsed else "‹")
    splitter = getattr(main, "workspace_splitter", None)
    if splitter is None:
        return
    sizes = splitter.sizes()
    rest = sizes[1] if len(sizes) > 1 else 900
    splitter.setSizes([36 if collapsed else 220, max(rest, 400)])


def toggle_workspace_rail(main: MainWindow) -> None:
    rail = getattr(main, "workspace_rail", None)
    collapsed = bool(rail is not None and not rail.isHidden())
    apply_workspace_rail_collapsed(main, collapsed)
    if hasattr(main, "_settings"):
        data = main._settings.load()
        data["workspace_rail_collapsed"] = collapsed
        main._settings.save(data)


def refresh_workspace_rail(main: MainWindow) -> None:
    tree = getattr(main, "workspace_tree", None)
    if tree is None:
        return
    tree.blockSignals(True)
    tree.clear()
    new_chat = QTreeWidgetItem(["Новый чат", ""])
    new_chat.setData(0, _ROLE_KIND, "new_chat")
    new_chat.setToolTip(0, "Выбрать или создать каталог воркспейса и открыть в нём новый чат")
    tree.addTopLevelItem(new_chat)

    current = ""
    if hasattr(main, "root_edit"):
        current = str(main.root_edit.text() or "").strip()
    current_resolved = str(Path(current).expanduser().resolve()) if current else ""
    roots: list[str] = []
    if hasattr(main, "_settings"):
        roots = list(main._settings.list_workspace_roots())
    if current_resolved and current_resolved not in roots:
        roots.append(current_resolved)

    from eurika.api.chat_sessions import active_chat_id, list_chats

    seen: set[str] = set()
    select: QTreeWidgetItem | None = None
    for raw in roots:
        path = str(Path(raw).expanduser().resolve()) if raw else ""
        if not path or path in seen:
            continue
        seen.add(path)
        item = QTreeWidgetItem([workspace_display_name(path), ""])
        item.setData(0, _ROLE_KIND, "workspace")
        item.setData(0, _ROLE_PATH, path)
        item.setToolTip(0, path)
        tree.addTopLevelItem(item)
        plus = QPushButton("+")
        plus.setFlat(True)
        plus.setFixedWidth(24)
        plus.setToolTip("Новый чат в этом воркспейсе")
        plus.clicked.connect(lambda _checked=False, p=path: add_chat_in_workspace(main, p))
        tree.setItemWidget(item, 1, plus)
        chats = list_chats(Path(path))
        active = active_chat_id(Path(path)) if path == current_resolved else ""
        for chat in chats:
            child = QTreeWidgetItem([str(chat.get("title") or "чат"), ""])
            child.setData(0, _ROLE_KIND, "chat")
            child.setData(0, _ROLE_PATH, path)
            child.setData(0, _ROLE_CHAT, str(chat.get("id") or "default"))
            item.addChild(child)
            if path == current_resolved and str(chat.get("id") or "") == active:
                select = child
        if path == current_resolved:
            item.setExpanded(True)
            if select is None and item.childCount():
                select = item.child(0)
    if select is not None:
        tree.setCurrentItem(select)
    tree.blockSignals(False)


def add_chat_in_workspace(main: MainWindow, path: str) -> None:
    from eurika.api.chat_sessions import add_chat
    from qt_app.ui.handlers import chat_handlers

    resolved = str(Path(path).expanduser().resolve()) if path else ""
    if not resolved:
        return
    if hasattr(main, "_set_project_root"):
        current = str(getattr(main, "root_edit").text() or "").strip()
        if not current or str(Path(current).expanduser().resolve()) != resolved:
            main._set_project_root(resolved)
    add_chat(Path(resolved))
    chat_handlers.reload_chat_session(main)
    refresh_workspace_rail(main)
    if hasattr(main, "chat_tab_index"):
        main.tabs.setCurrentIndex(main.chat_tab_index)


def _on_workspace_item(main: MainWindow, item: QTreeWidgetItem | None, col: int = 0) -> None:
    if item is None or col != 0:
        return
    kind = str(item.data(0, _ROLE_KIND) or "")
    path = str(item.data(0, _ROLE_PATH) or "")
    chat_id = str(item.data(0, _ROLE_CHAT) or "")
    if kind == "new_chat":
        selected = pick_workspace_root_for_new_chat(main)
        if selected:
            add_chat_in_workspace(main, selected)
        elif hasattr(main, "chat_tab_index"):
            main.tabs.setCurrentIndex(main.chat_tab_index)
        return
    if kind == "workspace" and path:
        if hasattr(main, "_set_project_root"):
            main._set_project_root(path)
        return
    if kind == "chat" and path:
        from eurika.api.chat_sessions import set_active_chat
        from qt_app.ui.handlers import chat_handlers

        if hasattr(main, "_set_project_root"):
            current = str(getattr(main, "root_edit").text() or "").strip()
            if not current or str(Path(current).expanduser().resolve()) != str(
                Path(path).expanduser().resolve()
            ):
                main._set_project_root(path)
        set_active_chat(Path(path), chat_id or "default")
        chat_handlers.reload_chat_session(main)
        refresh_workspace_rail(main)
        if hasattr(main, "chat_tab_index"):
            main.tabs.setCurrentIndex(main.chat_tab_index)


def pick_workspace_root_for_new_chat(main: MainWindow) -> str:
    current = ""
    if hasattr(main, "root_edit"):
        current = str(main.root_edit.text() or "").strip()
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return current
    start = current or str(Path.home())
    selected = QFileDialog.getExistingDirectory(
        main, "Выберите или создайте каталог воркспейса", start
    )
    return str(selected or "").strip()


def _on_chat_context_menu(main: MainWindow, pos: QPoint) -> None:
    tree = getattr(main, "workspace_tree", None)
    if tree is None:
        return
    item = tree.itemAt(pos)
    if item is None or str(item.data(0, _ROLE_KIND) or "") != "chat":
        return
    path = str(item.data(0, _ROLE_PATH) or "")
    chat_id = str(item.data(0, _ROLE_CHAT) or "")
    if not path or not chat_id:
        return
    menu = QMenu(tree)
    rename_act = menu.addAction("Переименовать")
    delete_act = menu.addAction("Удалить")
    chosen = menu.exec(tree.viewport().mapToGlobal(pos))
    if chosen is None:
        return
    from eurika.api.chat_sessions import list_chats, remove_chat, rename_chat
    from qt_app.ui.handlers import chat_handlers

    root = Path(path)
    if chosen == rename_act:
        current_title = item.text(0)
        title, ok = QInputDialog.getText(
            main, "Переименовать чат", "Название:", text=current_title
        )
        if ok and rename_chat(root, chat_id, title):
            refresh_workspace_rail(main)
        return
    if chosen != delete_act:
        return
    if len(list_chats(root)) < 2:
        QMessageBox.information(main, "Чат", "Нельзя удалить единственный чат воркспейса.")
        return
    confirm = QMessageBox.question(
        main,
        "Удалить чат",
        f"Удалить «{item.text(0)}»?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if confirm != QMessageBox.StandardButton.Yes:
        return
    if remove_chat(root, chat_id):
        chat_handlers.reload_chat_session(main)
        refresh_workspace_rail(main)


def wrap_tabs_with_workspace_rail(main: MainWindow, tabs: Any, body_layout: Any) -> None:
    """Insert toggle+rail to the left of ``tabs`` inside a horizontal layout."""
    from PySide6.QtWidgets import QSplitter

    rail, toggle = build_workspace_rail(main)
    left = QWidget()
    left_layout = QHBoxLayout(left)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(0)
    left_layout.addWidget(toggle)
    left_layout.addWidget(rail)
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setObjectName("workspaceBodySplitter")
    splitter.addWidget(left)
    splitter.addWidget(tabs)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([220, 900])
    main.workspace_splitter = splitter
    collapsed = False
    if hasattr(main, "_settings"):
        collapsed = bool(main._settings.load().get("workspace_rail_collapsed"))
    apply_workspace_rail_collapsed(main, collapsed)
    body_layout.addWidget(splitter, 1)
