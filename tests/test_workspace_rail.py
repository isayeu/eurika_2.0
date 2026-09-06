from pathlib import Path
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qt_app.ui.workspace_rail import workspace_display_name


def test_workspace_display_name_uses_folder() -> None:
    assert workspace_display_name("/mnt/storage/project/eurika_2.0.Qt") == "eurika_2.0.Qt"
    assert workspace_display_name("") == "(workspace)"


def test_main_window_builds_workspace_rail() -> None:
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from qt_app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    first = window.workspace_tree.topLevelItem(0)
    assert first is not None
    assert first.text(0) == "Новый чат"
    assert window.workspace_toggle_btn is not None
    current = window.workspace_tree.currentItem()
    if str(window.root_edit.text() or "").strip():
        from PySide6.QtCore import Qt as _Qt

        assert current is not None
        assert current.parent() is not None
        assert str(current.data(0, int(_Qt.ItemDataRole.UserRole)) or "") == "chat"
    window.close()
    app.processEvents()


def test_workspace_rail_toggle_hides_panel() -> None:
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from qt_app.ui.main_window import MainWindow
    from qt_app.ui.workspace_rail import apply_workspace_rail_collapsed, toggle_workspace_rail

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    apply_workspace_rail_collapsed(window, False)
    assert window.workspace_rail.isHidden() is False
    toggle_workspace_rail(window)
    assert window.workspace_rail.isHidden() is True
    assert window.workspace_toggle_btn.text() == "›"
    toggle_workspace_rail(window)
    assert window.workspace_rail.isHidden() is False
    assert window.workspace_toggle_btn.text() == "‹"
    window.close()
    app.processEvents()


def test_chat_sessions_add_rename_remove(tmp_path: Path) -> None:
    from eurika.api.chat_sessions import (
        active_chat_id,
        add_chat,
        list_chats,
        remove_chat,
        rename_chat,
        set_active_chat,
    )

    root = tmp_path / "proj"
    root.mkdir()
    first = list_chats(root)
    assert len(first) == 1
    assert first[0]["id"] == "default"
    created = add_chat(root, "второй")
    assert created["title"] == "второй"
    assert active_chat_id(root) == created["id"]
    assert len(list_chats(root)) == 2
    renamed = rename_chat(root, created["id"], "переименован")
    assert renamed is not None
    assert renamed["title"] == "переименован"
    set_active_chat(root, "default")
    assert active_chat_id(root) == "default"
    assert remove_chat(root, created["id"]) is True
    assert len(list_chats(root)) == 1
    assert remove_chat(root, "default") is False


def test_add_chat_in_workspace_switches_root(tmp_path: Path, monkeypatch) -> None:
    from eurika.api.chat_sessions import list_chats
    from qt_app.ui import workspace_rail

    root = tmp_path / "ws"
    root.mkdir()
    set_calls: list[str] = []
    reload_calls: list[str] = []

    class _Edit:
        def __init__(self) -> None:
            self._text = ""

        def text(self) -> str:
            return self._text

    class _Tabs:
        def __init__(self) -> None:
            self.index = -1

        def setCurrentIndex(self, index: int) -> None:
            self.index = index

    main = type("M", (), {})()
    main.root_edit = _Edit()
    main.tabs = _Tabs()
    main.chat_tab_index = 0
    main._set_project_root = lambda path: (
        set_calls.append(path),
        setattr(main.root_edit, "_text", path),
    )
    monkeypatch.setattr(
        "qt_app.ui.handlers.chat_handlers.reload_chat_session",
        lambda _main: reload_calls.append("reload"),
    )
    monkeypatch.setattr(workspace_rail, "refresh_workspace_rail", lambda _main: None)
    workspace_rail.add_chat_in_workspace(main, str(root))
    assert set_calls and Path(set_calls[0]).resolve() == root.resolve()
    assert reload_calls == ["reload"]
    assert main.tabs.index == 0
    assert len(list_chats(root)) == 2


def test_remove_workspace_from_rail_switches_root(tmp_path: Path, monkeypatch) -> None:
    from qt_app.services.settings_service import SettingsService
    from qt_app.ui import workspace_rail

    a = tmp_path / "ws_a"
    b = tmp_path / "ws_b"
    a.mkdir()
    b.mkdir()
    settings = SettingsService(settings_path=tmp_path / "qt_settings.json")
    settings.remember_workspace_root(str(a))
    settings.remember_workspace_root(str(b))

    set_calls: list[str] = []

    class _Edit:
        def __init__(self) -> None:
            self._text = str(b.resolve())

        def text(self) -> str:
            return self._text

        def setText(self, value: str) -> None:
            self._text = value

    main = type("M", (), {})()
    main.root_edit = _Edit()
    main._settings = settings
    main._set_project_root = lambda path: (
        set_calls.append(path),
        main.root_edit.setText(path),
        settings.set_project_root(path) if path else settings.set_project_root(""),
        settings.remember_workspace_root(path) if path else None,
    )
    monkeypatch.setattr(workspace_rail, "refresh_workspace_rail", lambda _main: None)
    workspace_rail.remove_workspace_from_rail(main, str(b))
    assert set_calls
    assert Path(set_calls[0]).resolve() == a.resolve()
    assert str(a.resolve()) in [str(Path(x).resolve()) for x in settings.list_workspace_roots()]
    assert str(b.resolve()) not in [str(Path(x).resolve()) for x in settings.list_workspace_roots()]
