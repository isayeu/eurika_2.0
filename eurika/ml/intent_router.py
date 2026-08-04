"""Tiny chat intent router (CR-G3): char features → MLP → handler | LLM.

YAML/direct intents always win first. Enable with ``EURIKA_USE_ML_INTENT=1``.
Trains from intent exemplars under ``.eurika/ml/weights/intent_router.*``.
"""

from __future__ import annotations

import json
import re
import zlib
from pathlib import Path
from typing import Any, Optional, Sequence

from eurika.ml.market_store import ml_root
from eurika.ml.torch_runtime import torch_available

LLM_LABEL = "__llm__"
FEATURE_DIM = 128
HIDDEN = 64
DEFAULT_EPOCHS = 120
MIN_EXAMPLES_PER_LABEL = 2


def intent_weights_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "weights" / "intent_router.pt"


def intent_meta_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "weights" / "intent_router_meta.json"


def _use_ml_intent() -> bool:
    from eurika.utils.env import env_bool

    return env_bool("EURIKA_USE_ML_INTENT")


def message_features(text: str, *, dim: int = FEATURE_DIM) -> list[float]:
    """Stable bag-of-char n-gram hash features (not Python's salted ``hash``)."""
    msg = (text or "").lower().strip()
    msg = re.sub(r"\s+", " ", msg)
    vec = [0.0] * dim
    if not msg:
        return vec
    padded = f"#{msg}#"
    for n in (2, 3, 4):
        for i in range(max(0, len(padded) - n + 1)):
            gram = padded[i : i + n]
            h = zlib.adler32(gram.encode("utf-8")) % dim
            vec[h] += 1.0
    # A few token cues
    for tok in re.findall(r"[a-zа-яё0-9_]+", msg):
        h = zlib.adler32(f"w:{tok}".encode("utf-8")) % dim
        vec[h] += 1.5
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _collect_training_rows(project_root: str | Path) -> list[tuple[str, str]]:
    """(text, label) from curated exemplars + LLM negatives."""
    rows: list[tuple[str, str]] = []
    try:
        from eurika.api.chat_intents_config import _load_config

        cfg = _load_config(Path(project_root).resolve())
    except Exception:
        cfg = {}
    intents = cfg.get("intents") or {}
    for handler_id, spec in intents.items():
        if not isinstance(spec, dict):
            continue
        # Prefer clean exemplars; patterns only as fallback (skip regex).
        texts: list[str] = []
        for key in ("vector_exemplars", "exact"):
            for item in spec.get(key) or []:
                if isinstance(item, str) and item.strip():
                    texts.append(item.strip())
        if len(texts) < MIN_EXAMPLES_PER_LABEL:
            for item in spec.get("patterns") or []:
                if not isinstance(item, str):
                    continue
                s = item.strip()
                if not s or s.startswith("^") or "\\" in s or s.startswith(r"\s"):
                    continue
                texts.append(s)
        # Dedup keep order
        seen: set[str] = set()
        uniq: list[str] = []
        for t in texts:
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(t)
        for t in uniq[:16]:
            rows.append((t, str(handler_id)))

    llm_negatives = (
        "почему модуль X связан с Y?",
        "объясни архитектуру слоёв",
        "как лучше назвать функцию",
        "что думаешь о рефакторинге",
        "напиши пример на python",
        "why is this design chosen",
        "how should I structure the API",
        "расскажи анекдот",
        "сравни два подхода к DI",
        "что такое dependency inversion",
        "help me debug a race condition",
        "предложи дизайн API для чата",
        "как устроен event loop",
        "переведи этот абзац на английский",
        "оцени качество этого кода",
        "какие плюсы у hexagonal architecture",
    )
    for t in llm_negatives:
        rows.append((t, LLM_LABEL))
    return rows


def _build_model(n_labels: int) -> Any:
    import torch.nn as nn

    return nn.Sequential(
        nn.Linear(FEATURE_DIM, HIDDEN),
        nn.ReLU(),
        nn.Linear(HIDDEN, n_labels),
    )


def train_intent_router(
    project_root: str | Path,
    *,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = 0.05,
) -> dict[str, Any]:
    """Train tiny MLP router on CPU. Requires torch extra."""
    if not torch_available():
        return {"ok": False, "error": "torch not available", "path": str(intent_weights_path(project_root))}
    import torch
    import torch.nn as nn

    rows = _collect_training_rows(project_root)
    if len(rows) < 8:
        return {"ok": False, "error": "not enough exemplars", "samples": len(rows)}

    # Drop rare labels (< MIN) except LLM
    counts: dict[str, int] = {}
    for _, lab in rows:
        counts[lab] = counts.get(lab, 0) + 1
    keep = {lab for lab, n in counts.items() if lab == LLM_LABEL or n >= MIN_EXAMPLES_PER_LABEL}
    rows = [(t, lab) for t, lab in rows if lab in keep]
    if len(rows) < 8:
        return {"ok": False, "error": "not enough exemplars after filter", "samples": len(rows)}

    labels = sorted({lab for _, lab in rows})
    lab_to_idx = {lab: i for i, lab in enumerate(labels)}
    xs = [message_features(t) for t, _ in rows]
    ys = [lab_to_idx[lab] for _, lab in rows]

    # Force CPU — tiny net; avoids flaky CUDA driver paths on old GPUs.
    device = torch.device("cpu")
    x = torch.tensor(xs, dtype=torch.float32, device=device)
    y = torch.tensor(ys, dtype=torch.long, device=device)
    model = _build_model(len(labels)).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()
    model.train()
    for _ in range(max(20, int(epochs))):
        opt.zero_grad()
        logits = model(x)
        loss = loss_fn(logits, y)
        loss.backward()
        opt.step()
    model.eval()
    with torch.no_grad():
        pred = model(x).argmax(dim=1)
        acc = float((pred == y).float().mean().item())

    path = intent_weights_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "labels": labels,
            "feature_dim": FEATURE_DIM,
            "hidden": HIDDEN,
            "arch": "mlp2",
        },
        path,
    )
    meta = {
        "labels": labels,
        "samples": len(rows),
        "train_accuracy": round(acc, 4),
        "feature_dim": FEATURE_DIM,
        "hidden": HIDDEN,
        "arch": "mlp2",
        "device": "cpu",
        "label_counts": {k: counts.get(k, 0) for k in labels},
    }
    intent_meta_path(project_root).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "samples": len(rows),
        "train_accuracy": acc,
        "labels": labels,
        "classes": len(labels),
    }


