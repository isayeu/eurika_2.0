"""Binance read-only REST helpers (no orders).

Uses HMAC-signed spot API. Secrets never appear in return values or logs.
Enable testnet via BINANCE_TESTNET=1.
USD-M futures (public klines/ticker) via fapi — still no orders.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from eurika.utils.env import binance_credentials_status, env_bool

_MAINNET = "https://api.binance.com"
_TESTNET = "https://testnet.binance.vision"
_FUTURES_MAINNET = "https://fapi.binance.com"
_FUTURES_TESTNET = "https://testnet.binancefuture.com"
_DEFAULT_TIMEOUT = 10.0


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def binance_base_url() -> str:
    """REST base URL from BINANCE_TESTNET / BINANCE_BASE_URL override."""
    override = (os.environ.get("BINANCE_BASE_URL") or "").strip()
    if override:
        return override.rstrip("/")
    return _TESTNET if env_bool("BINANCE_TESTNET", default=False) else _MAINNET


def futures_base_url() -> str:
    """USD-M futures REST base from BINANCE_FUTURES_BASE_URL / BINANCE_TESTNET."""
    override = (os.environ.get("BINANCE_FUTURES_BASE_URL") or "").strip()
    if override:
        return override.rstrip("/")
    return _FUTURES_TESTNET if env_bool("BINANCE_TESTNET", default=False) else _FUTURES_MAINNET


def _api_key() -> str:
    return (os.environ.get("BINANCE_API_KEY") or "").strip()


def _api_secret() -> str:
    return (os.environ.get("BINANCE_API_SECRET") or "").strip()


def _sign(query: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


def _http_get(
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    signed: bool = False,
    timeout: float = _DEFAULT_TIMEOUT,
    base_url: Optional[str] = None,
) -> dict[str, Any] | list[Any]:
    """GET JSON from Binance. Raises RuntimeError on HTTP/API errors (message only)."""
    params = dict(params or {})
    headers = {"Accept": "application/json", "User-Agent": "eurika-binance-readonly/1"}
    if signed:
        key = _api_key()
        secret = _api_secret()
        if not key or not secret:
            raise RuntimeError("BINANCE_API_KEY / BINANCE_API_SECRET not set")
        params.setdefault("timestamp", int(time.time() * 1000))
        params.setdefault("recvWindow", 5000)
        query = urllib.parse.urlencode(params, doseq=True)
        query = f"{query}&signature={_sign(query, secret)}"
        headers["X-MBX-APIKEY"] = key
    else:
        query = urllib.parse.urlencode(params, doseq=True) if params else ""
    root = (base_url or binance_base_url()).rstrip("/")
    url = f"{root}{path}"
    if query:
        url = f"{url}?{query}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {body or exc.reason}") from None
    except Exception as exc:
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON: {exc}") from None
    if isinstance(data, dict) and "code" in data and "msg" in data and data.get("code") not in (0, "0", None):
        # Binance error payload
        raise RuntimeError(f"API {data.get('code')}: {data.get('msg')}")
    return data


def _parse_kline_rows(data: list[Any]) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, (list, tuple)) or len(row) < 7:
            continue
        candles.append(
            {
                "open_time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "close_time": int(row[6]),
            }
        )
    return candles


def ping(*, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Public ping. Returns {ok, latency_ms, base_url, error?}."""
    base = binance_base_url()
    t0 = time.perf_counter()
    try:
        _http_get("/api/v3/ping", timeout=timeout)
        ms = (time.perf_counter() - t0) * 1000.0
        return {"ok": True, "latency_ms": round(ms, 1), "base_url": base, "error": None}
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        return {"ok": False, "latency_ms": round(ms, 1), "base_url": base, "error": str(exc)}


