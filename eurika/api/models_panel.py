"""Models panel snapshot + safe prefs (VISION Qt↔Desktop Models-tab parity).

Read-only LLM/ML/Market-learning status. Prefs write routing keys only —
never API secrets. Does not start/stop Ollama and does not change Market
trading rules.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from eurika.utils.env import (
    apply_qt_chat_routing,
    default_qt_settings_path,
    load_project_dotenv,
    upsert_project_env_var,
)
from eurika.utils.llm_presets import (
    apply_llm_api_preset_env,
    detect_llm_api_preset,
    list_llm_api_presets,
)

CHAT_PROVIDERS = ("auto", "openai", "ollama", "cursor", "codex")
TORCH_DEVICES = ("cpu", "cuda", "mps")
CURSOR_ROUTERS = ("cost", "balanced", "intelligence")
ALLOWED_PREF_KEYS = frozenset(
    {
        "provider",
        "openai_model",
        "api_preset",
        "ollama_model",
        "cursor_model",
        "cursor_router",
        "timeout_sec",
        "torch_device",
    }
)
_SECRET_ENV = (
    "OPENAI_API_KEY",
    "OLLAMA_OPENAI_API_KEY",
    "CURSOR_API_KEY",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
)


def _load_qt_settings() -> Dict[str, Any]:
    path = default_qt_settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_qt_settings(data: Dict[str, Any]) -> None:
    path = default_qt_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _probe_ollama(base_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url=url, method="GET")
        with urllib.request.urlopen(req, timeout=1.8) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError, ValueError):
        return {"healthy": False, "models": []}
    raw = payload.get("models") if isinstance(payload, dict) else []
    names: List[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    names.append(name)
    return {"healthy": True, "models": names[:40]}


def _market_brief(root: Path) -> Dict[str, Any]:
    try:
        from eurika.ml.learning_status import market_learning_status

        raw = market_learning_status(root)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:160]}
    if not isinstance(raw, dict):
        return {}
    paper = raw.get("paper") if isinstance(raw.get("paper"), dict) else {}
    live = raw.get("live") if isinstance(raw.get("live"), dict) else {}
    model = raw.get("model") if isinstance(raw.get("model"), dict) else {}
    portfolio = raw.get("portfolio") if isinstance(raw.get("portfolio"), dict) else {}
    opens = raw.get("opens") if isinstance(raw.get("opens"), dict) else {}
    heads = model.get("heads") if isinstance(model.get("heads"), dict) else {}
    return {
        "trades": paper.get("count"),
        "accuracy": paper.get("accuracy"),
        "live_n": live.get("count"),
        "equity": portfolio.get("equity_usdt"),
        "opens": opens.get("count"),
        "model": model.get("weights") or heads.get("entry"),
        "note": "paper only — display, not a trading control",
    }


def build_models_state(project_root: str | Path) -> Dict[str, Any]:
    """Serializable Models snapshot. Never includes secret values."""
    root = Path(project_root).resolve()
    load_project_dotenv(root)
    settings = _load_qt_settings()
    provider = str(
        settings.get("chat_provider") or os.environ.get("EURIKA_CHAT_PROVIDER") or "auto"
    ).strip().lower()
    if provider not in CHAT_PROVIDERS:
        provider = "auto"
    base_url = str(os.environ.get("OPENAI_BASE_URL") or "").strip()
    preset = str(settings.get("chat_api_preset") or detect_llm_api_preset(base_url) or "")
    torch: Dict[str, Any] = {}
    try:
        from eurika.ml.torch_runtime import torch_status

        torch = torch_status(run_smoke_check=False)
    except Exception as exc:
        torch = {"available": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
    ollama = _probe_ollama()
    return {
        "panel": "models",
        "llm": {
            "provider": provider,
            "providers": list(CHAT_PROVIDERS),
            "openai_model": str(
                settings.get("chat_openai_model") or os.environ.get("OPENAI_MODEL") or ""
            ),
            "openai_base_url": base_url,
            "api_preset": preset,
            "presets": [
                {"id": p.id, "label": p.label, "default_model": p.default_model}
                for p in list_llm_api_presets()
            ],
            "ollama_model": str(
                settings.get("chat_ollama_model") or os.environ.get("OLLAMA_OPENAI_MODEL") or ""
            ),
            "cursor_model": str(
                settings.get("chat_cursor_model") or os.environ.get("CURSOR_MODEL") or ""
            ),
            "cursor_router": str(
                settings.get("chat_cursor_router") or os.environ.get("CURSOR_OPTIMIZE_FOR") or ""
            ),
            "timeout_sec": int(settings.get("chat_timeout_sec") or 120),
            "keys_present": {name: bool((os.environ.get(name) or "").strip()) for name in _SECRET_ENV},
            "ollama": ollama,
        },
        "ml": {
            "torch": torch,
            "torch_device": str(
                settings.get("torch_device") or os.environ.get("EURIKA_TORCH_DEVICE") or "cpu"
            ),
            "devices": list(TORCH_DEVICES),
            "market": _market_brief(root),
        },
        "note": (
            "Models-tab parity v0: routing prefs + status. "
            "Keys stay in .env. No Ollama start/stop. Market freeze."
        ),
    }


def apply_models_prefs(
    project_root: str | Path,
    prefs: Dict[str, Any],
) -> Dict[str, Any]:
    """Write allowed routing prefs to qt_settings + project .env (no secrets)."""
    root = Path(project_root).resolve()
    if not isinstance(prefs, dict):
        raise ValueError("prefs must be an object")
    unknown = sorted(set(prefs) - ALLOWED_PREF_KEYS)
    if unknown:
        raise ValueError(f"unsupported prefs: {', '.join(unknown)}")
    settings = _load_qt_settings()
    env_updates: Dict[str, str] = {}

    if "provider" in prefs:
        provider = str(prefs.get("provider") or "").strip().lower()
        if provider not in CHAT_PROVIDERS:
            raise ValueError(f"provider must be one of {', '.join(CHAT_PROVIDERS)}")
        settings["chat_provider"] = provider
        env_updates["EURIKA_CHAT_PROVIDER"] = provider

    if "api_preset" in prefs:
        preset_id = str(prefs.get("api_preset") or "").strip().lower()
        settings["chat_api_preset"] = preset_id
        if preset_id:
            env_updates.update(
                apply_llm_api_preset_env(
                    preset_id=preset_id,
                    model=str(prefs.get("openai_model") or settings.get("chat_openai_model") or ""),
                    set_provider_openai="provider" not in prefs,
                )
            )

    if "openai_model" in prefs:
        model = str(prefs.get("openai_model") or "").strip()
        settings["chat_openai_model"] = model
        if model:
            env_updates["OPENAI_MODEL"] = model

    if "ollama_model" in prefs:
        model = str(prefs.get("ollama_model") or "").strip()
        settings["chat_ollama_model"] = model
        if model:
            env_updates["OLLAMA_OPENAI_MODEL"] = model

    if "cursor_model" in prefs:
        model = str(prefs.get("cursor_model") or "").strip()
        settings["chat_cursor_model"] = model
        if model:
            env_updates["CURSOR_MODEL"] = model

    if "cursor_router" in prefs:
        router = str(prefs.get("cursor_router") or "").strip().lower()
        if router and router not in CURSOR_ROUTERS:
            raise ValueError(f"cursor_router must be one of {', '.join(CURSOR_ROUTERS)}")
        settings["chat_cursor_router"] = router
        if router:
            env_updates["CURSOR_OPTIMIZE_FOR"] = router

    if "timeout_sec" in prefs:
        try:
            timeout = int(prefs.get("timeout_sec"))
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout_sec must be an integer") from exc
        settings["chat_timeout_sec"] = max(10, min(timeout, 600))

    if "torch_device" in prefs:
        device = str(prefs.get("torch_device") or "").strip().lower()
        if device not in TORCH_DEVICES:
            raise ValueError(f"torch_device must be one of {', '.join(TORCH_DEVICES)}")
        settings["torch_device"] = device
        env_updates["EURIKA_TORCH_DEVICE"] = device

    _save_qt_settings(settings)
    for key, value in env_updates.items():
        if key in _SECRET_ENV:
            continue
        upsert_project_env_var(root, key, value)
    apply_qt_chat_routing()
    return build_models_state(root)
