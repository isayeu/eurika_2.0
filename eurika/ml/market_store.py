"""Persist Binance klines under ``{project}/.eurika/ml/market/`` (no secrets).

Spot and USD-M futures are stored separately:
``market/spot/{SYM}_{iv}.json`` and ``market/futures/{SYM}_{iv}.json``.
Legacy flat ``market/{SYM}_{iv}.json`` is read as spot when the new path is missing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal, Optional

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "1h"
MarketKind = Literal["spot", "futures"]
DEFAULT_MARKET: MarketKind = "spot"


def normalize_market(market: str | None) -> MarketKind:
    m = (market or DEFAULT_MARKET).strip().lower()
    if m in ("futures", "fut", "um", "perp", "perpetual"):
        return "futures"
    return "spot"


def parse_markets(mode: str | None) -> tuple[MarketKind, ...]:
    """Map UI/CLI mode spot|futures|both → ordered market kinds."""
    m = (mode or "spot").strip().lower()
    if m in ("both", "all", "spot+futures"):
        return ("spot", "futures")
    if m in ("futures", "fut", "um", "perp"):
        return ("futures",)
    return ("spot",)


def ml_root(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".eurika" / "ml"


def market_dir(project_root: str | Path, market: str | None = None) -> Path:
    """Root market dir, or ``market/spot`` / ``market/futures`` when kind given."""
    root = ml_root(project_root) / "market"
    if market is None:
        return root
    return root / normalize_market(market)


def legacy_candles_path(project_root: str | Path, symbol: str, interval: str) -> Path:
    sym = (symbol or DEFAULT_SYMBOL).strip().upper()
    iv = (interval or DEFAULT_INTERVAL).strip()
    safe_iv = iv.replace("/", "_")
    return market_dir(project_root) / f"{sym}_{safe_iv}.json"


def candles_path(
    project_root: str | Path,
    symbol: str,
    interval: str,
    *,
    market: str | None = DEFAULT_MARKET,
) -> Path:
    sym = (symbol or DEFAULT_SYMBOL).strip().upper()
    iv = (interval or DEFAULT_INTERVAL).strip()
    safe_iv = iv.replace("/", "_")
    kind = normalize_market(market)
    return market_dir(project_root, kind) / f"{sym}_{safe_iv}.json"


def read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    """Objects from a newline-delimited JSON log, skipping unreadable lines.

    Streams the file: the sample logs grow into tens of megabytes and are
    re-read on every micro-training, so slurping them whole would hold the raw
    text and the split line list in memory alongside the parsed rows.
    """
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return rows
    return rows


def _read_candle_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("candles") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out = [r for r in rows if isinstance(r, dict) and "open_time" in r]
    out.sort(key=lambda r: int(r["open_time"]))
    return out


def load_candles(
    project_root: str | Path,
    symbol: str = DEFAULT_SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    *,
    market: str | None = DEFAULT_MARKET,
) -> list[dict[str, Any]]:
    kind = normalize_market(market)
    path = candles_path(project_root, symbol, interval, market=kind)
    rows = _read_candle_file(path)
    if rows:
        return rows
    # Legacy flat path only for spot (pre-futures layout).
    if kind == "spot":
        return _read_candle_file(legacy_candles_path(project_root, symbol, interval))
    return []


def save_candles(
    project_root: str | Path,
    candles: list[dict[str, Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    market: str | None = DEFAULT_MARKET,
) -> Path:
    kind = normalize_market(market)
    path = candles_path(project_root, symbol, interval, market=kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = sorted(
        [c for c in candles if isinstance(c, dict) and "open_time" in c],
        key=lambda r: int(r["open_time"]),
    )
    # Dedup by open_time (last wins)
    by_t: dict[int, dict[str, Any]] = {}
    for row in cleaned:
        by_t[int(row["open_time"])] = row
    merged = [by_t[k] for k in sorted(by_t)]
    payload = {
        "symbol": (symbol or DEFAULT_SYMBOL).strip().upper(),
        "interval": (interval or DEFAULT_INTERVAL).strip(),
        "market": kind,
        "count": len(merged),
        "candles": merged,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def merge_candles(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_t: dict[int, dict[str, Any]] = {}
    for row in existing + incoming:
        if not isinstance(row, dict) or "open_time" not in row:
            continue
        by_t[int(row["open_time"])] = row
    return [by_t[k] for k in sorted(by_t)]


def sync_klines(
    project_root: str | Path,
    *,
    symbol: str = DEFAULT_SYMBOL,
    interval: str = DEFAULT_INTERVAL,
    limit: int = 500,
    market: str | None = DEFAULT_MARKET,
    fetch: Optional[Callable[..., dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Fetch klines and merge onto disk. ``fetch`` injectable for tests."""
    kind = normalize_market(market)
    if fetch is None:
        if kind == "futures":
            from eurika.integrations.binance_readonly import futures_klines as fetch_klines
        else:
            from eurika.integrations.binance_readonly import klines as fetch_klines

        fetch = fetch_klines
    existing = load_candles(project_root, symbol, interval, market=kind)
    start_time: Optional[int] = None
    if existing:
        # Refetch the latest candle: Binance returns the current in-progress
        # kline, whose OHLCV keeps changing until close. Starting after it
        # would freeze the first partial snapshot permanently.
        start_time = int(existing[-1]["open_time"])
    result = fetch(symbol, interval=interval, limit=limit, start_time=start_time)
    if not result.get("ok"):
        # First sync / gap: retry without startTime for a full window
        if start_time is not None:
            result = fetch(symbol, interval=interval, limit=limit)
        if not result.get("ok"):
            return {
                "ok": False,
                "symbol": symbol,
                "interval": interval,
                "market": kind,
                "added": 0,
                "total": len(existing),
                "path": str(candles_path(project_root, symbol, interval, market=kind)),
                "error": result.get("error") or "klines failed",
            }
    incoming = list(result.get("candles") or [])
    merged = merge_candles(existing, incoming)
    path = save_candles(project_root, merged, symbol=symbol, interval=interval, market=kind)
    return {
        "ok": True,
        "symbol": (symbol or DEFAULT_SYMBOL).strip().upper(),
        "interval": (interval or DEFAULT_INTERVAL).strip(),
        "market": kind,
        "added": max(0, len(merged) - len(existing)),
        "total": len(merged),
        "path": str(path),
        "error": None,
    }


def _series_entry(path: Path, *, market: str | None = None) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        kind = market or data.get("market") or ("futures" if "futures" in path.parts else "spot")
        return {
            "file": path.name,
            "path": str(path),
            "symbol": data.get("symbol"),
            "interval": data.get("interval"),
            "market": kind,
            "count": int(data.get("count") or len(data.get("candles") or [])),
        }
    except Exception:
        return {"file": path.name, "path": str(path), "error": "unreadable", "market": market}


def market_status(project_root: str | Path) -> dict[str, Any]:
    root = market_dir(project_root)
    files: list[dict[str, Any]] = []
    seen_spot: set[str] = set()
    if root.is_dir():
        for kind in ("spot", "futures"):
            sub = root / kind
            if sub.is_dir():
                for path in sorted(sub.glob("*.json")):
                    entry = _series_entry(path, market=kind)
                    files.append(entry)
                    if kind == "spot":
                        seen_spot.add(path.name)
        # Legacy flat files only if no spot/<same> exists (avoid double-count after migrate).
        for path in sorted(root.glob("*.json")):
            if path.name in seen_spot:
                continue
            files.append(_series_entry(path, market="spot"))
    return {"market_dir": str(root), "series": files}
