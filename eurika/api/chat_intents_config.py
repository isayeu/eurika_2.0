"""Chat intents config loader (ROADMAP: вынос команд из кода в .eurika/config/chat_intents.yaml)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

_CACHE: Optional[dict[str, Any]] = None
_CACHE_ROOT: Optional[Path] = None


def _load_config(root: Path) -> dict[str, Any]:
    """Load chat_intents.yaml; cache per root."""
    global _CACHE, _CACHE_ROOT
    root = Path(root).resolve()
    if _CACHE is not None and _CACHE_ROOT == root:
        return _CACHE
    path = root / ".eurika" / "config" / "chat_intents.yaml"
    if not path.exists():
        _CACHE = {}
        _CACHE_ROOT = root
        return _CACHE
    try:
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml:
            raw = path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
            _CACHE = data if isinstance(data, dict) else {}
        else:
            _CACHE = {}
        _CACHE_ROOT = root
        return _CACHE
    except Exception:
        _CACHE = {}
        _CACHE_ROOT = root
        return _CACHE


def match_direct_intent(root: Path, message: str) -> Optional[tuple[str, Optional[str]]]:
    """
    Match message against configured intents. Returns (handler_id, emit_cmd) or None.
    First match wins (order in YAML). emit_cmd can be None (no Terminal emit).
    """
    msg = (message or "").strip()
    if not msg:
        return None
    msg_lower = msg.lower()
    cfg = _load_config(root)
    intents = cfg.get("intents") or {}
    question_prefix = cfg.get("question_prefix")
    if question_prefix:
        try:
            if re.search(question_prefix, msg_lower):
                return None  # Question-like, skip
        except re.error:
            pass

    for handler_id, spec in intents.items():
        if not isinstance(spec, dict):
            continue
        # exclude_prefix: if msg starts with any → skip this intent
        if any(msg_lower.startswith((p or "").strip().lower()) for p in (spec.get("exclude_prefix") or [])):
            continue
        # exclude: any substring in msg → skip this intent
        exclude = spec.get("exclude") or []
        if any((e in msg_lower for e in exclude)):
            continue
        # exact
        exact_list = spec.get("exact") or []
        if exact_list and msg_lower in [e.lower() for e in exact_list]:
            emit = spec.get("emit")
            return (handler_id, emit)
        # require (all must be present)
        require = spec.get("require")
        if require:
            req_list = require if isinstance(require, list) else [require]
            if not all((r in msg_lower for r in req_list)):
                continue
        # require_path (must have path-like: . or /)
        if spec.get("require_path") and "." not in msg and "/" not in msg:
            continue
        # patterns
        patterns = spec.get("patterns") or []
        for p in patterns:
            if spec.get("match_mode") == "regex":
                try:
                    if re.search(p, msg_lower):
                        return (handler_id, spec.get("emit"))
                except re.error:
                    pass
            else:
                if p.lower() in msg_lower:
                    emit = spec.get("emit")
                    if spec.get("emit_template"):
                        # Minimal template resolution (caller fills endpoint/module_path)
                        emit = spec["emit_template"]
                    return (handler_id, emit)
    return None


def get_intent_hints(root: Path) -> str:
    """Return intent_hints string for LLM prompt, or default."""
    cfg = _load_config(root)
    hints = cfg.get("intent_hints")
    if hints and isinstance(hints, str) and hints.strip():
        return hints.strip()
    return """- Commit / коммит → «собери коммит»: git status+diff, затем «применяй».
- Ritual → eurika scan . → eurika doctor . → eurika report-snapshot . → eurika fix .
- Report → «покажи отчёт» shows eurika doctor report.
- Refactor → «рефактори» + path, or eurika fix .
- List files → «выполни ls» or «покажи структуру проекта»."""


def clear_cache() -> None:
    """Clear config cache (for tests)."""
    global _CACHE, _CACHE_ROOT
    _CACHE = None
    _CACHE_ROOT = None
