"""Binance MCP read-only client (no orders).

Binance Agent OS exposes an MCP server over streamable HTTP. Eurika treats it as
an external **tool** (market data / read-only account), never as the decision
maker: order/transfer tools stay blocked here regardless of granted scopes.
Live execution requires lifting the Market freeze and an explicit HITL contour
(VISION § Market paper only).

Secrets (``BINANCE_MCP_TOKEN``) never appear in return values.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Mapping, Optional

DEFAULT_MCP_URL = "https://agent.binance.com/mcp/agentic"
PROTOCOL_VERSION = "2025-06-18"
_DEFAULT_TIMEOUT = 15.0

# Tokens that mark a tool as mutating (money or position moving). Matched on
# name tokens, so ``asset`` never looks like ``set`` and ``my_trades`` never
# looks like ``trade``.
ACTION_TOKENS = frozenset(
    {
        "place",
        "create",
        "new",
        "submit",
        "post",
        "cancel",
        "replace",
        "amend",
        "modify",
        "adjust",
        "change",
        "update",
        "set",
        "enable",
        "disable",
        "close",
        "open",
        "reduce",
        "increase",
        "flip",
        "liquidate",
        "transfer",
        "convert",
        "withdraw",
        "deposit",
        "borrow",
        "repay",
        "redeem",
        "subscribe",
        "leverage",
        "buy",
        "sell",
        "pay",
        "execute",
        "trade",
        "batch",
    }
)

# Names that start with these read the state and change nothing.
READ_PREFIXES = ("get", "list", "query", "read", "fetch", "show", "describe")

# Bare data names without a read prefix are allowed only when every token is
# plain market/account vocabulary — unknown shapes stay blocked.
PURE_DATA_TOKENS = frozenset(
    {
        "market",
        "spot",
        "futures",
        "coin",
        "usd",
        "um",
        "cm",
        "margin",
        "data",
        "ticker",
        "tickers",
        "price",
        "prices",
        "kline",
        "klines",
        "candle",
        "candles",
        "depth",
        "book",
        "orders",
        "fills",
        "funding",
        "rate",
        "rates",
        "fee",
        "fees",
        "symbol",
        "symbols",
        "exchange",
        "info",
        "status",
        "stats",
        "statistics",
        "summary",
        "overview",
        "history",
        "time",
        "ping",
        "server",
        "account",
        "accounts",
        "balance",
        "balances",
        "position",
        "positions",
        "asset",
        "assets",
        "interval",
        "limit",
        "search",
        "24hr",
        "avg",
    }
)

# Read-only names built from action tokens; rewritten to a single data token
# before classification so market data is not blocked by accident.
READ_ONLY_COMPOUNDS = (
    ("order_book", "book"),
    ("orderbook", "book"),
    ("open_orders", "orders"),
    ("order_history", "orders"),
    ("order_status", "orders"),
    ("all_orders", "orders"),
    ("my_trades", "fills"),
    ("trade_history", "fills"),
    ("recent_trades", "fills"),
    ("agg_trades", "fills"),
    ("aggregate_trades", "fills"),
    ("historical_trades", "fills"),
    ("trade_fee", "fee"),
    ("trading_day", "stats"),
)

POLICY_NOTE = (
    "read-only: market data + balances; order/transfer tools blocked "
    "(Market freeze, paper only)"
)


def mcp_endpoint() -> str:
    """MCP URL from ``BINANCE_MCP_URL`` or the published Binance endpoint."""
    override = (os.environ.get("BINANCE_MCP_URL") or "").strip()
    return (override or DEFAULT_MCP_URL).rstrip("/")


def _mcp_token() -> str:
    return (os.environ.get("BINANCE_MCP_TOKEN") or "").strip()


def _tool_tokens(name: str) -> list[str]:
    """Lowercase name tokens with read-only compounds folded into data tokens."""
    low = (name or "").strip().lower()
    for compound, replacement in READ_ONLY_COMPOUNDS:
        low = low.replace(compound, replacement)
    return [tok for tok in re.split(r"[^a-z0-9]+", low) if tok]


def is_read_only_tool(name: str) -> bool:
    """True when the tool name looks like observation, not execution.

    Deny-by-default: any action token blocks the tool, and what remains must
    either start with a read verb or be built purely from data vocabulary.
    ``reduce_position`` and ``position_flip`` stay blocked; ``get_order_book``
    and ``my_trades`` do not.
    """
    tokens = _tool_tokens(name)
    if not tokens:
        return False
    if any(tok in ACTION_TOKENS for tok in tokens):
        return False
    if tokens[0] in READ_PREFIXES:
        return True
    return all(tok in PURE_DATA_TOKENS for tok in tokens)


def classify_tools(tools: list[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Split advertised tool names into read-only vs blocked-by-policy."""
    read_only: list[str] = []
    blocked: list[str] = []
    for tool in tools or []:
        if not isinstance(tool, Mapping):
            continue
        name = str(tool.get("name") or "").strip()
        if not name:
            continue
        (read_only if is_read_only_tool(name) else blocked).append(name)
    return {"read_only": sorted(read_only), "blocked": sorted(blocked)}


