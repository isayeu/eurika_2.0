"""Spot-balance → trade universe (read-only; no orders).

Prefers ``*USDT``, then other quotes (FDUSD/USDC/BTC/BNB/ETH) when probing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from eurika.ml.market_store import DEFAULT_SYMBOL, ml_root

# Cash / fiat — never used as base for paper pairs.
_STABLE_ASSETS = frozenset(
    {
        "USDT",
        "USDC",
        "BUSD",
        "FDUSD",
        "TUSD",
        "DAI",
        "USD",
        "EUR",
        "TRY",
        "BRL",
        "AEUR",
    }
)

# Quote preference for bridges (first match wins when probing).
QUOTE_PRIORITY: tuple[str, ...] = ("USDT", "FDUSD", "USDC", "BTC", "BNB", "ETH")

DEFAULT_MAX_SYMBOLS = 8
_CACHE_TTL_SEC = 7 * 24 * 3600


def pair_cache_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "pair_cache.json"


def ticker_lists_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "ticker_lists.json"


def normalize_symbol_list(
    symbols: Sequence[str] | None,
    *,
    max_symbols: int = 32,
    fallback: str | None = None,
) -> list[str]:
    """Uppercase unique symbols; optional fallback if empty."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols or ():
        u = str(raw or "").strip().upper()
        if not u or not u.isalnum():
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= max(1, int(max_symbols)):
            break
    if not out and fallback:
        fb = str(fallback).strip().upper()
        if fb:
            out = [fb]
    return out


def load_ticker_lists(project_root: str | Path | None) -> dict[str, list[str]]:
    """Load ``{spot: [...], futures: [...]}`` from `.eurika/ml/ticker_lists.json`."""
    empty: dict[str, list[str]] = {"spot": [], "futures": []}
    if project_root is None:
        return empty
    path = ticker_lists_path(project_root)
    if not path.is_file():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict):
        return empty
    return {
        "spot": normalize_symbol_list(data.get("spot") or []),
        "futures": normalize_symbol_list(data.get("futures") or []),
    }


