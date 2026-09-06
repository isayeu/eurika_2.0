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

    def list_workspace_roots(self) -> list[str]:
        data = self.load()
        raw = data.get("workspace_roots")
        if not isinstance(raw, list):
            current = self.get_project_root()
            return [current] if current else []
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            path = str(item or "").strip()
            if path and path not in seen:
                seen.add(path)
                out.append(path)
        return out[:12]

    def remember_workspace_root(self, project_root: str) -> None:
        path = str(project_root or "").strip()
        if not path:
            return
        roots = self.list_workspace_roots()
        if path not in roots:
            roots.append(path)
        data = self.load()
        data["workspace_roots"] = roots[:12]
        data["project_root"] = path
        self.save(data)

    def forget_workspace_root(self, project_root: str) -> list[str]:
        """Remove a workspace from the rail list (does not delete files on disk).

        Returns the remaining roots. If the forgotten path was the active
        ``project_root``, switches active root to the first remaining (or ``""``).
        """
        target = str(project_root or "").strip()
        if not target:
            return self.list_workspace_roots()
        try:
            target_resolved = str(Path(target).expanduser().resolve())
        except OSError:
            target_resolved = target

        def _same(a: str) -> bool:
            raw = str(a or "").strip()
            if not raw:
                return False
            if raw == target or raw == target_resolved:
                return True
            try:
                return str(Path(raw).expanduser().resolve()) == target_resolved
            except OSError:
                return False

        roots = [r for r in self.list_workspace_roots() if not _same(r)]
        data = self.load()
        data["workspace_roots"] = roots[:12]
        current = str(data.get("project_root") or "").strip()
        if current and _same(current):
            data["project_root"] = roots[0] if roots else ""
        self.save(data)
        return roots

    def get_theme(self) -> str:
        """Return 'light' or 'dark'."""
        data = self.load()
        t = data.get("theme", "light")
        return "dark" if t == "dark" else "light"

    def set_theme(self, theme: str) -> None:
        data = self.load()
        data["theme"] = "dark" if theme == "dark" else "light"
        self.save(data)

