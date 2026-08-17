"""Chat prompt building and knowledge (P0.4 split from chat.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from eurika.api.chat_host_ops import (
    _tokenize_for_tool_exp,
    host_identity_prompt_facts,
    market_learning_prompt_facts,
    message_asks_market_learning,
    tool_protocol_instructions,
)

# Product/persona tokens match almost every chat; they must not pull identity few-shots
# into unrelated questions (e.g. polygon drills).
_FEEDBACK_EXTRA_STOP = frozenset(
    {
        "eurika",
        "ассистент",
        "assistant",
        "исаев",
        "prodg",
        "ты",
        "кто",
        "какая",
        "какие",
        "такой",
        "такая",
    }
)


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


def _feedback_query_tokens(message: str) -> set[str]:
    return {t for t in _tokenize_for_tool_exp(message) if t not in _FEEDBACK_EXTRA_STOP}


def _score_feedback_entry(entry: dict, query_tokens: set[str]) -> tuple[int, int]:
    """Return (score, overlap_count). Unrelated identity/persona rows score 0."""
    if not query_tokens:
        return (0, 0)
    hay = " ".join(
        [
            str(entry.get("user_message") or ""),
            str(entry.get("assistant_message") or ""),
            str(entry.get("clarification") or ""),
        ]
    )
    hay_tokens = _feedback_query_tokens(hay)
    overlap = query_tokens & hay_tokens
    if not overlap:
        return (0, 0)
    score = 0
    for tok in overlap:
        score += 2 if len(tok) >= 5 else 1
        if "/" in tok or tok.endswith(".py") or len(tok) >= 10:
            score += 3
    return (score, len(overlap))


def load_chat_feedback_for_prompt(
    root: Path,
    max_chars: int = 1200,
    message: str | None = None,
) -> str:
    """Load few-shot examples from .eurika/chat_feedback.json (ROADMAP 3.6.8 Phase 4).

    When ``message`` is set, only examples that share distinctive tokens are injected.
    Recency-only few-shots copy identity answers onto polygon/code questions.
    """
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
        if message is not None:
            query_tokens = _feedback_query_tokens(message)
            if not query_tokens:
                return ""
            scored: List[tuple[int, int, int, dict]] = []
            for idx, e in enumerate(entries):
                if not isinstance(e, dict):
                    continue
                helpful = bool(e.get("helpful", True))
                clarification = (e.get("clarification") or "").strip()
                if not helpful and not clarification:
                    continue
                score, overlap = _score_feedback_entry(e, query_tokens)
                if score <= 0 or overlap < 2:
                    continue
                scored.append((score, overlap, idx, e))
            scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
            ordered = [e for _s, _o, _i, e in scored[:8]]
        else:
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


def _user_prefers_russian(message: str, history: Optional[List[Dict[str, str]]] = None) -> bool:
    """Detect Russian from current message or recent user turns."""
    import re

    parts = [message or ""]
    if history:
        for turn in history[-3:]:
            if (turn or {}).get("role") == "user":
                parts.append(str(turn.get("content") or ""))
    return bool(re.search(r"[а-яёА-ЯЁ]", " ".join(parts)))


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
    tool_experience: Optional[str] = None,
) -> str:
    """Build system + user prompt for chat."""
    if save_target:
        system = (
            "You are Eurika. Never identify yourself as a base model/vendor name. "
            "If asked who you are, answer that you are Eurika. The user asked you to write code and save it. "
            "Generate ONLY the code. No questions, no apologies. Output must contain a ```python code block."
        )
    else:
        lang_rule = ""
        if _user_prefers_russian(message, history):
            lang_rule = (
                " Reply in Russian only. Do not mix Spanish, English, or other languages. "
                "Do not start with a greeting unless the user just greeted you. "
                "Be concise; use project context, do not invent file paths or commands. "
            )
        system = (
            "You are Eurika, an architecture-aware coding assistant. "
            "Never identify yourself as a base model. If asked who you are, answer that you are Eurika. "
            "You have context about the current project. Answer concisely and helpfully."
            + lang_rule
            + " "
            + tool_protocol_instructions(tool_experience)
        )
    context_block = f"\n\n[Project context]: {context}\n\n" if context else "\n\n"
    if not save_target:
        context_block += "\n" + host_identity_prompt_facts() + "\n\n"
    if rules_snippet:
        context_block += f"\n[Eurika Rules — следуй этим правилам]\n{rules_snippet}\n\n"
    default_hints = """- Commit / коммит → «собери коммит»: status+diff + предложение, затем «применяй».
- Git status/diff (без коммита) → ```eurika-cmds``` (`git status`, `git diff`); не угадывай.
- Ritual → eurika scan . → eurika doctor . → eurika report-snapshot . → eurika fix .
- Report → «покажи отчёт» shows eurika doctor report.
- Refactor → «рефактори» + path, or eurika fix .
- List files / дерево → через ```eurika-cmds``` (ls -la, find/tree); не угадывай список.
- Живые факты о хосте (сеть, устройства, процессы) → ```eurika-cmds``` (nmcli/ip/ss); не советуй macOS/Activity Monitor.
- Успехи обучения market ML → [Market facts] / format_market_learning_block; суди по вердикту/equity/edge, не accuracy (не eurika scan)."""
    hints = intent_hints if intent_hints is not None else default_hints
    context_block += f"\n[Intent interpretation]\n{hints}\n\n"
    if not save_target and message_asks_market_learning(message):
        context_block += "\n" + market_learning_prompt_facts() + "\n\n"
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
        hist_str = "\n".join(
            (f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history[-4:])
        )
        user_content = f"[Previous messages]\n{hist_str}\n\nUser: {message}"
    return f"{system}{context_block}\nUser: {user_content}"
