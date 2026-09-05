"""LLM teacher samples for paper-market MLP.

Cursor hourly reasoning → ``llm_teacher_samples.jsonl``. Outcomes are graded
on the later candle path (independent of whether MLP entered). Mixes into
train; never opens paper and never replaces live argmax.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Sequence

from eurika.ml.features import FEATURE_NAMES
from eurika.ml.market_store import ml_root, read_jsonl_rows

TEACHER_WEIGHT = 1.0
TEACHER_MAX_FRAC = 0.5
KIND = "llm_teacher"
_ACTION_IDX = {"HOLD": 0, "BUY": 1, "SELL": 2}

_YES = frozenset({"yes", "y", "true", "1", "да", "вход"})
_NO = frozenset({"no", "n", "false", "0", "нет", "hold"})
_WAIT = frozenset({"wait", "ждать", "later"})
_OPEN = frozenset({"open", "already", "in_market", "уже", "уже в рынке"})


def samples_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "llm_teacher_samples.jsonl"


def load_teacher_samples(project_root: str | Path) -> list[dict[str, Any]]:
    return read_jsonl_rows(samples_path(project_root))


def _try_obj(blob: str) -> dict[str, Any] | None:
    text = (blob or "").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    depth = 0
    end = -1
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    try:
        data = json.loads(text[: end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_teacher_samples(text: str) -> list[dict[str, Any]]:
    """Pull ``samples`` list from free text / fenced JSON, else read the prose blocks."""
    raw = text or ""
    blobs: list[str] = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if fence:
        blobs.append(fence.group(1))
    idx = raw.rfind('"samples"')
    if idx >= 0:
        start = raw.rfind("{", 0, idx + 1)
        if start >= 0:
            blobs.append(raw[start:])
    blobs.append(raw)
    for blob in blobs:
        data = _try_obj(blob)
        if not data:
            continue
        rows = data.get("samples")
        if isinstance(rows, list):
            parsed = [r for r in rows if isinstance(r, dict)]
            if parsed:
                return parsed
    return parse_markdown_samples(raw)


_BOOK_TAGS = {
    "spot": "spot",
    "спот": "spot",
    "fut": "fut",
    "futures": "fut",
    "perp": "fut",
    "фьюч": "fut",
    "фьючерс": "fut",
}
_FIELD_ALIASES = {
    "вход": "enter",
    "entry": "enter",
    "когда": "when",
    "when": "when",
    "сторона": "side",
    "side": "side",
    "плечо": "leverage",
    "leverage": "leverage",
}


def _header_symbol(line: str) -> tuple[str, str] | None:
    """``### MUUSDT [fut]`` / ``**SOXLUSDT [fut]**`` / ``### 1. SOLUSDT`` → symbol + book."""
    text = line.strip()
    if not text or len(text) > 64:
        return None
    # Require header decoration, else a bare ``HOLD`` line would open a fake block.
    if not (text.startswith("#") or "[" in text or re.match(r"^\*\*.+\*\*$", text)):
        return None
    text = re.sub(r"^[\s#>*_`~\-–—]+", "", text)
    text = re.sub(r"^\d+[.)]\s+", "", text)
    text = re.sub(r"[\s*_`~:]+$", "", text)
    m = re.match(r"^([A-Z0-9]{3,20})\s*(?:\[\s*([A-Za-zА-Яа-яЁё]+)\s*\])?$", text)
    if not m or not re.search(r"[A-Z]", m.group(1)):
        return None
    return m.group(1), _BOOK_TAGS.get((m.group(2) or "").lower(), "")


