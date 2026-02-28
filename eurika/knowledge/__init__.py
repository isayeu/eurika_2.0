"""Knowledge Provider Layer (после 1.0, review.md). ROADMAP 2.9.3: PEPProvider."""

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
from .topics import SMELL_TO_KNOWLEDGE_TOPICS

__all__ = [
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
