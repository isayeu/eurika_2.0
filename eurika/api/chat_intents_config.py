"""Chat intents config loader.

Provides declarative intent → handler mapping. Resolution order:

1. Hardcoded `DEFAULT_CONFIG` from `chat_intents_default` (works for any project).
2. User overrides from `<root>/.eurika/config/chat_intents.yaml` (if PyYAML installed).
3. Legacy fallback to `<root>/docs/chat_intents.example.yaml` (eurika-self project).

User config is merged per-intent on top of defaults: any intent declared by
the user fully replaces the default for that key, top-level keys (like
`intent_hints`, `question_prefix`) are taken from user if present.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from .chat_intents_default import DEFAULT_CONFIG

_CACHE: Optional[dict[str, Any]] = None
_CACHE_ROOT: Optional[Path] = None


def normalize_intent_text(text: str) -> str:
    """Normalize user text for intent matching: lower, ё→е, collapse whitespace."""
    s = (text or "").strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s


def _pattern_matches_message(pattern: str, msg_lower: str) -> bool:
    """Substring match with token boundaries for space-padded / short patterns.

    ``" ls "`` must not match inside ``goals`` after normalize strips spaces to ``ls``.
    """
    raw = pattern or ""
    padded = raw[:1].isspace() or raw[-1:].isspace()
    token = normalize_intent_text(raw)
    if not token:
        return False
    if padded or len(token) <= 3:
        return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", msg_lower) is not None
    return token in msg_lower


def _load_user_yaml(root: Path) -> dict[str, Any]:
    """Load user YAML from .eurika/config/ or docs/chat_intents.example.yaml."""
    path = root / ".eurika" / "config" / "chat_intents.yaml"
    if not path.exists():
        path = root / "docs" / "chat_intents.example.yaml"
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _merge_config(default: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """Merge user config on top of defaults.

    - Intents: dict merge (user intent replaces default intent of the same id).
    - Other top-level keys: user value wins if present.
    """
    if not user:
        return {k: v for k, v in default.items()}
    merged: dict[str, Any] = {k: v for k, v in default.items()}
    for key, value in user.items():
        if key == "intents" and isinstance(value, dict):
            merged_intents = dict(default.get("intents") or {})
            for intent_id, spec in value.items():
                if spec is None:
                    merged_intents.pop(intent_id, None)
                else:
                    merged_intents[intent_id] = spec
            merged["intents"] = merged_intents
        else:
            merged[key] = value
    return merged


def _load_config(root: Path) -> dict[str, Any]:
    """Load merged config; cache per root."""
    global _CACHE, _CACHE_ROOT
    root = Path(root).resolve()
    if _CACHE is not None and _CACHE_ROOT == root:
        return _CACHE
    user_cfg = _load_user_yaml(root)
    _CACHE = _merge_config(DEFAULT_CONFIG, user_cfg)
    _CACHE_ROOT = root
    return _CACHE


def match_direct_intent(root: Path, message: str) -> Optional[tuple[str, Optional[str]]]:
    """
    Match message against configured intents. Returns (handler_id, emit_cmd) or None.

    First matching intent wins (insertion order). `emit_cmd` may be None (no
    Terminal echo).
    """
    msg = (message or "").strip()
    if not msg:
        return None
    msg_lower = normalize_intent_text(msg)
    cfg = _load_config(root)
    intents = cfg.get("intents") or {}

    for handler_id, spec in intents.items():
        if not isinstance(spec, dict):
            continue
        exclude_prefix = spec.get("exclude_prefix") or []
        if any(
            msg_lower.startswith(normalize_intent_text(p or ""))
            for p in exclude_prefix
        ):
            continue
        exclude = spec.get("exclude") or []
        if any(normalize_intent_text(e) in msg_lower for e in exclude):
            continue
        exact_list = spec.get("exact") or []
        if exact_list and msg_lower in [normalize_intent_text(e) for e in exact_list]:
            return (handler_id, spec.get("emit"))
        require = spec.get("require")
        if require:
            req_list = require if isinstance(require, list) else [require]
            if not all(normalize_intent_text(r) in msg_lower for r in req_list):
                continue
        if spec.get("require_path") and "." not in msg and "/" not in msg:
            continue
        patterns = spec.get("patterns") or []
        is_regex = spec.get("match_mode") == "regex"
        for pattern in patterns:
            if is_regex:
                try:
                    if re.search(pattern, msg_lower):
                        return (handler_id, spec.get("emit"))
                except re.error:
                    continue
            else:
                if _pattern_matches_message(str(pattern), msg_lower):
                    emit = spec.get("emit_template") or spec.get("emit")
                    return (handler_id, emit)

    # Question-style messages with no specific intent match → LLM.
    question_prefix = cfg.get("question_prefix")
    if question_prefix:
        try:
            if re.search(question_prefix, msg_lower):
                return None
        except re.error:
            pass
    return None


def get_intent_hints(root: Path) -> str:
    """Return intent_hints string for LLM prompt."""
    cfg = _load_config(root)
    hints = cfg.get("intent_hints")
    if hints and isinstance(hints, str) and hints.strip():
        return hints.strip()
    return DEFAULT_CONFIG["intent_hints"]


def get_all_intents(root: Path) -> dict[str, Any]:
    """Expose merged intents (for diagnostics / Help tab)."""
    cfg = _load_config(root)
    return dict(cfg.get("intents") or {})


def clear_cache() -> None:
    """Clear config cache (for tests)."""
    global _CACHE, _CACHE_ROOT
    _CACHE = None
    _CACHE_ROOT = None
