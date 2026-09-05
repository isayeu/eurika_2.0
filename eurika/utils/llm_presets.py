"""OpenAI-compatible LLM API presets (Groq / OpenRouter / Gemini / …).

Keys stay in ``OPENAI_API_KEY`` (.env). Presets only set BASE_URL + suggest a model.
Local Ollama remains the default via ``EURIKA_CHAT_PROVIDER=auto|ollama``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, MutableMapping


# Groq retired these ids on 2026-08-16. Keep the map so old .env / Qt fields still work.
GROQ_RETIRED_MODELS = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
}


@dataclass(frozen=True)
class LlmApiPreset:
    """One remote OpenAI-compatible endpoint preset."""

    id: str
    label: str
    base_url: str
    default_model: str
    key_hint: str = ""
    notes: str = ""


# Empty id = use whatever is already in the environment / .env.
ENV_PRESET_ID = ""

LLM_API_PRESETS: dict[str, LlmApiPreset] = {
    "openai": LlmApiPreset(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        key_hint="platform.openai.com/api-keys",
        notes="Paid; free credits sometimes on new accounts.",
    ),
    "groq": LlmApiPreset(
        id="groq",
        label="Groq (free tier)",
        base_url="https://api.groq.com/openai/v1",
        default_model="openai/gpt-oss-120b",
        key_hint="console.groq.com/keys",
        notes="Fast inference; RPM/TPM limits on free tier. Llama 3.3 70B Versatile retired 2026-08-16.",
    ),
    "openrouter": LlmApiPreset(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="openrouter/free",
        key_hint="openrouter.ai/keys",
        notes="Aggregator; many :free models — pick one in Models field.",
    ),
    "gemini": LlmApiPreset(
        id="gemini",
        label="Google Gemini (OpenAI compat)",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-2.0-flash",
        key_hint="aistudio.google.com/apikey",
        notes="Free tier via AI Studio; OpenAI-compatible endpoint.",
    ),
    "cerebras": LlmApiPreset(
        id="cerebras",
        label="Cerebras (free tier)",
        base_url="https://api.cerebras.ai/v1",
        default_model="llama-3.3-70b",
        key_hint="cloud.cerebras.ai",
        notes="Fast free tier; check current model ids in console.",
    ),
    "mistral": LlmApiPreset(
        id="mistral",
        label="Mistral",
        base_url="https://api.mistral.ai/v1",
        default_model="mistral-small-latest",
        key_hint="console.mistral.ai",
        notes="Free/experiment quotas vary; set key in OPENAI_API_KEY.",
    ),
}


def list_llm_api_presets() -> list[LlmApiPreset]:
    """Stable order for UI / docs."""
    order = ("openai", "groq", "openrouter", "gemini", "cerebras", "mistral")
    return [LLM_API_PRESETS[k] for k in order if k in LLM_API_PRESETS]


def get_llm_api_preset(preset_id: str | None) -> LlmApiPreset | None:
    pid = (preset_id or "").strip().lower()
    if not pid:
        return None
    return LLM_API_PRESETS.get(pid)


def canonical_chat_model(model: str | None, base_url: str | None = None) -> str:
    """Rewrite retired Groq Llama ids to the current Groq replacements."""
    raw = (model or "").strip()
    if not raw:
        return raw
    host = (base_url or "").strip().lower()
    key = raw[5:] if raw.startswith("groq/") else raw
    groq_host = "groq" in host or raw.startswith("groq/")
    if groq_host and key in GROQ_RETIRED_MODELS:
        return GROQ_RETIRED_MODELS[key]
    return raw


def apply_retired_groq_model(environ: MutableMapping[str, str]) -> str | None:
    """Mutate OPENAI_MODEL in place. Returns the previous id when rewritten."""
    previous = (environ.get("OPENAI_MODEL") or "").strip()
    if not previous:
        return None
    canonical = canonical_chat_model(previous, environ.get("OPENAI_BASE_URL"))
    if canonical == previous:
        return None
    environ["OPENAI_MODEL"] = canonical
    return previous


def detect_llm_api_preset(base_url: str | None) -> str:
    """Match OPENAI_BASE_URL to a known preset id, or empty if custom/unset."""
    raw = (base_url or "").strip().lower().rstrip("/")
    if not raw:
        return ENV_PRESET_ID
    for preset in list_llm_api_presets():
        target = preset.base_url.strip().lower().rstrip("/")
        if raw == target or raw.startswith(target):
            return preset.id
    if "openrouter" in raw:
        return "openrouter"
    if "groq" in raw:
        return "groq"
    if "generativelanguage.googleapis" in raw or "gemini" in raw:
        return "gemini"
    if "cerebras" in raw:
        return "cerebras"
    if "mistral" in raw:
        return "mistral"
    if "api.openai.com" in raw:
        return "openai"
    return ENV_PRESET_ID


def resolve_preset_base_url(preset_id: str | None) -> str:
    """BASE_URL for a preset id, or empty for «from .env»."""
    preset = get_llm_api_preset(preset_id)
    return preset.base_url if preset else ""


def resolve_preset_default_model(preset_id: str | None) -> str:
    preset = get_llm_api_preset(preset_id)
    return preset.default_model if preset else ""


def apply_llm_api_preset_env(
    environ: Mapping[str, str] | None = None,
    *,
    preset_id: str | None,
    model: str | None = None,
    set_provider_openai: bool = True,
) -> dict[str, str]:
    """Return env updates for a preset (does not write os.environ by itself)."""
    preset = get_llm_api_preset(preset_id)
    if not preset:
        return {}
    out: dict[str, str] = {"OPENAI_BASE_URL": preset.base_url}
    chosen = canonical_chat_model((model or "").strip() or preset.default_model, preset.base_url)
    if chosen:
        out["OPENAI_MODEL"] = chosen
    if set_provider_openai:
        out["EURIKA_CHAT_PROVIDER"] = "openai"
    return out