def _as_float(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except (AttributeError, ValueError):
        return None


def _level_frac(segment: str) -> float | None:
    """Fraction from ``доля 0.021`` / ``1.5%`` / ``(0.012)``; ignore absolute prices."""
    seg = segment or ""
    m = re.search(r"(?:доля|share|frac\w*)\D{0,6}?(\d*[.,]\d+)", seg, flags=re.I)
    if m:
        return _frac(m.group(1))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", seg)
    if m:
        pct = _as_float(m.group(1))
        return None if pct is None else max(0.0, min(0.2, pct / 100.0))
    m = re.search(r"\(\s*[~≈]?\s*(\d*[.,]\d+)\s*\)", seg)
    if m:
        # Only a share fits in parens here; a price would clamp to a bogus 20%.
        val = _as_float(m.group(1))
        return val if val is not None and 0.0 < val <= 0.2 else None
    return None


def _tp_sl_from(value: str) -> tuple[float | None, float | None]:
    text = (value or "").replace("·", " ")
    m_tp = re.search(r"\bTP\b", text, flags=re.I)
    m_sl = re.search(r"\bSL\b", text, flags=re.I)
    tp_seg = ""
    sl_seg = ""
    if m_tp:
        end = m_sl.start() if m_sl and m_sl.start() > m_tp.start() else len(text)
        tp_seg = text[m_tp.end() : end]
    if m_sl:
        sl_seg = text[m_sl.end() :]
    return _level_frac(tp_seg), _level_frac(sl_seg)


def _block_sample(symbol: str, book: str, lines: list[str]) -> dict[str, Any] | None:
    item: dict[str, Any] = {"symbol": symbol}
    if book:
        item["market"] = book
    seen = False
    for raw_line in lines:
        line = re.sub(r"^[\s*\-•>#_`~]+", "", raw_line.strip())
        label, sep, value = line.partition(":")
        if not sep:
            continue
        label = re.sub(r"[*_`~#]+", "", label).strip().lower()
        value = value.strip()
        if not value:
            continue
        field = _FIELD_ALIASES.get(label)
        if field == "leverage":
            m = re.search(r"\d+(?:[.,]\d+)?", value)
            if m:
                item["leverage"] = float(m.group(0).replace(",", "."))
            seen = True
            continue
        if field:
            item[field] = value
            seen = True
            continue
        if "tp" in label or "уровн" in label or "параметр" in label:
            tp, sl = _tp_sl_from(value)
            if tp is not None:
                item["tp_pct"] = tp
            if sl is not None:
                item["sl_pct"] = sl
    if not seen or not (item.get("enter") or item.get("side")):
        return None
    return item


def parse_markdown_samples(text: str) -> list[dict[str, Any]]:
    """Fallback for answers that skipped the JSON block but kept per-ticker blocks."""
    out: list[dict[str, Any]] = []
    symbol = ""
    book = ""
    lines: list[str] = []
    for raw_line in (text or "").splitlines():
        head = _header_symbol(raw_line)
        if head is None:
            if symbol:
                lines.append(raw_line)
            continue
        if symbol:
            sample = _block_sample(symbol, book, lines)
            if sample:
                out.append(sample)
        symbol, book = head
        lines = []
    if symbol:
        sample = _block_sample(symbol, book, lines)
        if sample:
            out.append(sample)
    return out


def _norm_enter(raw: object) -> str:
    text = str(raw or "").strip().lower()
    if text in _OPEN or text.startswith("уже"):
        return "open"
    if text in _WAIT or text.startswith("ждать"):
        return "wait"
    if text in _YES or text.startswith("да"):
        return "yes"
    if text in _NO or text.startswith("нет"):
        return "no"
    return text or "no"


def _norm_side(raw: object) -> str:
    text = str(raw or "HOLD").strip().upper()
    if text in {"BUY", "SELL", "HOLD"}:
        return text
    if "ПОКУП" in text:
        return "BUY"
    if "ПРОДА" in text:
        return "SELL"
    return "HOLD"


def _norm_market(raw: object) -> str:
    text = str(raw or "spot").strip().lower()
    if text in {"futures", "fut", "perp"}:
        return "fut"
    return "spot"


def _frac(raw: object) -> float | None:
    if isinstance(raw, bool) or raw is None or raw == "":
        return None
    if not isinstance(raw, (int, float, str)):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val > 0.2:
        val = val / 100.0
    return max(0.0, min(0.2, val))


def _card_index(cards: Sequence[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for card in cards:
        key = (str(card.get("symbol") or "").upper(), _norm_market(card.get("market")))
        if key[0]:
            out[key] = dict(card)
    return out


def _feature_vec(card: dict[str, Any]) -> list[float] | None:
    vec = card.get("feature_vec")
    n_feat = len(FEATURE_NAMES)
    if isinstance(vec, list) and vec:
        out = [float(v) for v in vec[:n_feat] if isinstance(v, (int, float))]
        if len(out) < n_feat:
            out.extend([0.0] * (n_feat - len(out)))
        return out[:n_feat]
    feat = card.get("features")
    if isinstance(feat, dict) and feat:
        return [float(feat.get(name, 0.0) or 0.0) for name in FEATURE_NAMES]
    return None


def build_teacher_rows(
    payload: Sequence[dict[str, Any]],
    cards: Sequence[dict[str, Any]],
    *,
    now_ms: int,
) -> list[dict[str, Any]]:
    """Keep cards with features. Independent yes-entries stay even if MLP/gate said no."""
    index = _card_index(cards)
    rows: list[dict[str, Any]] = []
    for item in payload:
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        raw_market = str(item.get("market") or "").strip()
        market = _norm_market(raw_market) if raw_market else ""
        card = index.get((symbol, market)) if market else None
        if card is None:
            # The snapshot is the universe: one book for this symbol is unambiguous.
            same = [key for key in index if key[0] == symbol]
            if len(same) != 1:
                continue
            market = same[0][1]
            card = index[same[0]]
        vec = _feature_vec(card)
        if not vec:
            continue
        enter = _norm_enter(item.get("enter"))
        if enter == "open":
            continue
        side = _norm_side(item.get("side"))
        if enter in {"no", "wait"}:
            side = "HOLD"
        elif enter != "yes":
            side = "HOLD"
        if enter == "yes" and side not in {"BUY", "SELL"}:
            continue
        row: dict[str, Any] = {
            "ts": int(now_ms),
            "kind": KIND,
            "symbol": symbol,
            "market": "futures" if market == "fut" else "spot",
            "enter": enter,
            "side": side,
            "when": str(item.get("when") or ""),
            "feature_vec": vec,
            "weight": TEACHER_WEIGHT,
            "source": "cursor",
        }
        interval = str(card.get("interval") or "").strip()
        if interval:
            row["interval"] = interval
        interval2 = str(card.get("interval2") or "").strip()
        if interval2:
            row["interval2"] = interval2
        lev = item.get("leverage")
        if lev is None:
            lev = card.get("leverage")
        try:
            row["leverage"] = float(lev) if lev is not None else None
        except (TypeError, ValueError):
            row["leverage"] = None
        for key in ("tp_pct", "sl_pct", "trail_pct"):
            frac = _frac(item.get(key))
            if frac is None:
                frac = _frac(card.get(key))
            if frac is not None:
                row[key] = frac
        rows.append(row)
    return rows


def append_teacher_samples(project_root: str | Path, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    path = samples_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def harvest_teacher(
    project_root: str | Path,
    text: str,
    cards: Sequence[dict[str, Any]],
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    parsed = parse_teacher_samples(text)
    rows = build_teacher_rows(parsed, cards, now_ms=now)
    stored = append_teacher_samples(project_root, rows)
    from eurika.ml.llm_teacher_settle import settle_teacher

    settle_teacher(project_root, now_ms=now)
    return {
        "parsed": len(parsed),
        "stored": stored,
        "skipped": max(0, len(parsed) - stored),
        "rows": rows,
    }


def _teacher_xy(
    project_root: str | Path,
    *,
    settled: bool,
) -> tuple[list[list[float]], list[int], list[float]]:
    xs: list[list[float]] = []
    ys: list[int] = []
    ws: list[float] = []
    n_feat = len(FEATURE_NAMES)
    for row in load_teacher_samples(project_root):
        if row.get("skip"):
            continue
        if bool(row.get("settled")) != settled:
            continue
        vec = row.get("feature_vec")
        if not isinstance(vec, list) or not vec:
            continue
        padded = [float(v) for v in vec[:n_feat]]
        if len(padded) < n_feat:
            padded.extend([0.0] * (n_feat - len(padded)))
        side = _norm_side(row.get("side"))
        xs.append(padded[:n_feat])
        ys.append(int(_ACTION_IDX.get(side, 0)))
        try:
            raw_w = float(row.get("weight") or TEACHER_WEIGHT)
        except (TypeError, ValueError):
            raw_w = TEACHER_WEIGHT
        if settled:
            ws.append(max(0.25, min(8.0, raw_w)))
        else:
            ws.append(max(0.05, min(1.0, raw_w)))
    return xs, ys, ws


def _cap_weights(ws: list[float], cap: float) -> list[float]:
    total = sum(ws) or 0.0
    if total <= cap or cap <= 0 or not ws:
        return ws
    scale = cap / total
    return [w * scale for w in ws]


def mix_teacher_xy(
    project_root: str | Path,
    xs: list[list[float]],
    ys: list[int],
    ws: list[float],
    *,
    now_ms: int | None = None,
) -> tuple[list[list[float]], list[int], list[float], int]:
    """Pending ≤50% paper; settled uses path/PnL weight, bonus if LLM edge beats paper."""
    from eurika.ml.llm_teacher_settle import SETTLED_MAX_FRAC, settle_teacher

    info = settle_teacher(project_root, now_ms=now_ms)
    bonus = float(info.get("bonus") or 1.0)
    px, py, pw = _teacher_xy(project_root, settled=False)
    sx, sy, sw = _teacher_xy(project_root, settled=True)
    paper_w = sum(ws) or 1.0
    pw = _cap_weights(pw, paper_w * TEACHER_MAX_FRAC)
    sw = [w * bonus for w in sw]
    sw = _cap_weights(sw, paper_w * SETTLED_MAX_FRAC)
    n = len(px) + len(sx)
    if not n:
        return xs, ys, ws, 0
    return xs + px + sx, ys + py + sy, ws + pw + sw, n


def mix_teacher_levels_xy(
    project_root: str | Path,
    xs: list[list[float]],
    ys: list[list[float]],
) -> tuple[list[list[float]], list[list[float]], int]:
    """Optional TP/SL/trail targets from teacher JSON, count-capped."""
    from eurika.ml.llm_teacher_settle import settle_teacher

    settle_teacher(project_root)
    n_feat = len(FEATURE_NAMES)
    lx: list[list[float]] = []
    ly: list[list[float]] = []
    for row in load_teacher_samples(project_root):
        if row.get("skip"):
            continue
        tp = row.get("tp_pct")
        sl = row.get("sl_pct")
        if not isinstance(tp, (int, float)) or not isinstance(sl, (int, float)):
            continue
        vec = row.get("feature_vec")
        if not isinstance(vec, list) or not vec:
            continue
        padded = [float(v) for v in vec[:n_feat]]
        if len(padded) < n_feat:
            padded.extend([0.0] * (n_feat - len(padded)))
        trail = row.get("trail_pct")
        trail_f = float(trail) if isinstance(trail, (int, float)) else max(0.0, float(tp) * 0.5)
        lx.append(padded[:n_feat])
        ly.append([float(tp), float(sl), trail_f])
    if not lx:
        return xs, ys, 0
    cap_n = max(1, int(len(xs) * TEACHER_MAX_FRAC)) if xs else 0
    if cap_n <= 0:
        return xs, ys, 0
    lx, ly = lx[-cap_n:], ly[-cap_n:]
    return xs + lx, ys + ly, len(lx)
