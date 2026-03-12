"""Vector memory for chat intent fuzzy match (CR-G2).

Embeddings via Ollama /api/embed. Optional: EURIKA_USE_VECTOR_INTENT=1.
Fallback when match_direct_intent returns None.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity in [0, 1] for normalized vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum((x * y for x, y in zip(a, b)))
    na = sum((x * x for x in a)) ** 0.5
    nb = sum((x * x for x in b)) ** 0.5
    if na <= 0 or nb <= 0:
        return 0.0
    raw = dot / (na * nb)
    return max(0.0, min(1.0, (raw + 1) / 2))

def _use_vector_intent() -> bool:
    return os.environ.get('EURIKA_USE_VECTOR_INTENT', '').strip().lower() in ('1', 'true', 'yes')

def _ollama_embed(text: str, *, model: str='nomic-embed-text', base_url: str='http://localhost:11434', timeout: float=5.0) -> Optional[List[float]]:
    """Call Ollama /api/embed. Returns embedding vector or None on failure."""
    url = f"{base_url.rstrip('/')}/api/embed"
    try:
        import urllib.request
        body = json.dumps({'model': model, 'input': text[:8192]}).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        emb = data.get('embeddings')
        if isinstance(emb, list) and emb:
            return emb[0] if isinstance(emb[0], list) else emb
        return None
    except Exception:
        return None

def _intent_exemplars(cfg: Dict[str, Any]) -> List[Tuple[str, str, Optional[str]]]:
    """Collect (handler_id, exemplar_text, emit) from config intents.

    Prefers vector_exemplars per intent (curated for embeddings); else exact + patterns.
    """
    result: List[Tuple[str, str, Optional[str]]] = []
    intents = cfg.get('intents') or {}
    for handler_id, spec in intents.items():
        if not isinstance(spec, dict):
            continue
        emit = spec.get('emit')
        vec_ex = spec.get('vector_exemplars')
        if vec_ex and isinstance(vec_ex, list):
            for ex in vec_ex:
                if isinstance(ex, str) and ex.strip():
                    result.append((handler_id, ex.strip(), emit))
        else:
            for exact in spec.get('exact') or []:
                if isinstance(exact, str) and exact.strip():
                    result.append((handler_id, exact.strip(), emit))
            for pat in spec.get('patterns') or []:
                if isinstance(pat, str) and pat.strip():
                    result.append((handler_id, pat.strip(), emit))
    return result

def _cache_path(root: Path) -> Path:
    return root / '.eurika' / 'vector_intent_cache.json'

def _load_cache(root: Path) -> Dict[str, List[float]]:
    p = _cache_path(root)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return {k: v for k, v in (data or {}).items() if isinstance(v, list)}
    except Exception:
        return {}

def _save_cache(root: Path, cache: Dict[str, List[float]]) -> None:
    try:
        p = _cache_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass

def _extracted_block_147(sim_env: str) -> float:
    try:
        return float(sim_env)
    except ValueError:
        return 0.72

def match_fuzzy_intent(root: Path, message: str, *, min_similarity: Optional[float]=None, embed_model: Optional[str]=None) -> Optional[Tuple[str, Optional[str], float]]:
    """
    Fuzzy intent match via embeddings. Returns (handler_id, emit, similarity) or None.
    CR-G2: Embeddings для fuzzy match (опционально).

    min_similarity: 0.68–0.85. Lower = more permissive. Sources (priority):
      - argument
      - config vector_min_similarity
      - EURIKA_VECTOR_MIN_SIM env
      - default 0.72
    """
    if not _use_vector_intent():
        return None
    cfg = None
    try:
        from eurika.api.chat_intents_config import _load_config
        cfg = _load_config(root)
    except Exception:
        cfg = {}
    sim_cfg = cfg.get('vector_min_similarity')
    sim_env = os.environ.get('EURIKA_VECTOR_MIN_SIM', '').strip()
    if min_similarity is not None:
        threshold = min_similarity
    elif sim_cfg is not None:
        try:
            threshold = float(sim_cfg)
        except (TypeError, ValueError):
            threshold = 0.72
    elif sim_env:
        threshold = _extracted_block_147(sim_env)
    else:
        threshold = 0.72
    threshold = max(0.5, min(0.95, threshold))
    model = embed_model or os.environ.get('OLLAMA_EMBED_MODEL', 'nomic-embed-text')
    msg = (message or '').strip()
    if not msg:
        return None
    exemplars = _intent_exemplars(cfg or {})
    if not exemplars:
        return None
    cache = _load_cache(root)
    host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    base_url = host if host.startswith('http') else f'http://{host}'
    query_emb = _ollama_embed(msg, model=model, base_url=base_url)
    if not query_emb:
        return None
    best_handler: Optional[str] = None
    best_emit: Optional[str] = None
    best_sim = threshold
    for handler_id, exemplar, emit in exemplars:
        key = f'{handler_id}:{exemplar}'
        if key not in cache:
            emb = _ollama_embed(exemplar, model=model, base_url=base_url)
            if emb:
                cache[key] = emb
        emb = cache.get(key)
        if emb:
            sim = _cosine_sim(query_emb, emb)
            if sim >= best_sim:
                best_sim = sim
                best_handler = handler_id
                best_emit = emit
    _save_cache(root, cache)
    if best_handler is not None:
        return (best_handler, best_emit, best_sim)
    return None