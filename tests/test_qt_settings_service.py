from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qt_app.services.settings_service import SettingsService


def test_settings_service_roundtrip_project_root(tmp_path: Path) -> None:
    settings_path = tmp_path / "qt_settings.json"
    svc = SettingsService(settings_path=settings_path)

    assert svc.get_project_root() == ""

    svc.set_project_root("/tmp/demo")
    assert settings_path.exists()
    assert svc.get_project_root() == "/tmp/demo"


def test_settings_service_remembers_workspace_roots(tmp_path: Path) -> None:
    settings_path = tmp_path / "qt_settings.json"
    svc = SettingsService(settings_path=settings_path)
    svc.remember_workspace_root("/tmp/eurika")
    svc.remember_workspace_root("/tmp/binance")
    svc.remember_workspace_root("/tmp/eurika")
    assert svc.list_workspace_roots() == ["/tmp/eurika", "/tmp/binance"]


def test_settings_service_forgets_workspace_root(tmp_path: Path) -> None:
    settings_path = tmp_path / "qt_settings.json"
    svc = SettingsService(settings_path=settings_path)
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    svc.remember_workspace_root(str(a))
    svc.remember_workspace_root(str(b))
    assert svc.get_project_root() == str(b)
    remaining = svc.forget_workspace_root(str(b))
    assert remaining == [str(a.resolve())] or remaining == [str(a)]
    # Active root switched off the forgotten workspace.
    assert Path(svc.get_project_root()).resolve() == a.resolve()
    remaining2 = svc.forget_workspace_root(str(a))
    assert remaining2 == []
    assert svc.get_project_root() == ""


def test_settings_service_handles_invalid_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "qt_settings.json"
    settings_path.write_text("{bad json", encoding="utf-8")
    svc = SettingsService(settings_path=settings_path)

    assert svc.load() == {}

