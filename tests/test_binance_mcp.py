"""Binance MCP read-only client: policy guard + offline probe parsing."""
from __future__ import annotations

from pathlib import Path

from eurika.integrations import binance_mcp
from eurika.integrations.binance_mcp import (
    DEFAULT_MCP_URL,
    _parse_mcp_body,
    call_read_only_tool,
    classify_tools,
    format_binance_mcp_text,
    is_read_only_tool,
    mcp_endpoint,
    probe_binance_mcp,
)

_TOOLS = [
    {"name": "get_ticker_price"},
    {"name": "list_klines"},
    {"name": "get_account_balances"},
    {"name": "place_spot_order"},
    {"name": "cancel_order"},
    {"name": "futures_transfer"},
    {"name": "convert_quote"},
]


def test_read_only_classification_blocks_execution() -> None:
    assert is_read_only_tool("get_ticker_price")
    assert is_read_only_tool("list_klines")
    assert not is_read_only_tool("place_spot_order")
    assert not is_read_only_tool("cancel_order")
    assert not is_read_only_tool("futures_transfer")
    assert not is_read_only_tool("withdraw_funds")
    assert not is_read_only_tool("new_margin_order")
    assert not is_read_only_tool("close_futures_position")
    assert not is_read_only_tool("set_leverage")
    assert not is_read_only_tool("spot_trade")
    # Mutating position tools must not pass just because they mention "position".
    assert not is_read_only_tool("reduce_position")
    assert not is_read_only_tool("increase_position")
    assert not is_read_only_tool("position_flip")
    assert not is_read_only_tool("update_margin_type")
    assert not is_read_only_tool("batch_orders")
    classes = classify_tools(_TOOLS)
    assert "get_ticker_price" in classes["read_only"]
    assert {"place_spot_order", "cancel_order", "futures_transfer", "convert_quote"} <= set(
        classes["blocked"]
    )


def test_market_data_named_after_orders_stays_readable() -> None:
    # Nouns must not block observation: order book / open orders are read-only.
    assert is_read_only_tool("get_order_book")
    assert is_read_only_tool("get_open_orders")
    assert is_read_only_tool("query_order_history")
    assert is_read_only_tool("get_my_trades")
    assert is_read_only_tool("get_recent_trades")
    assert is_read_only_tool("get_funding_rate_history")
    assert is_read_only_tool("get_positions")
    assert is_read_only_tool("get_asset_info")
    assert is_read_only_tool("my_trades")
    assert is_read_only_tool("ticker_price")


def test_mcp_env_keys_are_loaded_from_project_dotenv() -> None:
    from eurika.utils.env import _PROJECT_ENV_KEYS

    assert "BINANCE_MCP_URL" in _PROJECT_ENV_KEYS
    assert "BINANCE_MCP_TOKEN" in _PROJECT_ENV_KEYS


def test_call_read_only_tool_refuses_orders_without_network() -> None:
    out = call_read_only_tool("place_spot_order", {"symbol": "BTCUSDT"})
    assert out["ok"] is False
    assert out["policy_blocked"] is True
    assert "not read-only" in str(out["error"])


def test_endpoint_default_and_override(monkeypatch) -> None:
    monkeypatch.delenv("BINANCE_MCP_URL", raising=False)
    assert mcp_endpoint() == DEFAULT_MCP_URL
    monkeypatch.setenv("BINANCE_MCP_URL", "http://127.0.0.1:9/mcp/")
    assert mcp_endpoint() == "http://127.0.0.1:9/mcp"


def test_parse_sse_body_takes_last_data_frame() -> None:
    body = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"binance"}}}\n'
        "\n"
    )
    parsed = _parse_mcp_body(body)
    assert parsed["result"]["serverInfo"]["name"] == "binance"
    assert _parse_mcp_body("not json") == {}


def test_probe_reports_tools_and_policy(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_rpc(method, params=None, *, request_id=1, session_id=None, timeout=15.0):
        calls.append(method)
        if method == "initialize":
            return ({"result": {"serverInfo": {"name": "binance-mcp"}}}, "sess-1", None)
        if method == "tools/list":
            return ({"result": {"tools": _TOOLS}}, session_id, None)
        return ({}, session_id, None)

    monkeypatch.setattr(binance_mcp, "_rpc", _fake_rpc)
    result = probe_binance_mcp()
    assert result["ok"] is True
    assert result["tools_total"] == len(_TOOLS)
    assert "place_spot_order" in result["blocked_tools"]
    assert result["server_name"] == "binance-mcp"
    assert "notifications/initialized" in calls
    text = format_binance_mcp_text(result)
    assert "read-only" in text
    assert "заблокировано политикой" in text


def test_probe_surfaces_auth_requirement(monkeypatch) -> None:
    def _fake_rpc(method, params=None, *, request_id=1, session_id=None, timeout=15.0):
        return ({}, session_id, "HTTP 401: unauthorized")

    monkeypatch.setattr(binance_mcp, "_rpc", _fake_rpc)
    result = probe_binance_mcp()
    assert result["ok"] is False
    assert result["needs_auth"] is True
    text = format_binance_mcp_text(result)
    assert "paper-only" in text or "paper" in text
    assert "BINANCE_MCP_TOKEN" in text


def test_chat_intent_and_cli(tmp_path: Path, monkeypatch) -> None:
    from argparse import Namespace

    from eurika.api.chat_direct import resolve_direct_handler

    (tmp_path / ".eurika").mkdir()
    assert resolve_direct_handler(tmp_path, "binance mcp")[0] == "binance_mcp"
    assert resolve_direct_handler(tmp_path, "бинанс mcp")[0] == "binance_mcp"

    monkeypatch.setattr(
        binance_mcp,
        "probe_binance_mcp",
        lambda **_kw: {"ok": True, "url": DEFAULT_MCP_URL, "tools_total": 0, "policy": "read-only"},
    )
    from cli.core_handlers_ml_market import _cmd_mcp

    code = _cmd_mcp(Namespace(json=True, timeout=1.0), tmp_path)
    assert code == 0
