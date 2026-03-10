"""Knowledge Provider Layer (после 1.0, review.md). ROADMAP 2.9.3: PEPProvider. R10: code_graph."""

from .base import (
    CompositeKnowledgeProvider,
    KnowledgeProvider,
    LocalKnowledgeProvider,
    OSSPatternProvider,
    OfficialDocsProvider,
    PEPProvider,
    ReleaseNotesProvider,
    StaticAnalyzerProvider,
    StructuredKnowledge,
)
from .code_graph import CodeGraph, build_code_graph
from .knowledge_graph import build_test_links
from .topics import SMELL_TO_KNOWLEDGE_TOPICS

__all__ = [
    "CodeGraph",
    "build_code_graph",
    "build_test_links",
    "SMELL_TO_KNOWLEDGE_TOPICS",
    "CompositeKnowledgeProvider",
    "KnowledgeProvider",
    "LocalKnowledgeProvider",
    "OSSPatternProvider",
    "OfficialDocsProvider",
    "PEPProvider",
    "ReleaseNotesProvider",
    "StaticAnalyzerProvider",
    "StructuredKnowledge",
]
