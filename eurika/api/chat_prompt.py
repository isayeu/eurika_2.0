"""Chat prompt building and knowledge (P0.4 split from chat.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def knowledge_topics_for_chat(intent: str, scope: Optional[Dict[str, Any]]) -> List[str]:
    """Topics for Knowledge from intent and scope (ROADMAP 3.6.6)."""
    from eurika.knowledge import SMELL_TO_KNOWLEDGE_TOPICS

    topics: List[str] = ["python"]
    if intent in ("refactor", "save", "code_edit_patch", "create"):
        if "architecture_refactor" not in topics:
            topics.append("architecture_refactor")
    if scope and scope.get("smells"):
        for s in scope["smells"]:
            smell = (s or "").strip().lower()
            for t in SMELL_TO_KNOWLEDGE_TOPICS.get(smell, []):
                if t not in topics:
                    topics.append(t)
    return topics


def fetch_knowledge_for_chat(root: Path, topics: List[str], max_chars: int = 800) -> str:
    """Fetch knowledge snippets (ROADMAP 3.6.6)."""
    import os

    from eurika.knowledge import (
        CompositeKnowledgeProvider,
        LocalKnowledgeProvider,
        OfficialDocsProvider,
        OSSPatternProvider,
        PEPProvider,
        ReleaseNotesProvider,
        StructuredKnowledge,
    )

    cache_dir = root / ".eurika" / "knowledge_cache"
    ttl = float(os.environ.get("EURIKA_KNOWLEDGE_TTL", "86400"))
    oss_path = root / ".eurika" / "pattern_library.json"
    provider = CompositeKnowledgeProvider([
        LocalKnowledgeProvider(root / "eurika_knowledge.json"),
        OSSPatternProvider(oss_path),
        PEPProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
        OfficialDocsProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
        ReleaseNotesProvider(cache_dir=cache_dir, ttl_seconds=ttl, force_online=False, rate_limit_seconds=0),
    ])
    all_fragments: List[Dict[str, Any]] = []
    for t in topics[:5]:
        if not t:
            continue
        kn = provider.query(t.strip())
        if isinstance(kn, StructuredKnowledge) and (not kn.is_empty()):
            for f in kn.fragments:
                if isinstance(f, dict):
                    all_fragments.append(f)
    if not all_fragments:
        return ""
    lines: List[str] = []
    for i, f in enumerate(all_fragments[:10], 1):
        title = f.get("title") or f.get("name") or f"Fragment {i}"
        content = f.get("content") or f.get("text") or str(f)
        lines.append(f"- {title}: {content[:400]}".rstrip() + ("..." if len(str(content)) > 400 else ""))
    snip = "\n".join(lines)
    return snip[:max_chars] + ("..." if len(snip) > max_chars else "")


def load_chat_feedback_for_prompt(root: Path, max_chars: int = 1200) -> str:
    """Load few-shot examples from .eurika/chat_feedback.json (ROADMAP 3.6.8 Phase 4)."""
    path = root / ".eurika" / "chat_feedback.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = list(data.get("entries") or [])
        if not entries:
            return ""
        neg = [e for e in entries if not e.get("helpful", True) and (e.get("clarification") or "").strip()]
        pos = [e for e in entries if e.get("helpful", True)]
        ordered = neg[-5:] + pos[-5:]
        ordered = ordered[-10:]
        lines: List[str] = []
        for e in ordered:
            user_msg = (e.get("user_message") or "")[:150].strip()
            asst_msg = (e.get("assistant_message") or "")[:120].strip()
            helpful = e.get("helpful", True)
            clarification = (e.get("clarification") or "").strip()[:200]
            if not user_msg:
                continue
            if helpful:
                snip = asst_msg[:80] + ("..." if len(asst_msg) > 80 else "")
                lines.append(f"- User: {user_msg} → correct: {snip}")
            elif clarification:
                lines.append(f"- User: {user_msg} → was wrong; user meant: {clarification}")
            if len("\n".join(lines)) >= max_chars:
                break
        if not lines:
            return ""
        return "\n[Few-shot from past feedback]\n" + "\n".join(lines[:8]) + "\n"
    except Exception:
        return ""


def load_eurika_rules_for_chat(root: Path) -> str:
    """Load .eurika/rules/*.mdc into chat context (CR-A)."""
    rules_dir = root / ".eurika" / "rules"
    if not rules_dir.is_dir():
        return ""
    lines: List[str] = []
    for p in sorted(rules_dir.glob("*.mdc")):
        try:
            raw = p.read_text(encoding="utf-8")
            if "---" in raw:
                parts = raw.split("---", 2)
                body = parts[2].strip() if len(parts) >= 3 else raw
            else:
                body = raw
            lines.append(f"\n[Rule: {p.name}]\n{body}")
            if sum(len(s) for s in lines) > 6000:
                break
        except Exception:
            pass
    return "\n".join(lines) if lines else ""


def intent_hints_for_prompt(root: Path) -> str:
    """Intent hints from .eurika/config/chat_intents.yaml or default."""
    from eurika.api.chat_intents_config import get_intent_hints

    return get_intent_hints(root)


def build_chat_prompt(
    message: str,
    context: str,
    history: Optional[List[Dict[str, str]]] = None,
    rag_examples: Optional[str] = None,
    save_target: Optional[str] = None,
    knowledge_snippet: Optional[str] = None,
    feedback_snippet: Optional[str] = None,
    rules_snippet: Optional[str] = None,
    intent_hints: Optional[str] = None,
) -> str:
    """Build system + user prompt for chat."""
    if save_target:
        system = (
            "You are Eurika. Never identify yourself as a base model/vendor name. "
            "If asked who you are, answer that you are Eurika. The user asked you to write code and save it. "
            "Generate ONLY the code. No questions, no apologies. Output must contain a ```python code block."
        )
    else:
        system = (
            "You are Eurika, an architecture-aware coding assistant. "
            "Never identify yourself as a base model. If asked who you are, answer that you are Eurika. "
            "You have context about the current project. Answer concisely and helpfully."
        )
    context_block = f"\n\n[Project context]: {context}\n\n" if context else "\n\n"
    if rules_snippet:
        context_block += f"\n[Eurika Rules — следуй этим правилам]\n{rules_snippet}\n\n"
    default_hints = """- Commit / коммит → «собери коммит»: git status+diff, затем «применяй».
- Ritual → eurika scan . → eurika doctor . → eurika report-snapshot . → eurika fix .
- Report → «покажи отчёт» shows eurika doctor report.
- Refactor → «рефактори» + path, or eurika fix .
- List files → «выполни ls» or «покажи структуру проекта»."""
    hints = intent_hints if intent_hints is not None else default_hints
    context_block += f"\n[Intent interpretation]\n{hints}\n\n"
    if feedback_snippet:
        context_block += feedback_snippet
    if rag_examples:
        context_block += rag_examples
    if knowledge_snippet:
        context_block += f"\n[Reference (from documentation)]:\n{knowledge_snippet}\n\n"
    if save_target:
        context_block += (
            f"\n[CRITICAL] User requested code to be saved to {save_target}. "
            "Reply ONLY with the code in a ```python block.\n\n"
        )
    user_content = message
    if history:
        hist_str = "\n".join((f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history[-4:]))
        user_content = f"[Previous messages]\n{hist_str}\n\nUser: {message}"
    return f"{system}{context_block}\nUser: {user_content}"
