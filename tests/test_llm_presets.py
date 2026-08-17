"""Tests for OpenAI-compatible LLM API presets."""

from __future__ import annotations

from eurika.utils.llm_presets import (
    apply_llm_api_preset_env,
    apply_retired_groq_model,
    canonical_chat_model,
    detect_llm_api_preset,
    list_llm_api_presets,
    resolve_preset_base_url,
    resolve_preset_default_model,
)


def test_list_presets_includes_free_tiers() -> None:
    ids = {p.id for p in list_llm_api_presets()}
    assert {"groq", "openrouter", "gemini", "cerebras", "mistral", "openai"} <= ids


def test_detect_preset_from_base_url() -> None:
    assert detect_llm_api_preset("https://api.groq.com/openai/v1") == "groq"
    assert detect_llm_api_preset("https://openrouter.ai/api/v1/") == "openrouter"
    assert (
        detect_llm_api_preset("https://generativelanguage.googleapis.com/v1beta/openai/")
        == "gemini"
    )
    assert detect_llm_api_preset("") == ""
    assert detect_llm_api_preset("https://example.com/v1") == ""


def test_apply_preset_env_sets_base_and_model() -> None:
    out = apply_llm_api_preset_env(preset_id="groq", model="")
    assert out["OPENAI_BASE_URL"] == "https://api.groq.com/openai/v1"
    assert out["OPENAI_MODEL"] == resolve_preset_default_model("groq")
    assert out["EURIKA_CHAT_PROVIDER"] == "openai"
    assert resolve_preset_base_url("groq").startswith("https://api.groq.com")
    assert apply_llm_api_preset_env(preset_id="") == {}
    remapped = apply_llm_api_preset_env(preset_id="groq", model="llama-3.3-70b-versatile")
    assert remapped["OPENAI_MODEL"] == "openai/gpt-oss-120b"


def test_groq_default_is_gpt_oss_120b() -> None:
    assert resolve_preset_default_model("groq") == "openai/gpt-oss-120b"


def test_canonical_chat_model_rewrites_retired_groq_llama() -> None:
    groq = "https://api.groq.com/openai/v1"
    assert canonical_chat_model("llama-3.3-70b-versatile", groq) == "openai/gpt-oss-120b"
    assert canonical_chat_model("groq/llama-3.1-8b-instant", groq) == "openai/gpt-oss-20b"
    assert canonical_chat_model("openai/gpt-oss-120b", groq) == "openai/gpt-oss-120b"
    assert canonical_chat_model("llama-3.3-70b-versatile", "https://api.openai.com/v1") == (
        "llama-3.3-70b-versatile"
    )


def test_apply_retired_groq_model_mutates_env() -> None:
    env = {
        "OPENAI_BASE_URL": "https://api.groq.com/openai/v1",
        "OPENAI_MODEL": "llama-3.3-70b-versatile",
    }
    assert apply_retired_groq_model(env) == "llama-3.3-70b-versatile"
    assert env["OPENAI_MODEL"] == "openai/gpt-oss-120b"
    assert apply_retired_groq_model(env) is None
