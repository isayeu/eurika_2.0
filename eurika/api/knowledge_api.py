"""Knowledge API facade (ROADMAP §11, KNOWLEDGE_LAYER.md).

Публичный фасад для запроса Knowledge Layer. Используется doctor, architect, explain;
API endpoint GET /api/knowledge даёт доступ для UI без дублирования логики.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict


def _build_knowledge_provider(project_root: Path, *, online: bool = False):
    """Build CompositeKnowledgeProvider (Local + OSS + PEP + OfficialDocs + ReleaseNotes)."""
    from eurika.knowledge import (
        CompositeKnowledgeProvider,
        LocalKnowledgeProvider,
        OfficialDocsProvider,
        OSSPatternProvider,
        PEPProvider,
        ReleaseNotesProvider,
    )

    root = Path(project_root).resolve()
    cache_dir = root / ".eurika" / "knowledge_cache"
    ttl = float(os.environ.get("EURIKA_KNOWLEDGE_TTL", "86400"))
    rate_limit = float(os.environ.get("EURIKA_KNOWLEDGE_RATE_LIMIT", "1.0" if online else "0"))
    oss_path = root / ".eurika" / "pattern_library.json"
    return CompositeKnowledgeProvider([
        LocalKnowledgeProvider(root / "eurika_knowledge.json"),
        OSSPatternProvider(oss_path),
        PEPProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
        OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
        ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=online, rate_limit_seconds=rate_limit),
    ])


def get_knowledge(
    project_root: Path,
    topic: str,
    *,
    online: bool = False,
) -> Dict[str, Any]:
    """
    Query Knowledge Layer by topic. Returns JSON-serializable dict.

    Keys: topic, source, fragments, meta. Same as StructuredKnowledge.
    """
    provider = _build_knowledge_provider(project_root, online=online)
    result = provider.query(topic)
    return asdict(result)
