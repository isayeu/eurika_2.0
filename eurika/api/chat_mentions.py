"""@-mention autocomplete catalog for Chat (Cursor-like A1).

Builds candidates from self_map modules + known smell types.
UI filters via ``filter_mention_candidates``; send path still uses ``parse_mentions``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from eurika.api.chat_intent import KNOWN_SMELL_TYPES

MENTION_MODULE_CAP = 300
MENTION_POPUP_LIMIT = 12

_AT_TOKEN_RE = re.compile(r"[a-zA-Z0-9_./\-]*\Z")


def smell_mention_ids() -> List[str]:
    """Canonical smell ids for autocomplete (skip alias ``cyclic``)."""
    return sorted(s for s in KNOWN_SMELL_TYPES if s != "cyclic")


def load_modules_from_self_map(root: Path | str | None) -> List[str]:
    """Module paths from ``self_map.json`` (empty if missing/unreadable)."""
    if not root:
        return []
    path = Path(root) / "self_map.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    modules = data.get("modules")
    if not isinstance(modules, list):
        return []
    out: List[str] = []
    seen: set[str] = set()
    for item in modules:
        raw = ""
        if isinstance(item, dict):
            raw = str(item.get("path") or item.get("name") or "").strip()
        elif isinstance(item, str):
            raw = item.strip()
        if not raw:
            continue
        norm = raw.replace("\\", "/")
        if not re.match(r"^[a-zA-Z0-9_./\-]+$", norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
        if len(out) >= MENTION_MODULE_CAP:
            break
    return out


def build_mention_catalog(root: Path | str | None) -> List[str]:
    """Full catalog: smells first, then modules (deduped)."""
    smells = smell_mention_ids()
    modules = load_modules_from_self_map(root)
    seen = set(smells)
    out = list(smells)
    for m in modules:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _basename(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def _match_score(name: str, prefix: str) -> Tuple[int, int, str]:
    """Lower is better. Prefer prefix on basename, then on full path, then substring."""
    p = prefix.lower()
    n = name.lower()
    base = _basename(n)
    if not p:
        return (2, len(n), n)
    if base.startswith(p):
        return (0, len(base), n)
    if n.startswith(p):
        return (1, len(n), n)
    if p in base:
        return (3, base.find(p), n)
    if p in n:
        return (4, n.find(p), n)
    return (99, 0, n)


def filter_mention_candidates(
    catalog: Sequence[str],
    prefix: str,
    *,
    limit: int = MENTION_POPUP_LIMIT,
) -> List[str]:
    """Filter/rank catalog by typed prefix after ``@``."""
    pref = (prefix or "").strip().lstrip("@")
    scored: List[Tuple[Tuple[int, int, str], str]] = []
    for name in catalog:
        score = _match_score(name, pref)
        if score[0] >= 99 and pref:
            continue
        scored.append((score, name))
    scored.sort(key=lambda x: x[0])
    return [name for _, name in scored[: max(0, int(limit))]]


def mention_candidates(
    root: Path | str | None,
    prefix: str,
    *,
    limit: int = MENTION_POPUP_LIMIT,
    catalog: Optional[Sequence[str]] = None,
) -> List[str]:
    """Convenience: build (or reuse) catalog and filter by prefix."""
    cat = list(catalog) if catalog is not None else build_mention_catalog(root)
    return filter_mention_candidates(cat, prefix, limit=limit)


def extract_at_token(text: str, cursor: int) -> Optional[Tuple[int, int, str]]:
    """If cursor is inside/after an ``@token``, return (at_index, end, prefix).

    ``prefix`` is the text after ``@`` up to cursor (may be empty right after ``@``).
    """
    if cursor < 0:
        return None
    s = text or ""
    if cursor > len(s):
        cursor = len(s)
    before = s[:cursor]
    at = before.rfind("@")
    if at < 0:
        return None
    if at > 0:
        prev = before[at - 1]
        if prev.isalnum() or prev in "_./-":
            # email-like / mid-word — not a mention trigger
            return None
    token = before[at + 1 :]
    if not _AT_TOKEN_RE.fullmatch(token):
        return None
    # Don't keep completing if cursor is past token end with space etc.
    return (at, cursor, token)


def merge_catalogs(*parts: Iterable[str]) -> List[str]:
    """Dedupe preserving order (for tests / refresh)."""
    out: List[str] = []
    seen: set[str] = set()
    for part in parts:
        for item in part:
            name = str(item or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
    return out
