"""Tests for CLI environment loading and OpenAI/Ollama key precedence."""

import os
from pathlib import Path

import pytest


def test_load_environment_overrides_llm_keys_from_dotenv(tmp_path: Path, monkeypatch) -> None:
    """Project .env should override exported OPENAI/OLLAMA routing keys. Requires python-dotenv."""
    try:
        import dotenv
    except ImportError:
        pytest.skip("python-dotenv not installed (pip install python-dotenv or eurika[env])")

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=project-key",
                "OPENAI_MODEL=project-model",
                "OPENAI_BASE_URL=http://127.0.0.1:11434/v1",
                "OLLAMA_OPENAI_MODEL=project-ollama-model",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "shell-key")
    monkeypatch.setenv("OPENAI_MODEL", "shell-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OLLAMA_OPENAI_MODEL", "shell-ollama-model")

    from eurika_cli import _load_environment

    _load_environment(env_file)

    assert os.environ["OPENAI_API_KEY"] == "project-key"
    assert os.environ["OPENAI_MODEL"] == "project-model"
    assert os.environ["OPENAI_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert os.environ["OLLAMA_OPENAI_MODEL"] == "project-ollama-model"