def _ensure_trained(project_root: str | Path) -> bool:
    path = intent_weights_path(project_root)
    if path.is_file():
        # Retrain if legacy linear weights (no arch) or very weak meta.
        try:
            meta = json.loads(intent_meta_path(project_root).read_text(encoding="utf-8"))
            if float(meta.get("train_accuracy") or 0) >= 0.5 and meta.get("arch") == "mlp2":
                return True
        except Exception:
            pass
    st = train_intent_router(project_root)
    return bool(st.get("ok"))


def predict_intent_route(project_root: str | Path, message: str) -> dict[str, Any]:
    """Predict handler_id or LLM. Never raises to callers (returns ok=False)."""
    root = Path(project_root).resolve()
    msg = (message or "").strip()
    if not msg:
        return {"ok": False, "error": "empty", "route": "llm", "handler_id": None}
    if not torch_available():
        return {"ok": False, "error": "no torch", "route": "llm", "handler_id": None}
    if not _ensure_trained(root):
        return {"ok": False, "error": "train failed", "route": "llm", "handler_id": None}
    import torch

    try:
        blob = torch.load(intent_weights_path(root), map_location="cpu", weights_only=False)
    except TypeError:
        blob = torch.load(intent_weights_path(root), map_location="cpu")
    except Exception as exc:
        return {"ok": False, "error": str(exc), "route": "llm", "handler_id": None}
    labels: Sequence[str] = blob.get("labels") or []
    if not labels:
        return {"ok": False, "error": "no labels", "route": "llm", "handler_id": None}
    if blob.get("arch") == "mlp2":
        model = _build_model(len(labels))
    else:
        # Legacy single Linear — retrain next ensure; still try load if shapes match
        import torch.nn as nn

        model = nn.Linear(int(blob.get("feature_dim") or FEATURE_DIM), len(labels))
    try:
        model.load_state_dict(blob["state_dict"])
    except Exception:
        st = train_intent_router(root)
        if not st.get("ok"):
            return {"ok": False, "error": "reload train failed", "route": "llm", "handler_id": None}
        return predict_intent_route(root, message)
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor([message_features(msg)], dtype=torch.float32))
        probs = torch.softmax(logits, dim=1)[0]
        idx = int(probs.argmax().item())
        conf = float(probs[idx].item())
    label = str(labels[idx])
    if label == LLM_LABEL:
        return {
            "ok": True,
            "route": "llm",
            "handler_id": None,
            "confidence": conf,
            "source": "ml",
        }
    return {
        "ok": True,
        "route": "direct",
        "handler_id": label,
        "confidence": conf,
        "source": "ml",
        "emit": _emit_for_handler(root, label),
    }


def _emit_for_handler(project_root: Path, handler_id: str) -> Optional[str]:
    try:
        from eurika.api.chat_intents_config import _load_config

        spec = (_load_config(project_root).get("intents") or {}).get(handler_id) or {}
        emit = spec.get("emit")
        return str(emit) if emit else None
    except Exception:
        return None


def match_ml_intent(
    project_root: str | Path,
    message: str,
    *,
    min_confidence: float = 0.55,
) -> Optional[tuple[str, Optional[str]]]:
    """Return ``(handler_id, emit)`` when ML routes to a direct handler.

    Returns ``None`` when disabled, unsure, or routes to LLM.
    Heavy/side-effect handlers are blocked unless the text clearly matches.
    """
    if not _use_ml_intent():
        return None
    st = predict_intent_route(project_root, message)
    if not st.get("ok"):
        return None
    if st.get("route") != "direct":
        return None
    handler = st.get("handler_id")
    if not handler:
        return None
    if float(st.get("confidence") or 0.0) < float(min_confidence):
        return None
    msg = (message or "").lower()
    # Guard: do not let ML fire ritual/release/git on vague "статус ML" phrases.
    if handler == "ritual" and "ритуал" not in msg and "ritual" not in msg and "scan" not in msg:
        return None
    if handler == "release_check" and "release" not in msg:
        return None
    if handler == "git_commit" and "коммит" not in msg and "commit" not in msg and "git" not in msg:
        return None
    return (str(handler), st.get("emit"))
