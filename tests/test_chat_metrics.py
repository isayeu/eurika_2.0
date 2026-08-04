"""Tests for chat routing metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eurika.api.chat import chat_send
from eurika.api.chat_intents_config import clear_cache
from eurika.api.chat_metrics import record_chat_metric


@pytest.fixture(autouse=True)
def _clear_intent_cache() -> None:
    clear_cache()
    yield
    clear_cache()


def test_record_chat_metric_appends_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EURIKA_CHAT_METRICS", "1")
    record_chat_metric(tmp_path, "intent_match", handler="greeting", message="привет")
    path = tmp_path / ".eurika" / "chat_metrics.jsonl"
    assert path.exists()
    line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
    data = json.loads(line)
    assert data["event"] == "intent_match"
    assert data["handler"] == "greeting"


def test_chat_send_logs_intent_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EURIKA_CHAT_METRICS", "1")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    chat_send(tmp_path, "привет")
    path = tmp_path / ".eurika" / "chat_metrics.jsonl"
    assert path.exists()
    events = [json.loads(line)["event"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert "intent_match" in events


def test_chat_send_logs_intent_miss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EURIKA_CHAT_METRICS", "1")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    def _fake_llm(prompt: str, max_tokens: int = 1024) -> tuple[str | None, str | None]:
        return ("тестовый ответ", None)

    monkeypatch.setattr("eurika.reasoning.architect.call_llm_with_prompt", _fake_llm)
    chat_send(tmp_path, "объясни зачем нужен модуль app.py")
    path = tmp_path / ".eurika" / "chat_metrics.jsonl"
    events = [json.loads(line)["event"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert "intent_miss" in events


def test_record_chat_metric_respects_disable_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EURIKA_CHAT_METRICS", "0")
    record_chat_metric(tmp_path, "intent_miss", message="test")
    assert not (tmp_path / ".eurika" / "chat_metrics.jsonl").exists()
