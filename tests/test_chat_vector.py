"""Tests for eurika.api.chat_vector (CR-G2 vector memory)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _reportish_embed(text: str, *args, **kwargs):
    """Distinct axes so merged default intents don't all tie at sim=1.0."""
    t = (text or "").lower()
    if "ritual" in t or "ритуал" in t:
        return [0.0, 0.0, 1.0] + [0.0] * 61
    if (
        "покажи отчёт" in t
        or "покажи отчет" in t
        or "show report" in t
        or "report please" in t
        or ("покажи" in t and ("отчёт" in t or "отчет" in t))
    ):
        return [1.0, 0.0, 0.0] + [0.0] * 61
    return [0.0, 1.0, 0.0] + [0.0] * 61


def test_cosine_sim() -> None:
    from eurika.api.chat_vector import _cosine_sim

    assert _cosine_sim([1.0, 0, 0], [1.0, 0, 0]) >= 0.99
    assert _cosine_sim([1.0, 0, 0], [0, 1.0, 0]) < 0.6
    assert _cosine_sim([], [1.0]) == 0.0


def test_vector_intent_disabled_by_default(monkeypatch) -> None:
    from eurika.api.chat_vector import match_fuzzy_intent

    monkeypatch.delenv("EURIKA_USE_VECTOR_INTENT", raising=False)
    tmp = Path("/tmp/nonexistent_proj")
    assert match_fuzzy_intent(tmp, "покажи отчёт") is None


def test_vector_intent_no_config_returns_none(monkeypatch, tmp_path: Path) -> None:
    from eurika.api.chat_vector import match_fuzzy_intent

    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")
    (tmp_path / ".eurika" / "config").mkdir(parents=True, exist_ok=True)
    assert match_fuzzy_intent(tmp_path, "покажи отчёт") is None


def test_vector_intent_with_mock_embed(monkeypatch, tmp_path: Path) -> None:
    from eurika.api import chat_vector
    from eurika.api.chat_intents_config import clear_cache

    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")
    clear_cache()
    (tmp_path / ".eurika" / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".eurika" / "config" / "chat_intents.yaml").write_text(
        """
vector_min_similarity: 0.75
intents:
  show_report:
    patterns: ["покажи отчёт", "show report"]
    emit: null
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_vector, "_ollama_embed", _reportish_embed)
    result = chat_vector.match_fuzzy_intent(tmp_path, "покажи мне отчёт по анализу")
    assert result is not None
    assert result[0] == "show_report"
    assert result[2] >= 0.75


def test_resolve_direct_handler_fuzzy_fallback(monkeypatch, tmp_path: Path) -> None:
    from eurika.api import chat_direct, chat_vector
    from eurika.api.chat_intents_config import clear_cache

    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")
    clear_cache()
    (tmp_path / ".eurika" / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".eurika" / "config" / "chat_intents.yaml").write_text(
        """
vector_min_similarity: 0.75
intents:
  show_report:
    patterns: ["покажи отчёт", "show report"]
    emit: null
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_vector, "_ollama_embed", _reportish_embed)

    handler, _emit = chat_direct.resolve_direct_handler(tmp_path, "report please")
    assert handler == "show_report"


def test_resolve_direct_handler_skips_fuzzy_for_llm_directive(monkeypatch, tmp_path: Path) -> None:
    """«ответь одним словом …» must go to LLM — not vector→project_overview."""
    from eurika.api import chat_direct, chat_vector

    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")
    monkeypatch.setattr(
        chat_vector,
        "match_fuzzy_intent",
        lambda *_a, **_k: ("project_overview", None, 0.95),
    )
    handler, _emit = chat_direct.resolve_direct_handler(
        tmp_path, 'ответь одним словом "Жопа"'
    )
    assert handler is None
    assert chat_direct.is_llm_directive_message('ответь одним словом "Жопа"')
    assert chat_direct.is_llm_directive_message("say only the word hi")


def test_resolve_direct_handler_skips_fuzzy_for_price_asks(monkeypatch, tmp_path: Path) -> None:
    """Live price asks must reach LLM tools — not vector→wrong intent."""
    from eurika.api import chat_direct, chat_vector

    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")
    monkeypatch.setattr(
        chat_vector,
        "match_fuzzy_intent",
        lambda *_a, **_k: ("goal_status", None, 0.99),
    )
    handler, _emit = chat_direct.resolve_direct_handler(tmp_path, "цена DOT сейчас")
    assert handler is None


def test_vector_exemplars_preferred_over_patterns(monkeypatch, tmp_path: Path) -> None:
    """vector_exemplars used when present; else patterns."""
    from eurika.api import chat_vector
    from eurika.api.chat_intents_config import clear_cache

    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")
    clear_cache()
    (tmp_path / ".eurika" / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".eurika" / "config" / "chat_intents.yaml").write_text(
        """
vector_min_similarity: 0.75
intents:
  ritual:
    vector_exemplars: ["run full ritual", "прогони ритуал"]
    patterns: ["ignored when vector_exemplars present"]
    emit: null
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_vector, "_ollama_embed", _reportish_embed)
    result = chat_vector.match_fuzzy_intent(tmp_path, "run full ritual")
    assert result is not None
    assert result[0] == "ritual"


def test_docs_example_fallback(monkeypatch) -> None:
    """When .eurika/config missing, docs/chat_intents.example.yaml used."""
    from eurika.api.chat_intents_config import _load_config, clear_cache

    clear_cache()
    docs_example = ROOT / "docs" / "chat_intents.example.yaml"
    if not docs_example.exists():
        return
    cfg = _load_config(ROOT)
    assert "intents" in cfg or "vector_min_similarity" in cfg


def test_vector_min_similarity_from_config(monkeypatch, tmp_path: Path) -> None:
    """vector_min_similarity in YAML overrides default."""
    from eurika.api import chat_vector
    from eurika.api.chat_intents_config import clear_cache

    monkeypatch.setenv("EURIKA_USE_VECTOR_INTENT", "1")
    monkeypatch.delenv("EURIKA_VECTOR_MIN_SIM", raising=False)
    clear_cache()
    (tmp_path / ".eurika" / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".eurika" / "config" / "chat_intents.yaml").write_text(
        """
vector_min_similarity: 0.65
intents:
  show_report:
    patterns: ["покажи отчёт"]
    emit: null
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_vector, "_ollama_embed", _reportish_embed)
    result = chat_vector.match_fuzzy_intent(tmp_path, "покажи отчёт")
    assert result is not None
    assert result[2] >= 0.65
