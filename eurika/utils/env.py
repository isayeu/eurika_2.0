"""Environment variable utilities (L0)."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Project .env keys that override shell exports when present.
_PROJECT_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
    "EURIKA_CHAT_PROVIDER",
    "OLLAMA_OPENAI_API_KEY",
    "OLLAMA_OPENAI_MODEL",
    "OLLAMA_OPENAI_BASE_URL",
    "TAVILY_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "EURIKA_WEB_SEARCH",
    "EURIKA_WEB_SEARCH_PROVIDER",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BINANCE_TESTNET",
    "BINANCE_BASE_URL",
    "EURIKA_LBOT_SSH_HOST",
    "EURIKA_LBOT_REMOTE_DIR",
    "EURIKA_LBOT_SSH_TIMEOUT",
    "EURIKA_LBOT_PROBE",
    "EURIKA_TELEGRAM_BOT_TOKEN",
    "EURIKA_TELEGRAM_CHAT_IDS",
    "EURIKA_TELEGRAM_ALLOW_ANY",
    "EURIKA_USE_ML_INTENT",
    "EURIKA_USE_VECTOR_INTENT",
    "EURIKA_TORCH_DEVICE",
    "CURSOR_API_KEY",
    "CURSOR_MODEL",
    "CURSOR_OPTIMIZE_FOR",
)

# Subset for callers that only need LLM routing and must not flip feature flags
# (e.g. the chat API, which can be imported by tests and other apps).
LLM_ROUTING_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
    "EURIKA_CHAT_PROVIDER",
    "OLLAMA_OPENAI_API_KEY",
    "OLLAMA_OPENAI_MODEL",
    "OLLAMA_OPENAI_BASE_URL",
    "CURSOR_API_KEY",
    "CURSOR_MODEL",
    "CURSOR_OPTIMIZE_FOR",
)

# Qt ChatWorker sets this so .env cannot clobber Models → Источник for one call.
LLM_ENV_LOCK_KEY = "EURIKA_LLM_ENV_LOCKED"
LLM_ENV_LOCKED_ROUTING_KEYS = frozenset(
    {
        "EURIKA_CHAT_PROVIDER",
        "CURSOR_MODEL",
        "CURSOR_OPTIMIZE_FOR",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "OLLAMA_OPENAI_MODEL",
    }
)
CURSOR_SECRET_ENV_KEYS = ("CURSOR_API_KEY",)
_CHAT_PROVIDERS = frozenset({"auto", "openai", "ollama", "codex", "cursor"})
_CURSOR_OPTIMIZE_VALUES = frozenset({"cost", "balanced", "intelligence"})


def _parse_env_file(env_path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser (no python-dotenv required)."""
    out: dict[str, str] = {}
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[7:].strip()
        if "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def env_bool(name: str, default: bool = False) -> bool:
    """Parse env var as boolean; \"1\", \"true\", \"yes\" (case-insensitive) -> True."""
    fallback = "1" if default else "0"
    val = os.environ.get(name, fallback).strip().lower()
    return val in ("1", "true", "yes")


def upsert_project_env_var(
    project_root: str | Path,
    key: str,
    value: str,
) -> Path:
    """Set ``KEY=value`` in project ``.env`` and ``os.environ`` (no secrets logged)."""
    root = Path(project_root).resolve()
    env_path = root / ".env"
    key = (key or "").strip()
    if not key:
        raise ValueError("empty env key")
    value = str(value)
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    replaced = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            out.append(line)
            continue
        if stripped.startswith(prefix) or stripped.startswith(f"export {prefix}"):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out).rstrip() + "\n"
    env_path.write_text(text, encoding="utf-8")
    os.environ[key] = value
    return env_path


def load_project_dotenv(
    project_root: str | Path | None = None,
    *,
    keys: tuple[str, ...] | None = None,
) -> None:
    """Load .env from project root; selected project keys override shell exports.

    Uses python-dotenv when installed; otherwise a tiny built-in parser so API
    keys still reach the Qt process.

    ``keys`` restricts what is applied (e.g. ``LLM_ROUTING_ENV_KEYS``); nothing
    outside that set reaches ``os.environ``, so a library caller cannot flip
    feature flags for the whole process.
    """
    root = Path(project_root or ".").resolve()
    env_path = root / ".env"
    if not env_path.is_file():
        return
    wanted = keys if keys is not None else _PROJECT_ENV_KEYS
    values: dict[str, str | None] = {}
    try:
        from dotenv import dotenv_values, load_dotenv

        if keys is None:
            load_dotenv(dotenv_path=str(env_path), override=False)
        raw = dotenv_values(dotenv_path=str(env_path))
        values = {k: (str(v) if v is not None else None) for k, v in raw.items()}
    except ImportError:
        values = {k: v for k, v in _parse_env_file(env_path).items()}
    locked = (os.environ.get(LLM_ENV_LOCK_KEY) or "").strip() == "1"
    for key in wanted:
        value = values.get(key)
        if not value:
            continue
        if locked and key in LLM_ENV_LOCKED_ROUTING_KEYS:
            continue
        os.environ[key] = value
    from eurika.utils.llm_presets import apply_retired_groq_model

    apply_retired_groq_model(os.environ)
    # .env often has Groq/openai; Qt Models is the live source. Re-apply after every
    # dotenv load so a restart cannot silently switch Chat/agent-chat back to Groq→Ollama.
    if not locked:
        apply_qt_chat_routing()


def default_qt_settings_path() -> Path:
    override = (os.environ.get("EURIKA_QT_SETTINGS_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".eurika" / "qt_settings.json"


def llm_env_is_locked() -> bool:
    return (os.environ.get(LLM_ENV_LOCK_KEY) or "").strip() == "1"


def apply_qt_chat_routing(
    environ: dict[str, str] | None = None,
    *,
    settings_path: Path | None = None,
) -> str | None:
    """Apply Qt Models → Источник over ``.env``. No-op if ChatWorker locked routing.

    Returns the provider that was applied, or None if settings were missing.
    """
    if llm_env_is_locked():
        raw = (os.environ.get("EURIKA_CHAT_PROVIDER") or "").strip().lower()
        return raw if raw in _CHAT_PROVIDERS else None
    path = settings_path or default_qt_settings_path()
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    provider = str(data.get("chat_provider") or "").strip().lower()
    if provider not in _CHAT_PROVIDERS:
        return None
    target = environ if environ is not None else os.environ
    target["EURIKA_CHAT_PROVIDER"] = provider
    if provider == "cursor":
        model = str(data.get("chat_cursor_model") or "").strip()
        if model:
            target["CURSOR_MODEL"] = model
        opt = str(data.get("chat_cursor_router") or "").strip().lower()
        if opt in _CURSOR_OPTIMIZE_VALUES:
            target["CURSOR_OPTIMIZE_FOR"] = opt
        else:
            target.pop("CURSOR_OPTIMIZE_FOR", None)
    return provider


def binance_credentials_status() -> dict[str, object]:
    """Presence check for Binance keys (never returns secret values)."""
    key = (os.environ.get("BINANCE_API_KEY") or "").strip()
    secret = (os.environ.get("BINANCE_API_SECRET") or "").strip()
    return {
        "api_key_set": bool(key),
        "api_secret_set": bool(secret),
        "testnet": env_bool("BINANCE_TESTNET", default=False),
        "ready": bool(key and secret),
    }
