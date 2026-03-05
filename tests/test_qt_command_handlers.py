"""Tests for qt_app command handlers (run_release_check passes ollama_model)."""

from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qt_app.ui.handlers import command_handlers


def test_run_release_check_passes_ollama_model(tmp_path: Path, monkeypatch) -> None:
    """run_release_check passes ollama_model from _resolve_ollama_model_for_command to CommandService."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "release_check.sh").write_text("#!/bin/bash\nexit 0")

    mock_service = MagicMock()
    mock_main = MagicMock()
    mock_main.root_edit.text.return_value = str(tmp_path)
    mock_main._resolve_ollama_model_for_command.return_value = "qwen2.5-coder:7b"
    mock_main._command_service = mock_service

    monkeypatch.setattr(
        "qt_app.ui.handlers.command_handlers.QMessageBox.warning",
        lambda *args, **kwargs: None,
    )

    command_handlers.run_release_check(mock_main)

    mock_service.run_release_check.assert_called_once_with(
        project_root=str(tmp_path),
        ollama_model="qwen2.5-coder:7b",
    )