def _parse_mcp_body(raw: str) -> dict[str, Any]:
    """Parse JSON or SSE (``text/event-stream``) MCP response body."""
    text = (raw or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    last: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        chunk = line[len("data:"):].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            payload = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            last = payload
    return last


def _rpc(
    method: str,
    params: Optional[dict[str, Any]] = None,
    *,
    request_id: Optional[int] = 1,
    session_id: Optional[str] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[dict[str, Any], Optional[str], Optional[str]]:
    """One JSON-RPC call over streamable HTTP.

    Returns ``(payload, session_id, error)``. Notifications (``request_id=None``)
    return an empty payload.
    """
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "User-Agent": "eurika-binance-mcp-readonly/1",
    }
    token = _mcp_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(
        mcp_endpoint(),
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            new_session = response.headers.get("Mcp-Session-Id") or session_id
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            detail = ""
        return {}, session_id, f"HTTP {exc.code}: {detail}".strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {}, session_id, str(exc)
    payload = _parse_mcp_body(raw)
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, Mapping):
        return payload, new_session, str(err.get("message") or err)
    return payload, new_session, None


def list_mcp_tools(*, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Handshake + ``tools/list``. Returns {ok, tools, needs_auth, error?}."""
    init, session_id, error = _rpc(
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "eurika", "version": "1"},
        },
        request_id=1,
        timeout=timeout,
    )
    if error:
        return {
            "ok": False,
            "tools": [],
            "needs_auth": _looks_like_auth_error(error),
            "error": error,
        }
    server = ((init.get("result") or {}).get("serverInfo") or {}) if isinstance(init, dict) else {}
    _rpc("notifications/initialized", request_id=None, session_id=session_id, timeout=timeout)
    listing, _, error = _rpc(
        "tools/list", {}, request_id=2, session_id=session_id, timeout=timeout
    )
    if error:
        return {
            "ok": False,
            "tools": [],
            "server": server,
            "needs_auth": _looks_like_auth_error(error),
            "error": error,
        }
    result = listing.get("result") if isinstance(listing, dict) else {}
    tools = (result or {}).get("tools") if isinstance(result, Mapping) else []
    return {
        "ok": True,
        "tools": [t for t in (tools or []) if isinstance(t, Mapping)],
        "server": server,
        "needs_auth": False,
        "error": None,
    }


def _looks_like_auth_error(error: str) -> bool:
    low = (error or "").lower()
    return "401" in low or "403" in low or "unauthor" in low or "forbidden" in low


def call_read_only_tool(
    name: str,
    arguments: Optional[dict[str, Any]] = None,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call one MCP tool, refusing anything that can move money or positions."""
    tool = (name or "").strip()
    if not tool:
        return {"ok": False, "tool": tool, "result": None, "policy_blocked": False, "error": "tool name required"}
    if not is_read_only_tool(tool):
        return {
            "ok": False,
            "tool": tool,
            "result": None,
            "policy_blocked": True,
            "error": f"blocked by policy: '{tool}' is not read-only ({POLICY_NOTE})",
        }
    init, session_id, error = _rpc(
        "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "eurika", "version": "1"},
        },
        request_id=1,
        timeout=timeout,
    )
    if error:
        return {"ok": False, "tool": tool, "result": None, "policy_blocked": False, "error": error}
    _rpc("notifications/initialized", request_id=None, session_id=session_id, timeout=timeout)
    payload, _, error = _rpc(
        "tools/call",
        {"name": tool, "arguments": dict(arguments or {})},
        request_id=3,
        session_id=session_id,
        timeout=timeout,
    )
    if error:
        return {"ok": False, "tool": tool, "result": None, "policy_blocked": False, "error": error}
    return {
        "ok": True,
        "tool": tool,
        "result": payload.get("result") if isinstance(payload, dict) else None,
        "policy_blocked": False,
        "error": None,
    }


def probe_binance_mcp(*, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """One-shot read-only probe: reachability + advertised tools by policy class."""
    started = time.perf_counter()
    listing = list_mcp_tools(timeout=timeout)
    latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
    tools = listing.get("tools") or []
    classes = classify_tools(tools)
    server = listing.get("server") if isinstance(listing.get("server"), Mapping) else {}
    return {
        "version": 1,
        "ok": bool(listing.get("ok")),
        "url": mcp_endpoint(),
        "latency_ms": latency_ms,
        "token_present": bool(_mcp_token()),
        "needs_auth": bool(listing.get("needs_auth")),
        "server_name": str((server or {}).get("name") or ""),
        "tools_total": len(tools),
        "read_only_tools": classes["read_only"],
        "blocked_tools": classes["blocked"],
        "policy": POLICY_NOTE,
        "error": listing.get("error"),
    }


def format_binance_mcp_text(result: Mapping[str, Any]) -> str:
    """Chat/CLI summary for the read-only probe."""
    lines = ["**Binance MCP (read-only tool, не мозг Market)**"]
    lines.append(f"endpoint: `{result.get('url') or ''}`")
    lines.append(f"политика: {result.get('policy') or POLICY_NOTE}")
    if not result.get("ok"):
        err = str(result.get("error") or "unreachable")
        lines.append(f"статус: недоступен — {err}")
        if result.get("needs_auth"):
            lines.append(
                "Нужна авторизация: Binance выдаёт agentic sub-account и scopes; "
                "токен — в `BINANCE_MCP_TOKEN`, без права withdraw."
            )
        elif not result.get("token_present"):
            lines.append("Токена нет (`BINANCE_MCP_TOKEN` пуст) — публичный доступ не отвечает.")
        lines.append("Market остаётся paper-only; ордера из Eurika не идут.")
        return "\n".join(lines)
    lines.append(
        f"статус: доступен ({result.get('latency_ms')} ms), инструментов: {result.get('tools_total')}"
    )
    server_name = str(result.get("server_name") or "")
    if server_name:
        lines.append(f"server: `{server_name}`")
    read_only = list(result.get("read_only_tools") or [])
    blocked = list(result.get("blocked_tools") or [])
    if read_only:
        lines.append(f"разрешено читать ({len(read_only)}): " + ", ".join(f"`{t}`" for t in read_only[:12]))
    if blocked:
        lines.append(
            f"заблокировано политикой ({len(blocked)}): " + ", ".join(f"`{t}`" for t in blocked[:12])
        )
    lines.append("Ордера/переводы не вызываются: live-исполнение только после снятия freeze + HITL.")
    lines.append("CLI: `eurika ml-market mcp .`")
    return "\n".join(lines)