def save_ticker_lists(
    project_root: str | Path,
    *,
    spot: Sequence[str] | None = None,
    futures: Sequence[str] | None = None,
) -> Path:
    """Persist independent spot / futures ticker lists."""
    path = ticker_lists_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_ticker_lists(project_root)
    payload = {
        "spot": normalize_symbol_list(spot if spot is not None else existing["spot"]),
        "futures": normalize_symbol_list(futures if futures is not None else existing["futures"]),
        "ts": time.time(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def universe_snapshot_path(project_root: str | Path) -> Path:
    return ml_root(project_root) / "universe_snapshot.json"


def save_universe_snapshot(
    project_root: str | Path,
    symbols: Sequence[str],
    *,
    bridges: Optional[dict[str, str]] = None,
) -> Path:
    """Persist last good universe so DNS/API blips do not collapse to one fallback."""
    path = universe_snapshot_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbols": [str(s).strip().upper() for s in symbols if str(s).strip()],
        "bridges": bridges or {},
        "ts": time.time(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_universe_snapshot(project_root: str | Path) -> list[str]:
    path = universe_snapshot_path(project_root)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for s in data.get("symbols") or []:
        u = str(s or "").strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def recover_universe_symbols(
    project_root: str | Path | None,
    *,
    fallback: str = DEFAULT_SYMBOL,
    max_symbols: int = DEFAULT_MAX_SYMBOLS,
) -> dict[str, Any]:
    """Best-effort symbols when balances API is down.

    Priority: last snapshot → open paper symbols → candle series on disk → single fallback.
    """
    fb = (fallback or DEFAULT_SYMBOL).strip().upper() or DEFAULT_SYMBOL
    lim = max(1, int(max_symbols))
    if project_root is None:
        return {
            "symbols": [fb],
            "source": "fallback",
            "fallback_used": True,
        }

    snap = load_universe_snapshot(project_root)
    if snap:
        return {
            "symbols": snap[:lim],
            "source": "snapshot",
            "fallback_used": False,
        }

    opens: list[dict[str, Any]] = []
    try:
        op_path = ml_root(project_root) / "open_paper.json"
        if op_path.is_file():
            raw_op = json.loads(op_path.read_text(encoding="utf-8"))
            if isinstance(raw_op, dict):
                rows = raw_op.get("positions") or []
            elif isinstance(raw_op, list):
                rows = raw_op
            else:
                rows = []
            opens = [r for r in rows if isinstance(r, dict)]
    except (OSError, json.JSONDecodeError, TypeError):
        opens = []
    open_syms: list[str] = []
    seen: set[str] = set()
    for p in opens:
        u = str(p.get("symbol") or "").strip().upper()
        if u and u not in seen:
            seen.add(u)
            open_syms.append(u)
    if open_syms:
        open_syms.sort()
        return {
            "symbols": open_syms[:lim],
            "source": "open_positions",
            "fallback_used": False,
        }

    try:
        from eurika.ml.market_store import market_status

        series = (market_status(project_root) or {}).get("series") or []
    except Exception:
        series = []
    disk: list[str] = []
    seen = set()
    for row in series:
        if not isinstance(row, dict):
            continue
        u = str(row.get("symbol") or "").strip().upper()
        if u and u not in seen:
            seen.add(u)
            disk.append(u)
    if disk:
        disk.sort()
        return {
            "symbols": disk[:lim],
            "source": "market_store",
            "fallback_used": False,
        }

    return {
        "symbols": [fb],
        "source": "fallback",
        "fallback_used": True,
    }


def _load_pair_cache(project_root: str | Path | None) -> dict[str, Any]:
    if project_root is None:
        return {}
    path = pair_cache_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_pair_cache(project_root: str | Path | None, cache: dict[str, Any]) -> None:
    if project_root is None:
        return
    path = pair_cache_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_base_asset(asset: str) -> Optional[str]:
    """Return tradeable base asset or None (stables / Earn dust / junk)."""
    a = (asset or "").strip().upper()
    if not a or not a.isalnum():
        return None
    if a in _STABLE_ASSETS:
        return None
    if a.startswith("LD") and len(a) > 2:
        return None
    return a


def candidate_symbols(asset: str) -> list[str]:
    """Ordered pair candidates: ASSET+quote by ``QUOTE_PRIORITY``."""
    base = normalize_base_asset(asset)
    if not base:
        return []
    out: list[str] = []
    for quote in QUOTE_PRIORITY:
        if base == quote:
            continue
        out.append(f"{base}{quote}")
    return out


def asset_to_usdt_symbol(asset: str) -> Optional[str]:
    """Map a spot asset to preferred ``ASSETUSDT`` (compat helper)."""
    cands = candidate_symbols(asset)
    for sym in cands:
        if sym.endswith("USDT"):
            return sym
    return cands[0] if cands else None


def _cache_get(cache: dict[str, Any], asset: str) -> Optional[str]:
    row = cache.get(asset)
    if not isinstance(row, dict):
        return None
    ts = float(row.get("ts") or 0)
    if ts and (time.time() - ts) > _CACHE_TTL_SEC:
        return None
    sym = str(row.get("symbol") or "").strip().upper()
    return sym or None


def _cache_put(cache: dict[str, Any], asset: str, symbol: str) -> None:
    cache[asset] = {"symbol": symbol, "ts": time.time()}


def resolve_pair_for_asset(
    asset: str,
    *,
    probe: Optional[Callable[[str], bool]] = None,
    cache: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Pick best pair for asset.

    Without ``probe``: first candidate (USDT preference).
    With ``probe``: first candidate where probe(symbol) is True; uses cache when set.
    """
    base = normalize_base_asset(asset)
    if not base:
        return None
    cands = candidate_symbols(base)
    if not cands:
        return None
    if cache is not None:
        hit = _cache_get(cache, base)
        if hit and hit in cands:
            if probe is None or probe(hit):
                return hit
    if probe is None:
        chosen = cands[0]
        if cache is not None:
            _cache_put(cache, base, chosen)
        return chosen
    for sym in cands:
        try:
            ok = bool(probe(sym))
        except Exception:
            ok = False
        if ok:
            if cache is not None:
                _cache_put(cache, base, sym)
            return sym
    return None


def default_ticker_probe(symbol: str) -> bool:
    """Public ticker exists and has a price (no secrets)."""
    from eurika.integrations.binance_readonly import ticker_price

    st = ticker_price(symbol)
    if not st.get("ok"):
        return False
    price = st.get("price")
    if price is None or str(price).strip() == "":
        return False
    try:
        return float(price) > 0
    except (TypeError, ValueError):
        return False


def default_futures_ticker_probe(symbol: str) -> bool:
    """Public USD-M futures ticker exists and has a price."""
    from eurika.integrations.binance_readonly import futures_ticker_price

    st = futures_ticker_price(symbol)
    if not st.get("ok"):
        return False
    price = st.get("price")
    if price is None or str(price).strip() == "":
        return False
    try:
        return float(price) > 0
    except (TypeError, ValueError):
        return False


def to_usdt_perp_symbol(symbol: str) -> Optional[str]:
    """Map a spot pair (any quote) to ``BASEUSDT`` for USD-M perps."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    if sym.endswith("USDT") and len(sym) > 4:
        base = sym[:-4]
        return f"{base}USDT" if normalize_base_asset(base) else None
    for quote in QUOTE_PRIORITY:
        if sym.endswith(quote) and len(sym) > len(quote):
            base = sym[: -len(quote)]
            if normalize_base_asset(base):
                return f"{base}USDT"
    # Bare asset name
    if normalize_base_asset(sym):
        return f"{sym}USDT"
    return None


def symbols_for_futures(
    spot_symbols: Sequence[str],
    *,
    max_symbols: int = DEFAULT_MAX_SYMBOLS,
    fallback: str = DEFAULT_SYMBOL,
    probe: Optional[Callable[[str], bool]] = None,
    project_root: str | Path | None = None,
    use_probe: bool = True,
) -> dict[str, Any]:
    """Filter/map spot universe → USD-M USDT-M symbols that exist on futures."""
    active_probe = probe
    if use_probe and active_probe is None:
        active_probe = default_futures_ticker_probe
    if not use_probe:
        active_probe = None

    cache = _load_pair_cache(project_root) if project_root is not None else None
    found: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for raw in spot_symbols:
        fut = to_usdt_perp_symbol(str(raw or ""))
        if not fut:
            if raw:
                skipped.append(str(raw).strip().upper())
            continue
        base = fut[:-4] if fut.endswith("USDT") else fut
        cache_key = f"fut:{base}"
        if cache is not None:
            hit = _cache_get(cache, cache_key)
            if hit == fut:
                if active_probe is None or active_probe(fut):
                    if fut not in seen:
                        seen.add(fut)
                        found.append(fut)
                    continue
        ok = True
        if active_probe is not None:
            try:
                ok = bool(active_probe(fut))
            except Exception:
                ok = False
        if not ok:
            skipped.append(fut)
            continue
        if cache is not None:
            _cache_put(cache, cache_key, fut)
        if fut not in seen:
            seen.add(fut)
            found.append(fut)

    if project_root is not None and cache is not None:
        _save_pair_cache(project_root, cache)

    lim = max(1, int(max_symbols))
    capped = found[:lim]
    fb = (fallback or DEFAULT_SYMBOL).strip().upper() or DEFAULT_SYMBOL
    # Prefer USDT form of fallback
    fb_fut = to_usdt_perp_symbol(fb) or fb
    if not capped:
        capped = [fb_fut]
        return {
            "ok": True,
            "symbols": capped,
            "skipped": sorted(set(skipped)),
            "fallback_used": True,
            "count": 1,
        }
    return {
        "ok": True,
        "symbols": capped,
        "skipped": sorted(set(skipped)),
        "fallback_used": False,
        "count": len(capped),
    }


def symbols_from_balance_rows(
    balances: Sequence[dict[str, Any]],
    *,
    max_symbols: int = DEFAULT_MAX_SYMBOLS,
    fallback: str = DEFAULT_SYMBOL,
    always_include: Sequence[str] | None = None,
    probe: Optional[Callable[[str], bool]] = None,
    cache: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build sorted unique pairs from balance rows."""
    skipped: list[str] = []
    found: list[str] = []
    bridges: dict[str, str] = {}
    seen: set[str] = set()
    for row in balances:
        if not isinstance(row, dict):
            continue
        asset = str(row.get("asset") or "")
        base = normalize_base_asset(asset)
        if not base:
            if asset:
                skipped.append(asset.upper())
            continue
        sym = resolve_pair_for_asset(base, probe=probe, cache=cache)
        if sym is None:
            skipped.append(base)
            continue
        quote = sym[len(base) :] if sym.startswith(base) else ""
        bridges[base] = quote or "?"
        if sym not in seen:
            seen.add(sym)
            found.append(sym)
    for extra in always_include or ():
        s = str(extra or "").strip().upper()
        if s and s not in seen:
            seen.add(s)
            found.append(s)
    found.sort()
    capped = found[: max(1, int(max_symbols))]
    fb = (fallback or DEFAULT_SYMBOL).strip().upper() or DEFAULT_SYMBOL
    if not capped:
        capped = [fb]
        return {
            "ok": True,
            "symbols": capped,
            "skipped": sorted(set(skipped)),
            "bridges": bridges,
            "fallback_used": True,
            "count": 1,
        }
    return {
        "ok": True,
        "symbols": capped,
        "skipped": sorted(set(skipped)),
        "bridges": bridges,
        "fallback_used": False,
        "count": len(capped),
    }


def symbols_from_balances(
    *,
    min_free: float = 0.0,
    max_symbols: int = DEFAULT_MAX_SYMBOLS,
    fallback: str = DEFAULT_SYMBOL,
    always_include: Sequence[str] | None = None,
    fetch_balances: Optional[Callable[..., dict[str, Any]]] = None,
    project_root: str | Path | None = None,
    probe: Optional[Callable[[str], bool]] = None,
    use_probe: bool = True,
) -> dict[str, Any]:
    """Read Binance spot balances → paper universe (multi-quote).

    Returns ``{ok, symbols, balances, skipped, bridges, fallback_used, count, error?}``.
    Never includes API secrets.
    """
    fetch = fetch_balances
    if fetch is None:
        from eurika.integrations.binance_readonly import account_balances

        fetch = account_balances
    try:
        raw = fetch(min_free=min_free)
    except Exception as exc:
        recovered = recover_universe_symbols(
            project_root, fallback=fallback, max_symbols=max_symbols
        )
        return {
            "ok": False,
            "symbols": recovered["symbols"],
            "balances": [],
            "skipped": [],
            "bridges": {},
            "fallback_used": recovered["fallback_used"],
            "stale": True,
            "source": recovered["source"],
            "count": len(recovered["symbols"]),
            "error": f"{type(exc).__name__}: {exc}",
        }
    if not raw.get("ok"):
        recovered = recover_universe_symbols(
            project_root, fallback=fallback, max_symbols=max_symbols
        )
        return {
            "ok": False,
            "symbols": recovered["symbols"],
            "balances": [],
            "skipped": [],
            "bridges": {},
            "fallback_used": recovered["fallback_used"],
            "stale": True,
            "source": recovered["source"],
            "count": len(recovered["symbols"]),
            "error": str(raw.get("error") or "balances failed"),
        }
    balances = [b for b in (raw.get("balances") or []) if isinstance(b, dict)]
    cache = _load_pair_cache(project_root) if project_root is not None else None
    active_probe = probe
    if use_probe and active_probe is None:
        active_probe = default_ticker_probe
    if not use_probe:
        active_probe = None
    built = symbols_from_balance_rows(
        balances,
        max_symbols=max_symbols,
        fallback=fallback,
        always_include=always_include,
        probe=active_probe,
        cache=cache,
    )
    if project_root is not None and cache is not None:
        _save_pair_cache(project_root, cache)
    # If probing wiped everything (e.g. DNS blip on tickers), recover instead of 1 fallback.
    symbols = list(built["symbols"] or [])
    source = "balances"
    stale = False
    err: str | None = None
    if built.get("fallback_used") and project_root is not None:
        recovered = recover_universe_symbols(
            project_root, fallback=fallback, max_symbols=max_symbols
        )
        if recovered["source"] != "fallback":
            symbols = list(recovered["symbols"])
            source = recovered["source"]
            stale = True
            err = "балансы ок, но пары не собрались — взят кэш/открытые"
    if project_root is not None and symbols and source == "balances" and not built.get("fallback_used"):
        save_universe_snapshot(project_root, symbols, bridges=built.get("bridges") or {})
    return {
        "ok": not stale,
        "symbols": symbols,
        "balances": [{"asset": b.get("asset"), "free": b.get("free"), "locked": b.get("locked")} for b in balances],
        "skipped": built["skipped"],
        "bridges": built.get("bridges") or {},
        "fallback_used": bool(built.get("fallback_used")) and source == "balances",
        "stale": stale,
        "source": source,
        "count": len(symbols),
        "error": err,
    }
