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


def test_settings_service_handles_invalid_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "qt_settings.json"
    settings_path.write_text("{bad json", encoding="utf-8")
    svc = SettingsService(settings_path=settings_path)

    assert svc.load() == {}

