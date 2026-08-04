"""Environment variable utilities (L0)."""

from __future__ import annotations

import os
from pathlib import Path

# Project .env keys that override shell exports when present.
_PROJECT_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
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
    "EURIKA_USE_ML_INTENT",
    "EURIKA_USE_VECTOR_INTENT",
    "EURIKA_TORCH_DEVICE",
)


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


def load_project_dotenv(project_root: str | Path | None = None) -> None:
    """Load .env from project root; selected project keys override shell exports."""
    try:
        from dotenv import dotenv_values, load_dotenv
    except ImportError:
        return
    root = Path(project_root or ".").resolve()
    env_path = root / ".env"
    if not env_path.is_file():
        return
    load_dotenv(dotenv_path=str(env_path), override=False)
    values = dotenv_values(dotenv_path=str(env_path))
    for key in _PROJECT_ENV_KEYS:
        value = values.get(key)
        if value:
            os.environ[key] = value


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
