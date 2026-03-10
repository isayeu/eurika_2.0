"""Knowledge API facade (ROADMAP §11, KNOWLEDGE_LAYER.md).

Публичный фасад для запроса Knowledge Layer. Используется doctor, architect, explain;
API endpoint GET /api/knowledge даёт доступ для UI без дублирования логики.
"""

from __future__ import annotations

import json
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


def get_test_links(project_root: Path) -> Dict[str, Any]:
    """
    R10 Knowledge Graph: связи test_file → tested_module.

    Returns {"links": [[test_path, module_path], ...]}. Requires self_map.json.
    """
    from eurika.knowledge import build_code_graph, build_test_links

    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return {"links": [], "error": "self_map.json not found", "hint": "run eurika scan first"}
    try:
        self_map = json.loads(self_map_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"links": [], "error": str(e)}
    cg = build_code_graph(self_map)
    links = build_test_links(root, cg)
    return {"links": [[a, b] for a, b in links]}


def get_knowledge_graph(project_root: Path) -> Dict[str, Any]:
    """
    R10 Knowledge Graph — объединённый фасад (KNOWLEDGE_GRAPH_DESIGN §5).

    Returns: code (nodes, edges_count), test_links. Architecture graph — отдельно (get_graph, get_summary).
    """
    from eurika.knowledge import build_code_graph, build_test_links

    root = Path(project_root).resolve()
    self_map_path = root / "self_map.json"
    if not self_map_path.exists():
        return {
            "code": {"nodes": [], "edges_count": 0},
            "test_links": [],
            "error": "self_map.json not found",
            "hint": "run eurika scan first",
        }
    try:
        self_map = json.loads(self_map_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"code": {"nodes": [], "edges_count": 0}, "test_links": [], "error": str(e)}

    cg = build_code_graph(self_map)
    links = build_test_links(root, cg)
    return {
        "code": {
            "nodes": sorted(cg.nodes),
            "edges_count": sum(len(dsts) for dsts in cg.edges.values()),
        },
        "test_links": [[a, b] for a, b in links],
    }