def ticker_price(symbol: str = "BTCUSDT", *, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Public ticker price. Returns {ok, symbol, price, error?}."""
    sym = (symbol or "BTCUSDT").strip().upper()
    try:
        data = _http_get("/api/v3/ticker/price", params={"symbol": sym}, timeout=timeout)
        if not isinstance(data, dict):
            raise RuntimeError("unexpected ticker payload")
        return {
            "ok": True,
            "symbol": str(data.get("symbol") or sym),
            "price": str(data.get("price") or ""),
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "symbol": sym, "price": None, "error": str(exc)}


def account_balances(
    *,
    min_free: float = 0.0,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Signed account balances (non-zero free+locked by default).

    Returns {ok, balances: [{asset, free, locked}], count, error?} — no API secrets.
    """
    creds = binance_credentials_status()
    if not creds.get("ready"):
        return {"ok": False, "balances": [], "count": 0, "error": "credentials not ready"}
    try:
        data = _http_get("/api/v3/account", signed=True, timeout=timeout)
        if not isinstance(data, dict):
            raise RuntimeError("unexpected account payload")
        out: list[dict[str, str]] = []
        for row in data.get("balances") or []:
            if not isinstance(row, dict):
                continue
            asset = str(row.get("asset") or "")
            free_s = str(row.get("free") or "0")
            locked_s = str(row.get("locked") or "0")
            try:
                free_f = float(free_s)
                locked_f = float(locked_s)
            except ValueError:
                continue
            if free_f + locked_f <= min_free:
                continue
            out.append({"asset": asset, "free": free_s, "locked": locked_s})
        out.sort(key=lambda r: r["asset"])
        return {"ok": True, "balances": out, "count": len(out), "error": None}
    except Exception as exc:
        return {"ok": False, "balances": [], "count": 0, "error": str(exc)}


def klines(
    symbol: str = "BTCUSDT",
    *,
    interval: str = "1h",
    limit: int = 500,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Public spot klines. Returns {ok, symbol, interval, candles[…], error?}."""
    return _klines_request(
        "/api/v3/klines",
        symbol,
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        timeout=timeout,
        base_url=binance_base_url(),
        market="spot",
    )


def futures_ticker_price(symbol: str = "BTCUSDT", *, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Public USD-M futures ticker. Returns {ok, symbol, price, error?}."""
    sym = (symbol or "BTCUSDT").strip().upper()
    try:
        data = _http_get(
            "/fapi/v1/ticker/price",
            params={"symbol": sym},
            timeout=timeout,
            base_url=futures_base_url(),
        )
        if not isinstance(data, dict):
            raise RuntimeError("unexpected futures ticker payload")
        return {
            "ok": True,
            "symbol": str(data.get("symbol") or sym),
            "price": str(data.get("price") or ""),
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "symbol": sym, "price": None, "error": str(exc)}


def futures_klines(
    symbol: str = "BTCUSDT",
    *,
    interval: str = "1h",
    limit: int = 500,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Public USD-M futures klines (same candle shape as spot)."""
    return _klines_request(
        "/fapi/v1/klines",
        symbol,
        interval=interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        timeout=timeout,
        base_url=futures_base_url(),
        market="futures",
    )


def futures_premium_index(
    symbol: str = "BTCUSDT",
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Public mark price + last funding rate (``/fapi/v1/premiumIndex``).

    Returns {ok, symbol, mark_price, last_funding_rate, next_funding_time, error?}.
    No API key required.
    """
    sym = (symbol or "BTCUSDT").strip().upper()
    try:
        data = _http_get(
            "/fapi/v1/premiumIndex",
            params={"symbol": sym},
            timeout=timeout,
            base_url=futures_base_url(),
        )
        if not isinstance(data, dict):
            raise RuntimeError("unexpected premiumIndex payload")
        rate = _coerce_float(data.get("lastFundingRate"))
        next_ms = _coerce_int(data.get("nextFundingTime"))
        mark = data.get("markPrice")
        return {
            "ok": True,
            "symbol": str(data.get("symbol") or sym),
            "mark_price": str(mark) if mark is not None else None,
            "last_funding_rate": rate,
            "next_funding_time": next_ms,
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "symbol": sym,
            "mark_price": None,
            "last_funding_rate": None,
            "next_funding_time": None,
            "error": str(exc),
        }


def futures_funding_rate_history(
    symbol: str = "BTCUSDT",
    *,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 100,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Public funding settlement history (``/fapi/v1/fundingRate``).

    Returns {ok, symbol, rows:[{funding_rate, funding_time, …}], error?}.
    """
    sym = (symbol or "BTCUSDT").strip().upper()
    lim = max(1, min(int(limit), 1000))
    params: dict[str, Any] = {"symbol": sym, "limit": lim}
    if start_time is not None:
        params["startTime"] = int(start_time)
    if end_time is not None:
        params["endTime"] = int(end_time)
    try:
        data = _http_get(
            "/fapi/v1/fundingRate",
            params=params,
            timeout=timeout,
            base_url=futures_base_url(),
        )
        if not isinstance(data, list):
            raise RuntimeError("unexpected fundingRate payload")
        rows: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            rate = _coerce_float(item.get("fundingRate"))
            ts = _coerce_int(item.get("fundingTime"))
            if rate is None or ts is None:
                continue
            rows.append(
                {
                    "symbol": str(item.get("symbol") or sym),
                    "funding_rate": rate,
                    "funding_time": ts,
                }
            )
        return {"ok": True, "symbol": sym, "rows": rows, "count": len(rows), "error": None}
    except Exception as exc:
        return {"ok": False, "symbol": sym, "rows": [], "count": 0, "error": str(exc)}


def _klines_request(
    path: str,
    symbol: str,
    *,
    interval: str,
    limit: int,
    start_time: Optional[int],
    end_time: Optional[int],
    timeout: float,
    base_url: str,
    market: str,
) -> dict[str, Any]:
    sym = (symbol or "BTCUSDT").strip().upper()
    iv = (interval or "1h").strip()
    lim = max(1, min(int(limit), 1000))
    params: dict[str, Any] = {"symbol": sym, "interval": iv, "limit": lim}
    if start_time is not None:
        params["startTime"] = int(start_time)
    if end_time is not None:
        params["endTime"] = int(end_time)
    try:
        data = _http_get(path, params=params, timeout=timeout, base_url=base_url)
        if not isinstance(data, list):
            raise RuntimeError(f"unexpected {market} klines payload")
        candles = _parse_kline_rows(data)
        return {
            "ok": True,
            "symbol": sym,
            "interval": iv,
            "market": market,
            "candles": candles,
            "count": len(candles),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "symbol": sym,
            "interval": iv,
            "market": market,
            "candles": [],
            "count": 0,
            "error": str(exc),
        }


def probe_readonly(
    *,
    symbol: str = "BTCUSDT",
    include_balances: bool = True,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """One-shot read-only health: ping + ticker + optional balances."""
    result: dict[str, Any] = {
        "credentials": binance_credentials_status(),
        "ping": ping(timeout=timeout),
        "ticker": ticker_price(symbol, timeout=timeout),
        "balances": None,
    }
    if include_balances and result["credentials"].get("ready"):
        result["balances"] = account_balances(timeout=timeout)
    return result
