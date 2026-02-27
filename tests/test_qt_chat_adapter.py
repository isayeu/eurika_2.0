from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qt_app.adapters import eurika_api_adapter as adapter_mod
from qt_app.adapters.eurika_api_adapter import EurikaApiAdapter


def test_chat_send_uses_ollama_provider(monkeypatch) -> None:
    captured = {}

    def _fake_chat_send(_root, _message, _history):
        import os

        captured["openai_api_key"] = os.environ.get("OPENAI_API_KEY")
        captured["openai_model"] = os.environ.get("OPENAI_MODEL")
        captured["ollama_model"] = os.environ.get("OLLAMA_OPENAI_MODEL")
        return {"text": "ok", "error": None}

    monkeypatch.setattr(adapter_mod, "_chat_send", _fake_chat_send)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "should-be-removed")

    api = EurikaApiAdapter(".")
    out = api.chat_send(
        message="hello",
        history=[],
        provider="ollama",
        openai_model="",
        ollama_model="qwen2.5-coder:7b",
        timeout_sec=11,
    )

    assert out["error"] is None
    assert captured["openai_api_key"] is None
    assert captured["openai_model"] is None
    assert captured["ollama_model"] == "qwen2.5-coder:7b"


def test_list_ollama_models_parses_tags_payload(monkeypatch) -> None:
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"models":[{"name":"qwen2.5-coder:7b"},{"name":"llama3.1:8b"}]}'

    monkeypatch.setattr(adapter_mod, "urlopen", lambda *_args, **_kwargs: _Resp())
    api = EurikaApiAdapter(".")
    models = api.list_ollama_models()
    assert models == ["qwen2.5-coder:7b", "llama3.1:8b"]


def test_is_ollama_healthy_false_when_unavailable(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(adapter_mod, "urlopen", _boom)
    api = EurikaApiAdapter(".")
    assert api.is_ollama_healthy() is False

