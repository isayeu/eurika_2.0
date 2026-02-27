"""Persist Qt shell settings outside core Eurika artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SettingsService:
    """Store user preferences in ~/.eurika/qt_settings.json by default."""

    def __init__(self, settings_path: Path | None = None) -> None:
        default_path = Path.home() / ".eurika" / "qt_settings.json"
        self._path = settings_path or default_path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, payload: dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        except OSError:
            # Settings persistence is best-effort and must not break UI workflow.
            return

    def get_project_root(self) -> str:
        data = self.load()
        root = data.get("project_root")
        return str(root) if isinstance(root, str) else ""

    def set_project_root(self, project_root: str) -> None:
        data = self.load()
        data["project_root"] = project_root
        self.save(data)

