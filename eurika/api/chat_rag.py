"""RAG for chat: retrieve similar past exchanges from .eurika/chat_history/ (ROADMAP 3.5.11.B).

Uses TF-IDF + cosine similarity (pure Python, no deps). Skips assistant responses
that start with "[Error]" or "[Request failed]" — only successful exchanges.
"""
from __future__ import annotations
import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def _tokenize(text: str) -> List[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric, filter short."""
    cleaned = re.sub('[^\\w\\s]', ' ', (text or '').lower())
    return [w for w in cleaned.split() if len(w) >= 2]

def _tfidf_similarity(query_tokens: List[str], doc_tokens: List[str], idf: Dict[str, float]) -> float:
    """Cosine similarity between query and doc using TF-IDF weights."""

    def vec(tokens: List[str]) -> Dict[str, float]:
        tf: Dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1.0
        return {t: tf[t] * idf.get(t, 1.0) for t in tf}
    qv = vec(query_tokens)
    dv = vec(doc_tokens)
    if not qv or not dv:
        return 0.0
    dot = sum((qv.get(t, 0) * dv.get(t, 0) for t in set(qv) & set(dv)))
    nq = math.sqrt(sum((v * v for v in qv.values())))
    nd = math.sqrt(sum((v * v for v in dv.values())))
    if nq <= 0 or nd <= 0:
        return 0.0
    return dot / (nq * nd)

def _load_chat_pairs(path: Path) -> List[Tuple[str, str, str]]:
    """Load (user_query, assistant_response, ts) from chat.jsonl. Skip error responses."""
    pairs: List[Tuple[str, str, str]] = []
    if not path.exists():
        return pairs
    buf: Optional[str] = None
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = (rec.get('role') or '').strip().lower()
            content = (rec.get('content') or '').strip()
            ts = rec.get('ts') or ''
            if role == 'user':
                buf = content
            elif role == 'assistant' and buf is not None:
                if content and (not content.startswith('[Error')) and (not content.startswith('[Request failed')):
                    pairs.append((buf, content, ts))
                buf = None
    except Exception:
        pass
    return pairs

def retrieve_similar_chats(project_root: Path, query: str, top_k: int=3, min_similarity: float=0.15) -> List[Dict[str, str]]:
    """
    Retrieve top-k similar past (user, assistant) exchanges for RAG.

    Returns list of {"user": "...", "assistant": "..."}. Empty if no history or
    no sufficiently similar pairs.
    """
    root = Path(project_root).resolve()
    chat_path = root / '.eurika' / 'chat_history' / 'chat.jsonl'
    pairs = _load_chat_pairs(chat_path)
    if not pairs:
        return []
    all_docs = [p[0] for p in pairs]
    all_tokens = [_tokenize(d) for d in all_docs]
    query_tokens = _tokenize(query)
    doc_freq: Dict[str, int] = {}
    for tokens in all_tokens:
        for t in set(tokens):
            doc_freq[t] = doc_freq.get(t, 0) + 1
    n_docs = len(all_docs)
    idf = {t: math.log((n_docs + 1) / (doc_freq[t] + 1)) + 1 for t in doc_freq}
    scored: List[Tuple[float, int]] = []
    for i, doc_tokens in enumerate(all_tokens):
        sim = _tfidf_similarity(query_tokens, doc_tokens, idf)
        if sim >= min_similarity:
            scored.append((sim, i))
    scored.sort(key=lambda x: -x[0])
    results: List[Dict[str, str]] = []
    for _, idx in scored[:top_k]:
        u, a, _ = pairs[idx]
        results.append({'user': u[:300], 'assistant': a[:500]})
    return results

def format_rag_examples(examples: List[Dict[str, str]]) -> str:
    """Format retrieved examples for prompt injection."""
    if not examples:
        return ''
    lines = ['[Similar past exchanges — use as reference if relevant]']
    for i, ex in enumerate(examples, 1):
        u = ex.get('user', '')
        a = ex.get('assistant', '')
        if u or a:
            lines.append(f'{i}. User: {u}')
            lines.append(f'   Assistant: {a}')
    return '\n'.join(lines) + '\n\n'


# TODO (eurika): refactor deep_nesting '_load_chat_pairs' — consider extracting nested block
